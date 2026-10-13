package httpapi

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/gathered/kitframe/apps/api/internal/apperr"
	"github.com/gathered/kitframe/apps/api/internal/db"
	"github.com/gathered/kitframe/apps/api/internal/domain"
	"github.com/gathered/kitframe/apps/api/internal/permissions"
	"github.com/gathered/kitframe/apps/api/internal/shopify"
	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"
)

func brandToMap(b *db.Brand) map[string]any {
	return map[string]any{
		"id":                     b.ID,
		"name":                   b.Name,
		"taxonomy_schema":        json.RawMessage(b.TaxonomySchema),
		"translation_glossary":   json.RawMessage(b.TranslationGlossary),
		"shopify_store_domain":   b.ShopifyStoreDomain,
		"shopify_environment":    b.ShopifyEnvironment,
		"qc_pass_threshold":      b.QCPassThreshold,
		"qc_fail_threshold":      b.QCFailThreshold,
		"qc_check_floor":         b.QCCheckFloor,
		"created_at":             b.CreatedAt,
		"updated_at":             b.UpdatedAt,
	}
}

func productToMap(p *db.Product) map[string]any {
	return map[string]any{
		"id":                    p.ID,
		"collection_id":         p.CollectionID,
		"internal_reference":    p.InternalReference,
		"category":              p.Category,
		"status":                p.Status,
		"structured_data":       json.RawMessage(p.StructuredData),
		"extraction_confidence": json.RawMessage(p.ExtractionConfidence),
		"seo":                   json.RawMessage(p.SEO),
		"translations":          json.RawMessage(p.Translations),
		"assigned_team":         p.AssignedTeam,
		"shopify_product_id":    p.ShopifyProductID,
		"created_at":            p.CreatedAt,
		"updated_at":            p.UpdatedAt,
	}
}

func assetToMap(a *db.Asset) map[string]any {
	return map[string]any{
		"id":                  a.ID,
		"product_id":          a.ProductID,
		"variant_id":          a.VariantID,
		"type":                a.Type,
		"origin":              a.Origin,
		"image_role":          a.ImageRole,
		"file_url":            a.FileURL,
		"generation_provider": a.GenerationProvider,
		"qc_status":           a.QCStatus,
		"created_at":          a.CreatedAt,
	}
}

func (s *Server) handleGetBrand(w http.ResponseWriter, r *http.Request) {
	b, err := s.db.GetBrand(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, apperr.NotFound("brand not found"))
		return
	}
	writeJSON(w, http.StatusOK, brandToMap(b))
}

func (s *Server) handlePatchBrand(w http.ResponseWriter, r *http.Request) {
	var body map[string]any
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	allowed := map[string]string{
		"name":                   "name",
		"taxonomy_schema":        "taxonomy_schema",
		"translation_glossary":   "translation_glossary",
		"shopify_store_domain":   "shopify_store_domain",
		"shopify_environment":    "shopify_environment",
		"shopify_live_store_domain": "shopify_live_store_domain",
		"qc_pass_threshold":      "qc_pass_threshold",
		"qc_fail_threshold":      "qc_fail_threshold",
		"qc_check_floor":         "qc_check_floor",
	}
	fields := map[string]any{}
	for k, col := range allowed {
		if v, ok := body[k]; ok {
			fields[col] = v
		}
	}
	b, err := s.db.PatchBrand(r.Context(), chi.URLParam(r, "id"), fields)
	if err != nil {
		writeError(w, apperr.Internal("failed to update brand"))
		return
	}
	uid := userIDFrom(r.Context()).String()
	brandID := b.ID
	_ = s.db.InsertAudit(r.Context(), s.db.Pool, &uid, &brandID, "brand", brandID, "update", db.MustJSON(fields))
	writeJSON(w, http.StatusOK, brandToMap(b))
}

func (s *Server) handleCreateChannelSpec(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Channel         string `json:"channel"`
		WidthPx         int    `json:"width_px"`
		HeightPx        int    `json:"height_px"`
		Format          string `json:"format"`
		ColorProfile    string `json:"color_profile"`
		FilenamePattern string `json:"filename_pattern"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if body.ColorProfile == "" {
		body.ColorProfile = "sRGB"
	}
	brandID := chi.URLParam(r, "id")
	var id string
	err := s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO channel_specs (brand_id, channel, width_px, height_px, format, color_profile, filename_pattern)
		VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id::text`,
		brandID, body.Channel, body.WidthPx, body.HeightPx, body.Format, body.ColorProfile, body.FilenamePattern,
	).Scan(&id)
	if err != nil {
		writeError(w, apperr.Conflict("could not create channel spec"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"id": id, "brand_id": brandID, "channel": body.Channel})
}

func (s *Server) handleListChannelSpecs(w http.ResponseWriter, r *http.Request) {
	brandID := chi.URLParam(r, "id")
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, brand_id::text, channel, width_px, height_px, format, color_profile, filename_pattern, created_at
		FROM channel_specs WHERE brand_id = $1 ORDER BY channel`, brandID)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	var data []map[string]any
	for rows.Next() {
		var id, bid, channel, format, profile, pattern string
		var wpx, hpx int
		var created time.Time
		if err := rows.Scan(&id, &bid, &channel, &wpx, &hpx, &format, &profile, &pattern, &created); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{
			"id": id, "brand_id": bid, "channel": channel, "width_px": wpx, "height_px": hpx,
			"format": format, "color_profile": profile, "filename_pattern": pattern, "created_at": created,
		})
	}
	if data == nil {
		data = []map[string]any{}
	}
	writePage(w, data, len(data), 1)
}

func (s *Server) handlePatchChannelSpec(w http.ResponseWriter, r *http.Request) {
	var body map[string]any
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	id := chi.URLParam(r, "id")
	var brandID string
	if err := s.db.Pool.QueryRow(r.Context(), `SELECT brand_id::text FROM channel_specs WHERE id = $1`, id).Scan(&brandID); err != nil {
		writeError(w, apperr.NotFound("channel spec not found"))
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermManageBrandSettings) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	cols := map[string]string{"width_px": "width_px", "height_px": "height_px", "format": "format", "color_profile": "color_profile", "filename_pattern": "filename_pattern"}
	for k, col := range cols {
		if v, ok := body[k]; ok {
			_, err := s.db.Pool.Exec(r.Context(), `UPDATE channel_specs SET `+col+` = $1 WHERE id = $2`, v, id)
			if err != nil {
				writeError(w, apperr.Internal("update failed"))
				return
			}
		}
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": id, "status": "updated"})
}

func (s *Server) handleGetCollection(w http.ResponseWriter, r *http.Request) {
	c, err := s.db.GetCollection(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, apperr.NotFound("collection not found"))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"id": c.ID, "brand_id": c.BrandID, "name": c.Name,
		"sample_arrival_date": c.SampleArrivalDate, "must_ship_date": c.MustShipDate,
		"sale_date": c.SaleDate, "created_at": c.CreatedAt, "updated_at": c.UpdatedAt,
	})
}

func (s *Server) handleListBrandCollections(w http.ResponseWriter, r *http.Request) {
	p := paginationFrom(r)
	cols, total, err := s.db.ListCollectionsByBrand(r.Context(), chi.URLParam(r, "id"), p)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	data := make([]map[string]any, 0, len(cols))
	for i := range cols {
		c := &cols[i]
		data = append(data, map[string]any{
			"id": c.ID, "brand_id": c.BrandID, "name": c.Name,
			"sample_arrival_date": c.SampleArrivalDate, "must_ship_date": c.MustShipDate,
			"sale_date": c.SaleDate, "created_at": c.CreatedAt, "updated_at": c.UpdatedAt,
		})
	}
	writePage(w, data, total, p.Page)
}

func (s *Server) handleListCollectionProducts(w http.ResponseWriter, r *http.Request) {
	p := paginationFrom(r)
	products, total, err := s.db.ListCollectionProducts(r.Context(), chi.URLParam(r, "id"), r.URL.Query().Get("step"), r.URL.Query().Get("team"), p)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	data := make([]map[string]any, 0, len(products))
	for i := range products {
		data = append(data, productToMap(&products[i]))
	}
	writePage(w, data, total, p.Page)
}

func (s *Server) handleBottlenecks(w http.ResponseWriter, r *http.Request) {
	colID := chi.URLParam(r, "id")
	var brandID string
	if err := s.db.Pool.QueryRow(r.Context(), `SELECT brand_id::text FROM collections WHERE id = $1`, colID).Scan(&brandID); err != nil {
		writeError(w, apperr.NotFound("collection not found"))
		return
	}
	thresholds := map[string]float64{}
	thrRows, err := s.db.Pool.Query(r.Context(), `
		SELECT step, threshold_hours FROM alert_rules WHERE brand_id = $1`, brandID)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	for thrRows.Next() {
		var step string
		var thr float64
		if err := thrRows.Scan(&step, &thr); err != nil {
			thrRows.Close()
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		thresholds[step] = thr
	}
	thrRows.Close()

	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT p.status, COUNT(*) AS cnt,
			COALESCE(AVG(EXTRACT(EPOCH FROM (now() - p.updated_at))/3600), 0) AS avg_hours
		FROM products p
		WHERE p.collection_id = $1 AND p.status <> 'published'
		GROUP BY p.status
		ORDER BY avg_hours DESC`, colID)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		var status string
		var cnt int
		var avg float64
		if err := rows.Scan(&status, &cnt, &avg); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		threshold, ok := thresholds[status]
		if !ok {
			threshold = 48
		}
		if avg < threshold {
			continue
		}
		data = append(data, map[string]any{
			"step":             status,
			"average_hours":    avg,
			"threshold_hours":  threshold,
			"product_count":    cnt,
		})
	}
	writeJSON(w, http.StatusOK, data)
}

func (s *Server) handleCollectionEvents(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, apperr.Internal("streaming unsupported"))
		return
	}
	colID := chi.URLParam(r, "id")
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	ch := s.hub.Subscribe(colID)
	defer s.hub.Unsubscribe(colID, ch)
	s.hub.Publish(colID, "connected", map[string]string{"collection_id": colID})
	ticker := time.NewTicker(25 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-r.Context().Done():
			return
		case msg, ok := <-ch:
			if !ok {
				return
			}
			sseWrite(w, flusher, msg)
		case <-ticker.C:
			_, _ = w.Write([]byte(": ping\n\n"))
			flusher.Flush()
		}
	}
}

func sseWrite(w http.ResponseWriter, flusher http.Flusher, data []byte) {
	_, _ = w.Write([]byte("data: "))
	_, _ = w.Write(data)
	_, _ = w.Write([]byte("\n\n"))
	flusher.Flush()
}

func (s *Server) handleCreateAlertRule(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Step           string  `json:"step"`
		ThresholdHours float64 `json:"threshold_hours"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	brandID := chi.URLParam(r, "id")
	var id string
	err := s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO alert_rules (brand_id, step, threshold_hours) VALUES ($1,$2,$3) RETURNING id::text`,
		brandID, body.Step, body.ThresholdHours).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"id": id, "brand_id": brandID, "step": body.Step, "threshold_hours": body.ThresholdHours})
}

func (s *Server) handleListAlertRules(w http.ResponseWriter, r *http.Request) {
	brandID := chi.URLParam(r, "id")
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, brand_id::text, step, threshold_hours, created_at, updated_at
		FROM alert_rules WHERE brand_id = $1`, brandID)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	var data []map[string]any
	for rows.Next() {
		var id, bid, step string
		var thr float64
		var created, updated time.Time
		if err := rows.Scan(&id, &bid, &step, &thr, &created, &updated); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{"id": id, "brand_id": bid, "step": step, "threshold_hours": thr, "created_at": created, "updated_at": updated})
	}
	if data == nil {
		data = []map[string]any{}
	}
	writePage(w, data, len(data), 1)
}

func (s *Server) handleGetProduct(w http.ResponseWriter, r *http.Request) {
	p, err := s.db.GetProduct(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, apperr.NotFound("product not found"))
		return
	}
	out := productToMap(p)
	assetRows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, product_id::text, variant_id::text, type, origin, image_role, file_url,
			generation_provider, qc_status, created_at
		FROM assets WHERE product_id = $1 ORDER BY created_at DESC`, p.ID)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer assetRows.Close()
	assets := make([]map[string]any, 0)
	for assetRows.Next() {
		var id, productID, typ, origin, imageRole, fileURL, qcStatus string
		var variantID, provider *string
		var created time.Time
		if err := assetRows.Scan(&id, &productID, &variantID, &typ, &origin, &imageRole, &fileURL, &provider, &qcStatus, &created); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		assets = append(assets, map[string]any{
			"id": id, "product_id": productID, "variant_id": variantID, "type": typ,
			"origin": origin, "image_role": imageRole, "file_url": fileURL, "generation_provider": provider,
			"qc_status": qcStatus, "created_at": created,
		})
	}
	out["assets"] = assets
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) handlePatchProduct(w http.ResponseWriter, r *http.Request) {
	m := membershipFrom(r.Context())
	role := permissions.Role(m.Role)
	if !permissions.Has(role, permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	p, err := s.db.GetProduct(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, apperr.NotFound("product not found"))
		return
	}
	userTeam := ""
	if m.Team != nil {
		userTeam = *m.Team
	}
	resourceTeam := ""
	if p.AssignedTeam != nil {
		resourceTeam = *p.AssignedTeam
	}
	if !permissions.CanActOnTeam(role, permissions.PermEditStructuredData, userTeam, resourceTeam) {
		writeError(w, apperr.Forbidden("not your team's step"))
		return
	}
	var body map[string]any
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	fields := map[string]any{}
	if v, ok := body["structured_data"]; ok {
		fields["structured_data"] = db.MustJSON(v)
	}
	if v, ok := body["seo"]; ok {
		fields["seo"] = db.MustJSON(v)
	}
	if v, ok := body["translations"]; ok {
		fields["translations"] = db.MustJSON(v)
	}
	if v, ok := body["category"].(string); ok {
		fields["category"] = v
	}
	if v, ok := body["assigned_team"].(string); ok {
		fields["assigned_team"] = v
	}
	if err := s.db.UpdateProduct(r.Context(), s.db.Pool, p.ID, fields); err != nil {
		writeError(w, apperr.Internal("update failed"))
		return
	}
	uid := userIDFrom(r.Context()).String()
	brandID, _ := r.Context().Value(ctxBrandID).(string)
	_ = s.db.InsertAudit(r.Context(), s.db.Pool, &uid, &brandID, "product", p.ID, "update", db.MustJSON(body))
	updated, _ := s.db.GetProduct(r.Context(), p.ID)
	col, _ := s.db.GetCollection(r.Context(), updated.CollectionID)
	if col != nil {
		s.hub.Publish(col.ID, "product.updated", productToMap(updated))
	}
	writeJSON(w, http.StatusOK, productToMap(updated))
}

func (s *Server) handleGenerateSEO(w http.ResponseWriter, r *http.Request) {
	m := membershipFrom(r.Context())
	if !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	productID := chi.URLParam(r, "id")
	if err := s.jobs.EnqueueGenerateSEO(r.Context(), productID); err != nil {
		writeError(w, apperr.Internal("enqueue failed"))
		return
	}
	jobID, _ := s.db.CreateJobRecord(r.Context(), s.db.Pool, "generate_seo", "queued", "product", &productID)
	writeJSON(w, http.StatusAccepted, map[string]any{"job_id": jobID, "status": "queued"})
}

func (s *Server) handleAdvanceStep(w http.ResponseWriter, r *http.Request) {
	m := membershipFrom(r.Context())
	role := permissions.Role(m.Role)
	if !permissions.Has(role, permissions.PermAdvanceStep) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	p, err := s.db.GetProduct(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, apperr.NotFound("product not found"))
		return
	}
	userTeam := ""
	if m.Team != nil {
		userTeam = *m.Team
	}
	resourceTeam := ""
	if p.AssignedTeam != nil {
		resourceTeam = *p.AssignedTeam
	}
	if !permissions.CanActOnTeam(role, permissions.PermAdvanceStep, userTeam, resourceTeam) {
		writeError(w, apperr.Forbidden("not your team's step"))
		return
	}
	var body struct {
		To            string `json:"to"`
		AdminOverride bool   `json:"admin_override"`
	}
	_ = decodeJSON(r, &body)
	target, err := domain.ResolveTarget(p.Status, body.To)
	if err != nil {
		writeError(w, err)
		return
	}
	qcPass, err := s.db.AssetsAllQCPass(r.Context(), p.ID)
	if err != nil {
		writeError(w, apperr.Internal("qc check failed"))
		return
	}
	override := body.AdminOverride && permissions.Has(role, permissions.PermOverrideQC)
	if err := domain.ValidateAdvance(p.Status, target, domain.AdvanceOptions{QCAllPass: qcPass, AdminOverride: override}); err != nil {
		writeError(w, err)
		return
	}
	uid := userIDFrom(r.Context()).String()
	brandID, _ := r.Context().Value(ctxBrandID).(string)
	err = s.db.WithTx(r.Context(), func(tx pgx.Tx) error {
		if err := s.db.UpdateProduct(r.Context(), tx, p.ID, map[string]any{"status": target}); err != nil {
			return err
		}
		detail := map[string]any{"from": p.Status, "to": target, "admin_override": override}
		if err := s.db.InsertAudit(r.Context(), tx, &uid, &brandID, "product", p.ID, "advance_step", db.MustJSON(detail)); err != nil {
			return err
		}
		if target == domain.StepPublished {
			return s.publishProductShopify(r, tx, p)
		}
		return nil
	})
	if err != nil {
		if ae, ok := err.(*apperr.Error); ok {
			writeError(w, ae)
			return
		}
		writeError(w, apperr.Internal("advance failed: "+err.Error()))
		return
	}
	updated, _ := s.db.GetProduct(r.Context(), p.ID)
	col, _ := s.db.GetCollection(r.Context(), updated.CollectionID)
	if col != nil {
		s.hub.Publish(col.ID, "product.advanced", productToMap(updated))
	}
	writeJSON(w, http.StatusOK, productToMap(updated))
}

func (s *Server) publishProductShopify(r *http.Request, tx pgx.Tx, p *db.Product) error {
	var structured, seo, translations map[string]any
	_ = json.Unmarshal(p.StructuredData, &structured)
	_ = json.Unmarshal(p.SEO, &seo)
	_ = json.Unmarshal(p.Translations, &translations)
	rows, err := tx.Query(r.Context(), `SELECT sku, color, size, color_normalized FROM variants WHERE product_id = $1`, p.ID)
	if err != nil {
		return err
	}
	defer rows.Close()
	var variants []shopify.VariantInput
	for rows.Next() {
		var sku string
		var color, size, cn *string
		if err := rows.Scan(&sku, &color, &size, &cn); err != nil {
			return err
		}
		variants = append(variants, shopify.VariantInput{SKU: sku, Color: color, Size: size, ColorNormalized: cn})
	}
	payload := shopify.MapProductToShopifyPayload(shopify.ProductInput{
		InternalReference: p.InternalReference,
		Category:          p.Category,
		StructuredData:    structured,
		SEO:               seo,
		Translations:      translations,
		Variants:          variants,
		ShopifyProductID:  p.ShopifyProductID,
	})
	shopifyID := p.ShopifyProductID
	if shopifyID == nil {
		id := "shopify-stub-" + p.ID
		shopifyID = &id
		if err := s.db.UpdateProduct(r.Context(), tx, p.ID, map[string]any{"shopify_product_id": *shopifyID}); err != nil {
			return err
		}
	}
	uid := userIDFrom(r.Context()).String()
	brandID, _ := r.Context().Value(ctxBrandID).(string)
	return s.db.InsertAudit(r.Context(), tx, &uid, &brandID, "product", p.ID, "publish_shopify", db.MustJSON(payload))
}

func (s *Server) handlePublishShopify(w http.ResponseWriter, r *http.Request) {
	m := membershipFrom(r.Context())
	if !permissions.Has(permissions.Role(m.Role), permissions.PermPublishShopify) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	p, err := s.db.GetProduct(r.Context(), chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, apperr.NotFound("product not found"))
		return
	}
	qcPass, err := s.db.AssetsAllQCPass(r.Context(), p.ID)
	if err != nil {
		writeError(w, apperr.Internal("qc check failed"))
		return
	}
	if !qcPass {
		writeError(w, apperr.QCRequired())
		return
	}
	err = s.db.WithTx(r.Context(), func(tx pgx.Tx) error {
		if p.Status != domain.StepPublished {
			if err := s.db.UpdateProduct(r.Context(), tx, p.ID, map[string]any{"status": domain.StepPublished}); err != nil {
				return err
			}
		}
		return s.publishProductShopify(r, tx, p)
	})
	if err != nil {
		writeError(w, apperr.Internal("publish failed"))
		return
	}
	updated, _ := s.db.GetProduct(r.Context(), p.ID)
	writeJSON(w, http.StatusOK, productToMap(updated))
}

func (s *Server) handleExportProduct(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Channel string `json:"channel"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if body.Channel == "" {
		body.Channel = "shopify"
	}
	productID := chi.URLParam(r, "id")
	if err := s.jobs.EnqueueExport(r.Context(), productID, body.Channel); err != nil {
		writeError(w, apperr.Internal("enqueue failed"))
		return
	}
	jobID, _ := s.db.CreateJobRecord(r.Context(), s.db.Pool, "export", "queued", "product", &productID)
	writeJSON(w, http.StatusAccepted, map[string]any{"job_id": jobID, "status": "queued", "channel": body.Channel})
}
