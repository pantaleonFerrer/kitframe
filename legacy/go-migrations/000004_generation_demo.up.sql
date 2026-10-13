INSERT INTO rights_records (
  id,
  brand_id,
  subject_type,
  subject_name,
  status,
  cleared_at,
  cleared_by,
  notes
) VALUES (
  '11000000-0000-4000-8000-000000000001',
  'a0000000-0000-4000-8000-000000000001',
  'model',
  'Campaign Model A',
  'cleared',
  now(),
  'b0000000-0000-4000-8000-000000000001',
  'Demo clearance for local generation'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO pose_references (id, brand_id, name, skeleton_data_url) VALUES
  (
    '12000000-0000-4000-8000-000000000001',
    'a0000000-0000-4000-8000-000000000001',
    'Studio front',
    'https://placehold.co/512x768/png?text=Pose+Front'
  ),
  (
    '12000000-0000-4000-8000-000000000002',
    'a0000000-0000-4000-8000-000000000001',
    'Three-quarter',
    'https://placehold.co/512x768/png?text=Pose+3Q'
  )
ON CONFLICT (id) DO NOTHING;

INSERT INTO assets (id, product_id, type, origin, file_url, qc_status) VALUES
  (
    '13000000-0000-4000-8000-000000000001',
    'e0000000-0000-4000-8000-000000000001',
    'product_only',
    'real_photo',
    'https://placehold.co/800x1000/7d1a1d/f1ebe3/png?text=Home+Kit',
    'pass'
  ),
  (
    '13000000-0000-4000-8000-000000000002',
    'e0000000-0000-4000-8000-000000000002',
    'product_only',
    'real_photo',
    'https://placehold.co/800x1000/1f2428/f1ebe3/png?text=Training',
    'pass'
  ),
  (
    '13000000-0000-4000-8000-000000000003',
    'e0000000-0000-4000-8000-000000000003',
    'product_only',
    'real_photo',
    'https://placehold.co/800x1000/d4c1ac/1f2428/png?text=Leisure',
    'pass'
  )
ON CONFLICT (id) DO NOTHING;
