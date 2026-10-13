package httpapi

import (
	"encoding/json"
	"io"
	"net/http"
	"time"

	"github.com/gathered/kitframe/apps/api/internal/apperr"
	"github.com/gathered/kitframe/apps/api/internal/db"
	"github.com/gathered/kitframe/apps/api/internal/permissions"
	"github.com/gathered/kitframe/apps/api/internal/shopify"
	"github.com/go-chi/chi/v5"
)

func (s *Server) handleCreateSourceDocument(w http.ResponseWriter, r *http.Request) {
	var body struct {
		ProductID *string `json:"product_id"`
		FileURL   string  `json:"file_url"`
		FileType  string  `json:"file_type"`
		BrandID   string  `json:"brand_id"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if body.FileURL == "" || body.FileType == "" {
		writeError(w, apperr.InvalidRequest("file_url and file_type required", nil))
		return
	}
	brandID := body.BrandID
	if brandID == "" && body.ProductID != nil {
		var err error
		brandID, err = s.db.ProductBrandID(r.Context(), *body.ProductID)
		if err != nil {
			writeError(w, apperr.NotFound("product not found"))
			return
		}
	}
	uid := userIDFrom(r.Context())
	if brandID != "" {
		m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
		if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
			writeError(w, apperr.Forbidden("insufficient permissions"))
			return
		}
	}
	var id string
	err := s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO source_documents (product_id, file_url, file_type)
		VALUES ($1,$2,$3) RETURNING id::text`, body.ProductID, body.FileURL, body.FileType).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	_ = s.jobs.EnqueueExtract(r.Context(), id)
	jobID, _ := s.db.CreateJobRecord(r.Context(), s.db.Pool, "extract", "queued", "source_document", &id)
	writeJSON(w, http.StatusAccepted, map[string]any{"id": id, "job_id": jobID, "extraction_status": "pending"})
}

func (s *Server) handleGetSourceDocument(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	row := s.db.Pool.QueryRow(r.Context(), `
		SELECT id::text, product_id::text, file_url, file_type, extraction_status, raw_extraction, created_at
		FROM source_documents WHERE id = $1`, id)
	var sid, fileURL, fileType, status string
	var productID *string
	var raw []byte
	var created time.Time
	if err := row.Scan(&sid, &productID, &fileURL, &fileType, &status, &raw, &created); err != nil {
		writeError(w, apperr.NotFound("source document not found"))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"id": sid, "product_id": productID, "file_url": fileURL, "file_type": fileType,
		"extraction_status": status, "raw_extraction": json.RawMessage(raw), "created_at": created,
	})
}

func (s *Server) handleCreateAsset(w http.ResponseWriter, r *http.Request) {
	var body struct {
		ProductID          string  `json:"product_id"`
		VariantID          *string `json:"variant_id"`
		Type               string  `json:"type"`
		Origin             string  `json:"origin"`
		ImageRole          string  `json:"image_role"`
		FileURL            string  `json:"file_url"`
		GenerationProvider *string `json:"generation_provider"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if body.Type == "" {
		body.Type = "product_only"
	}
	if body.Origin == "" {
		body.Origin = "real_photo"
	}
	if body.ImageRole == "" {
		if body.Origin == "generated" {
			body.ImageRole = "final"
		} else {
			body.ImageRole = "raw"
		}
	}
	brandID, err := s.db.ProductBrandID(r.Context(), body.ProductID)
	if err != nil {
		writeError(w, apperr.NotFound("product not found"))
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	a, err := s.db.CreateAsset(r.Context(), body.ProductID, body.VariantID, body.Type, body.Origin, body.ImageRole, body.FileURL, body.GenerationProvider)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, assetToMap(a))
}

func (s *Server) handleGetAsset(w http.ResponseWriter, r *http.Request) {
	a, err := s.db.GetAsset(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, apperr.NotFound("asset not found"))
		return
	}
	writeJSON(w, http.StatusOK, assetToMap(a))
}

func (s *Server) handleRunQC(w http.ResponseWriter, r *http.Request) {
	m := membershipFrom(r.Context())
	if !permissions.Has(permissions.Role(m.Role), permissions.PermRunQC) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	var body struct {
		GoldenSetImageID string `json:"golden_set_image_id"`
	}
	_ = decodeJSON(r, &body)
	assetID := chi.URLParam(r, "id")
	if err := s.jobs.EnqueueQC(r.Context(), assetID, body.GoldenSetImageID); err != nil {
		writeError(w, apperr.Internal("enqueue failed"))
		return
	}
	jobID, _ := s.db.CreateJobRecord(r.Context(), s.db.Pool, "qc", "queued", "asset", &assetID)
	writeJSON(w, http.StatusAccepted, map[string]any{"job_id": jobID, "status": "queued"})
}

func (s *Server) handleApproveAsset(w http.ResponseWriter, r *http.Request) {
	m := membershipFrom(r.Context())
	role := permissions.Role(m.Role)
	if !permissions.Has(role, permissions.PermApproveQC) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	assetID := chi.URLParam(r, "id")
	var body struct {
		Override bool   `json:"override"`
		Reason   string `json:"reason"`
	}
	_ = decodeJSON(r, &body)
	var latestResult *string
	_ = s.db.Pool.QueryRow(r.Context(), `
		SELECT result FROM qc_runs WHERE asset_id = $1 ORDER BY created_at DESC LIMIT 1`, assetID).Scan(&latestResult)
	if (latestResult == nil || *latestResult != "pass") && !body.Override {
		writeError(w, apperr.QCRequired())
		return
	}
	if body.Override && !permissions.Has(role, permissions.PermOverrideQC) {
		writeError(w, apperr.Forbidden("override not allowed"))
		return
	}
	if err := s.db.UpdateAssetQCStatus(r.Context(), s.db.Pool, assetID, "pass"); err != nil {
		writeError(w, apperr.Internal("update failed"))
		return
	}
	uid := userIDFrom(r.Context()).String()
	brandID, _ := r.Context().Value(ctxBrandID).(string)
	action := "qc.approve"
	if body.Override {
		action = "qc.override"
	}
	_ = s.db.InsertAudit(r.Context(), s.db.Pool, &uid, &brandID, "asset", assetID, action, db.MustJSON(map[string]any{
		"override": body.Override, "reason": body.Reason, "latest_result": latestResult,
	}))
	a, _ := s.db.GetAsset(r.Context(), assetID)
	writeJSON(w, http.StatusOK, assetToMap(a))
}

func (s *Server) handleSearchAssets(w http.ResponseWriter, r *http.Request) {
	p := paginationFrom(r)
	q := r.URL.Query().Get("q")
	category := r.URL.Query().Get("category")
	color := r.URL.Query().Get("color")
	brandID := r.Header.Get("X-Brand-Id")
	if brandID == "" {
		brandID = r.URL.Query().Get("brand_id")
	}
	uid := userIDFrom(r.Context())
	if brandID != "" {
		if _, err := s.db.GetMembership(r.Context(), uid.String(), brandID); err != nil {
			writeError(w, apperr.Forbidden("not a member of this brand"))
			return
		}
	}
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT a.id::text, a.product_id::text, a.variant_id::text, a.type, a.origin, a.image_role, a.file_url,
			a.generation_provider, a.qc_status, a.created_at
		FROM assets a
		JOIN products p ON p.id = a.product_id
		JOIN collections c ON c.id = p.collection_id
		LEFT JOIN asset_embeddings e ON e.asset_id = a.id
		WHERE ($1 = '' OR c.brand_id::text = $1)
			AND ($2 = '' OR e.tags::text ILIKE '%' || $2 || '%' OR a.file_url ILIKE '%' || $2 || '%')
			AND ($3 = '' OR p.category = $3)
			AND ($4 = '' OR p.structured_data->>'color_normalized' = $4)
		ORDER BY a.created_at DESC
		LIMIT $5 OFFSET $6`, brandID, q, category, color, p.PageSize, p.Offset())
	if err != nil {
		writeError(w, apperr.Internal("search failed"))
		return
	}
	defer rows.Close()
	var data []map[string]any
	for rows.Next() {
		var a db.Asset
		if err := rows.Scan(&a.ID, &a.ProductID, &a.VariantID, &a.Type, &a.Origin, &a.ImageRole, &a.FileURL, &a.GenerationProvider, &a.QCStatus, &a.CreatedAt); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, assetToMap(&a))
	}
	if data == nil {
		data = []map[string]any{}
	}
	writePage(w, data, len(data), p.Page)
}

func (s *Server) handleReindexAsset(w http.ResponseWriter, r *http.Request) {
	assetID := chi.URLParam(r, "id")
	_, err := s.db.Pool.Exec(r.Context(), `
		INSERT INTO asset_embeddings (asset_id, tags)
		VALUES ($1, '{}'::jsonb)
		ON CONFLICT (asset_id) DO UPDATE SET tags = EXCLUDED.tags, created_at = now()`, assetID)
	if err != nil {
		writeError(w, apperr.Internal("reindex failed"))
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": assetID, "status": "reindexed"})
}

func (s *Server) handleListGoldenSet(w http.ResponseWriter, r *http.Request) {
	brandID := r.URL.Query().Get("brand_id")
	category := r.URL.Query().Get("category")
	p := paginationFrom(r)
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, brand_id::text, garment_category, file_url, reference_color_lab, logo_bounding_box, approved_by::text, created_at
		FROM golden_set_images
		WHERE ($1 = '' OR brand_id::text = $1) AND ($2 = '' OR garment_category = $2) AND superseded_by IS NULL
		ORDER BY created_at DESC LIMIT $3 OFFSET $4`, brandID, category, p.PageSize, p.Offset())
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	var data []map[string]any
	for rows.Next() {
		var id, bid, cat, url string
		var colorLab, bbox []byte
		var approvedBy *string
		var created time.Time
		if err := rows.Scan(&id, &bid, &cat, &url, &colorLab, &bbox, &approvedBy, &created); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{
			"id": id, "brand_id": bid, "garment_category": cat, "file_url": url,
			"reference_color_lab": json.RawMessage(colorLab), "logo_bounding_box": json.RawMessage(bbox),
			"approved_by": approvedBy, "created_at": created,
		})
	}
	if data == nil {
		data = []map[string]any{}
	}
	writePage(w, data, len(data), p.Page)
}

func (s *Server) handleCreateGoldenSet(w http.ResponseWriter, r *http.Request) {
	var body struct {
		BrandID          string          `json:"brand_id"`
		GarmentCategory  string          `json:"garment_category"`
		FileURL          string          `json:"file_url"`
		ReferenceColorLab json.RawMessage `json:"reference_color_lab"`
		LogoBoundingBox  json.RawMessage `json:"logo_bounding_box"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), body.BrandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermManageGoldenSet) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	var id string
	err = s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO golden_set_images (brand_id, garment_category, file_url, reference_color_lab, logo_bounding_box, approved_by)
		VALUES ($1,$2,$3,COALESCE($4,'{}'::jsonb),$5,$6) RETURNING id::text`,
		body.BrandID, body.GarmentCategory, body.FileURL, []byte(body.ReferenceColorLab), []byte(body.LogoBoundingBox), uid.String(),
	).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"id": id})
}

func (s *Server) handleListRights(w http.ResponseWriter, r *http.Request) {
	brandID := r.URL.Query().Get("brand_id")
	p := paginationFrom(r)
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, brand_id::text, subject_type, subject_name, status, cleared_at, cleared_by::text, notes, created_at, updated_at
		FROM rights_records WHERE ($1 = '' OR brand_id::text = $1)
		ORDER BY updated_at DESC LIMIT $2 OFFSET $3`, brandID, p.PageSize, p.Offset())
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	var data []map[string]any
	for rows.Next() {
		var id, bid, stype, sname, status string
		var notes, clearedBy *string
		var clearedAt *time.Time
		var created, updated time.Time
		if err := rows.Scan(&id, &bid, &stype, &sname, &status, &clearedAt, &clearedBy, &notes, &created, &updated); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{
			"id": id, "brand_id": bid, "subject_type": stype, "subject_name": sname, "status": status,
			"cleared_at": clearedAt, "cleared_by": clearedBy, "notes": notes, "created_at": created, "updated_at": updated,
		})
	}
	if data == nil {
		data = []map[string]any{}
	}
	writePage(w, data, len(data), p.Page)
}

func (s *Server) handleCreateRights(w http.ResponseWriter, r *http.Request) {
	var body struct {
		BrandID     string  `json:"brand_id"`
		SubjectType string  `json:"subject_type"`
		SubjectName string  `json:"subject_name"`
		Notes       *string `json:"notes"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), body.BrandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermManageRights) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	var id string
	err = s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO rights_records (brand_id, subject_type, subject_name, notes)
		VALUES ($1,$2,$3,$4) RETURNING id::text`, body.BrandID, body.SubjectType, body.SubjectName, body.Notes).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"id": id, "status": "not_cleared"})
}

func (s *Server) handlePatchRights(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	var brandID string
	if err := s.db.Pool.QueryRow(r.Context(), `SELECT brand_id::text FROM rights_records WHERE id = $1`, id).Scan(&brandID); err != nil {
		writeError(w, apperr.NotFound("rights record not found"))
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermManageRights) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	var body struct {
		Status string  `json:"status"`
		Notes  *string `json:"notes"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if body.Status == "cleared" {
		_, err = s.db.Pool.Exec(r.Context(), `
			UPDATE rights_records SET status = 'cleared', cleared_at = now(), cleared_by = $2, notes = COALESCE($3, notes), updated_at = now()
			WHERE id = $1`, id, uid.String(), body.Notes)
	} else {
		_, err = s.db.Pool.Exec(r.Context(), `
			UPDATE rights_records SET status = $2, notes = COALESCE($3, notes), updated_at = now() WHERE id = $1`, id, body.Status, body.Notes)
	}
	if err != nil {
		writeError(w, apperr.Internal("update failed"))
		return
	}
	_ = s.db.InsertAudit(r.Context(), s.db.Pool, ptr(uid.String()), &brandID, "rights_record", id, "update", db.MustJSON(body))
	writeJSON(w, http.StatusOK, map[string]any{"id": id, "status": body.Status})
}

func (s *Server) handleShopifyWebhook(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		writeError(w, apperr.InvalidRequest("cannot read body", nil))
		return
	}
	sig := r.Header.Get("X-Shopify-Hmac-Sha256")
	if !shopify.VerifyWebhookHMAC(s.cfg.ShopifyWebhookSecret, body, sig) {
		writeError(w, apperr.WebhookInvalid())
		return
	}
	topic := r.Header.Get("X-Shopify-Topic")
	uid := (*string)(nil)
	_ = s.db.InsertAudit(r.Context(), s.db.Pool, uid, nil, "webhook", "00000000-0000-4000-8000-000000000000", "shopify."+topic, body)
	writeJSON(w, http.StatusOK, map[string]string{"status": "accepted"})
}

func ptr[T any](v T) *T { return &v }
