DROP TABLE IF EXISTS avatar_studio_versions CASCADE;
DROP TABLE IF EXISTS avatar_studio_sessions CASCADE;

ALTER TABLE generation_requests DROP COLUMN IF EXISTS background_prompt;
ALTER TABLE generation_requests DROP COLUMN IF EXISTS pose_prompt;
ALTER TABLE generation_requests DROP COLUMN IF EXISTS garment_prompt;
ALTER TABLE generation_requests DROP COLUMN IF EXISTS background_reference_id;
ALTER TABLE generation_requests DROP COLUMN IF EXISTS model_reference_id;
ALTER TABLE generation_requests DROP COLUMN IF EXISTS reference_asset_ids;
ALTER TABLE generation_requests DROP COLUMN IF EXISTS raw_asset_id;
ALTER TABLE generation_requests DROP COLUMN IF EXISTS source_final_asset_id;
ALTER TABLE generation_requests DROP COLUMN IF EXISTS parent_request_id;

ALTER TABLE pose_references DROP COLUMN IF EXISTS prompt_text;

DROP TABLE IF EXISTS reference_library_items CASCADE;

ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_image_role_check;
DROP INDEX IF EXISTS assets_product_id_image_role_idx;
ALTER TABLE assets DROP COLUMN IF EXISTS image_role;
