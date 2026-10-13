CREATE TABLE library_projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  collection_id UUID REFERENCES collections(id) ON DELETE SET NULL,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX library_projects_brand_id_idx ON library_projects (brand_id);

CREATE TABLE library_folders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES library_projects(id) ON DELETE CASCADE,
  parent_folder_id UUID REFERENCES library_folders(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX library_folders_project_id_idx ON library_folders (project_id);
CREATE INDEX library_folders_parent_folder_id_idx ON library_folders (parent_folder_id);

CREATE TABLE library_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES library_projects(id) ON DELETE CASCADE,
  folder_id UUID REFERENCES library_folders(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  file_url TEXT NOT NULL,
  content_type TEXT,
  size_bytes BIGINT,
  assigned_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX library_files_project_id_idx ON library_files (project_id);
CREATE INDEX library_files_folder_id_idx ON library_files (folder_id);
CREATE INDEX library_files_assigned_user_id_idx ON library_files (assigned_user_id);

CREATE TABLE library_file_comments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  file_id UUID NOT NULL REFERENCES library_files(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  author_name TEXT,
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX library_file_comments_file_id_idx ON library_file_comments (file_id);

CREATE TABLE library_shares (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  project_id UUID REFERENCES library_projects(id) ON DELETE CASCADE,
  folder_id UUID REFERENCES library_folders(id) ON DELETE CASCADE,
  file_id UUID REFERENCES library_files(id) ON DELETE CASCADE,
  token TEXT NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(24), 'hex'),
  label TEXT,
  allow_comments BOOLEAN NOT NULL DEFAULT true,
  expires_at TIMESTAMPTZ,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    (project_id IS NOT NULL AND folder_id IS NULL AND file_id IS NULL)
    OR (folder_id IS NOT NULL AND file_id IS NULL)
    OR (file_id IS NOT NULL)
  )
);

CREATE INDEX library_shares_token_idx ON library_shares (token);
CREATE INDEX library_shares_project_id_idx ON library_shares (project_id);

INSERT INTO library_projects (id, brand_id, name, description, collection_id, created_by)
SELECT
  'f0000000-0000-4000-8000-000000000001',
  'a0000000-0000-4000-8000-000000000001',
  'SS26 — Producción visual',
  'Carpeta compartible con materiales del drop SS26.',
  c.id,
  'b0000000-0000-4000-8000-000000000003'
FROM collections c
WHERE c.brand_id = 'a0000000-0000-4000-8000-000000000001'
LIMIT 1;

INSERT INTO library_folders (id, project_id, parent_folder_id, name, created_by) VALUES
  ('f0000000-0000-4000-8000-000000000011', 'f0000000-0000-4000-8000-000000000001', NULL, 'Referencias', 'b0000000-0000-4000-8000-000000000003'),
  ('f0000000-0000-4000-8000-000000000012', 'f0000000-0000-4000-8000-000000000001', NULL, 'Entregables', 'b0000000-0000-4000-8000-000000000003');
