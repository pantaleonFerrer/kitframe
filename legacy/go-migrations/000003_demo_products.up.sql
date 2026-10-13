INSERT INTO products (
  id,
  collection_id,
  internal_reference,
  category,
  status,
  structured_data,
  extraction_confidence,
  assigned_team
) VALUES
(
  'e0000000-0000-4000-8000-000000000001',
  'c0000000-0000-4000-8000-000000000001',
  'FCB-HOME-26-001',
  'jersey',
  'technical_sheet',
  '{"composition":"100% recycled polyester","care_instructions":"Machine wash cold","origin":"Portugal","category":"jersey","gender":"adult_men","color_normalized":"blaugrana"}'::jsonb,
  '{"composition":0.96,"care_instructions":0.91,"origin":0.88,"category":0.99,"gender":0.97,"color_normalized":0.94}'::jsonb,
  'creative'
),
(
  'e0000000-0000-4000-8000-000000000002',
  'c0000000-0000-4000-8000-000000000001',
  'FCB-TRAIN-26-014',
  'training',
  'visual_production',
  '{"composition":"88% polyester 12% elastane","care_instructions":"Do not bleach","origin":"Vietnam","category":"training","gender":"unisex","color_normalized":"black"}'::jsonb,
  '{"composition":0.93,"care_instructions":0.9,"origin":0.85,"category":0.98,"gender":0.92,"color_normalized":0.95}'::jsonb,
  'graphic_design'
),
(
  'e0000000-0000-4000-8000-000000000003',
  'c0000000-0000-4000-8000-000000000001',
  'FCB-LEISURE-26-008',
  'leisure',
  'retouch_qc',
  '{"composition":"100% cotton","care_instructions":"Wash inside out","origin":"Spain","category":"leisure","gender":"adult_women","color_normalized":"white"}'::jsonb,
  '{"composition":0.97,"care_instructions":0.89,"origin":0.94,"category":0.99,"gender":0.96,"color_normalized":0.93}'::jsonb,
  'creative'
)
ON CONFLICT (collection_id, internal_reference) DO NOTHING;

INSERT INTO variants (id, product_id, color, color_normalized, size, sku) VALUES
  ('f0000000-0000-4000-8000-000000000001', 'e0000000-0000-4000-8000-000000000001', 'Blaugrana', 'blaugrana', 'M', 'FCB-HOME-26-001-M'),
  ('f0000000-0000-4000-8000-000000000002', 'e0000000-0000-4000-8000-000000000002', 'Black', 'black', 'L', 'FCB-TRAIN-26-014-L'),
  ('f0000000-0000-4000-8000-000000000003', 'e0000000-0000-4000-8000-000000000003', 'White', 'white', 'S', 'FCB-LEISURE-26-008-S')
ON CONFLICT (sku) DO NOTHING;

INSERT INTO audit_log (user_id, brand_id, entity_type, entity_id, action, detail)
SELECT
  'b0000000-0000-4000-8000-000000000001',
  'a0000000-0000-4000-8000-000000000001',
  'product',
  id,
  'seeded',
  jsonb_build_object('reference', internal_reference, 'status', status)
FROM products
WHERE collection_id = 'c0000000-0000-4000-8000-000000000001'
  AND internal_reference IN ('FCB-HOME-26-001', 'FCB-TRAIN-26-014', 'FCB-LEISURE-26-008');
