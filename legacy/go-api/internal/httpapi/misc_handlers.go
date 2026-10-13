package httpapi

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/gathered/kitframe/apps/api/internal/apperr"
	"github.com/gathered/kitframe/apps/api/internal/auth"
	"github.com/gathered/kitframe/apps/api/internal/db"
	"github.com/gathered/kitframe/apps/api/internal/permissions"
	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

func (s *Server) handleCreateAvatar(w http.ResponseWriter, r *http.Request) {
	var body struct {
		BrandID            string   `json:"brand_id"`
		Name               string   `json:"name"`
		ReferenceAssetURLs []string `json:"reference_asset_urls"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), body.BrandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	var id string
	err = s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO avatars (brand_id, name, reference_asset_urls, status)
		VALUES ($1,$2,$3,'training') RETURNING id::text`, body.BrandID, body.Name, db.MustJSON(body.ReferenceAssetURLs)).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	_ = s.jobs.EnqueueTrainAvatar(r.Context(), id)
	writeJSON(w, http.StatusAccepted, map[string]any{"id": id, "status": "training"})
}

func (s *Server) handleListAvatars(w http.ResponseWriter, r *http.Request) {
	brandID := r.URL.Query().Get("brand_id")
	p := paginationFrom(r)
	var total int
	_ = s.db.Pool.QueryRow(r.Context(), `
		SELECT COUNT(*) FROM avatars WHERE ($1 = '' OR brand_id::text = $1)`, brandID).Scan(&total)
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, brand_id::text, name, reference_asset_urls, identity_profile_ref, status, created_at
		FROM avatars
		WHERE ($1 = '' OR brand_id::text = $1)
		ORDER BY created_at DESC
		LIMIT $2 OFFSET $3`, brandID, p.PageSize, p.Offset())
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		var id, bid, name, status string
		var refs []byte
		var identity *string
		var created time.Time
		if err := rows.Scan(&id, &bid, &name, &refs, &identity, &status, &created); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{
			"id": id, "brand_id": bid, "name": name, "reference_asset_urls": json.RawMessage(refs),
			"identity_profile_ref": identity, "status": status, "created_at": created,
		})
	}
	writePage(w, data, total, p.Page)
}

func (s *Server) handleGetAvatar(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	row := s.db.Pool.QueryRow(r.Context(), `
		SELECT id::text, brand_id::text, name, reference_asset_urls, identity_profile_ref, status, created_at
		FROM avatars WHERE id = $1`, id)
	var aid, bid, name, status string
	var refs []byte
	var identity *string
	var created time.Time
	if err := row.Scan(&aid, &bid, &name, &refs, &identity, &status, &created); err != nil {
		writeError(w, apperr.NotFound("avatar not found"))
		return
	}
	genRows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, product_id::text, avatar_id::text, pose_reference_id::text, provider,
			rights_record_id::text, scene_description, status, result_asset_id::text, requested_by::text, created_at, completed_at
		FROM generation_requests WHERE avatar_id = $1
		ORDER BY created_at DESC LIMIT 50`, id)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer genRows.Close()
	history := make([]map[string]any, 0)
	for genRows.Next() {
		var gid, productID, provider, gStatus, requestedBy string
		var avatarID, poseID, rightsID, scene, resultID *string
		var gCreated time.Time
		var completed *time.Time
		if err := genRows.Scan(&gid, &productID, &avatarID, &poseID, &provider, &rightsID, &scene, &gStatus, &resultID, &requestedBy, &gCreated, &completed); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		item := map[string]any{
			"id": gid, "product_id": productID, "avatar_id": avatarID, "pose_reference_id": poseID,
			"provider": provider, "rights_record_id": rightsID, "scene_description": scene,
			"status": gStatus, "result_asset_id": resultID, "requested_by": requestedBy,
			"created_at": gCreated, "completed_at": completed,
		}
		if resultID != nil {
			var fileURL string
			if err := s.db.Pool.QueryRow(r.Context(), `SELECT file_url FROM assets WHERE id = $1`, *resultID).Scan(&fileURL); err == nil {
				item["result_asset"] = map[string]any{"id": *resultID, "file_url": fileURL}
			}
		}
		history = append(history, item)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"id": aid, "brand_id": bid, "name": name, "reference_asset_urls": json.RawMessage(refs),
		"identity_profile_ref": identity, "status": status, "created_at": created,
		"generation_requests": history,
	})
}

func (s *Server) handleListPoseReferences(w http.ResponseWriter, r *http.Request) {
	brandID := r.URL.Query().Get("brand_id")
	p := paginationFrom(r)
	var total int
	_ = s.db.Pool.QueryRow(r.Context(), `
		SELECT COUNT(*) FROM pose_references WHERE ($1 = '' OR brand_id::text = $1)`, brandID).Scan(&total)
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, brand_id::text, name, skeleton_data_url, created_at
		FROM pose_references
		WHERE ($1 = '' OR brand_id::text = $1)
		ORDER BY created_at DESC
		LIMIT $2 OFFSET $3`, brandID, p.PageSize, p.Offset())
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		var id, bid, name, skeleton string
		var created time.Time
		if err := rows.Scan(&id, &bid, &name, &skeleton, &created); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{
			"id": id, "brand_id": bid, "name": name, "skeleton_data_url": skeleton, "created_at": created,
		})
	}
	writePage(w, data, total, p.Page)
}

func (s *Server) handleCreatePoseReference(w http.ResponseWriter, r *http.Request) {
	var body struct {
		BrandID         string `json:"brand_id"`
		Name            string `json:"name"`
		SkeletonDataURL string `json:"skeleton_data_url"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), body.BrandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	var id string
	err = s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO pose_references (brand_id, name, skeleton_data_url)
		VALUES ($1,$2,$3) RETURNING id::text`, body.BrandID, body.Name, body.SkeletonDataURL).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"id": id, "brand_id": body.BrandID, "name": body.Name, "skeleton_data_url": body.SkeletonDataURL,
	})
}

func (s *Server) handleGetGenerationRequest(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	row := s.db.Pool.QueryRow(r.Context(), `
		SELECT id::text, product_id::text, avatar_id::text, pose_reference_id::text, provider,
			rights_record_id::text, scene_description, status, result_asset_id::text, requested_by::text, created_at, completed_at
		FROM generation_requests WHERE id = $1`, id)
	var gid, productID, provider, status, requestedBy string
	var avatarID, poseID, rightsID, scene, resultID *string
	var created time.Time
	var completed *time.Time
	if err := row.Scan(&gid, &productID, &avatarID, &poseID, &provider, &rightsID, &scene, &status, &resultID, &requestedBy, &created, &completed); err != nil {
		writeError(w, apperr.NotFound("generation request not found"))
		return
	}
	out := map[string]any{
		"id": gid, "product_id": productID, "avatar_id": avatarID, "pose_reference_id": poseID,
		"provider": provider, "rights_record_id": rightsID, "scene_description": scene,
		"status": status, "result_asset_id": resultID, "requested_by": requestedBy,
		"created_at": created, "completed_at": completed,
	}
	if resultID != nil {
		var fileURL string
		if err := s.db.Pool.QueryRow(r.Context(), `SELECT file_url FROM assets WHERE id = $1`, *resultID).Scan(&fileURL); err == nil {
			out["result_asset"] = map[string]any{"id": *resultID, "file_url": fileURL}
		}
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) handleRunBenchmark(w http.ResponseWriter, r *http.Request) {
	var body struct {
		BrandID          string   `json:"brand_id"`
		GoldenSetImageID string   `json:"golden_set_image_id"`
		Providers        []string `json:"providers"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), body.BrandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermPublishShopify) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	results := make([]map[string]any, 0, len(body.Providers))
	for _, provider := range body.Providers {
		var qcRunID string
		err := s.db.Pool.QueryRow(r.Context(), `
			INSERT INTO qc_runs (asset_id, golden_set_image_id, overall_score, result, raw_output)
			SELECT a.id, $1, 0.5, 'needs_review', '{"benchmark":true}'::jsonb
			FROM assets a LIMIT 1
			RETURNING id::text`, body.GoldenSetImageID).Scan(&qcRunID)
		if err != nil {
			qcRunID = uuid.NewString()
			_, _ = s.db.Pool.Exec(r.Context(), `
				INSERT INTO qc_runs (id, asset_id, golden_set_image_id, overall_score, result, raw_output)
				SELECT $1, a.id, $2, 0.5, 'needs_review', '{"benchmark":true}'::jsonb FROM assets a LIMIT 1`,
				qcRunID, body.GoldenSetImageID)
		}
		var id string
		_ = s.db.Pool.QueryRow(r.Context(), `
			INSERT INTO provider_benchmarks (brand_id, provider, golden_set_image_id, qc_run_id, cost_usd, latency_ms)
			VALUES ($1,$2,$3,$4,0,0) RETURNING id::text`,
			body.BrandID, provider, body.GoldenSetImageID, qcRunID).Scan(&id)
		results = append(results, map[string]any{"id": id, "provider": provider, "qc_run_id": qcRunID})
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"data": results})
}

func (s *Server) handleListBenchmarks(w http.ResponseWriter, r *http.Request) {
	gsID := r.URL.Query().Get("golden_set_image_id")
	p := paginationFrom(r)
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, brand_id::text, provider, golden_set_image_id::text, qc_run_id::text,
			generated_asset_url, cost_usd, latency_ms, created_at
		FROM provider_benchmarks
		WHERE ($1 = '' OR golden_set_image_id::text = $1)
		ORDER BY created_at DESC LIMIT $2 OFFSET $3`, gsID, p.PageSize, p.Offset())
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	var data []map[string]any
	for rows.Next() {
		var id, bid, provider, gsid, qcid string
		var url *string
		var cost *float64
		var latency *int
		var created time.Time
		if err := rows.Scan(&id, &bid, &provider, &gsid, &qcid, &url, &cost, &latency, &created); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{
			"id": id, "brand_id": bid, "provider": provider, "golden_set_image_id": gsid,
			"qc_run_id": qcid, "generated_asset_url": url, "cost_usd": cost, "latency_ms": latency, "created_at": created,
		})
	}
	if data == nil {
		data = []map[string]any{}
	}
	writePage(w, data, len(data), p.Page)
}

func (s *Server) handleGetNotificationPrefs(w http.ResponseWriter, r *http.Request) {
	uid := userIDFrom(r.Context())
	brandID := r.URL.Query().Get("brand_id")
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, user_id::text, brand_id::text, event_type, channel, frequency,
			quiet_hours_start::text, quiet_hours_end::text
		FROM notification_preferences WHERE user_id = $1 AND ($2 = '' OR brand_id::text = $2)`, uid.String(), brandID)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		var id, userID, bid, et, ch, freq string
		var qStart, qEnd *string
		if err := rows.Scan(&id, &userID, &bid, &et, &ch, &freq, &qStart, &qEnd); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{
			"id": id, "user_id": userID, "brand_id": bid, "event_type": et, "channel": ch,
			"frequency": freq, "quiet_hours_start": qStart, "quiet_hours_end": qEnd,
		})
	}
	writeJSON(w, http.StatusOK, data)
}

func (s *Server) handlePatchNotificationPrefs(w http.ResponseWriter, r *http.Request) {
	uid := userIDFrom(r.Context())
	raw, err := decodeJSONRaw(r)
	if err != nil {
		writeError(w, err)
		return
	}

	type prefBody struct {
		BrandID         string  `json:"brand_id"`
		EventType       string  `json:"event_type"`
		Channel         string  `json:"channel"`
		Frequency       string  `json:"frequency"`
		QuietHoursStart *string `json:"quiet_hours_start"`
		QuietHoursEnd   *string `json:"quiet_hours_end"`
	}

	var items []prefBody
	if err := json.Unmarshal(raw, &items); err != nil {
		var single prefBody
		if err2 := json.Unmarshal(raw, &single); err2 != nil {
			writeError(w, apperr.InvalidRequest("invalid JSON body", map[string]any{"reason": err.Error()}))
			return
		}
		items = []prefBody{single}
	}

	out := make([]map[string]any, 0, len(items))
	for _, body := range items {
		if body.BrandID == "" || body.EventType == "" || body.Channel == "" {
			continue
		}
		if body.Frequency == "" {
			body.Frequency = "immediate"
		}
		var id string
		err := s.db.Pool.QueryRow(r.Context(), `
			INSERT INTO notification_preferences (user_id, brand_id, event_type, channel, frequency, quiet_hours_start, quiet_hours_end)
			VALUES ($1,$2,$3,$4,$5,$6::time,$7::time)
			ON CONFLICT (user_id, brand_id, event_type, channel) DO UPDATE SET
				frequency = EXCLUDED.frequency,
				quiet_hours_start = EXCLUDED.quiet_hours_start,
				quiet_hours_end = EXCLUDED.quiet_hours_end
			RETURNING id::text`,
			uid.String(), body.BrandID, body.EventType, body.Channel, body.Frequency, body.QuietHoursStart, body.QuietHoursEnd,
		).Scan(&id)
		if err != nil {
			writeError(w, apperr.Internal("upsert failed"))
			return
		}
		out = append(out, map[string]any{
			"id": id, "user_id": uid.String(), "brand_id": body.BrandID,
			"event_type": body.EventType, "channel": body.Channel, "frequency": body.Frequency,
			"quiet_hours_start": body.QuietHoursStart, "quiet_hours_end": body.QuietHoursEnd,
		})
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) handleListNotifications(w http.ResponseWriter, r *http.Request) {
	uid := userIDFrom(r.Context())
	p := paginationFrom(r)
	var total int
	_ = s.db.Pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM notifications WHERE user_id = $1`, uid.String()).Scan(&total)
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, user_id::text, brand_id::text, event_type, payload, status, read_at, sent_at, created_at
		FROM notifications WHERE user_id = $1
		ORDER BY created_at DESC LIMIT $2 OFFSET $3`, uid.String(), p.PageSize, p.Offset())
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		var id, userID, bid, et, status string
		var payload []byte
		var readAt, sentAt *time.Time
		var created time.Time
		if err := rows.Scan(&id, &userID, &bid, &et, &payload, &status, &readAt, &sentAt, &created); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{
			"id": id, "user_id": userID, "brand_id": bid, "event_type": et,
			"payload": json.RawMessage(payload), "status": status, "read_at": readAt, "sent_at": sentAt, "created_at": created,
		})
	}
	writePage(w, data, total, p.Page)
}

func (s *Server) handleMarkNotificationRead(w http.ResponseWriter, r *http.Request) {
	uid := userIDFrom(r.Context())
	id := chi.URLParam(r, "id")
	tag, err := s.db.Pool.Exec(r.Context(), `
		UPDATE notifications SET read_at = COALESCE(read_at, now())
		WHERE id = $1 AND user_id = $2`, id, uid.String())
	if err != nil {
		writeError(w, apperr.Internal("update failed"))
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, apperr.NotFound("notification not found"))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"id": id, "status": "read"})
}

func (s *Server) handleMarkAllNotificationsRead(w http.ResponseWriter, r *http.Request) {
	uid := userIDFrom(r.Context())
	_, err := s.db.Pool.Exec(r.Context(), `
		UPDATE notifications SET read_at = now()
		WHERE user_id = $1 AND read_at IS NULL`, uid.String())
	if err != nil {
		writeError(w, apperr.Internal("update failed"))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (s *Server) handleListAuditLog(w http.ResponseWriter, r *http.Request) {
	p := paginationFrom(r)
	brandID := r.URL.Query().Get("brand_id")
	var total int
	_ = s.db.Pool.QueryRow(r.Context(), `
		SELECT COUNT(*) FROM audit_log WHERE ($1 = '' OR brand_id::text = $1)`, brandID).Scan(&total)
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, user_id::text, entity_type, entity_id::text, action, detail, created_at
		FROM audit_log
		WHERE ($1 = '' OR brand_id::text = $1)
		ORDER BY created_at DESC
		LIMIT $2 OFFSET $3`, brandID, p.PageSize, p.Offset())
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		var id, entityType, entityID, action string
		var userID *string
		var detail []byte
		var created time.Time
		if err := rows.Scan(&id, &userID, &entityType, &entityID, &action, &detail, &created); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		item := map[string]any{
			"id": id, "user_id": userID, "entity_type": entityType, "entity_id": entityID,
			"action": action, "created_at": created,
		}
		if detail != nil {
			item["detail"] = json.RawMessage(detail)
		}
		data = append(data, item)
	}
	writePage(w, data, total, p.Page)
}

func (s *Server) handleGetJob(w http.ResponseWriter, r *http.Request) {
	job, err := s.db.GetJobRecord(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, apperr.NotFound("job not found"))
		return
	}
	writeJSON(w, http.StatusOK, job)
}

func (s *Server) handleListJobs(w http.ResponseWriter, r *http.Request) {
	status := r.URL.Query().Get("status")
	p := paginationFrom(r)
	if status == "failed" {
		data, total, err := s.db.ListFailedJobs(r.Context(), p)
		if err != nil {
			writeError(w, apperr.Internal("query failed"))
			return
		}
		if data == nil {
			data = []map[string]any{}
		}
		writePage(w, data, total, p.Page)
		return
	}
	writePage(w, []map[string]any{}, 0, p.Page)
}

func (s *Server) handleListBrandUsers(w http.ResponseWriter, r *http.Request) {
	brandID := chi.URLParam(r, "id")
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT u.id::text, u.email, u.display_name, m.id::text, m.role, m.team, m.created_at
		FROM brand_memberships m JOIN users u ON u.id = m.user_id
		WHERE m.brand_id = $1 ORDER BY u.email`, brandID)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		var uid, email, mid, role string
		var display *string
		var team *string
		var created time.Time
		if err := rows.Scan(&uid, &email, &display, &mid, &role, &team, &created); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{
			"id": mid, "user_id": uid, "brand_id": brandID, "role": role, "team": team, "created_at": created,
			"user": map[string]any{"id": uid, "email": email, "name": display, "display_name": display},
		})
	}
	writeJSON(w, http.StatusOK, data)
}

func (s *Server) handleInviteUser(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Email       string  `json:"email"`
		Role        string  `json:"role"`
		Team        *string `json:"team"`
		DisplayName *string `json:"display_name"`
		Password    string  `json:"password"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if body.Password == "" {
		body.Password = seedDevInvitePassword()
	} else if len(body.Password) < auth.MinPasswordLength {
		writeError(w, apperr.PasswordTooShort())
		return
	}
	hash, err := auth.HashPassword(body.Password)
	if err != nil {
		writeError(w, apperr.Internal("hash failed"))
		return
	}
	brandID := chi.URLParam(r, "id")
	var userID string
	existing, err := s.db.GetUserByEmail(r.Context(), body.Email)
	if err == nil {
		userID = existing.ID
	} else {
		err = s.db.Pool.QueryRow(r.Context(), `
			INSERT INTO users (email, password_hash, display_name) VALUES ($1,$2,$3) RETURNING id::text`,
			body.Email, hash, body.DisplayName).Scan(&userID)
		if err != nil {
			writeError(w, apperr.Conflict("could not create user"))
			return
		}
	}
	var mid string
	err = s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO brand_memberships (user_id, brand_id, role, team)
		VALUES ($1,$2,$3,$4) RETURNING id::text`, userID, brandID, body.Role, body.Team).Scan(&mid)
	if err != nil {
		writeError(w, apperr.Conflict("membership exists"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"membership_id": mid, "user_id": userID})
}

func (s *Server) handlePatchMembership(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	m, err := s.db.GetMembershipByID(r.Context(), id)
	if err != nil {
		writeError(w, apperr.NotFound("membership not found"))
		return
	}
	uid := userIDFrom(r.Context())
	actor, err := s.db.GetMembership(r.Context(), uid.String(), m.BrandID)
	if err != nil || !permissions.Has(permissions.Role(actor.Role), permissions.PermManageUsers) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	var body struct {
		Role *string `json:"role"`
		Team *string `json:"team"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if body.Role != nil {
		_, _ = s.db.Pool.Exec(r.Context(), `UPDATE brand_memberships SET role = $2 WHERE id = $1`, id, *body.Role)
	}
	if body.Team != nil {
		_, _ = s.db.Pool.Exec(r.Context(), `UPDATE brand_memberships SET team = $2 WHERE id = $1`, id, *body.Team)
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": id, "status": "updated"})
}

func (s *Server) handleDeleteMembership(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	m, err := s.db.GetMembershipByID(r.Context(), id)
	if err != nil {
		writeError(w, apperr.NotFound("membership not found"))
		return
	}
	uid := userIDFrom(r.Context())
	actor, err := s.db.GetMembership(r.Context(), uid.String(), m.BrandID)
	if err != nil || !permissions.Has(permissions.Role(actor.Role), permissions.PermManageUsers) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	_, err = s.db.Pool.Exec(r.Context(), `DELETE FROM brand_memberships WHERE id = $1`, id)
	if err != nil {
		writeError(w, apperr.Internal("delete failed"))
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) handleListBriefs(w http.ResponseWriter, r *http.Request) {
	brandID := r.URL.Query().Get("brand_id")
	p := paginationFrom(r)
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, brand_id::text, created_by::text, notes, draft_content, status, created_at, updated_at
		FROM briefs WHERE ($1 = '' OR brand_id::text = $1)
		ORDER BY updated_at DESC LIMIT $2 OFFSET $3`, brandID, p.PageSize, p.Offset())
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	var data []map[string]any
	for rows.Next() {
		var id, bid, createdBy, notes, status string
		var draft *string
		var created, updated time.Time
		if err := rows.Scan(&id, &bid, &createdBy, &notes, &draft, &status, &created, &updated); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{
			"id": id, "brand_id": bid, "created_by": createdBy, "notes": notes,
			"draft_content": draft, "status": status, "created_at": created, "updated_at": updated,
		})
	}
	if data == nil {
		data = []map[string]any{}
	}
	writePage(w, data, len(data), p.Page)
}

func (s *Server) handleCreateBrief(w http.ResponseWriter, r *http.Request) {
	var body struct {
		BrandID string `json:"brand_id"`
		Notes   string `json:"notes"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	uid := userIDFrom(r.Context())
	draft := "Draft brief based on notes:\n" + body.Notes
	var id string
	err := s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO briefs (brand_id, created_by, notes, draft_content, status)
		VALUES ($1,$2,$3,$4,'draft') RETURNING id::text`,
		body.BrandID, uid.String(), body.Notes, draft).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"id": id, "draft": draft, "draft_content": draft, "status": "draft",
	})
}

func (s *Server) handleGetBrief(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	row := s.db.Pool.QueryRow(r.Context(), `
		SELECT id::text, brand_id::text, created_by::text, notes, draft_content, status, created_at, updated_at
		FROM briefs WHERE id = $1`, id)
	var bid, brandID, createdBy, notes, status string
	var draft *string
	var created, updated time.Time
	if err := row.Scan(&bid, &brandID, &createdBy, &notes, &draft, &status, &created, &updated); err != nil {
		writeError(w, apperr.NotFound("brief not found"))
		return
	}
	draftVal := ""
	if draft != nil {
		draftVal = *draft
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"id": bid, "brand_id": brandID, "created_by": createdBy, "notes": notes,
		"draft": draftVal, "draft_content": draft, "status": status, "created_at": created, "updated_at": updated,
	})
}

func (s *Server) handlePatchBrief(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	var body struct {
		Notes        *string `json:"notes"`
		Draft        *string `json:"draft"`
		DraftContent *string `json:"draft_content"`
		Status       *string `json:"status"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if body.Notes != nil {
		_, _ = s.db.Pool.Exec(r.Context(), `UPDATE briefs SET notes = $2, updated_at = now() WHERE id = $1`, id, *body.Notes)
	}
	draft := body.DraftContent
	if draft == nil {
		draft = body.Draft
	}
	if draft != nil {
		_, _ = s.db.Pool.Exec(r.Context(), `UPDATE briefs SET draft_content = $2, updated_at = now() WHERE id = $1`, id, *draft)
	}
	if body.Status != nil {
		_, _ = s.db.Pool.Exec(r.Context(), `UPDATE briefs SET status = $2, updated_at = now() WHERE id = $1`, id, *body.Status)
	}
	s.handleGetBrief(w, r)
}

func (s *Server) handleSendBriefValidation(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	_, err := s.db.Pool.Exec(r.Context(), `UPDATE briefs SET status = 'pending_validation', updated_at = now() WHERE id = $1`, id)
	if err != nil {
		writeError(w, apperr.Internal("update failed"))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"id": id, "status": "pending_validation"})
}

func seedDevInvitePassword() string {
	return "Password123!"
}
