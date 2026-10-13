package db

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

func (d *DB) GetBrand(ctx context.Context, id string) (*Brand, error) {
	row := d.Pool.QueryRow(ctx, `
		SELECT id::text, name, taxonomy_schema, translation_glossary,
			shopify_store_domain, shopify_access_token_encrypted,
			shopify_live_store_domain, shopify_live_access_token_encrypted,
			shopify_environment, qc_pass_threshold, qc_fail_threshold, qc_check_floor,
			created_at, updated_at
		FROM brands WHERE id = $1`, id)
	var b Brand
	if err := row.Scan(
		&b.ID, &b.Name, &b.TaxonomySchema, &b.TranslationGlossary,
		&b.ShopifyStoreDomain, &b.ShopifyAccessTokenEncrypted,
		&b.ShopifyLiveStoreDomain, &b.ShopifyLiveAccessTokenEncrypted,
		&b.ShopifyEnvironment, &b.QCPassThreshold, &b.QCFailThreshold, &b.QCCheckFloor,
		&b.CreatedAt, &b.UpdatedAt,
	); err != nil {
		return nil, err
	}
	return &b, nil
}

func (d *DB) PatchBrand(ctx context.Context, id string, fields map[string]any) (*Brand, error) {
	if len(fields) == 0 {
		return d.GetBrand(ctx, id)
	}
	sets := make([]string, 0, len(fields)+1)
	args := make([]any, 0, len(fields)+1)
	i := 1
	for k, v := range fields {
		sets = append(sets, fmt.Sprintf("%s = $%d", k, i))
		args = append(args, v)
		i++
	}
	sets = append(sets, "updated_at = now()")
	args = append(args, id)
	query := fmt.Sprintf(`UPDATE brands SET %s WHERE id = $%d`, strings.Join(sets, ", "), i)
	if _, err := d.Pool.Exec(ctx, query, args...); err != nil {
		return nil, err
	}
	return d.GetBrand(ctx, id)
}

func (d *DB) GetCollection(ctx context.Context, id string) (*Collection, error) {
	row := d.Pool.QueryRow(ctx, `
		SELECT id::text, brand_id::text, name, sample_arrival_date, must_ship_date, sale_date, created_at, updated_at
		FROM collections WHERE id = $1`, id)
	var c Collection
	if err := row.Scan(&c.ID, &c.BrandID, &c.Name, &c.SampleArrivalDate, &c.MustShipDate, &c.SaleDate, &c.CreatedAt, &c.UpdatedAt); err != nil {
		return nil, err
	}
	return &c, nil
}

func (d *DB) ListCollectionsByBrand(ctx context.Context, brandID string, p Pagination) ([]Collection, int, error) {
	var total int
	if err := d.Pool.QueryRow(ctx, `SELECT COUNT(*) FROM collections WHERE brand_id = $1`, brandID).Scan(&total); err != nil {
		return nil, 0, err
	}
	rows, err := d.Pool.Query(ctx, `
		SELECT id::text, brand_id::text, name, sample_arrival_date, must_ship_date, sale_date, created_at, updated_at
		FROM collections
		WHERE brand_id = $1
		ORDER BY created_at DESC
		LIMIT $2 OFFSET $3`, brandID, p.PageSize, p.Offset())
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	out := make([]Collection, 0)
	for rows.Next() {
		var c Collection
		if err := rows.Scan(&c.ID, &c.BrandID, &c.Name, &c.SampleArrivalDate, &c.MustShipDate, &c.SaleDate, &c.CreatedAt, &c.UpdatedAt); err != nil {
			return nil, 0, err
		}
		out = append(out, c)
	}
	return out, total, rows.Err()
}

func (d *DB) ListCollectionProducts(ctx context.Context, collectionID, step, team string, p Pagination) ([]Product, int, error) {
	where := []string{"collection_id = $1"}
	args := []any{collectionID}
	i := 2
	if step != "" {
		where = append(where, fmt.Sprintf("status = $%d", i))
		args = append(args, step)
		i++
	}
	if team != "" {
		where = append(where, fmt.Sprintf("assigned_team = $%d", i))
		args = append(args, team)
		i++
	}
	w := strings.Join(where, " AND ")
	var total int
	if err := d.Pool.QueryRow(ctx, `SELECT COUNT(*) FROM products WHERE `+w, args...).Scan(&total); err != nil {
		return nil, 0, err
	}
	args = append(args, p.PageSize, p.Offset())
	rows, err := d.Pool.Query(ctx, `
		SELECT id::text, collection_id::text, internal_reference, category, status,
			structured_data, extraction_confidence, seo, translations, assigned_team,
			shopify_product_id, created_at, updated_at
		FROM products WHERE `+w+`
		ORDER BY updated_at DESC
		LIMIT $`+fmt.Sprintf("%d", i)+` OFFSET $`+fmt.Sprintf("%d", i+1), args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	var out []Product
	for rows.Next() {
		var pr Product
		if err := rows.Scan(
			&pr.ID, &pr.CollectionID, &pr.InternalReference, &pr.Category, &pr.Status,
			&pr.StructuredData, &pr.ExtractionConfidence, &pr.SEO, &pr.Translations, &pr.AssignedTeam,
			&pr.ShopifyProductID, &pr.CreatedAt, &pr.UpdatedAt,
		); err != nil {
			return nil, 0, err
		}
		out = append(out, pr)
	}
	return out, total, rows.Err()
}

func (d *DB) GetProduct(ctx context.Context, id string) (*Product, error) {
	row := d.Pool.QueryRow(ctx, `
		SELECT id::text, collection_id::text, internal_reference, category, status,
			structured_data, extraction_confidence, seo, translations, assigned_team,
			shopify_product_id, created_at, updated_at
		FROM products WHERE id = $1`, id)
	var pr Product
	if err := row.Scan(
		&pr.ID, &pr.CollectionID, &pr.InternalReference, &pr.Category, &pr.Status,
		&pr.StructuredData, &pr.ExtractionConfidence, &pr.SEO, &pr.Translations, &pr.AssignedTeam,
		&pr.ShopifyProductID, &pr.CreatedAt, &pr.UpdatedAt,
	); err != nil {
		return nil, err
	}
	return &pr, nil
}

func (d *DB) UpdateProduct(ctx context.Context, q Querier, id string, fields map[string]any) error {
	if len(fields) == 0 {
		return nil
	}
	sets := make([]string, 0, len(fields)+1)
	args := make([]any, 0, len(fields)+1)
	i := 1
	for k, v := range fields {
		sets = append(sets, fmt.Sprintf("%s = $%d", k, i))
		args = append(args, v)
		i++
	}
	sets = append(sets, "updated_at = now()")
	args = append(args, id)
	_, err := q.Exec(ctx, fmt.Sprintf(`UPDATE products SET %s WHERE id = $%d`, strings.Join(sets, ", "), i), args...)
	return err
}

func (d *DB) ProductBrandID(ctx context.Context, productID string) (string, error) {
	var brandID string
	err := d.Pool.QueryRow(ctx, `
		SELECT c.brand_id::text FROM products p
		JOIN collections c ON c.id = p.collection_id
		WHERE p.id = $1`, productID).Scan(&brandID)
	return brandID, err
}

func (d *DB) AssetsAllQCPass(ctx context.Context, productID string) (bool, error) {
	var total, passed int
	err := d.Pool.QueryRow(ctx, `
		SELECT COUNT(*), COUNT(*) FILTER (WHERE qc_status = 'pass')
		FROM assets WHERE product_id = $1`, productID).Scan(&total, &passed)
	if err != nil {
		return false, err
	}
	if total == 0 {
		return true, nil
	}
	return total == passed, nil
}

func (d *DB) GetAsset(ctx context.Context, id string) (*Asset, error) {
	row := d.Pool.QueryRow(ctx, `
		SELECT id::text, product_id::text, variant_id::text, type, origin, image_role, file_url,
			generation_provider, qc_status, created_at
		FROM assets WHERE id = $1`, id)
	var a Asset
	if err := row.Scan(&a.ID, &a.ProductID, &a.VariantID, &a.Type, &a.Origin, &a.ImageRole, &a.FileURL, &a.GenerationProvider, &a.QCStatus, &a.CreatedAt); err != nil {
		return nil, err
	}
	return &a, nil
}

func (d *DB) CreateAsset(ctx context.Context, productID string, variantID *string, typ, origin, imageRole, fileURL string, provider *string) (*Asset, error) {
	if imageRole == "" {
		imageRole = "raw"
	}
	row := d.Pool.QueryRow(ctx, `
		INSERT INTO assets (product_id, variant_id, type, origin, image_role, file_url, generation_provider)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
		RETURNING id::text, product_id::text, variant_id::text, type, origin, image_role, file_url, generation_provider, qc_status, created_at`,
		productID, variantID, typ, origin, imageRole, fileURL, provider)
	var a Asset
	if err := row.Scan(&a.ID, &a.ProductID, &a.VariantID, &a.Type, &a.Origin, &a.ImageRole, &a.FileURL, &a.GenerationProvider, &a.QCStatus, &a.CreatedAt); err != nil {
		return nil, err
	}
	return &a, nil
}

func (d *DB) UpdateAssetQCStatus(ctx context.Context, q Querier, assetID, status string) error {
	_, err := q.Exec(ctx, `UPDATE assets SET qc_status = $2 WHERE id = $1`, assetID, status)
	return err
}

func (d *DB) CreateJobRecord(ctx context.Context, q Querier, jobType, status, entityType string, entityID *string) (string, error) {
	var id string
	err := q.QueryRow(ctx, `
		INSERT INTO job_records (job_type, status, related_entity_type, related_entity_id)
		VALUES ($1, $2, $3, $4) RETURNING id::text`, jobType, status, entityType, entityID).Scan(&id)
	return id, err
}

func (d *DB) UpdateJobRecord(ctx context.Context, q Querier, id, status string, errDetail *string, attempts *int) error {
	_, err := q.Exec(ctx, `
		UPDATE job_records SET status = $2, error_detail = COALESCE($3, error_detail),
			attempts = COALESCE($4, attempts), updated_at = now()
		WHERE id = $1`, id, status, errDetail, attempts)
	return err
}

func (d *DB) GetJobRecord(ctx context.Context, id string) (map[string]any, error) {
	row := d.Pool.QueryRow(ctx, `
		SELECT id::text, job_type, status, related_entity_type, related_entity_id::text,
			error_detail, attempts, created_at, updated_at
		FROM job_records WHERE id = $1`, id)
	var (
		jid, jobType, status string
		relType, relID, errD *string
		attempts             int
		created, updated     time.Time
	)
	if err := row.Scan(&jid, &jobType, &status, &relType, &relID, &errD, &attempts, &created, &updated); err != nil {
		return nil, err
	}
	return map[string]any{
		"id":                  jid,
		"job_type":            jobType,
		"status":              status,
		"related_entity_type": relType,
		"related_entity_id":   relID,
		"error_detail":        errD,
		"attempts":            attempts,
		"created_at":          created,
		"updated_at":          updated,
	}, nil
}

func (d *DB) ListFailedJobs(ctx context.Context, p Pagination) ([]map[string]any, int, error) {
	var total int
	if err := d.Pool.QueryRow(ctx, `SELECT COUNT(*) FROM job_records WHERE status = 'failed'`).Scan(&total); err != nil {
		return nil, 0, err
	}
	rows, err := d.Pool.Query(ctx, `
		SELECT id::text, job_type, status, related_entity_type, related_entity_id::text,
			error_detail, attempts, created_at, updated_at
		FROM job_records WHERE status = 'failed'
		ORDER BY updated_at DESC
		LIMIT $1 OFFSET $2`, p.PageSize, p.Offset())
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	var out []map[string]any
	for rows.Next() {
		var (
			jid, jobType, status string
			relType, relID, errD *string
			attempts             int
			created, updated     time.Time
		)
		if err := rows.Scan(&jid, &jobType, &status, &relType, &relID, &errD, &attempts, &created, &updated); err != nil {
			return nil, 0, err
		}
		out = append(out, map[string]any{
			"id": jid, "job_type": jobType, "status": status,
			"related_entity_type": relType, "related_entity_id": relID,
			"error_detail": errD, "attempts": attempts,
			"created_at": created, "updated_at": updated,
		})
	}
	return out, total, rows.Err()
}

func MustJSON(v any) []byte {
	b, err := json.Marshal(v)
	if err != nil {
		return []byte("{}")
	}
	return b
}

func NullIfEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func TxOrPool(d *DB, tx pgx.Tx) Querier {
	if tx != nil {
		return tx
	}
	return d.Pool
}
