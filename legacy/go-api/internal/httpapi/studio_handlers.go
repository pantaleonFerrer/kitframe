package httpapi

import (
	"net/http"
	"time"

	"github.com/gathered/kitframe/apps/api/internal/apperr"
	"github.com/gathered/kitframe/apps/api/internal/db"
	"github.com/gathered/kitframe/apps/api/internal/permissions"
	"github.com/go-chi/chi/v5"
)

type generationCreateInput struct {
	ProductID             string
	AvatarID              *string
	PoseReferenceID       *string
	Provider              string
	RightsRecordID        *string
	SceneDescription      *string
	GarmentPrompt         *string
	PosePrompt            *string
	BackgroundPrompt      *string
	RawAssetID            *string
	ReferenceAssetIDs     []string
	ModelReferenceID      *string
	BackgroundReferenceID *string
	SourceFinalAssetID    *string
	ParentRequestID       *string
}

func (s *Server) insertGenerationRequest(w http.ResponseWriter, r *http.Request, uid string, in generationCreateInput) (string, string, bool) {
	if in.Provider == "" {
		in.Provider = "mock"
	}
	brandID, err := s.db.ProductBrandID(r.Context(), in.ProductID)
	if err != nil {
		writeError(w, apperr.NotFound("product not found"))
		return "", "", false
	}
	m, err := s.db.GetMembership(r.Context(), uid, brandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return "", "", false
	}

	status := "queued"
	if in.RightsRecordID != nil {
		var rightsStatus string
		err := s.db.Pool.QueryRow(r.Context(), `SELECT status FROM rights_records WHERE id = $1`, *in.RightsRecordID).Scan(&rightsStatus)
		if err != nil {
			writeError(w, apperr.NotFound("rights record not found"))
			return "", "", false
		}
		if rightsStatus != "cleared" {
			status = "blocked_rights"
		}
	} else if in.AvatarID != nil {
		status = "blocked_rights"
	}

	refJSON := []byte("[]")
	if len(in.ReferenceAssetIDs) > 0 {
		refJSON = db.MustJSON(in.ReferenceAssetIDs)
	}

	var id string
	err = s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO generation_requests (
			product_id, avatar_id, pose_reference_id, provider, rights_record_id, scene_description,
			garment_prompt, pose_prompt, background_prompt, raw_asset_id, reference_asset_ids,
			model_reference_id, background_reference_id, source_final_asset_id, parent_request_id,
			status, requested_by
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17) RETURNING id::text`,
		in.ProductID, in.AvatarID, in.PoseReferenceID, in.Provider, in.RightsRecordID, in.SceneDescription,
		in.GarmentPrompt, in.PosePrompt, in.BackgroundPrompt, in.RawAssetID, refJSON,
		in.ModelReferenceID, in.BackgroundReferenceID, in.SourceFinalAssetID, in.ParentRequestID,
		status, uid,
	).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return "", "", false
	}

	if status == "blocked_rights" {
		writeJSON(w, http.StatusConflict, map[string]any{
			"id":     id,
			"status": status,
			"error": map[string]any{
				"code":    apperr.CodeRightsNotCleared,
				"message": "Rights record is not cleared",
				"details": map[string]any{},
			},
		})
		return id, status, false
	}

	if err := s.jobs.EnqueueGenerate(r.Context(), id); err != nil {
		writeError(w, apperr.Internal("enqueue failed"))
		return "", "", false
	}
	return id, status, true
}

func (s *Server) handleListReferenceLibrary(w http.ResponseWriter, r *http.Request) {
	brandID := r.URL.Query().Get("brand_id")
	kind := r.URL.Query().Get("kind")
	p := paginationFrom(r)
	var total int
	_ = s.db.Pool.QueryRow(r.Context(), `
		SELECT COUNT(*) FROM reference_library_items
		WHERE ($1 = '' OR brand_id::text = $1) AND ($2 = '' OR kind = $2)`, brandID, kind).Scan(&total)
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, brand_id::text, kind, name, file_url, prompt_text, created_at
		FROM reference_library_items
		WHERE ($1 = '' OR brand_id::text = $1) AND ($2 = '' OR kind = $2)
		ORDER BY created_at DESC
		LIMIT $3 OFFSET $4`, brandID, kind, p.PageSize, p.Offset())
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		var id, bid, k, name, fileURL, prompt string
		var created time.Time
		if err := rows.Scan(&id, &bid, &k, &name, &fileURL, &prompt, &created); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{
			"id": id, "brand_id": bid, "kind": k, "name": name, "file_url": fileURL,
			"prompt_text": prompt, "created_at": created,
		})
	}
	writePage(w, data, total, p.Page)
}

func (s *Server) handleCreateReferenceLibrary(w http.ResponseWriter, r *http.Request) {
	var body struct {
		BrandID    string `json:"brand_id"`
		Kind       string `json:"kind"`
		Name       string `json:"name"`
		FileURL    string `json:"file_url"`
		PromptText string `json:"prompt_text"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if body.Kind != "model" && body.Kind != "background" && body.Kind != "pose" {
		writeError(w, apperr.InvalidRequest("kind must be model, background, or pose", nil))
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
		INSERT INTO reference_library_items (brand_id, kind, name, file_url, prompt_text)
		VALUES ($1,$2,$3,$4,$5) RETURNING id::text`,
		body.BrandID, body.Kind, body.Name, body.FileURL, body.PromptText).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"id": id, "brand_id": body.BrandID, "kind": body.Kind, "name": body.Name,
		"file_url": body.FileURL, "prompt_text": body.PromptText,
	})
}

func (s *Server) handleGenerateProductFinals(w http.ResponseWriter, r *http.Request) {
	productID := chi.URLParam(r, "id")
	var body struct {
		Provider              string   `json:"provider"`
		RawAssetID            string   `json:"raw_asset_id"`
		ReferenceAssetIDs     []string `json:"reference_asset_ids"`
		GarmentPrompt         *string  `json:"garment_prompt"`
		SceneDescription      *string  `json:"scene_description"`
		PosePrompt            *string  `json:"pose_prompt"`
		BackgroundPrompt      *string  `json:"background_prompt"`
		AvatarID              *string  `json:"avatar_id"`
		RightsRecordID        *string  `json:"rights_record_id"`
		PoseReferenceID       *string  `json:"pose_reference_id"`
		ModelReferenceID      *string  `json:"model_reference_id"`
		BackgroundReferenceID *string  `json:"background_reference_id"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	var rawID *string
	if body.RawAssetID != "" {
		rawID = &body.RawAssetID
	}
	uid := userIDFrom(r.Context())
	genID, status, ok := s.insertGenerationRequest(w, r, uid.String(), generationCreateInput{
		ProductID:             productID,
		AvatarID:              body.AvatarID,
		PoseReferenceID:       body.PoseReferenceID,
		Provider:              body.Provider,
		RightsRecordID:        body.RightsRecordID,
		SceneDescription:      body.SceneDescription,
		GarmentPrompt:         body.GarmentPrompt,
		PosePrompt:            body.PosePrompt,
		BackgroundPrompt:      body.BackgroundPrompt,
		RawAssetID:            rawID,
		ReferenceAssetIDs:     body.ReferenceAssetIDs,
		ModelReferenceID:      body.ModelReferenceID,
		BackgroundReferenceID: body.BackgroundReferenceID,
	})
	if !ok {
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"id": genID, "status": status})
}

func (s *Server) handleApplyFinalToAvatar(w http.ResponseWriter, r *http.Request) {
	finalAssetID := chi.URLParam(r, "id")
	var body struct {
		AvatarID              string  `json:"avatar_id"`
		RightsRecordID        string  `json:"rights_record_id"`
		Provider              string  `json:"provider"`
		GarmentPrompt         *string `json:"garment_prompt"`
		SceneDescription      *string `json:"scene_description"`
		PosePrompt            *string `json:"pose_prompt"`
		BackgroundPrompt      *string `json:"background_prompt"`
		PoseReferenceID       *string `json:"pose_reference_id"`
		ModelReferenceID      *string `json:"model_reference_id"`
		BackgroundReferenceID *string `json:"background_reference_id"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	var productID, imageRole, brandID string
	err := s.db.Pool.QueryRow(r.Context(), `
		SELECT a.product_id::text, a.image_role, c.brand_id::text
		FROM assets a
		JOIN products p ON p.id = a.product_id
		JOIN collections c ON c.id = p.collection_id
		WHERE a.id = $1`, finalAssetID).Scan(&productID, &imageRole, &brandID)
	if err != nil {
		writeError(w, apperr.NotFound("asset not found"))
		return
	}
	if imageRole != "final" {
		writeError(w, apperr.InvalidRequest("asset must be a final image", nil))
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}

	var sessionID string
	err = s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO avatar_studio_sessions (brand_id, final_asset_id, avatar_id, rights_record_id)
		VALUES ($1,$2,$3,$4) RETURNING id::text`,
		brandID, finalAssetID, body.AvatarID, body.RightsRecordID).Scan(&sessionID)
	if err != nil {
		writeError(w, apperr.Internal("create session failed"))
		return
	}

	sourceFinal := finalAssetID
	rightsID := body.RightsRecordID
	genID, status, ok := s.insertGenerationRequest(w, r, uid.String(), generationCreateInput{
		ProductID:             productID,
		AvatarID:              &body.AvatarID,
		PoseReferenceID:       body.PoseReferenceID,
		Provider:              body.Provider,
		RightsRecordID:        &rightsID,
		SceneDescription:      body.SceneDescription,
		GarmentPrompt:         body.GarmentPrompt,
		PosePrompt:            body.PosePrompt,
		BackgroundPrompt:      body.BackgroundPrompt,
		ModelReferenceID:      body.ModelReferenceID,
		BackgroundReferenceID: body.BackgroundReferenceID,
		SourceFinalAssetID:    &sourceFinal,
	})
	if !ok {
		return
	}

	var versionID string
	err = s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO avatar_studio_versions
			(session_id, generation_request_id, version_number, garment_prompt, pose_prompt, background_prompt, scene_description)
		VALUES ($1,$2,1,$3,$4,$5,$6) RETURNING id::text`,
		sessionID, genID, body.GarmentPrompt, body.PosePrompt, body.BackgroundPrompt, body.SceneDescription).Scan(&versionID)
	if err != nil {
		writeError(w, apperr.Internal("create version failed"))
		return
	}

	writeJSON(w, http.StatusAccepted, map[string]any{
		"session_id":              sessionID,
		"version_id":              versionID,
		"generation_request_id":   genID,
		"status":                  status,
		"version_number":          1,
	})
}

func (s *Server) handleGetAvatarStudioSession(w http.ResponseWriter, r *http.Request) {
	sessionID := chi.URLParam(r, "id")
	var brandID, finalAssetID, avatarID string
	var activeVersionID, rightsID *string
	var created, updated time.Time
	err := s.db.Pool.QueryRow(r.Context(), `
		SELECT brand_id::text, final_asset_id::text, avatar_id::text, rights_record_id::text,
			active_version_id::text, created_at, updated_at
		FROM avatar_studio_sessions WHERE id = $1`, sessionID).Scan(
		&brandID, &finalAssetID, &avatarID, &rightsID, &activeVersionID, &created, &updated)
	if err != nil {
		writeError(w, apperr.NotFound("session not found"))
		return
	}

	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT v.id::text, v.version_number, v.generation_request_id::text, v.garment_prompt, v.pose_prompt,
			v.background_prompt, v.scene_description, v.result_asset_id::text, v.created_at, g.status
		FROM avatar_studio_versions v
		JOIN generation_requests g ON g.id = v.generation_request_id
		WHERE v.session_id = $1
		ORDER BY v.version_number ASC`, sessionID)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	versions := make([]map[string]any, 0)
	for rows.Next() {
		var vid string
		var versionNum int
		var genID, genStatus string
		var garment, pose, bg, scene, resultID *string
		var vCreated time.Time
		if err := rows.Scan(&vid, &versionNum, &genID, &garment, &pose, &bg, &scene, &resultID, &vCreated, &genStatus); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		item := map[string]any{
			"id": vid, "version_number": versionNum, "generation_request_id": genID,
			"garment_prompt": garment, "pose_prompt": pose, "background_prompt": bg,
			"scene_description": scene, "result_asset_id": resultID, "created_at": vCreated,
			"status": genStatus,
		}
		if resultID != nil {
			var fileURL string
			if err := s.db.Pool.QueryRow(r.Context(), `SELECT file_url FROM assets WHERE id = $1`, *resultID).Scan(&fileURL); err == nil {
				item["result_asset"] = map[string]any{"id": *resultID, "file_url": fileURL}
			}
		}
		versions = append(versions, item)
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"id": sessionID, "brand_id": brandID, "final_asset_id": finalAssetID,
		"avatar_id": avatarID, "rights_record_id": rightsID, "active_version_id": activeVersionID,
		"created_at": created, "updated_at": updated, "versions": versions,
	})
}

func (s *Server) handleIterateAvatarStudio(w http.ResponseWriter, r *http.Request) {
	sessionID := chi.URLParam(r, "id")
	var body struct {
		BaseVersionID         string  `json:"base_version_id"`
		Provider              string  `json:"provider"`
		GarmentPrompt         *string `json:"garment_prompt"`
		SceneDescription      *string `json:"scene_description"`
		PosePrompt            *string `json:"pose_prompt"`
		BackgroundPrompt      *string `json:"background_prompt"`
		PoseReferenceID       *string `json:"pose_reference_id"`
		ModelReferenceID      *string `json:"model_reference_id"`
		BackgroundReferenceID *string `json:"background_reference_id"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}

	var productID, finalAssetID, avatarID, brandID string
	var rightsID *string
	var parentGenID *string
	var nextVersion int
	err := s.db.Pool.QueryRow(r.Context(), `
		SELECT s.brand_id::text, s.final_asset_id::text, s.avatar_id::text, s.rights_record_id::text,
			a.product_id::text, v.generation_request_id::text,
			(SELECT COALESCE(MAX(version_number), 0) + 1 FROM avatar_studio_versions WHERE session_id = s.id)
		FROM avatar_studio_sessions s
		JOIN assets a ON a.id = s.final_asset_id
		JOIN avatar_studio_versions v ON v.id = $2
		WHERE s.id = $1`, sessionID, body.BaseVersionID).Scan(
		&brandID, &finalAssetID, &avatarID, &rightsID, &productID, &parentGenID, &nextVersion)
	if err != nil {
		writeError(w, apperr.NotFound("session or version not found"))
		return
	}

	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}

	sourceFinal := finalAssetID
	genID, status, ok := s.insertGenerationRequest(w, r, uid.String(), generationCreateInput{
		ProductID:             productID,
		AvatarID:              &avatarID,
		PoseReferenceID:       body.PoseReferenceID,
		Provider:              body.Provider,
		RightsRecordID:        rightsID,
		SceneDescription:      body.SceneDescription,
		GarmentPrompt:         body.GarmentPrompt,
		PosePrompt:            body.PosePrompt,
		BackgroundPrompt:      body.BackgroundPrompt,
		ModelReferenceID:      body.ModelReferenceID,
		BackgroundReferenceID: body.BackgroundReferenceID,
		SourceFinalAssetID:    &sourceFinal,
		ParentRequestID:       parentGenID,
	})
	if !ok {
		return
	}

	var versionID string
	err = s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO avatar_studio_versions
			(session_id, generation_request_id, version_number, garment_prompt, pose_prompt, background_prompt, scene_description)
		VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id::text`,
		sessionID, genID, nextVersion, body.GarmentPrompt, body.PosePrompt, body.BackgroundPrompt, body.SceneDescription).Scan(&versionID)
	if err != nil {
		writeError(w, apperr.Internal("create version failed"))
		return
	}

	writeJSON(w, http.StatusAccepted, map[string]any{
		"session_id":            sessionID,
		"version_id":            versionID,
		"generation_request_id": genID,
		"status":                status,
		"version_number":        nextVersion,
	})
}

func (s *Server) handleCreateGenerationRequest(w http.ResponseWriter, r *http.Request) {
	var body struct {
		ProductID             string   `json:"product_id"`
		AvatarID              *string  `json:"avatar_id"`
		PoseReferenceID       *string  `json:"pose_reference_id"`
		Provider              string   `json:"provider"`
		RightsRecordID        *string  `json:"rights_record_id"`
		SceneDescription      *string  `json:"scene_description"`
		GarmentPrompt         *string  `json:"garment_prompt"`
		PosePrompt            *string  `json:"pose_prompt"`
		BackgroundPrompt      *string  `json:"background_prompt"`
		RawAssetID            *string  `json:"raw_asset_id"`
		ReferenceAssetIDs     []string `json:"reference_asset_ids"`
		ModelReferenceID      *string  `json:"model_reference_id"`
		BackgroundReferenceID *string  `json:"background_reference_id"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	uid := userIDFrom(r.Context())
	genID, status, ok := s.insertGenerationRequest(w, r, uid.String(), generationCreateInput{
		ProductID:             body.ProductID,
		AvatarID:              body.AvatarID,
		PoseReferenceID:       body.PoseReferenceID,
		Provider:              body.Provider,
		RightsRecordID:        body.RightsRecordID,
		SceneDescription:      body.SceneDescription,
		GarmentPrompt:         body.GarmentPrompt,
		PosePrompt:            body.PosePrompt,
		BackgroundPrompt:      body.BackgroundPrompt,
		RawAssetID:            body.RawAssetID,
		ReferenceAssetIDs:     body.ReferenceAssetIDs,
		ModelReferenceID:      body.ModelReferenceID,
		BackgroundReferenceID: body.BackgroundReferenceID,
	})
	if !ok {
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"id": genID, "status": status})
}
