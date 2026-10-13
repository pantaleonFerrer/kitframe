export type Role = "owner" | "admin" | "editor" | "member" | "viewer";

export type Team =
  | "creative"
  | "graphic_design"
  | "social"
  | "retail"
  | "ecommerce"
  | null;

export type WorkflowStep =
  | "technical_sheet"
  | "visual_production"
  | "retouch_qc"
  | "approval"
  | "published";

export type QcStatus = "pending" | "pass" | "needs_review" | "fail";

export type JobStatus = "queued" | "running" | "completed" | "failed";

export type RightsStatus = "not_cleared" | "in_progress" | "cleared";

export type AvatarStatus = "training" | "ready" | "failed";

export type AssetType = "product_only" | "model" | "social" | "campaign";

export type AssetOrigin = "real_photo" | "generated";

export type AssetImageRole = "raw" | "reference" | "final";

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    retry_after?: number;
  };
}

export interface Paginated<T> {
  data: T[];
  total: number;
  page: number;
}

export interface User {
  id: string;
  email: string;
  name?: string;
  created_at: string;
}

export interface BrandMembership {
  id: string;
  user_id: string;
  brand_id: string;
  role: Role;
  team: Team;
  user?: User;
  brand?: Brand;
}

export interface MeResponse {
  user: User;
  memberships: BrandMembership[];
}

export interface Brand {
  id: string;
  name: string;
  taxonomy_schema: TaxonomySchema;
  translation_glossary: Record<string, unknown>;
  shopify_store_domain?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaxonomyField {
  key: string;
  label: string;
  type: "string" | "enum" | "number" | "boolean";
  required: boolean;
  values?: string[];
}

export interface TaxonomySchema {
  fields: TaxonomyField[];
}

export interface Collection {
  id: string;
  brand_id: string;
  name: string;
  sample_arrival_date?: string | null;
  must_ship_date?: string | null;
  sale_date?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Product {
  id: string;
  collection_id: string;
  internal_reference: string;
  category?: string | null;
  status: WorkflowStep;
  structured_data: Record<string, unknown>;
  extraction_confidence?: Record<string, number> | null;
  seo?: {
    title?: string;
    meta_description?: string;
    keywords?: string[];
  } | null;
  translations?: Record<string, Record<string, unknown>> | null;
  assigned_team?: Team;
  shopify_product_id?: string | null;
  thumbnail_url?: string | null;
  days_in_step?: number;
  qc_status?: QcStatus | null;
  created_at: string;
  updated_at: string;
}

export interface Variant {
  id: string;
  product_id: string;
  color?: string | null;
  color_normalized?: string | null;
  size?: string | null;
  sku: string;
  created_at: string;
}

export interface Asset {
  id: string;
  product_id: string;
  variant_id?: string | null;
  type: AssetType;
  origin: AssetOrigin;
  image_role?: AssetImageRole;
  file_url: string;
  generation_provider?: string | null;
  qc_status: QcStatus;
  tags?: string[];
  created_at: string;
}

export interface QcRun {
  id: string;
  asset_id: string;
  golden_set_image_id: string;
  color_score?: number | null;
  logo_position_score?: number | null;
  resolution_score?: number | null;
  overall_score: number;
  threshold: number;
  result: "pass" | "needs_review" | "fail";
  raw_output?: Record<string, unknown> | null;
  created_at: string;
}

export interface GoldenSetImage {
  id: string;
  brand_id: string;
  garment_category: string;
  file_url: string;
  reference_color_lab?: Record<string, unknown> | null;
  logo_bounding_box?: { x: number; y: number; w: number; h: number } | null;
  is_primary?: boolean;
  approved_by?: string | null;
  created_at: string;
}

export interface RightsRecord {
  id: string;
  subject_type: string;
  subject_name: string;
  status: RightsStatus;
  cleared_at?: string | null;
  cleared_by?: string | null;
  notes?: string | null;
  updated_by_name?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface Avatar {
  id: string;
  brand_id: string;
  name: string;
  reference_asset_urls: string[];
  identity_profile_ref?: string | null;
  status: AvatarStatus;
  created_at: string;
}

export interface PoseReference {
  id: string;
  brand_id: string;
  name: string;
  skeleton_data_url: string;
  prompt_text?: string;
  created_at: string;
}

export interface ReferenceLibraryItem {
  id: string;
  brand_id: string;
  kind: "model" | "background" | "pose";
  name: string;
  file_url: string;
  prompt_text: string;
  created_at: string;
}

export interface AvatarStudioVersion {
  id: string;
  version_number: number;
  generation_request_id: string;
  garment_prompt?: string | null;
  pose_prompt?: string | null;
  background_prompt?: string | null;
  scene_description?: string | null;
  result_asset_id?: string | null;
  result_asset?: Asset | null;
  status: string;
  created_at: string;
}

export interface AvatarStudioSession {
  id: string;
  brand_id: string;
  final_asset_id: string;
  avatar_id: string;
  rights_record_id?: string | null;
  active_version_id?: string | null;
  created_at: string;
  updated_at: string;
  versions: AvatarStudioVersion[];
}

export interface GenerationRequest {
  id: string;
  product_id: string;
  avatar_id?: string | null;
  pose_reference_id?: string | null;
  provider: string;
  rights_record_id?: string | null;
  status: "queued" | "running" | "completed" | "failed" | "blocked_rights";
  result_asset_id?: string | null;
  result_asset?: Asset | null;
  requested_by: string;
  created_at: string;
  scene_description?: string;
  garment_prompt?: string;
  pose_prompt?: string;
  background_prompt?: string;
  raw_asset_id?: string;
  reference_asset_ids?: string[];
  model_reference_id?: string;
  background_reference_id?: string;
  parent_request_id?: string | null;
  source_final_asset_id?: string | null;
  completed_at?: string | null;
}

export interface ProviderBenchmark {
  id: string;
  brand_id: string;
  provider: string;
  golden_set_image_id: string;
  qc_run_id: string;
  cost_usd?: number | null;
  latency_ms?: number | null;
  color_score?: number | null;
  logo_position_score?: number | null;
  resolution_score?: number | null;
  overall_score?: number | null;
  result_image_url?: string | null;
  created_at: string;
}

export interface NotificationPreference {
  id: string;
  user_id: string;
  brand_id: string;
  event_type: string;
  channel: "in_app" | "email";
  frequency: "immediate" | "hourly_digest" | "daily_digest";
  quiet_hours_start?: string | null;
  quiet_hours_end?: string | null;
}

export interface Notification {
  id: string;
  user_id: string;
  brand_id: string;
  event_type: string;
  payload: {
    summary?: string;
    entity_type?: string;
    entity_id?: string;
    href?: string;
    [key: string]: unknown;
  };
  status: string;
  read_at?: string | null;
  sent_at?: string | null;
  created_at: string;
}

export interface JobRecord {
  id: string;
  job_type: string;
  status: JobStatus;
  related_entity_type?: string | null;
  related_entity_id?: string | null;
  error_detail?: string | null;
  attempts: number;
  created_at: string;
  updated_at: string;
}

export interface SourceDocument {
  id: string;
  product_id?: string | null;
  file_url: string;
  file_type: "pdf" | "xlsx" | "image";
  extraction_status: "pending" | "extracted" | "needs_review" | "failed";
  raw_extraction?: Record<string, unknown> | null;
  job_id?: string | null;
  filename?: string;
  created_at: string;
}

export interface ChannelSpec {
  id: string;
  brand_id: string;
  channel: string;
  width_px: number;
  height_px: number;
  format: string;
  color_profile: string;
  filename_pattern: string;
  created_at: string;
}

export interface Bottleneck {
  step: WorkflowStep;
  average_hours: number;
  threshold_hours: number;
  product_count: number;
}

export interface AlertRule {
  id: string;
  brand_id: string;
  step: WorkflowStep;
  threshold_hours: number;
}

export interface LoginResponse {
  access_token: string;
  token_type?: string;
  expires_in?: number;
  user?: User;
}

export interface AssetSearchResponse extends Paginated<Asset> {
  interpreted_query?: string;
}

export const WORKFLOW_STEPS: { key: WorkflowStep; label: string }[] = [
  { key: "technical_sheet", label: "Technical sheet" },
  { key: "visual_production", label: "Visual production" },
  { key: "retouch_qc", label: "Retouch & QC" },
  { key: "approval", label: "Approval" },
  { key: "published", label: "Published" },
];

export interface LibraryProject {
  id: string;
  brand_id: string;
  name: string;
  description?: string | null;
  collection_id?: string | null;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface LibraryFolder {
  id: string;
  name: string;
  parent_folder_id?: string | null;
  created_at?: string;
}

export interface LibraryFile {
  id: string;
  name: string;
  file_url: string;
  content_type?: string | null;
  size_bytes?: number | null;
  assigned_user_id?: string | null;
  assignee_name?: string | null;
  created_at: string;
}

export interface LibraryBreadcrumb {
  id: string | null;
  name: string;
}

export interface LibraryContents {
  project_id: string;
  project_name: string;
  folder_id?: string | null;
  breadcrumbs: LibraryBreadcrumb[];
  folders: LibraryFolder[];
  files: LibraryFile[];
}

export interface LibraryFileComment {
  id: string;
  user_id?: string | null;
  author_name: string;
  body: string;
  created_at: string;
}

export interface LibraryShare {
  id: string;
  token: string;
  label?: string | null;
  allow_comments: boolean;
  expires_at?: string | null;
  created_at: string;
  project_id?: string | null;
  folder_id?: string | null;
  file_id?: string | null;
  url_path: string;
}

export interface PublicShareView {
  scope: "file" | "folder";
  label?: string | null;
  allow_comments: boolean;
  file?: LibraryFile;
  comments?: LibraryFileComment[];
  project_id?: string;
  folder_id?: string | null;
  contents?: Omit<LibraryContents, "project_id"> & { project_name: string };
}

export const ADJACENT_STEPS: Record<WorkflowStep, WorkflowStep[]> = {
  technical_sheet: ["visual_production"],
  visual_production: ["technical_sheet", "retouch_qc"],
  retouch_qc: ["visual_production", "approval"],
  approval: ["retouch_qc", "published"],
  published: ["approval"],
};
