package jobs

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/gathered/kitframe/apps/api/internal/ai"
	"github.com/gathered/kitframe/apps/api/internal/db"
	"github.com/gathered/kitframe/apps/api/internal/storage"
	"github.com/jackc/pgx/v5"
	"github.com/riverqueue/river"
	"github.com/riverqueue/river/riverdriver/riverpgxv5"
)

type ExtractArgs struct {
	SourceDocumentID string `json:"source_document_id"`
}

func (ExtractArgs) Kind() string { return "extract" }

type QCArgs struct {
	AssetID          string `json:"asset_id"`
	GoldenSetImageID string `json:"golden_set_image_id"`
}

func (QCArgs) Kind() string { return "qc" }

type GenerateArgs struct {
	GenerationRequestID string `json:"generation_request_id"`
}

func (GenerateArgs) Kind() string { return "generate" }

type GenerateSEOArgs struct {
	ProductID string `json:"product_id"`
}

func (GenerateSEOArgs) Kind() string { return "generate_seo" }

type TrainAvatarArgs struct {
	AvatarID string `json:"avatar_id"`
}

func (TrainAvatarArgs) Kind() string { return "train_avatar" }

type ExportArgs struct {
	ProductID string `json:"product_id"`
	Channel   string `json:"channel"`
}

func (ExportArgs) Kind() string { return "export" }

type NotifyDigestArgs struct {
	Frequency string `json:"frequency"`
}

func (NotifyDigestArgs) Kind() string { return "notify_digest" }

type ShopifyReconcileArgs struct {
	BrandID string `json:"brand_id"`
}

func (ShopifyReconcileArgs) Kind() string { return "shopify_reconcile" }

type Workers struct {
	DB    *db.DB
	AI    *ai.Client
	Store *storage.Store
}

type Enqueuer struct {
	Client *river.Client[pgx.Tx]
}

func (e *Enqueuer) EnqueueExtract(ctx context.Context, sourceDocumentID string) error {
	_, err := e.Client.Insert(ctx, ExtractArgs{SourceDocumentID: sourceDocumentID}, nil)
	return err
}

func (e *Enqueuer) EnqueueQC(ctx context.Context, assetID, goldenSetImageID string) error {
	_, err := e.Client.Insert(ctx, QCArgs{AssetID: assetID, GoldenSetImageID: goldenSetImageID}, nil)
	return err
}

func (e *Enqueuer) EnqueueGenerate(ctx context.Context, generationRequestID string) error {
	_, err := e.Client.Insert(ctx, GenerateArgs{GenerationRequestID: generationRequestID}, nil)
	return err
}

func (e *Enqueuer) EnqueueGenerateSEO(ctx context.Context, productID string) error {
	_, err := e.Client.Insert(ctx, GenerateSEOArgs{ProductID: productID}, nil)
	return err
}

func (e *Enqueuer) EnqueueTrainAvatar(ctx context.Context, avatarID string) error {
	_, err := e.Client.Insert(ctx, TrainAvatarArgs{AvatarID: avatarID}, nil)
	return err
}

func (e *Enqueuer) EnqueueExport(ctx context.Context, productID, channel string) error {
	_, err := e.Client.Insert(ctx, ExportArgs{ProductID: productID, Channel: channel}, nil)
	return err
}

type ExtractWorker struct {
	river.WorkerDefaults[ExtractArgs]
	W *Workers
}

func (w *ExtractWorker) Work(ctx context.Context, job *river.Job[ExtractArgs]) error {
	var fileURL string
	var productID *string
	err := w.W.DB.Pool.QueryRow(ctx, `SELECT file_url, product_id::text FROM source_documents WHERE id = $1`, job.Args.SourceDocumentID).Scan(&fileURL, &productID)
	if err != nil {
		return err
	}
	taxonomy := map[string]any{}
	if productID != nil {
		brandID, err := w.W.DB.ProductBrandID(ctx, *productID)
		if err == nil {
			b, err := w.W.DB.GetBrand(ctx, brandID)
			if err == nil {
				_ = json.Unmarshal(b.TaxonomySchema, &taxonomy)
			}
		}
	}
	result, err := w.W.AI.Extract(ctx, fileURL, taxonomy)
	status := "extracted"
	if err != nil {
		_, _ = w.W.DB.Pool.Exec(ctx, `UPDATE source_documents SET extraction_status = 'failed' WHERE id = $1`, job.Args.SourceDocumentID)
		return err
	}
	if needs, ok := result["needs_review_fields"].([]any); ok && len(needs) > 0 {
		status = "needs_review"
	}
	_, err = w.W.DB.Pool.Exec(ctx, `
		UPDATE source_documents SET extraction_status = $2, raw_extraction = $3 WHERE id = $1`,
		job.Args.SourceDocumentID, status, db.MustJSON(result))
	if err != nil {
		return err
	}
	if productID != nil {
		if fields, ok := result["fields"].(map[string]any); ok {
			structured := map[string]any{}
			confidence := map[string]any{}
			for k, v := range fields {
				if m, ok := v.(map[string]any); ok {
					structured[k] = m["value"]
					confidence[k] = m["confidence"]
				}
			}
			_ = w.W.DB.UpdateProduct(ctx, w.W.DB.Pool, *productID, map[string]any{
				"structured_data":       db.MustJSON(structured),
				"extraction_confidence": db.MustJSON(confidence),
			})
		}
	}
	return nil
}

type QCWorker struct {
	river.WorkerDefaults[QCArgs]
	W *Workers
}

func (w *QCWorker) Work(ctx context.Context, job *river.Job[QCArgs]) error {
	a, err := w.W.DB.GetAsset(ctx, job.Args.AssetID)
	if err != nil {
		return err
	}
	result, err := w.W.AI.QCScore(ctx, a.FileURL, job.Args.GoldenSetImageID)
	if err != nil {
		return err
	}
	overall, _ := result["overall_score"].(float64)
	res, _ := result["result"].(string)
	if res == "" {
		res = "needs_review"
	}
	color, _ := result["color_score"].(float64)
	logo, _ := result["logo_position_score"].(float64)
	reso, _ := result["resolution_score"].(float64)
	var goldenID *string
	if job.Args.GoldenSetImageID != "" {
		goldenID = &job.Args.GoldenSetImageID
	}
	_, err = w.W.DB.Pool.Exec(ctx, `
		INSERT INTO qc_runs (asset_id, golden_set_image_id, color_score, logo_position_score, resolution_score, overall_score, result, raw_output)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
		job.Args.AssetID, goldenID, color, logo, reso, overall, res, db.MustJSON(result))
	if err != nil {
		return err
	}
	return w.W.DB.UpdateAssetQCStatus(ctx, w.W.DB.Pool, job.Args.AssetID, res)
}

type GenerateWorker struct {
	river.WorkerDefaults[GenerateArgs]
	W *Workers
}

func (w *GenerateWorker) Work(ctx context.Context, job *river.Job[GenerateArgs]) error {
	var status string
	var productID string
	var avatarID, poseID, rightsID, scene, provider *string
	var garmentPrompt, posePrompt, backgroundPrompt *string
	var rawAssetID, sourceFinalAssetID, modelRefID, bgRefID *string
	var referenceAssetIDs []byte
	err := w.W.DB.Pool.QueryRow(ctx, `
		SELECT status, product_id::text, avatar_id::text, pose_reference_id::text, rights_record_id::text,
			scene_description, provider, garment_prompt, pose_prompt, background_prompt,
			raw_asset_id::text, reference_asset_ids, model_reference_id::text, background_reference_id::text,
			source_final_asset_id::text
		FROM generation_requests WHERE id = $1`, job.Args.GenerationRequestID).Scan(
		&status, &productID, &avatarID, &poseID, &rightsID, &scene, &provider,
		&garmentPrompt, &posePrompt, &backgroundPrompt, &rawAssetID, &referenceAssetIDs,
		&modelRefID, &bgRefID, &sourceFinalAssetID)
	if err != nil {
		return err
	}
	if status == "blocked_rights" {
		return nil
	}
	if avatarID != nil {
		if rightsID == nil {
			_, _ = w.W.DB.Pool.Exec(ctx, `UPDATE generation_requests SET status = 'blocked_rights' WHERE id = $1`, job.Args.GenerationRequestID)
			return nil
		}
		var rs string
		if err := w.W.DB.Pool.QueryRow(ctx, `SELECT status FROM rights_records WHERE id = $1`, *rightsID).Scan(&rs); err != nil || rs != "cleared" {
			_, _ = w.W.DB.Pool.Exec(ctx, `UPDATE generation_requests SET status = 'blocked_rights' WHERE id = $1`, job.Args.GenerationRequestID)
			return nil
		}
	}
	_, _ = w.W.DB.Pool.Exec(ctx, `UPDATE generation_requests SET status = 'running' WHERE id = $1`, job.Args.GenerationRequestID)
	prov := "mock"
	if provider != nil && *provider != "" && *provider != "default" {
		prov = *provider
	}

	garmentURL := ""
	if sourceFinalAssetID != nil {
		_ = w.W.DB.Pool.QueryRow(ctx, `SELECT file_url FROM assets WHERE id = $1`, *sourceFinalAssetID).Scan(&garmentURL)
	} else if rawAssetID != nil {
		_ = w.W.DB.Pool.QueryRow(ctx, `SELECT file_url FROM assets WHERE id = $1`, *rawAssetID).Scan(&garmentURL)
	}
	if garmentURL == "" {
		garmentURL = w.firstAssetURLByRole(ctx, productID, "raw")
	}

	refs := w.parseReferenceURLs(ctx, referenceAssetIDs)
	if len(refs) == 0 {
		refs = w.assetURLsByRole(ctx, productID, "reference")
	}
	if modelRefID != nil {
		var url, prompt string
		if err := w.W.DB.Pool.QueryRow(ctx, `SELECT file_url, prompt_text FROM reference_library_items WHERE id = $1`, *modelRefID).Scan(&url, &prompt); err == nil && url != "" {
			refs = append(refs, url)
		}
	}
	if bgRefID != nil {
		var url, prompt string
		if err := w.W.DB.Pool.QueryRow(ctx, `SELECT file_url, prompt_text FROM reference_library_items WHERE id = $1`, *bgRefID).Scan(&url, &prompt); err == nil {
			if backgroundPrompt == nil && prompt != "" {
				backgroundPrompt = &prompt
			}
			if url != "" {
				refs = append(refs, url)
			}
		}
	}

	sceneParts := make([]string, 0, 4)
	if garmentPrompt != nil && *garmentPrompt != "" {
		sceneParts = append(sceneParts, *garmentPrompt)
	}
	if scene != nil && *scene != "" {
		sceneParts = append(sceneParts, *scene)
	}
	if posePrompt != nil && *posePrompt != "" {
		sceneParts = append(sceneParts, "pose: "+*posePrompt)
	}
	if backgroundPrompt != nil && *backgroundPrompt != "" {
		sceneParts = append(sceneParts, "background: "+*backgroundPrompt)
	}
	sceneStr := strings.Join(sceneParts, ". ")
	if sceneStr == "" {
		sceneStr = "studio product look, clean lighting, fashion ecommerce"
	}

	body := map[string]any{
		"provider":         prov,
		"reference_assets": refs,
		"prompt": map[string]any{
			"garment_asset_url": garmentURL,
			"scene_description": sceneStr,
			"output_type":       "image",
		},
	}
	if avatarID != nil {
		var identity *string
		_ = w.W.DB.Pool.QueryRow(ctx, `SELECT identity_profile_ref FROM avatars WHERE id = $1`, *avatarID).Scan(&identity)
		if identity != nil {
			body["avatar_identity_ref"] = *identity
		}
	}
	if poseID != nil {
		var skeleton, prompt string
		_ = w.W.DB.Pool.QueryRow(ctx, `SELECT skeleton_data_url, prompt_text FROM pose_references WHERE id = $1`, *poseID).Scan(&skeleton, &prompt)
		if skeleton != "" {
			body["pose_skeleton_url"] = skeleton
		}
		if posePrompt == nil && prompt != "" {
			sceneStr = sceneStr + ". pose: " + prompt
			body["prompt"].(map[string]any)["scene_description"] = sceneStr
		}
	}
	out, err := w.W.AI.GenerateImage(ctx, body)
	if err != nil {
		_, _ = w.W.DB.Pool.Exec(ctx, `UPDATE generation_requests SET status = 'failed', completed_at = now() WHERE id = $1`, job.Args.GenerationRequestID)
		return err
	}
	url, _ := out["generated_url"].(string)
	if url == "" {
		_, _ = w.W.DB.Pool.Exec(ctx, `UPDATE generation_requests SET status = 'failed', completed_at = now() WHERE id = $1`, job.Args.GenerationRequestID)
		return fmt.Errorf("empty generated_url")
	}
	url, err = w.persistGeneratedURL(ctx, url, job.Args.GenerationRequestID+".png")
	if err != nil {
		_, _ = w.W.DB.Pool.Exec(ctx, `UPDATE generation_requests SET status = 'failed', completed_at = now() WHERE id = $1`, job.Args.GenerationRequestID)
		return err
	}
	usedProvider, _ := out["provider_used"].(string)
	if usedProvider == "" {
		usedProvider = prov
	}
	a, err := w.W.DB.CreateAsset(ctx, productID, nil, "model", "generated", "final", url, &usedProvider)
	if err != nil {
		return err
	}
	_, err = w.W.DB.Pool.Exec(ctx, `
		UPDATE generation_requests SET status = 'completed', result_asset_id = $2, completed_at = now() WHERE id = $1`,
		job.Args.GenerationRequestID, a.ID)
	if err != nil {
		return err
	}
	_, _ = w.W.DB.Pool.Exec(ctx, `
		UPDATE avatar_studio_versions SET result_asset_id = $2
		WHERE generation_request_id = $1`, job.Args.GenerationRequestID, a.ID)
	_, _ = w.W.DB.Pool.Exec(ctx, `
		UPDATE avatar_studio_sessions SET active_version_id = v.id, updated_at = now()
		FROM avatar_studio_versions v
		WHERE v.generation_request_id = $1 AND avatar_studio_sessions.id = v.session_id`,
		job.Args.GenerationRequestID)
	return nil
}

func (w *GenerateWorker) parseReferenceURLs(ctx context.Context, raw []byte) []string {
	var ids []string
	_ = json.Unmarshal(raw, &ids)
	out := make([]string, 0, len(ids))
	for _, id := range ids {
		var url string
		if err := w.W.DB.Pool.QueryRow(ctx, `SELECT file_url FROM assets WHERE id = $1`, id).Scan(&url); err == nil && url != "" {
			out = append(out, url)
		}
	}
	return out
}

func (w *GenerateWorker) firstAssetURLByRole(ctx context.Context, productID, role string) string {
	var url string
	_ = w.W.DB.Pool.QueryRow(ctx, `
		SELECT file_url FROM assets WHERE product_id = $1 AND image_role = $2
		ORDER BY created_at ASC LIMIT 1`, productID, role).Scan(&url)
	return url
}

func (w *GenerateWorker) assetURLsByRole(ctx context.Context, productID, role string) []string {
	rows, err := w.W.DB.Pool.Query(ctx, `
		SELECT file_url FROM assets WHERE product_id = $1 AND image_role = $2
		ORDER BY created_at ASC LIMIT 12`, productID, role)
	if err != nil {
		return nil
	}
	defer rows.Close()
	out := make([]string, 0)
	for rows.Next() {
		var u string
		if err := rows.Scan(&u); err != nil {
			continue
		}
		if u != "" {
			out = append(out, u)
		}
	}
	return out
}

func (w *GenerateWorker) avatarReferenceURLs(ctx context.Context, avatarID string) []string {
	var refs []byte
	if err := w.W.DB.Pool.QueryRow(ctx, `SELECT reference_asset_urls FROM avatars WHERE id = $1`, avatarID).Scan(&refs); err != nil {
		return nil
	}
	var urls []string
	_ = json.Unmarshal(refs, &urls)
	out := make([]string, 0, len(urls))
	for _, u := range urls {
		if u != "" {
			out = append(out, u)
		}
	}
	return out
}

func (w *GenerateWorker) persistGeneratedURL(ctx context.Context, raw, filename string) (string, error) {
	if w.W.Store == nil {
		return raw, nil
	}
	if strings.HasPrefix(raw, "data:") {
		parts := strings.SplitN(raw, ",", 2)
		if len(parts) != 2 {
			return "", fmt.Errorf("invalid data url")
		}
		meta, payload := parts[0], parts[1]
		var data []byte
		var err error
		if strings.Contains(meta, ";base64") {
			data, err = base64.StdEncoding.DecodeString(payload)
			if err != nil {
				return "", err
			}
		} else {
			data = []byte(payload)
		}
		ct := "image/png"
		if strings.Contains(meta, "image/jpeg") || strings.Contains(meta, "image/jpg") {
			ct = "image/jpeg"
		} else if strings.Contains(meta, "image/webp") {
			ct = "image/webp"
		}
		put, err := w.W.Store.Put(ctx, filename, ct, bytes.NewReader(data), int64(len(data)))
		if err != nil {
			return "", err
		}
		return put.URL, nil
	}
	if strings.HasPrefix(raw, "http://") || strings.HasPrefix(raw, "https://") || strings.HasPrefix(raw, "/v1/uploads/") {
		return raw, nil
	}
	return raw, nil
}

type GenerateSEOWorker struct {
	river.WorkerDefaults[GenerateSEOArgs]
	W *Workers
}

func (w *GenerateSEOWorker) Work(ctx context.Context, job *river.Job[GenerateSEOArgs]) error {
	p, err := w.W.DB.GetProduct(ctx, job.Args.ProductID)
	if err != nil {
		return err
	}
	brandID, err := w.W.DB.ProductBrandID(ctx, p.ID)
	if err != nil {
		return err
	}
	b, err := w.W.DB.GetBrand(ctx, brandID)
	if err != nil {
		return err
	}
	var structured, glossary any
	_ = json.Unmarshal(p.StructuredData, &structured)
	_ = json.Unmarshal(b.TranslationGlossary, &glossary)
	out, err := w.W.AI.GenerateCopy(ctx, structured, []string{"es", "ca", "en"}, glossary)
	if err != nil {
		return err
	}
	return w.W.DB.UpdateProduct(ctx, w.W.DB.Pool, p.ID, map[string]any{
		"seo":          db.MustJSON(out["seo"]),
		"translations": db.MustJSON(out["translations"]),
	})
}

type TrainAvatarWorker struct {
	river.WorkerDefaults[TrainAvatarArgs]
	W *Workers
}

func (w *TrainAvatarWorker) Work(ctx context.Context, job *river.Job[TrainAvatarArgs]) error {
	var refs []byte
	err := w.W.DB.Pool.QueryRow(ctx, `SELECT reference_asset_urls FROM avatars WHERE id = $1`, job.Args.AvatarID).Scan(&refs)
	if err != nil {
		return err
	}
	var urls []string
	_ = json.Unmarshal(refs, &urls)
	out, err := w.W.AI.TrainAvatarIdentity(ctx, urls)
	if err != nil {
		_, _ = w.W.DB.Pool.Exec(ctx, `UPDATE avatars SET status = 'failed' WHERE id = $1`, job.Args.AvatarID)
		return err
	}
	ref, _ := out["identity_profile_ref"].(string)
	_, err = w.W.DB.Pool.Exec(ctx, `UPDATE avatars SET status = 'ready', identity_profile_ref = $2 WHERE id = $1`, job.Args.AvatarID, ref)
	return err
}

type ExportWorker struct {
	river.WorkerDefaults[ExportArgs]
	W *Workers
}

func (w *ExportWorker) Work(ctx context.Context, job *river.Job[ExportArgs]) error {
	slog.Info("export job", "product_id", job.Args.ProductID, "channel", job.Args.Channel)
	return nil
}

type NotifyDigestWorker struct {
	river.WorkerDefaults[NotifyDigestArgs]
	W *Workers
}

func (w *NotifyDigestWorker) Work(ctx context.Context, job *river.Job[NotifyDigestArgs]) error {
	_, err := w.W.DB.Pool.Exec(ctx, `
		UPDATE notifications SET status = 'digested', sent_at = now()
		WHERE status = 'pending'
			AND id IN (
				SELECT n.id FROM notifications n
				JOIN notification_preferences p ON p.user_id = n.user_id AND p.brand_id = n.brand_id AND p.event_type = n.event_type
				WHERE p.frequency = $1
				LIMIT 500
			)`, job.Args.Frequency)
	return err
}

type ShopifyReconcileWorker struct {
	river.WorkerDefaults[ShopifyReconcileArgs]
	W *Workers
}

func (w *ShopifyReconcileWorker) Work(ctx context.Context, job *river.Job[ShopifyReconcileArgs]) error {
	slog.Info("shopify reconcile", "brand_id", job.Args.BrandID)
	return nil
}

func registerWorkers(rw *river.Workers, workers *Workers) {
	river.AddWorker(rw, &ExtractWorker{W: workers})
	river.AddWorker(rw, &QCWorker{W: workers})
	river.AddWorker(rw, &GenerateWorker{W: workers})
	river.AddWorker(rw, &GenerateSEOWorker{W: workers})
	river.AddWorker(rw, &TrainAvatarWorker{W: workers})
	river.AddWorker(rw, &ExportWorker{W: workers})
	river.AddWorker(rw, &NotifyDigestWorker{W: workers})
	river.AddWorker(rw, &ShopifyReconcileWorker{W: workers})
}

func NewAPIClient(database *db.DB, aiClient *ai.Client, store *storage.Store) (*river.Client[pgx.Tx], *Enqueuer, error) {
	workers := &Workers{DB: database, AI: aiClient, Store: store}
	rw := river.NewWorkers()
	registerWorkers(rw, workers)
	client, err := river.NewClient(riverpgxv5.New(database.Pool), &river.Config{
		Workers: rw,
	})
	if err != nil {
		return nil, nil, err
	}
	return client, &Enqueuer{Client: client}, nil
}

func NewWorkerClient(database *db.DB, aiClient *ai.Client, store *storage.Store) (*river.Client[pgx.Tx], *Enqueuer, error) {
	workers := &Workers{DB: database, AI: aiClient, Store: store}
	rw := river.NewWorkers()
	registerWorkers(rw, workers)
	client, err := river.NewClient(riverpgxv5.New(database.Pool), &river.Config{
		Queues: map[string]river.QueueConfig{
			river.QueueDefault: {MaxWorkers: 8},
		},
		Workers: rw,
		PeriodicJobs: []*river.PeriodicJob{
			river.NewPeriodicJob(river.PeriodicInterval(time.Hour), func() (river.JobArgs, *river.InsertOpts) {
				return NotifyDigestArgs{Frequency: "hourly_digest"}, nil
			}, nil),
			river.NewPeriodicJob(river.PeriodicInterval(24*time.Hour), func() (river.JobArgs, *river.InsertOpts) {
				return NotifyDigestArgs{Frequency: "daily_digest"}, nil
			}, nil),
			river.NewPeriodicJob(river.PeriodicInterval(15*time.Minute), func() (river.JobArgs, *river.InsertOpts) {
				return ShopifyReconcileArgs{}, nil
			}, nil),
		},
	})
	if err != nil {
		return nil, nil, err
	}
	return client, &Enqueuer{Client: client}, nil
}
