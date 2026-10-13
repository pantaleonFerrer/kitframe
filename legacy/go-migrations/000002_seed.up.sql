INSERT INTO brands (
  id,
  name,
  taxonomy_schema,
  translation_glossary,
  shopify_store_domain,
  shopify_environment
) VALUES (
  'a0000000-0000-4000-8000-000000000001',
  'FC Barcelona',
  '{
    "fields": [
      {"key": "composition", "label": "Composition", "type": "string", "required": true},
      {"key": "care_instructions", "label": "Care instructions", "type": "string", "required": true},
      {"key": "origin", "label": "Origin", "type": "string", "required": false},
      {"key": "category", "label": "Category", "type": "enum", "values": ["jersey", "training", "leisure", "accessories"], "required": true},
      {"key": "gender", "label": "Gender", "type": "enum", "values": ["kids", "adult_men", "adult_women", "unisex"], "required": true},
      {"key": "color_normalized", "label": "Normalized color", "type": "enum", "values": ["blaugrana", "white", "black", "gold"], "required": true}
    ]
  }'::jsonb,
  '{
    "do_not_translate": ["FC Barcelona", "Barça", "Camp Nou", "Blaugrana", "Nike"]
  }'::jsonb,
  'kitframe-staging.myshopify.com',
  'staging'
);

INSERT INTO users (id, email, password_hash, display_name) VALUES
  ('b0000000-0000-4000-8000-000000000001', 'owner@kitframe.local', '$argon2id$v=19$m=65536,t=3,p=2$c2FsdHNhbHRzYWx0c2FsdA$8QwqY5lqJ5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y', 'Owner User'),
  ('b0000000-0000-4000-8000-000000000002', 'admin@kitframe.local', '$argon2id$v=19$m=65536,t=3,p=2$c2FsdHNhbHRzYWx0c2FsdA$8QwqY5lqJ5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y', 'Admin User'),
  ('b0000000-0000-4000-8000-000000000003', 'editor@kitframe.local', '$argon2id$v=19$m=65536,t=3,p=2$c2FsdHNhbHRzYWx0c2FsdA$8QwqY5lqJ5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y', 'Editor User'),
  ('b0000000-0000-4000-8000-000000000004', 'viewer@kitframe.local', '$argon2id$v=19$m=65536,t=3,p=2$c2FsdHNhbHRzYWx0c2FsdA$8QwqY5lqJ5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y5Y', 'Viewer User');

INSERT INTO brand_memberships (user_id, brand_id, role, team) VALUES
  ('b0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000001', 'owner', NULL),
  ('b0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000001', 'admin', 'ecommerce'),
  ('b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000001', 'editor', 'creative'),
  ('b0000000-0000-4000-8000-000000000004', 'a0000000-0000-4000-8000-000000000001', 'viewer', 'retail');

INSERT INTO collections (id, brand_id, name, sample_arrival_date, must_ship_date, sale_date) VALUES
  ('c0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000001', 'Home Kit 2026/27', CURRENT_DATE - 7, CURRENT_DATE + 45, CURRENT_DATE + 60);

INSERT INTO channel_specs (brand_id, channel, width_px, height_px, format, color_profile, filename_pattern) VALUES
  ('a0000000-0000-4000-8000-000000000001', 'shopify', 2048, 2048, 'jpg', 'sRGB', '{sku}_{channel}_{w}x{h}.{ext}'),
  ('a0000000-0000-4000-8000-000000000001', 'instagram', 1080, 1350, 'jpg', 'sRGB', '{sku}_{channel}_{w}x{h}.{ext}'),
  ('a0000000-0000-4000-8000-000000000001', 'print_retail', 3000, 3000, 'png', 'sRGB', '{sku}_{channel}_{w}x{h}.{ext}'),
  ('a0000000-0000-4000-8000-000000000001', 'email', 600, 600, 'jpg', 'sRGB', '{sku}_{channel}_{w}x{h}.{ext}');

INSERT INTO alert_rules (brand_id, step, threshold_hours) VALUES
  ('a0000000-0000-4000-8000-000000000001', 'visual_production', 72),
  ('a0000000-0000-4000-8000-000000000001', 'retouch_qc', 48);

INSERT INTO golden_set_images (id, brand_id, garment_category, file_url, reference_color_lab, logo_bounding_box, approved_by) VALUES
  (
    'd0000000-0000-4000-8000-000000000001',
    'a0000000-0000-4000-8000-000000000001',
    'jersey',
    's3://kitframe-assets/golden-set/jersey-home-ref.jpg',
    '{"L": 35.2, "a": 42.1, "b": 18.4}'::jsonb,
    '{"x": 0.42, "y": 0.28, "w": 0.16, "h": 0.18}'::jsonb,
    'b0000000-0000-4000-8000-000000000001'
  );
