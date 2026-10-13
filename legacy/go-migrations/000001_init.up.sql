CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE brands (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  taxonomy_schema JSONB NOT NULL DEFAULT '{}',
  translation_glossary JSONB NOT NULL DEFAULT '{}',
  shopify_store_domain TEXT,
  shopify_access_token_encrypted TEXT,
  shopify_live_store_domain TEXT,
  shopify_live_access_token_encrypted TEXT,
  shopify_environment TEXT NOT NULL DEFAULT 'staging' CHECK (shopify_environment IN ('staging', 'live')),
  qc_pass_threshold NUMERIC NOT NULL DEFAULT 0.90,
  qc_fail_threshold NUMERIC NOT NULL DEFAULT 0.60,
  qc_check_floor NUMERIC NOT NULL DEFAULT 0.75,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  refresh_token_version INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE brand_memberships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'editor', 'viewer')),
  team TEXT CHECK (team IS NULL OR team IN ('creative', 'graphic_design', 'social', 'retail', 'ecommerce')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, brand_id)
);

CREATE INDEX brand_memberships_user_id_idx ON brand_memberships (user_id);
CREATE INDEX brand_memberships_brand_id_idx ON brand_memberships (brand_id);

CREATE TABLE collections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  sample_arrival_date DATE,
  must_ship_date DATE,
  sale_date DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX collections_brand_id_idx ON collections (brand_id);

CREATE TABLE products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  internal_reference TEXT NOT NULL,
  category TEXT,
  status TEXT NOT NULL DEFAULT 'technical_sheet' CHECK (status IN ('technical_sheet', 'visual_production', 'retouch_qc', 'approval', 'published')),
  structured_data JSONB NOT NULL DEFAULT '{}',
  extraction_confidence JSONB,
  seo JSONB,
  translations JSONB,
  assigned_team TEXT,
  shopify_product_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (collection_id, internal_reference)
);

CREATE INDEX products_collection_id_status_idx ON products (collection_id, status);
CREATE INDEX products_collection_id_idx ON products (collection_id);

CREATE TABLE variants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  color TEXT,
  color_normalized TEXT,
  size TEXT,
  sku TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX variants_product_id_idx ON variants (product_id);

CREATE TABLE source_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID REFERENCES products(id) ON DELETE SET NULL,
  file_url TEXT NOT NULL,
  file_type TEXT NOT NULL CHECK (file_type IN ('pdf', 'xlsx', 'image')),
  extraction_status TEXT NOT NULL DEFAULT 'pending' CHECK (extraction_status IN ('pending', 'extracted', 'needs_review', 'failed')),
  raw_extraction JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX source_documents_product_id_idx ON source_documents (product_id);

CREATE TABLE assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  variant_id UUID REFERENCES variants(id) ON DELETE SET NULL,
  type TEXT NOT NULL CHECK (type IN ('product_only', 'model', 'social', 'campaign')),
  origin TEXT NOT NULL CHECK (origin IN ('real_photo', 'generated')),
  file_url TEXT NOT NULL,
  generation_provider TEXT,
  qc_status TEXT NOT NULL DEFAULT 'pending' CHECK (qc_status IN ('pending', 'pass', 'needs_review', 'fail')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX assets_product_id_qc_status_idx ON assets (product_id, qc_status);
CREATE INDEX assets_product_id_idx ON assets (product_id);

CREATE TABLE golden_set_images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  garment_category TEXT NOT NULL,
  file_url TEXT NOT NULL,
  reference_color_lab JSONB,
  logo_bounding_box JSONB,
  approved_by UUID REFERENCES users(id),
  superseded_by UUID REFERENCES golden_set_images(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX golden_set_images_brand_id_idx ON golden_set_images (brand_id);
CREATE INDEX golden_set_images_brand_category_idx ON golden_set_images (brand_id, garment_category);

CREATE TABLE qc_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  golden_set_image_id UUID REFERENCES golden_set_images(id),
  color_score NUMERIC,
  logo_position_score NUMERIC,
  resolution_score NUMERIC,
  overall_score NUMERIC NOT NULL,
  threshold NUMERIC NOT NULL DEFAULT 0.90,
  result TEXT NOT NULL CHECK (result IN ('pass', 'needs_review', 'fail')),
  raw_output JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX qc_runs_asset_id_idx ON qc_runs (asset_id);

CREATE TABLE tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  step TEXT NOT NULL,
  assigned_team TEXT NOT NULL,
  assigned_user_id UUID REFERENCES users(id),
  due_date DATE,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX tasks_product_id_idx ON tasks (product_id);
CREATE INDEX tasks_assigned_user_id_idx ON tasks (assigned_user_id);

CREATE TABLE rights_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  subject_type TEXT NOT NULL,
  subject_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'not_cleared' CHECK (status IN ('not_cleared', 'in_progress', 'cleared')),
  cleared_at TIMESTAMPTZ,
  cleared_by UUID REFERENCES users(id),
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX rights_records_brand_id_idx ON rights_records (brand_id);

CREATE TABLE channel_specs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  channel TEXT NOT NULL CHECK (channel IN ('shopify', 'instagram', 'print_retail', 'email')),
  width_px INT NOT NULL,
  height_px INT NOT NULL,
  format TEXT NOT NULL CHECK (format IN ('jpg', 'png', 'webp')),
  color_profile TEXT NOT NULL DEFAULT 'sRGB',
  filename_pattern TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (brand_id, channel)
);

CREATE INDEX channel_specs_brand_id_idx ON channel_specs (brand_id);

CREATE TABLE avatars (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  reference_asset_urls JSONB NOT NULL,
  identity_profile_ref TEXT,
  status TEXT NOT NULL DEFAULT 'training' CHECK (status IN ('training', 'ready', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX avatars_brand_id_idx ON avatars (brand_id);

CREATE TABLE pose_references (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  skeleton_data_url TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX pose_references_brand_id_idx ON pose_references (brand_id);

CREATE TABLE generation_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  avatar_id UUID REFERENCES avatars(id),
  pose_reference_id UUID REFERENCES pose_references(id),
  provider TEXT NOT NULL,
  rights_record_id UUID REFERENCES rights_records(id),
  scene_description TEXT,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed', 'blocked_rights')),
  result_asset_id UUID REFERENCES assets(id),
  requested_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX generation_requests_product_id_idx ON generation_requests (product_id);
CREATE INDEX generation_requests_avatar_id_idx ON generation_requests (avatar_id);

CREATE TABLE provider_benchmarks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  golden_set_image_id UUID NOT NULL REFERENCES golden_set_images(id),
  qc_run_id UUID NOT NULL REFERENCES qc_runs(id),
  generated_asset_url TEXT,
  cost_usd NUMERIC,
  latency_ms INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX provider_benchmarks_brand_id_idx ON provider_benchmarks (brand_id);
CREATE INDEX provider_benchmarks_golden_set_image_id_idx ON provider_benchmarks (golden_set_image_id);

CREATE TABLE asset_embeddings (
  asset_id UUID PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
  embedding VECTOR(768),
  tags JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX asset_embeddings_embedding_idx ON asset_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE notification_preferences (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  channel TEXT NOT NULL CHECK (channel IN ('in_app', 'email')),
  frequency TEXT NOT NULL DEFAULT 'immediate' CHECK (frequency IN ('immediate', 'hourly_digest', 'daily_digest')),
  quiet_hours_start TIME,
  quiet_hours_end TIME,
  UNIQUE (user_id, brand_id, event_type, channel)
);

CREATE INDEX notification_preferences_user_brand_idx ON notification_preferences (user_id, brand_id);

CREATE TABLE notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'digested', 'suppressed_quiet_hours', 'failed')),
  read_at TIMESTAMPTZ,
  sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX notifications_user_id_created_at_idx ON notifications (user_id, created_at DESC);
CREATE INDEX notifications_status_idx ON notifications (status);

CREATE TABLE job_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
  related_entity_type TEXT,
  related_entity_id UUID,
  error_detail TEXT,
  attempts INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX job_records_status_idx ON job_records (status);
CREATE INDEX job_records_related_idx ON job_records (related_entity_type, related_entity_id);

CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  brand_id UUID REFERENCES brands(id),
  entity_type TEXT NOT NULL,
  entity_id UUID NOT NULL,
  action TEXT NOT NULL,
  detail JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX audit_log_entity_idx ON audit_log (entity_type, entity_id, created_at DESC);
CREATE INDEX audit_log_brand_id_created_at_idx ON audit_log (brand_id, created_at DESC);

CREATE TABLE alert_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  step TEXT NOT NULL,
  threshold_hours NUMERIC NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX alert_rules_brand_id_idx ON alert_rules (brand_id);

CREATE TABLE briefs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  created_by UUID NOT NULL REFERENCES users(id),
  notes TEXT NOT NULL DEFAULT '',
  draft_content TEXT,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'pending_validation', 'validated', 'sent')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX briefs_brand_id_idx ON briefs (brand_id);

CREATE TABLE refresh_token_denylist (
  jti TEXT PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX refresh_token_denylist_user_id_idx ON refresh_token_denylist (user_id);
CREATE INDEX refresh_token_denylist_expires_at_idx ON refresh_token_denylist (expires_at);

CREATE TABLE login_attempts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL,
  ip_address TEXT NOT NULL,
  succeeded BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX login_attempts_email_created_at_idx ON login_attempts (email, created_at DESC);
CREATE INDEX login_attempts_ip_created_at_idx ON login_attempts (ip_address, created_at DESC);
