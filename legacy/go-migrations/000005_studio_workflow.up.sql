ALTER TABLE assets ADD COLUMN IF NOT EXISTS image_role TEXT;

UPDATE assets SET image_role = 'raw'
WHERE image_role IS NULL AND origin = 'real_photo' AND type = 'product_only';

UPDATE assets SET image_role = 'final'
WHERE image_role IS NULL AND origin = 'generated';

UPDATE assets SET image_role = 'reference'
WHERE image_role IS NULL AND origin = 'real_photo' AND type IN ('model', 'social', 'campaign');

UPDATE assets SET image_role = 'raw'
WHERE image_role IS NULL;

ALTER TABLE assets ALTER COLUMN image_role SET DEFAULT 'raw';
ALTER TABLE assets ALTER COLUMN image_role SET NOT NULL;
ALTER TABLE assets ADD CONSTRAINT assets_image_role_check
  CHECK (image_role IN ('raw', 'reference', 'final'));

CREATE INDEX assets_product_id_image_role_idx ON assets (product_id, image_role);

CREATE TABLE reference_library_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('model', 'background', 'pose')),
  name TEXT NOT NULL,
  file_url TEXT NOT NULL,
  prompt_text TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX reference_library_items_brand_kind_idx ON reference_library_items (brand_id, kind);

ALTER TABLE pose_references ADD COLUMN IF NOT EXISTS prompt_text TEXT NOT NULL DEFAULT '';

ALTER TABLE generation_requests ADD COLUMN IF NOT EXISTS parent_request_id UUID REFERENCES generation_requests(id);
ALTER TABLE generation_requests ADD COLUMN IF NOT EXISTS source_final_asset_id UUID REFERENCES assets(id);
ALTER TABLE generation_requests ADD COLUMN IF NOT EXISTS raw_asset_id UUID REFERENCES assets(id);
ALTER TABLE generation_requests ADD COLUMN IF NOT EXISTS reference_asset_ids JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE generation_requests ADD COLUMN IF NOT EXISTS model_reference_id UUID REFERENCES reference_library_items(id);
ALTER TABLE generation_requests ADD COLUMN IF NOT EXISTS background_reference_id UUID REFERENCES reference_library_items(id);
ALTER TABLE generation_requests ADD COLUMN IF NOT EXISTS garment_prompt TEXT;
ALTER TABLE generation_requests ADD COLUMN IF NOT EXISTS pose_prompt TEXT;
ALTER TABLE generation_requests ADD COLUMN IF NOT EXISTS background_prompt TEXT;

CREATE TABLE avatar_studio_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  final_asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  avatar_id UUID NOT NULL REFERENCES avatars(id) ON DELETE CASCADE,
  rights_record_id UUID REFERENCES rights_records(id),
  active_version_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX avatar_studio_sessions_final_asset_idx ON avatar_studio_sessions (final_asset_id);
CREATE INDEX avatar_studio_sessions_avatar_idx ON avatar_studio_sessions (avatar_id);

CREATE TABLE avatar_studio_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES avatar_studio_sessions(id) ON DELETE CASCADE,
  generation_request_id UUID NOT NULL REFERENCES generation_requests(id) ON DELETE CASCADE,
  version_number INT NOT NULL,
  garment_prompt TEXT,
  pose_prompt TEXT,
  background_prompt TEXT,
  scene_description TEXT,
  result_asset_id UUID REFERENCES assets(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (session_id, version_number)
);

CREATE INDEX avatar_studio_versions_session_idx ON avatar_studio_versions (session_id);
