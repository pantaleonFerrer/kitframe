# Kitframe — Build Specification
### Product data, creative workflow and AI image production for FC Barcelona merchandising
### Built by Gathered · Version 4.1 · Single source of truth for implementation

---

## 0. How to use this document

**For the implementer (human or AI coding agent):**

1. This document is the only specification. Build against it and nothing else. Do not add features, screens, services or dependencies that are not listed here.
2. Build in the order given in §25. Each module has a **Definition of Done (DoD)**; a module is finished only when every DoD item is true and verified.
3. Everything written here is a decision already made. The only things not decided are listed in §26 (they need client or business input). Where code depends on one of them, it must be written behind the interface described here, so the decision can be plugged in later without changing the rest of the system.
4. No mock, fake or placeholder may exist in a production code path. Fakes exist only in tests and local development and are selected by explicit configuration.
5. Code, identifiers, API and database names are in English. **All user-facing UI text is in Spanish** (default locale `es`), stored in translation files so `ca` and `en` can be added without code changes (§15.1).

**Naming:** the product is **Kitframe**. It is built and operated by Gathered, shown under the Gathered visual identity, but everything is named Kitframe so it can become a separate brand later with only asset and config changes.

**Working assumption:** a **Project** is a unit of work (a collection drop or a campaign) that contains products. Every product belongs to exactly one project.

---

## 1. Product scope

### 1.1 What Kitframe does
Kitframe takes a garment from its technical sheet to a published Shopify product with approved images. It does this through a fixed workflow of phases, each with assigned editors and reviewers, an AI **Studio** to generate model images from reference photos and a prompt, and a quality gate that blocks anything non-compliant from being published.

### 1.2 The core guarantee
A generative model cannot guarantee that every image it produces is correct. Kitframe instead guarantees that **100% of what is approved and published is compliant**, through four stacked layers:

1. **Real garment as input.** Generation always uses real photos of the actual garment as reference; the model is instructed to preserve it exactly (§5.4).
2. **Automated QC** against an approved golden set: color, crest and resolution (§7). Failures block progress.
3. **Project requirements checklist.** Every project defines explicit requirements; a reviewer must tick each one to approve (§3.5).
4. **Mandatory human approval** at every phase (§3). Nothing reaches Shopify without it.

Plus a hard **rights gate**: no generation involving a real, identifiable person is ever sent to a provider unless that person's rights are cleared (§5.5).

### 1.3 In scope
- Email/password authentication with invitations and password reset.
- Brand configuration: taxonomy, glossary, generation rules, required shots, QC thresholds, channel specs, Shopify connections.
- Projects with a team assigned per phase (editors and reviewers) and per-phase due dates.
- Technical sheet ingestion (PDF, XLSX, image) with LLM extraction, per-field confidence and confirmation.
- SEO copy and translations in `es`, `ca`, `en` with a do-not-translate glossary.
- A five-phase workflow with review, change requests and send-back (§3).
- Asset management with versions, shot types, background removal and comments with image annotations.
- **Studio**: AI image generation from garment photos + model reference set + pose + style references + prompt + restrictions.
- **Library**: model reference sets, pose references, style references, golden set.
- Automated QC and admin override with mandatory reason.
- Rights records and the rights gate.
- Channel exports (deterministic renditions + ZIP).
- Shopify publishing to a staging or live store, with explicit promotion.
- In-app and email notifications with per-event email preference.
- Audit log of every state-changing action.
- Responsive web UI (desktop first, usable on tablet and phone).

### 1.4 Out of scope (deliberate, not deferred)
Not part of this build; do not implement any part of them:
- SSO, multi-region, autoscaling, native mobile app, public API.
- Video generation.
- Training custom identity models (LoRA or similar). Model consistency comes from reference images (§5).
- Keypoint-based crest compositing. Crest fidelity is enforced by QC and review (§7).
- Ghost mannequin processing (done by the retouch team in their own tools; they upload a new version, §6.3).
- Semantic/embedding search, duplicate detection, AI briefing assistant, provider benchmarking UI.
- Notification digests and quiet hours.
- Shopify → Kitframe sync (webhooks, inventory). Kitframe is the source of truth for content; Shopify owns inventory.
- Real-time push (SSE/WebSockets). The UI polls (§11.5).
- Multi-brand UI. The data model is multi-tenant (`brand_id` everywhere) but the UI assumes one active brand per session, with a switcher only if the user belongs to more than one.

---

## 2. Concepts and glossary

| Concept | Meaning |
|---|---|
| Brand | A tenant (FC Barcelona). Owns all configuration and data. |
| Project | A unit of work (collection drop or campaign) with dates, a lead, a team per phase and a requirements checklist. |
| Product | A garment reference inside a project. Has structured data, variants, assets and one state per phase. |
| Variant | A color/size combination with SKU and price. |
| Phase | One of `data`, `visuals`, `retouch`, `approval`, `published` (§3.1). |
| Product phase | The state of one product in one phase: status, assignee, reviewer, due date. |
| Asset | An image attached to a product (real photo or generated), with a shot type and versions. |
| Asset version | An immutable image file. Editing an asset (retouch, background removal) creates a new version. QC runs on versions. |
| Shot type | `product_front`, `product_back`, `product_detail`, `model_front`, `model_back`, `lifestyle`. |
| Model reference set | A named set of 3–20 photos of one person (the "avatar"). `synthetic` or `real_person`. |
| Pose reference | An image showing a body pose to imitate. |
| Style reference | An image showing lighting, composition or mood to imitate. |
| Generation | One Studio request producing 1–4 images. |
| Golden set image | An approved reference image of a garment category and shot type, used by QC. |
| QC run | One automated quality check of one asset version. |
| Review | A reviewer's decision on a product phase. |
| Rights record | Clearance status for a real person whose likeness or name may appear. |

---

## 3. Workflow

### 3.1 Phases
Phases are fixed in this build (not brand-configurable).

| Key | UI label (es) | What happens | Typical editors |
|---|---|---|---|
| `data` | Datos de producto | Extraction review, variants, SEO, translations | E-commerce / product |
| `visuals` | Producción visual | Upload real photos, generate in Studio, choose images | Creative |
| `retouch` | Retoque y QC | Upload retouched versions, background removal, pass QC | Graphic design |
| `approval` | Aprobación final | Final review of the whole product and publish | (reviewers only) |
| `published` | Publicado | Terminal state; republish possible | — |

### 3.2 Product phase statuses
Each product has one `product_phases` row per phase (created when the product is created). Status values:

`todo` → `in_progress` → `in_review` → `done`, plus `changes_requested`.

| From | To | Who | Trigger |
|---|---|---|---|
| `todo` | `in_progress` | Editor of the phase | Button "Empezar" or first edit in that phase (automatic) |
| `in_progress` | `in_review` | Editor of the phase | "Enviar a revisión". Blocked unless exit criteria pass (§3.4) |
| `changes_requested` | `in_review` | Editor of the phase | "Reenviar a revisión". Same exit criteria |
| `in_review` | `done` | Reviewer of the phase | "Aprobar" with every project requirement ticked (§3.5) |
| `in_review` | `changes_requested` | Reviewer of the phase | "Solicitar cambios" with a mandatory comment |

When a phase becomes `done`, `products.current_phase` moves to the next phase and that phase's row gets `entered_at = now()`.

**Approval phase:** has no editor work. When a product enters `approval`, its row goes straight to `in_review`. The reviewer's action is **"Aprobar y publicar"**, which marks the phase `done` only after Shopify confirms the publish (§9.3). If publishing fails, the row stays `in_review` and the error is shown with a retry button.

**Send back:** a reviewer of `approval` (or any admin/owner) can "Devolver a fase…" any earlier phase with a mandatory comment. The target phase becomes `changes_requested`; every phase after it is reset to `todo`; `current_phase` becomes the target.

**Locking:**
- While a phase is `in_review`, editors cannot modify the product (API returns `phase_locked`).
- Structured data, variants, SEO and translations are editable only while `current_phase = data`. Afterwards only admin/owner can edit them, and every such edit is audit-logged.
- Assets are editable only while `current_phase` is `visuals` or `retouch`.

**Republish:** a `published` product can be republished by an admin/owner (same confirmation as publishing). This updates the Shopify product.

### 3.3 Who reviews
- Each product phase can have an explicit `reviewer_user_id`. If it is null, any reviewer assigned to that phase in the project may review.
- If the project has no reviewer for a phase, the **project lead** reviews it.
- Admins and owners can always review any phase.
- A user cannot approve a phase in which they were the submitting editor, unless they are the only possible reviewer (then allowed, and the audit log marks `self_review: true`).

### 3.4 Exit criteria (checked by the server on submit, shown live in the UI)
Implement in one module (`workflow/criteria.py`) as a function returning a list of `{code, message_key, ok}` so the UI can render the "Qué falta" checklist from the same source.

- **`data`**
  - Every `required` taxonomy field has a valid value for its type.
  - Every field whose extraction confidence is below `qc_config.extraction.confirm_below_confidence` is in `confirmed_fields`.
  - At least one variant, and every variant has SKU and price.
  - SEO title (≤ 70 chars) and meta description (≤ 160 chars) present for `es`, `ca`, `en`.
  - Product name and description present for `es`, `ca`, `en`.
- **`visuals`**
  - For each shot type in `brand.required_shots[garment_category]`, at least one asset with status `selected`.
  - Every selected generated asset came from a generation whose rights check passed, and the rights records involved are still `cleared` and not expired.
- **`retouch`**
  - Every selected asset's current version has a QC run whose result is `pass`, or a QC override.
  - Every selected asset has `alt_text` in `es`.
  - Every selected asset fits the primary channel spec without upscaling (scale factor to fit inside its box ≤ 1.0). Other channels may upscale; the export marks those files as upscaled.
- **`approval`** (checked before publishing)
  - All criteria above still hold.
  - The brand has a working Shopify connection for the active environment, and the store has the `ca` and `en` locales enabled.

### 3.5 Project requirements
Each project has a list of requirements (plain text, e.g. "El escudo debe verse nítido", "Fondo gris claro en las fotos de modelo"). They are shown in the review panel for phases `visuals`, `retouch` and `approval`. The reviewer must tick every requirement to enable "Aprobar". The ticked list is saved in the review record.

### 3.6 Due dates
- A project has default due dates per phase (`projects.phase_due_dates`). They are copied into `product_phases.due_date` when products are created. The lead can change them per product.
- A daily job (08:00 Europe/Madrid) notifies assignees of phases due in 2 days and of overdue phases.

### 3.7 DoD
- [ ] Every transition in §3.2 is covered by a test, and every forbidden transition returns `invalid_transition`.
- [ ] Exit criteria are computed by one function used by both the submit endpoint and the checklist endpoint.
- [ ] Send-back resets later phases and is covered by a test.
- [ ] Locking rules are covered by tests.
- [ ] Publish failure leaves the approval phase `in_review` and is covered by a test.

---

## 4. Library

The Library holds reusable references. UI: `/biblioteca` with tabs **Modelos**, **Poses**, **Estilos**, **Golden set** (§15.7).

### 4.1 Model reference sets ("avatars")
- A set has a name, `kind` (`synthetic` or `real_person`), notes, and 3–20 photos of the same person.
- `real_person` sets must be linked to a rights record (database constraint). They can be created with any rights status, but cannot be used in the Studio until the record is `cleared` (§5.5).
- Photo validation on upload (in the worker, result stored on the image):
  - Short side ≥ 1024 px, otherwise rejected.
  - Exact duplicates (same SHA-256) rejected.
  - Near-duplicates (perceptual hash distance ≤ 6) produce a warning, not a rejection.
- The set is usable as soon as it has ≥ 3 valid photos. There is no training step.
- The UI shows guidance: "Sube entre 5 y 15 fotos de la misma persona: de frente, de perfil y de tres cuartos, con buena luz y sin gafas de sol." A set with fewer than 5 photos shows a warning chip "Pocas fotos: los resultados serán menos consistentes".
- Sets can be archived. Archived sets are hidden from the Studio but remain linked to past generations.

### 4.2 Pose references
One image per pose with a name (e.g. "Frontal brazos relajados"). Short side ≥ 768 px.

### 4.3 Style references
Images with a name and free-text tags (e.g. "estudio", "fondo gris", "luz suave"). Short side ≥ 768 px.

### 4.4 Golden set
- One entry = one garment category + one shot type + one reference image.
- Only `product_front`, `product_back` and `model_front` shot types can have golden entries.
- On upload, the worker computes the reference colors (§7.2). The admin then draws the crest bounding box on the image (optional; categories without a crest skip it). Saving the box stores a crest template crop.
- Status: `draft` → `approved` → `archived`. Only users with `can_approve_golden_set` can approve.
- Only one `approved` entry per (brand, category, shot type), enforced by a partial unique index. Approving a new one archives the previous one and sets `supersedes_id`.
- Entries are never modified after approval (only archived), so historical QC runs stay interpretable.

### 4.5 DoD
- [ ] Upload validation rules are tested with real fixture images.
- [ ] The database rejects a `real_person` set without a rights record.
- [ ] The database rejects a second approved golden entry for the same category and shot type.
- [ ] Crest box drawing works with mouse and touch and is stored normalized (0..1).

---

## 5. Studio (image generation)

### 5.1 Entry points
- Main nav → **Estudio** (`/estudio`): the user first picks a product.
- Product page → Imágenes tab → **"Generar en Estudio"** or the **"Generar"** button in an empty required-shot slot: opens `/estudio?product={id}&shot={shot_type}` with product and shot preselected.

### 5.2 Inputs
| Input | Required | Rules |
|---|---|---|
| Product | yes | Must be in phase `visuals` (or the user is admin) |
| Garment references | yes | 1–3 asset versions of the product with origin `real_photo`. Default: `product_front`, then `product_back`, then `product_detail` (first available of each), up to 3 |
| Target shot type | yes | Stored on the resulting assets |
| Model reference set | no | Active set. Omit for product-only shots. The **first 3 photos of the set** (by `sort_order`) are sent; the user controls which ones by reordering the set in the Library |
| Pose reference | no | 0–1 |
| Style references | no | 0–2 |
| Prompt | yes | 10–1000 chars. Scene, background, framing, mood |
| Restrictions | no | 0–500 chars. What must not appear |
| Aspect ratio | yes | `1:1`, `4:5`, `3:4`, `2:3`, `9:16`, `16:9`. Default from the primary channel spec |
| Variants | yes | 1–4, default 4 |

The total number of reference images sent (garment + model + pose + style) can never exceed the adapter's `max_reference_images` (8 for FLUX.2, §5.7). With the limits above the maximum is exactly 3 + 3 + 1 + 2 = 9, so preflight rejects any selection above 8 with `validation_error` and the Studio disables adding more, explaining why ("Este proveedor admite como máximo 8 imágenes de referencia; quita una referencia de estilo o una foto de prenda").

Images are always sent in this fixed order, and numbered from 1 in that order: garment images, model images, pose image, style images. The prompt template (§5.4) refers to them by these numbers.

### 5.3 Flow
1. The user fills in the inputs. The panel "Prompt final" (collapsed by default) shows the composed prompt (§5.4), refreshed with `POST /generations/preflight` (debounced 500 ms). Preflight also returns blocking issues (rights, missing inputs), shown inline above the "Generar" button.
2. "Generar" → `POST /generations` → job enqueued → `status = queued`.
3. The results area shows N skeleton tiles with elapsed time. Polling every 3 s (§11.5).
4. When the job completes, each image becomes an **asset** with `status = studio`, `origin = generated`, one version, and a QC run is enqueued automatically if an approved golden entry exists for the product's category and the target shot type.
5. For each result the user can:
   - **"Añadir al producto"** → asset `status = candidate` (appears in the product's Imágenes tab).
   - **"Seleccionar para publicar"** → `status = selected` directly.
   - **"Descartar"** → `status = discarded`.
   - **"Regenerar ajustando"** → the form is refilled with the same inputs; the new generation stores `parent_generation_id`.
6. The history panel lists previous generations for the product (thumbnails, prompt, author, date), each reopenable with "Reutilizar ajustes".

### 5.4 Prompt composition
The server composes `final_prompt` from a fixed template. The user never edits the template, only their fields. Brand `generation_rules` is free text maintained by the owner.

```
{brand.generation_rules}

GARMENT: {garment_refs} show the real garment. Reproduce this garment exactly:
same colors, stripes, crest, sponsor logos, collar, cuffs, fabric texture and fit.
Do not add, remove, move, distort or redraw any logo, crest or text.
{if model_set} MODEL: The person must be the same person shown in {model_refs}: same face, hair, skin tone and body type. Only take the person from these images, not their clothing.
{if pose} POSE: Match the body pose shown in {pose_ref}. Only take the pose from this image, not the person or the clothing.
{if style} STYLE: Match the lighting, background treatment, composition and mood of {style_refs}. Do not copy people or garments from these images.
SCENE: {prompt}
{if restrictions} AVOID: {restrictions}
OUTPUT: Photorealistic e-commerce photograph, {shot_type_label_en}, aspect ratio {aspect_ratio}.
```

`{garment_refs}`, `{model_refs}`, `{pose_ref}` and `{style_refs}` are rendered from the image numbering in §5.2, e.g. `image 1 and image 2`, `images 3 to 5`, `image 6`, `image 7`. `{shot_type_label_en}` comes from this fixed table:

| Shot type | Label |
|---|---|
| `product_front` | front view of the garment alone, laid flat or on an invisible mannequin, no person |
| `product_back` | back view of the garment alone, laid flat or on an invisible mannequin, no person |
| `product_detail` | close-up detail of the garment, no person |
| `model_front` | full-body front view of the model wearing the garment |
| `model_back` | full-body back view of the model wearing the garment |
| `lifestyle` | the model wearing the garment in the described scene |

Both `prompt` and `final_prompt` are stored.

### 5.5 Rights gate (enforced in the API before enqueueing, and again in the worker before calling the provider)
A generation is **blocked** (`status = blocked_rights`, HTTP 422 `rights_not_cleared`, no provider call ever made) if any of these is true:
1. The model set is `real_person` and its rights record is not `cleared`, or `valid_until` is past.
2. The normalized prompt or restrictions (lowercase, accents removed, punctuation collapsed) contain the `subject_name` or any `alias` of **any** rights record of the brand, **unless** the selected model set is linked to that same record and it is cleared.

The blocked attempt is written to `generations` and `audit_log`. The UI names the subject and links to `/derechos` (for admins).

### 5.6 Provider abstraction
```python
class ImageGenerationRequest(BaseModel):
    final_prompt: str
    garment_image_urls: list[HttpUrl]      # signed URLs, 15 min
    model_image_urls: list[HttpUrl]
    pose_image_url: HttpUrl | None
    style_image_urls: list[HttpUrl]
    aspect_ratio: Literal["1:1","4:5","3:4","2:3","9:16","16:9"]
    variant_count: int                      # 1..4
    seed: int | None

class GeneratedImage(BaseModel):
    content: bytes
    mime_type: Literal["image/png","image/jpeg","image/webp"]
    width: int
    height: int

class ImageGenerationResult(BaseModel):
    images: list[GeneratedImage]
    provider: str
    provider_model: str
    cost_eur: Decimal | None
    latency_ms: int

class ImageProvider(Protocol):
    key: str
    max_reference_images: int
    def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult: ...
```
- Adapters live in `apps/api/kitframe/providers/image/<provider>.py`, one file each.
- `fake.py` returns fixture images and is only registered when `APP_ENV` is `test` or `local`. Startup fails if `fake` is configured in `staging` or `production`.
- The active provider and model come from `brands.provider_config.image` (§12.2). API keys come from environment variables.
- The one production provider is **FLUX.2 by Black Forest Labs** (§5.7). No other real image provider is implemented in the app.
- If the provider returns fewer images than requested, the generation still completes with what it returned and records the shortfall in `images_returned`.

### 5.7 Production image provider: FLUX.2 (Black Forest Labs)
File: `apps/api/kitframe/providers/image/bfl.py`, registered under the key `bfl`. `max_reference_images = 8`.

**Configuration** (`brands.provider_config.image`, validated by a Pydantic model):
```json
{ "provider": "bfl", "model": "flux-2-pro", "safety_tolerance": 2, "output_format": "png", "price_per_image_eur": 0.06 }
```
- `model` is one of `flux-2-pro` (default) or `flux-2-max`. Switching between them is a configuration change only (owner, Ajustes → Marca → Generación), audit-logged.
- `price_per_image_eur` is set by the owner from the current BFL price list and is used only to show an estimated cost (`cost_eur = price_per_image_eur × images_returned`); the UI labels it "Coste estimado".

**Endpoint and auth**
- Base URL from `BFL_API_BASE_URL`, default `https://api.eu.bfl.ai/v1` (EU-only routing). In `staging` and `production`, startup fails unless the host is exactly `api.eu.bfl.ai`.
- Every request carries the header `x-key: {BFL_API_KEY}`.

**Submit** — `POST {BFL_API_BASE_URL}/{model}` with JSON:
```json
{
  "prompt": "<final_prompt>",
  "input_image": "<ref 1 URL>",
  "input_image_2": "<ref 2 URL>",
  "...": "up to input_image_8, only for the references actually used, in the order of §5.2",
  "width": 1728,
  "height": 2160,
  "seed": 123456789,
  "output_format": "png",
  "safety_tolerance": 2
}
```
- Reference images are passed as presigned GET URLs of our storage, valid 15 minutes (§11.4).
- `width`/`height` come from this fixed table (multiples of 16, at most 4 megapixels, which is the model's maximum output):

| Aspect ratio | Output size |
|---|---|
| `1:1` | 2000 × 2000 |
| `4:5` | 1728 × 2160 |
| `3:4` | 1728 × 2304 |
| `2:3` | 1632 × 2448 |
| `9:16` | 1440 × 2560 |
| `16:9` | 2560 × 1440 |

- The response is `{ "id": "...", "polling_url": "..." }`.

**Polling** — the worker polls **the returned `polling_url`** (mandatory with regional endpoints; never build the URL itself) with `GET` and the same `x-key` header, every 1 second, for at most 120 seconds.
- `status = "Pending"` (or any in-progress status) → keep polling.
- `status = "Ready"` → download `result.sample` **immediately** (the URL expires after 10 minutes and must never be shown to users), verify it decodes as an image, store it as a new asset version.
- `status` containing `Moderated` → terminal, error code `provider_moderated`. The UI shows: "El proveedor ha rechazado la imagen por sus filtros de contenido. Ajusta el prompt o las referencias."
- Any other status (`Error`, `Failed`, `Task not found`, unknown) or timeout → terminal, error code `provider_error`, with the status and message stored in `error_detail`.

**Variants** — FLUX.2 returns one image per request. For N variants the adapter sends N submit requests concurrently (asyncio, at most 4 at once), with `seed = base_seed + i` for i = 0..N−1. `base_seed` is the request's seed or a random 32-bit integer, and it is stored on the generation so any result can be reproduced. If some variants fail, the generation completes with the rest; if all fail, the generation fails with the first error.

**Errors and retries**
- Network errors and HTTP 5xx: retry 2 times (backoff 2 s, 4 s).
- HTTP 429: retry 3 times (backoff 1 s, 2 s, 4 s).
- HTTP 402 (no credits): no retry, error `provider_error` with detail `bfl_out_of_credits`, and an immediate alert to admins (§19).
- BFL allows 24 concurrent tasks per account. Kitframe stays below it: at most 2 concurrent generation jobs per brand (§11.3) × 4 requests.

**Not used:** webhooks (the worker polls, so no public inbound endpoint is needed) and the global or US endpoints.

**Tests:** recorded HTTP fixtures with `respx` for submit, pending → ready, moderated, error, timeout, 402 and 429. CI never calls BFL. A nightly job on staging makes one real generation with one garment (§18).

### 5.8 DoD
- [ ] A generation with FLUX.2 on the EU endpoint completes end to end on a real FC Barcelona garment and its results appear in the product.
- [ ] Every aspect ratio produces exactly the size in the §5.7 table (tested against the real API once, then with fixtures).
- [ ] Startup refuses a BFL host other than `api.eu.bfl.ai` in `staging` and `production`.
- [ ] Every BFL fixture case in §5.7 is covered by a test, including partial variant failure.
- [ ] Preflight rejects more than 8 reference images.
- [ ] Both rights-gate rules are tested. A test asserts the provider adapter is never called for a blocked request.
- [ ] `final_prompt` is covered by snapshot tests for every combination of optional inputs.
- [ ] "Regenerar ajustando" restores every input exactly.
- [ ] Startup refuses the `fake` provider outside `test` and `local`.

---

## 6. Assets

### 6.1 Asset statuses
`studio` (generated, not yet added) → `candidate` (in the product) → `selected` (will be published) · `discarded` (hidden; can be restored from a "Descartadas" filter).

Real photos are uploaded directly as `candidate`.

### 6.2 Asset versions
- Every file is an immutable `asset_versions` row. `assets.current_version_id` points to the active one.
- New versions come from: manual upload ("Subir nueva versión"), background removal, or auto-crop for a channel.
- The asset viewer lists versions; any older version can be made current again (this creates no file, only moves the pointer, and is audit-logged).
- QC always refers to a specific version. When the current version changes, the asset's QC state is the latest run on the new version (none → `pending`).

### 6.3 Operations
- **Quitar fondo (background removal):** open-weight segmentation model (BiRefNet via `rembg`, version pinned in `pyproject.toml`), CPU in the worker. Produces a new version with a transparent PNG. Exports then apply the channel's background (§9.1).
- **Subir nueva versión:** the retoucher downloads the current version (original file), edits it in their own tools and uploads the result.
- **Descargar:** always the original file of the chosen version.

### 6.4 Comments and annotations
- Comments belong to a product and a phase, optionally to an asset version, optionally with a rectangle annotation (`{x, y, w, h}` normalized 0..1).
- In the asset viewer, "Comentar en la imagen" lets the user draw a rectangle and write a comment. Rectangles are shown as numbered markers on the image.
- `@mentions` of project members notify them.
- Comments can be resolved; resolved ones are collapsed but visible.
- A change request (§3.2) automatically creates a comment with the reviewer's text.

### 6.5 Upload rules
- Images: JPEG, PNG, WebP, TIFF; max 50 MB; type checked by content (magic bytes), not by extension. TIFF is converted to PNG on upload for display; the original is kept.
- Documents: PDF, XLSX; max 25 MB.
- Browser uploads go directly to object storage with a presigned PUT (§11.4). The API then registers the file and verifies size, type and SHA-256 with a server-side read.

### 6.6 DoD
- [ ] Version history and restore work and are audit-logged.
- [ ] Background removal produces a correct transparent PNG on real product photos.
- [ ] Annotations display correctly at any viewer zoom level.
- [ ] A spoofed file extension is rejected.

---

## 7. Quality control (QC)

QC runs in the worker (Python), on CPU, and is deterministic for the same inputs.

### 7.1 Checks
Each check returns `pass`, `needs_review` or `fail` plus its measurements. **Overall result = the worst check result.** Thresholds come from `brands.qc_config` (defaults in §12.2) and a snapshot is stored in each run.

| Check | Applies when | Method | Pass / review / fail |
|---|---|---|---|
| Resolution | Always | Short side of the image | ≥ `min_short_side_px` (real photos) or ≥ `min_short_side_px_generated` (generated images, whose maximum size is fixed by the provider, §5.7) pass, otherwise fail |
| Color | A golden entry exists | §7.2 | ΔE ≤ `pass_max_delta_e` pass; ≤ `review_max_delta_e` review; above that fail |
| Crest | The golden entry has a crest box | §7.3 | Confidence ≥ `pass_min_confidence` and position OK → pass; confidence ≥ `review_min_confidence` or position off → review; otherwise fail |

**Golden entry selection:** same brand, the product's `garment_category`, `approved`, same shot type. For `model_back`, `lifestyle` and `product_detail`, use `model_front` or `product_front` for color only (crest check skipped). If no golden entry is available, only resolution runs and the overall result is capped at `needs_review` with reason `no_golden_reference`.

### 7.2 Color algorithm
1. Garment mask on both images with a clothes-segmentation model (open-weight SegFormer fine-tuned for clothing, pinned version). For `product_*` shots on plain backgrounds, the background-removal mask is used instead.
2. Exclude pixels inside the crest box (if any), and very dark and very bright pixels (L* < 5 or L* > 95).
3. Convert to CIE Lab (D65). Run k-means with k = `color.clusters` (default 3) on the golden mask; store centroids and weights in `reference_colors` at golden upload time.
4. On the candidate, run k-means with the same k and match clusters to golden clusters with the Hungarian algorithm on ΔE2000.
5. Score = weight-averaged ΔE2000 of matched pairs. This handles striped blaugrana garments, where a single mean color would be meaningless.

### 7.3 Crest algorithm
1. Template = golden crest crop (stored at golden upload).
2. SIFT keypoints on template and candidate (OpenCV), ratio test 0.75, RANSAC homography.
3. Confidence = inliers / template keypoints, clamped to 0..1. If fewer than 8 inliers, fall back to multi-scale normalized template matching (scales 0.5–2.0, step 0.1) and use the peak correlation as confidence.
4. Position (only for `product_front` and `product_back` against a golden entry of the same shot type): projected crest box center distance ≤ `position_tolerance` (normalized), and area ratio within 0.8–1.25. For model shots, position is not checked (poses vary); only presence and fidelity count.
5. The detected box is stored in the run so the UI can draw it on the image.

### 7.4 Override
Admins and owners can override a `needs_review` or `fail` result with a mandatory reason (≥ 10 chars). The override is stored in `qc_overrides` and the audit log, and the badge shows "Aprobado manualmente" with the reason on hover. An override applies only to that version.

### 7.5 When QC runs
- Automatically after: generation, upload of a real photo, new version, background removal.
- Manually: "Repetir QC" in the asset viewer.
- Changing a threshold does not re-run anything automatically; the brand settings screen offers "Repetir QC de los productos en Retoque y QC".

### 7.6 DoD
- [ ] Unit tests for ΔE2000 against published reference values.
- [ ] Fixture tests: a correct blaugrana jersey passes color; the same jersey with hue shifted 15° fails; a jersey with the crest removed fails crest; a crest shifted 10% fails position on product shots.
- [ ] The run stores the thresholds used and the detected crest box.
- [ ] Override requires a reason and is audit-logged.
- [ ] QC of one image completes in under 15 s on the production worker (§21).

---

## 8. Extraction and copy

### 8.1 LLM access: Mistral
- One adapter interface `LLMClient.complete_json(system: str, user: str, json_schema: dict, schema_name: str, images: list[bytes] | None = None, temperature: float = 0.0) -> dict`. The only real implementation is `apps/api/kitframe/providers/llm/mistral.py` (key `mistral`); `fake.py` exists for `test`/`local` only, with the same startup guard as images.
- **Configuration** (`brands.provider_config.llm`):
  ```json
  { "provider": "mistral", "model": "mistral-large-2512" }
  ```
  - Always a **pinned** model id, never a `-latest` alias, so behavior never changes without a deliberate config change. `mistral-large-2512` is Mistral Large 3.
  - Escalation: if the extraction evaluation (§8.4) is below 95% field accuracy on required fields, set the model to `mistral-medium-2604` (Mistral Medium 3.5) and re-run the evaluation. No code change.
- **Endpoint and auth:** `POST {MISTRAL_API_BASE_URL}/chat/completions`, default base URL `https://api.mistral.ai/v1`, header `Authorization: Bearer {MISTRAL_API_KEY}`.
- **Request body:**
  ```json
  {
    "model": "mistral-large-2512",
    "temperature": 0.0,
    "max_tokens": 8192,
    "messages": [
      { "role": "system", "content": "<system prompt>" },
      { "role": "user", "content": [
          { "type": "text", "text": "<user prompt>" },
          { "type": "image_url", "image_url": "data:image/png;base64,<...>" }
      ] }
    ],
    "response_format": {
      "type": "json_schema",
      "json_schema": { "name": "<schema_name>", "schema": { }, "strict": true }
    }
  }
  ```
  - Temperature `0.0` for extraction, `0.4` for copy.
  - **Strict schema rules** (required by `strict: true`; the schema generator must always emit them): every object has `"additionalProperties": false`; every property is listed in `required`; optional values are expressed as nullable types (`["string","null"]`), never by omitting them from `required`. A unit test validates every generated schema against these rules.
- **Images:** PNG, pages rendered at 150 dpi, at most 20 MB per image and at most 8 images per call. Longer scanned documents are processed in batches of 8 pages and the results merged (a field keeps the value with the highest confidence).
- **Response:** parse `choices[0].message.content` as JSON and validate it with the Pydantic model derived from the same schema. On a parse or validation failure, retry once; then fail the job with `llm_invalid_output`.
- **Errors:** timeout 60 s; network errors and 5xx retry 2 times (2 s, 4 s); 429 retry 3 times (1 s, 2 s, 4 s); 401/403 fail immediately with an alert to admins.
- **Usage:** `usage.prompt_tokens` and `usage.completion_tokens` are stored in the job record for cost tracking.
- **Tests:** recorded HTTP fixtures with `respx`; CI never calls Mistral.
- **Alt text:** the same client generates the `es`, `ca` and `en` alt text of each selected asset from the product data and the shot type (text only, no image sent), when the asset becomes `selected`. Editors can edit it; edited values are never overwritten.

### 8.2 Extraction
1. Convert the document: PDF → text with layout (PyMuPDF), falling back to page images when a page has fewer than 50 characters (scanned page); XLSX → one markdown table per sheet (openpyxl); images → sent as images.
2. The JSON schema is **generated from `brands.taxonomy_schema`**. For each field it asks for `{value, confidence (0..1), source_quote}`. Never hand-write per-field prompts.
3. Deterministic validation after the model responds:
   - Values are validated against the field type and enum values; invalid values → `null`, confidence 0.
   - If `source_quote` is not found in the extracted text (normalized comparison), confidence is capped at 0.5. Image-only documents skip this check but are capped at 0.8.
4. A document can contain several products (one row per reference in an XLSX). Extraction returns a list; each item creates or updates a product in the project, matched by `internal_reference`. Existing products in `data` phase are updated and their changes listed; products past `data` are never overwritten (the result is attached as a new source document with a warning).
5. Variants are extracted when color/size/SKU columns exist.

### 8.3 Copy and translations
- Input: structured data, glossary, brand tone notes (`glossary.tone`, free text).
- Output per locale (`es`, `ca`, `en`): `name`, `description` (80–200 words), `seo_title` (≤ 70 chars), `seo_meta` (≤ 160 chars), `seo_keywords` (3–8).
- Glossary: `{ "do_not_translate": ["Spotify", "Blaugrana", ...], "preferred": { "es": {...}, "ca": {...}, "en": {...} } }`. After generation, check that every do-not-translate term present in the source appears unchanged in each locale. If not, regenerate once; if still wrong, save and flag the field with warning `glossary_violation` for the editor.
- Length limits are enforced by truncation at a word boundary after one regeneration attempt.
- The editor sees the three locales side by side and can edit any field; edited fields are marked `manually_edited` and are not overwritten by "Regenerar textos" unless the user ticks "Sobrescribir cambios manuales".

### 8.4 DoD
- [ ] Extraction tested on at least 5 real client technical sheets (PDF and XLSX), including Catalan and Spanish ones, with field accuracy recorded in `docs/extraction-eval.md`; required-field accuracy ≥ 95% with the configured Mistral model (escalating per §8.1 if needed).
- [ ] Every generated JSON schema passes the strict-schema rule test.
- [ ] The source-quote confidence cap is covered by a test.
- [ ] Multi-product XLSX creates the correct products and variants.
- [ ] The glossary check is covered by a test.

---

## 9. Exports and Shopify

### 9.1 Channel specs and exports
- `channel_specs` per brand: channel, width, height, format (`jpg`, `png`, `webp`), quality, background (`white`, `transparent`, `keep`), color profile (sRGB), filename pattern.
- Filename tokens: `{reference}`, `{sku}`, `{color}`, `{shot}`, `{index}`, `{channel}`. Filenames are slugified (lowercase ASCII, hyphens).
- Rendering with `pyvips`: fit inside the target box preserving aspect ratio, pad with the background color, convert to sRGB, strip metadata except copyright (`brand.name`).
- "Exportar" on a product → choose channels → a job builds a ZIP → download link (valid 24 h).
- Exports are deterministic: same inputs → byte-identical output (tested).

### 9.2 Shopify connections
- Each brand has up to two connections: `staging` and `live`, each with store domain and Admin API access token (encrypted at rest, §17).
- `brands.active_shopify_environment` (`staging` by default) decides where publishing goes. Changing it to `live` is an owner-only action with typed confirmation of the store domain, audit-logged.
- "Probar conexión" checks credentials, required scopes and enabled locales, and shows the result.
- Admin GraphQL API version is pinned in configuration (`SHOPIFY_API_VERSION`).

### 9.3 Publishing
Implemented as a job. Steps, all idempotent:
1. Re-check the approval exit criteria (§3.4).
2. Find the Shopify product: by `products.shopify_product_id` for the active environment; otherwise search by the first variant's SKU (to adopt products created outside Kitframe); otherwise create.
3. Map with one named, unit-tested function `map_product_to_shopify(product, variants, assets, brand)`:
   - Title, description (HTML from paragraphs), vendor (`brand.name`), product type (`garment_category`), tags (normalized color, gender, category).
   - SEO title and description from `es`.
   - Variants: options from color and size, SKU, price.
   - Metafields from `brands.shopify_metafields` mapping (`[{taxonomy_key, namespace, key, type}]`).
4. Upload selected assets in `sort_order` using the rendition of the `shopify` channel spec, via staged uploads. Existing media that Kitframe previously uploaded and that are no longer selected are removed; media not created by Kitframe are left untouched.
5. Register `ca` and `en` translations for title, description and SEO fields.
6. Store Shopify IDs per environment, set `published_at`, audit-log, notify the approver and project lead.
- Any step failing → job fails with a readable error (`shopify_error` with Shopify's message), approval stays `in_review`, and the UI shows "Reintentar publicación". Retries do not create duplicates (steps 2 and 4 are idempotent).

### 9.4 DoD
- [ ] `map_product_to_shopify` has unit tests with fixture products.
- [ ] Publish tested end to end against a Shopify development store, including republish and SKU adoption.
- [ ] A failed publish followed by retry does not create duplicate products or images.
- [ ] Switching to `live` requires typed confirmation and is audit-logged.
- [ ] At least one real product published to the live store with the owner's approval (final system check, §27).

---

## 10. Notifications

### 10.1 Channels
- **In-app**: always on. Bell with unread count, inbox panel (§15.2).
- **Email**: per user and event type toggle, sent immediately by a job through SMTP (provider D6). Default ON for events marked ★.

### 10.2 Events
| Event | Recipients |
|---|---|
| `phase_assigned` ★ | New assignee |
| `submitted_for_review` ★ | Product phase reviewer, or all phase reviewers, or the lead (§3.3) |
| `changes_requested` ★ | Phase assignee, or all phase editors |
| `phase_approved` | Editors of the next phase |
| `sent_back` ★ | Editors of the target phase |
| `mentioned` ★ | Mentioned user |
| `generation_completed` / `generation_failed` | Requester |
| `qc_needs_review` | Editors of the product's current phase |
| `publish_succeeded` / `publish_failed` ★ | Approver and project lead |
| `due_soon` / `overdue` ★ | Phase assignee, or phase editors |
| `golden_set_pending` | Users with `can_approve_golden_set` |
| `extraction_completed` / `extraction_failed` | Uploader |

Notifications to the user who triggered the event are never sent.

### 10.3 DoD
- [ ] Every event is covered by a test that asserts its recipients.
- [ ] Emails are rendered from Spanish templates, contain a direct link, and failures are retried 3 times and recorded.
- [ ] Clicking a notification marks it read and opens the related screen.

---

## 11. Architecture

### 11.1 Services
| Service | Tech | Role |
|---|---|---|
| `web` | Next.js 14 (App Router), TypeScript, Tailwind, shadcn/ui, TanStack Query, next-intl | UI. Talks only to `api` |
| `api` | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async) + Alembic | HTTP API, business rules, auth. Only component that writes to the database |
| `worker` | Same codebase as `api`, started with `kitframe worker` | Runs jobs with **Procrastinate** (PostgreSQL-backed queue): extraction, copy, QC, generation, background removal, exports, publishing, emails, scheduled jobs |
| `postgres` | PostgreSQL 16 | Data and job queue |
| Object storage | S3-compatible bucket, EU region, versioning on | All files |

No other services (no Redis, no broker, no vector database).

### 11.2 Why this shape
One backend language (Python) because all image and AI work is Python. The API and the worker share models, permissions and business rules, so there is one implementation of each rule.

### 11.3 Jobs
- Every job has a row in `jobs` (§12.1) with `type`, `status`, `entity_type`, `entity_id`, `attempts`, `error_detail`, so the UI can show progress independently of the queue internals.
- Job types and retries:

| Type | Max attempts | Timeout |
|---|---|---|
| `extract_document` | 3 | 180 s |
| `generate_copy` | 3 | 120 s |
| `generate_images` | 3 | 300 s |
| `run_qc` | 2 | 60 s |
| `remove_background` | 2 | 120 s |
| `validate_reference_image` | 2 | 60 s |
| `build_export` | 2 | 300 s |
| `publish_shopify` | 3 | 300 s |
| `send_email` | 3 | 30 s |
| `daily_due_dates` (scheduled 08:00 Europe/Madrid) | 1 | 300 s |

- Permanently failed jobs appear in Ajustes → Trabajos fallidos, with "Reintentar".
- The worker runs with concurrency 4; image generation is limited to 2 concurrent jobs per brand.

### 11.4 Files
- Storage keys: `brands/{brand_id}/{kind}/{uuid}/{original_filename}`.
- Uploads: `POST /uploads/presign` returns a presigned PUT URL (valid 10 min, content type and max size bound in the signature) and a `storage_key`. The client uploads, then calls the relevant register endpoint with the key.
- Presigned GET URLs must be reachable from the internet, because FLUX.2 fetches reference images from them (§5.7). The bucket itself stays private; only signed URLs work.
- Downloads and display: presigned GET URLs valid 15 min, generated by the API when serializing. Thumbnails (400 px and 1200 px WebP) are generated by the worker for every version and used in lists.

### 11.5 Polling instead of push
- Screens with running jobs poll `GET /jobs/{id}` every 3 s while any job is `queued` or `running`, and stop when none are.
- Mis tareas, the board and the notification count refresh every 30 s while the tab is visible, and on window focus.

### 11.6 DoD
- [ ] `docker compose up` starts the whole system locally with seed data (§23) in one command.
- [ ] Killing the worker during a job and restarting it finishes or retries the job without duplicates.
- [ ] The API contains no image or ML processing on the request path (all in jobs).

---

## 12. Data model

Alembic migrations, forward-only in deployed environments. UUID v4 primary keys. All timestamps `timestamptz`. `created_at` and `updated_at` default `now()`; `updated_at` maintained by a trigger. Every foreign key has an index. Every brand-owned table has `brand_id`; the data access layer always filters by the brand of the request (§14.3).

### 12.1 Schema
```sql
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE brands (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  taxonomy_schema JSONB NOT NULL DEFAULT '{"fields": []}',
  glossary JSONB NOT NULL DEFAULT '{"do_not_translate": [], "preferred": {}, "tone": ""}',
  generation_rules TEXT NOT NULL DEFAULT '',
  required_shots JSONB NOT NULL DEFAULT '{}',        -- { "<garment_category>": ["product_front", ...] }
  qc_config JSONB NOT NULL,                          -- defaults in §12.2
  provider_config JSONB NOT NULL,                    -- shapes and defaults in §5.7 and §8.1
  shopify_metafields JSONB NOT NULL DEFAULT '[]',
  active_shopify_environment TEXT NOT NULL DEFAULT 'staging' CHECK (active_shopify_environment IN ('staging','live')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE shopify_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  environment TEXT NOT NULL CHECK (environment IN ('staging','live')),
  store_domain TEXT NOT NULL,
  access_token_encrypted BYTEA NOT NULL,
  last_checked_at TIMESTAMPTZ,
  last_check_ok BOOLEAN,
  last_check_detail JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (brand_id, environment)
);

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email CITEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  locale TEXT NOT NULL DEFAULT 'es' CHECK (locale IN ('es','ca','en')),
  token_version INT NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT true,
  last_login_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE refresh_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL UNIQUE,
  family_id UUID NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  replaced_by UUID REFERENCES refresh_tokens(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE brand_memberships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  brand_id UUID NOT NULL REFERENCES brands(id),
  role TEXT NOT NULL CHECK (role IN ('owner','admin','member','viewer')),
  can_approve_golden_set BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, brand_id)
);

CREATE TABLE invitations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  email CITEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('owner','admin','member','viewer')),
  token_hash TEXT NOT NULL UNIQUE,
  invited_by UUID NOT NULL REFERENCES users(id),
  expires_at TIMESTAMPTZ NOT NULL,
  accepted_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE password_resets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  lead_user_id UUID NOT NULL REFERENCES users(id),
  requirements JSONB NOT NULL DEFAULT '[]',          -- [{ "id": "uuid", "text": "..." }]
  phase_due_dates JSONB NOT NULL DEFAULT '{}',       -- { "data": "2026-11-01", ... }
  sample_arrival_date DATE,
  must_ship_date DATE,
  sale_date DATE,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id),
  phase TEXT NOT NULL CHECK (phase IN ('data','visuals','retouch','approval')),
  user_id UUID NOT NULL REFERENCES users(id),
  role TEXT NOT NULL CHECK (role IN ('editor','reviewer')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, phase, user_id, role),
  CHECK (NOT (phase = 'approval' AND role = 'editor'))
);

CREATE TABLE products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  project_id UUID NOT NULL REFERENCES projects(id),
  internal_reference TEXT NOT NULL,
  garment_category TEXT,
  current_phase TEXT NOT NULL DEFAULT 'data'
    CHECK (current_phase IN ('data','visuals','retouch','approval','published')),
  structured_data JSONB NOT NULL DEFAULT '{}',
  field_confidence JSONB NOT NULL DEFAULT '{}',      -- { "<key>": 0.93 }
  confirmed_fields TEXT[] NOT NULL DEFAULT '{}',
  content JSONB NOT NULL DEFAULT '{}',               -- { "es": {name, description, seo_title, seo_meta, seo_keywords, manually_edited: []}, "ca": {...}, "en": {...} }
  content_warnings JSONB NOT NULL DEFAULT '[]',
  shopify_ids JSONB NOT NULL DEFAULT '{}',           -- { "staging": {"product_id": "...", "media": {...}}, "live": {...} }
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (brand_id, internal_reference)
);
CREATE INDEX ON products (project_id, current_phase);

CREATE TABLE product_phases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES products(id),
  phase TEXT NOT NULL CHECK (phase IN ('data','visuals','retouch','approval')),
  status TEXT NOT NULL DEFAULT 'todo'
    CHECK (status IN ('todo','in_progress','in_review','changes_requested','done')),
  assignee_user_id UUID REFERENCES users(id),
  reviewer_user_id UUID REFERENCES users(id),
  submitted_by UUID REFERENCES users(id),
  due_date DATE,
  entered_at TIMESTAMPTZ,
  submitted_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (product_id, phase)
);
CREATE INDEX ON product_phases (assignee_user_id, status);
CREATE INDEX ON product_phases (reviewer_user_id, status);

CREATE TABLE reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_phase_id UUID NOT NULL REFERENCES product_phases(id),
  reviewer_user_id UUID NOT NULL REFERENCES users(id),
  decision TEXT NOT NULL CHECK (decision IN ('approved','changes_requested','sent_back')),
  target_phase TEXT CHECK (target_phase IN ('data','visuals','retouch')),
  comment TEXT,
  requirements_checked JSONB NOT NULL DEFAULT '[]',
  self_review BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (decision = 'approved' OR (comment IS NOT NULL AND length(comment) > 0)),
  CHECK ((decision = 'sent_back') = (target_phase IS NOT NULL))
);

CREATE TABLE variants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  product_id UUID NOT NULL REFERENCES products(id),
  color TEXT,
  color_normalized TEXT,
  size TEXT,
  sku TEXT NOT NULL,
  barcode TEXT,
  price_eur NUMERIC(10,2),
  compare_at_price_eur NUMERIC(10,2),
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (brand_id, sku)
);

CREATE TABLE source_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  project_id UUID NOT NULL REFERENCES projects(id),
  storage_key TEXT NOT NULL,
  file_name TEXT NOT NULL,
  file_type TEXT NOT NULL CHECK (file_type IN ('pdf','xlsx','image')),
  sha256 TEXT NOT NULL,
  extraction_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (extraction_status IN ('pending','running','completed','failed')),
  extraction_result JSONB,
  product_ids UUID[] NOT NULL DEFAULT '{}',
  error_code TEXT,
  error_detail TEXT,
  uploaded_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE rights_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  subject_type TEXT NOT NULL CHECK (subject_type IN ('player','staff','model','other')),
  subject_name TEXT NOT NULL,
  aliases TEXT[] NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'not_cleared'
    CHECK (status IN ('not_cleared','in_progress','cleared','expired')),
  valid_until DATE,
  cleared_at TIMESTAMPTZ,
  cleared_by UUID REFERENCES users(id),
  notes TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE model_reference_sets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('synthetic','real_person')),
  rights_record_id UUID REFERENCES rights_records(id),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  notes TEXT NOT NULL DEFAULT '',
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (kind = 'synthetic' OR rights_record_id IS NOT NULL)
);

CREATE TABLE reference_images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  kind TEXT NOT NULL CHECK (kind IN ('model','pose','style')),
  set_id UUID REFERENCES model_reference_sets(id),
  name TEXT NOT NULL DEFAULT '',
  tags TEXT[] NOT NULL DEFAULT '{}',
  storage_key TEXT NOT NULL,
  width INT,
  height INT,
  sha256 TEXT NOT NULL,
  phash TEXT,
  sort_order INT NOT NULL DEFAULT 0,                 -- order inside a model set; the first 3 are sent to the provider
  validation_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (validation_status IN ('pending','valid','warning','rejected')),
  validation_detail JSONB,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((kind = 'model') = (set_id IS NOT NULL))
);

CREATE TABLE generations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  product_id UUID NOT NULL REFERENCES products(id),
  requested_by UUID NOT NULL REFERENCES users(id),
  parent_generation_id UUID REFERENCES generations(id),
  provider TEXT NOT NULL,
  provider_model TEXT NOT NULL,
  target_shot_type TEXT NOT NULL,
  model_set_id UUID REFERENCES model_reference_sets(id),
  pose_reference_id UUID REFERENCES reference_images(id),
  style_reference_ids UUID[] NOT NULL DEFAULT '{}',
  garment_version_ids UUID[] NOT NULL,
  prompt TEXT NOT NULL,
  restrictions TEXT NOT NULL DEFAULT '',
  final_prompt TEXT NOT NULL,
  aspect_ratio TEXT NOT NULL,
  variant_count INT NOT NULL CHECK (variant_count BETWEEN 1 AND 4),
  seed BIGINT,
  rights_check JSONB NOT NULL,                       -- { "ok": bool, "records": [ids], "reason": "..." }
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued','running','completed','failed','blocked_rights')),
  images_returned INT,
  cost_eur NUMERIC(10,4),
  latency_ms INT,
  error_detail TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);
CREATE INDEX ON generations (product_id, created_at DESC);

CREATE TABLE assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  product_id UUID NOT NULL REFERENCES products(id),
  shot_type TEXT NOT NULL CHECK (shot_type IN
    ('product_front','product_back','product_detail','model_front','model_back','lifestyle')),
  origin TEXT NOT NULL CHECK (origin IN ('real_photo','generated')),
  generation_id UUID REFERENCES generations(id),
  status TEXT NOT NULL CHECK (status IN ('studio','candidate','selected','discarded')),
  current_version_id UUID,                           -- FK added after asset_versions
  alt_text JSONB NOT NULL DEFAULT '{}',              -- { "es": "...", "ca": "...", "en": "..." }
  sort_order INT NOT NULL DEFAULT 0,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((origin = 'generated') = (generation_id IS NOT NULL))
);
CREATE INDEX ON assets (product_id, status);

CREATE TABLE asset_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id UUID NOT NULL REFERENCES assets(id),
  version_number INT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('upload','generation','background_removal')),
  storage_key TEXT NOT NULL,
  thumb_small_key TEXT,
  thumb_large_key TEXT,
  mime_type TEXT NOT NULL,
  width INT NOT NULL,
  height INT NOT NULL,
  sha256 TEXT NOT NULL,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (asset_id, version_number)
);
ALTER TABLE assets ADD CONSTRAINT assets_current_version_fk
  FOREIGN KEY (current_version_id) REFERENCES asset_versions(id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE golden_set_images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  garment_category TEXT NOT NULL,
  shot_type TEXT NOT NULL CHECK (shot_type IN ('product_front','product_back','model_front')),
  storage_key TEXT NOT NULL,
  reference_colors JSONB,                            -- [{ "lab": [L,a,b], "weight": 0.52 }, ...]
  crest_bbox JSONB,                                  -- { "x":0..1, "y":0..1, "w":0..1, "h":0..1 }
  crest_template_key TEXT,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','archived')),
  supersedes_id UUID REFERENCES golden_set_images(id),
  created_by UUID NOT NULL REFERENCES users(id),
  approved_by UUID REFERENCES users(id),
  approved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX golden_one_approved
  ON golden_set_images (brand_id, garment_category, shot_type) WHERE status = 'approved';

CREATE TABLE qc_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_version_id UUID NOT NULL REFERENCES asset_versions(id),
  golden_set_image_id UUID REFERENCES golden_set_images(id),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed')),
  result TEXT CHECK (result IN ('pass','needs_review','fail')),
  checks JSONB,                                      -- { "resolution": {...}, "color": {...}, "crest": {...} }
  config_snapshot JSONB,
  error_detail TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);
CREATE INDEX ON qc_runs (asset_version_id, created_at DESC);

CREATE TABLE qc_overrides (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_version_id UUID NOT NULL REFERENCES asset_versions(id),
  qc_run_id UUID NOT NULL REFERENCES qc_runs(id),
  user_id UUID NOT NULL REFERENCES users(id),
  reason TEXT NOT NULL CHECK (length(reason) >= 10),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE comments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  product_id UUID NOT NULL REFERENCES products(id),
  phase TEXT NOT NULL CHECK (phase IN ('data','visuals','retouch','approval')),
  asset_version_id UUID REFERENCES asset_versions(id),
  annotation JSONB,                                  -- { "x","y","w","h" } normalized; requires asset_version_id
  author_id UUID NOT NULL REFERENCES users(id),
  body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 4000),
  mentions UUID[] NOT NULL DEFAULT '{}',
  review_id UUID REFERENCES reviews(id),
  resolved_at TIMESTAMPTZ,
  resolved_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (annotation IS NULL OR asset_version_id IS NOT NULL)
);
CREATE INDEX ON comments (product_id, created_at);

CREATE TABLE channel_specs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  channel TEXT NOT NULL,                             -- e.g. shopify, instagram_feed, instagram_story, print_retail, email
  width_px INT NOT NULL CHECK (width_px > 0),
  height_px INT NOT NULL CHECK (height_px > 0),
  format TEXT NOT NULL CHECK (format IN ('jpg','png','webp')),
  quality INT NOT NULL DEFAULT 90 CHECK (quality BETWEEN 50 AND 100),
  background TEXT NOT NULL DEFAULT 'white' CHECK (background IN ('white','transparent','keep')),
  color_profile TEXT NOT NULL DEFAULT 'sRGB',
  filename_pattern TEXT NOT NULL,
  is_primary BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (brand_id, channel),
  CHECK (NOT (format = 'jpg' AND background = 'transparent'))
);

CREATE TABLE exports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  product_id UUID NOT NULL REFERENCES products(id),
  channels TEXT[] NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','failed')),
  storage_key TEXT,
  requested_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID REFERENCES brands(id),
  type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','failed')),
  entity_type TEXT,
  entity_id UUID,
  attempts INT NOT NULL DEFAULT 0,
  error_code TEXT,
  error_detail TEXT,
  requested_by UUID REFERENCES users(id),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON jobs (entity_type, entity_id);
CREATE INDEX ON jobs (status, created_at);

CREATE TABLE notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES brands(id),
  user_id UUID NOT NULL REFERENCES users(id),
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,                            -- includes "link" (relative URL) and render params
  read_at TIMESTAMPTZ,
  email_status TEXT NOT NULL DEFAULT 'none' CHECK (email_status IN ('none','pending','sent','failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON notifications (user_id, read_at, created_at DESC);

CREATE TABLE notification_preferences (
  user_id UUID NOT NULL REFERENCES users(id),
  brand_id UUID NOT NULL REFERENCES brands(id),
  event_type TEXT NOT NULL,
  email_enabled BOOLEAN NOT NULL,
  PRIMARY KEY (user_id, brand_id, event_type)
);

CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID REFERENCES brands(id),
  user_id UUID REFERENCES users(id),
  entity_type TEXT NOT NULL,
  entity_id UUID NOT NULL,
  action TEXT NOT NULL,
  detail JSONB NOT NULL DEFAULT '{}',                -- before/after for edits
  request_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON audit_log (entity_type, entity_id, created_at DESC);
CREATE INDEX ON audit_log (brand_id, created_at DESC);
```
Add the remaining foreign-key indexes in the same migration (every `REFERENCES` column not already covered).

### 12.2 JSON shapes and defaults

**`taxonomy_schema`**
```json
{ "fields": [
  { "key": "composition", "label": {"es":"Composición"}, "type": "string", "required": true },
  { "key": "care_instructions", "label": {"es":"Cuidados"}, "type": "text", "required": true },
  { "key": "origin", "label": {"es":"Origen"}, "type": "string", "required": false },
  { "key": "garment_category", "label": {"es":"Categoría"}, "type": "enum", "values": ["jersey","training","leisure","accessories"], "required": true },
  { "key": "gender", "label": {"es":"Género"}, "type": "enum", "values": ["kids","adult_men","adult_women","unisex"], "required": true },
  { "key": "season", "label": {"es":"Temporada"}, "type": "string", "required": false }
] }
```
Field types: `string`, `text`, `number`, `boolean`, `enum`, `list`. The `garment_category` key is reserved: its value is mirrored into `products.garment_category`. The real field list is decision D4.

**`qc_config` default**
```json
{
  "resolution": { "min_short_side_px": 2000, "min_short_side_px_generated": 1440 },
  "color": { "clusters": 3, "pass_max_delta_e": 3.0, "review_max_delta_e": 6.0 },
  "crest": { "pass_min_confidence": 0.80, "review_min_confidence": 0.55, "position_tolerance": 0.05 },
  "extraction": { "confirm_below_confidence": 0.85 }
}
```
Validated with a Pydantic model on write; invalid configs are rejected with `validation_error`.

**`required_shots` example**
```json
{ "jersey": ["product_front","product_back","model_front"], "accessories": ["product_front"] }
```

### 12.3 DoD
- [ ] `alembic upgrade head` on an empty database creates everything; CI runs it on every PR.
- [ ] Every `REFERENCES` column has an index (verified by a CI query on `pg_catalog`).
- [ ] Every CHECK constraint has a test proving it rejects bad data.

---

## 13. API

### 13.1 Conventions
- Base path `/api/v1`. JSON. OpenAPI generated by FastAPI at `/api/v1/openapi.json`, docs at `/api/v1/docs` (disabled in production unless the user is an owner).
- Auth: `Authorization: Bearer <access_token>` on every route except auth, invitations and health.
- Brand scope: header `X-Brand-Id` on every brand-scoped route. The server checks membership; any resource loaded by id must belong to that brand, otherwise **404** (never 403, to avoid leaking existence).
- Lists: `?page=1&page_size=25` (max 100) → `{ "data": [...], "total": n, "page": p, "page_size": s }`.
- Timestamps ISO 8601 UTC. Money as strings with two decimals.
- Idempotency: `POST` routes that start jobs accept an `Idempotency-Key` header; a repeated key within 24 h returns the original response.
- Every response has an `X-Request-Id` header.

### 13.2 Error contract
```json
{ "error": { "code": "exit_criteria_not_met", "message": "Human-readable English message", "details": { } } }
```
The frontend maps `code` to Spanish text; it never displays `message` directly. Codes (single enum module shared with the frontend via generated types):

`validation_error` (422), `unauthorized` (401), `forbidden` (403), `not_found` (404), `conflict` (409), `rate_limited` (429, `details.retry_after`), `invalid_transition` (409), `exit_criteria_not_met` (409, `details.criteria`), `phase_locked` (409), `rights_not_cleared` (422, `details.subjects`), `requirements_not_checked` (422), `self_review_not_allowed` (403), `qc_not_passed` (409), `golden_conflict` (409), `upload_invalid` (422), `file_too_large` (413), `provider_error` (502), `shopify_error` (502), `shopify_not_configured` (409), `shopify_locale_missing` (409), `invitation_invalid` (410), `token_invalid` (401), `internal_error` (500).

### 13.3 Endpoints
Permission keys refer to §14.

```
# Health
GET    /healthz                                   public; process alive
GET    /readyz                                    public; DB + storage reachable

# Auth
POST   /auth/login                                public
POST   /auth/refresh                              public (refresh cookie + X-Requested-With header)
POST   /auth/logout                               auth
POST   /auth/forgot-password                      public; always 204
POST   /auth/reset-password                       public
GET    /invitations/{token}                       public; returns brand name, email, role
POST   /invitations/{token}/accept                public; sets name + password, logs in
GET    /me                                        auth; user + memberships
PATCH  /me                                        auth; name, locale, password (requires current_password)

# Brand & settings
GET    /brand                                     brand.read
PATCH  /brand                                     brand.manage
GET    /brand/channel-specs                       brand.read
PUT    /brand/channel-specs                       brand.manage   (replaces the full list)
GET    /brand/shopify                             brand.manage   (connections without tokens)
PUT    /brand/shopify/{environment}               brand.manage
POST   /brand/shopify/{environment}/test          brand.manage
POST   /brand/shopify/activate                    brand.manage   { environment, confirm_text }
POST   /brand/qc/rerun                            brand.manage   (re-runs QC for products in retouch)

# Members & invitations
GET    /members                                   brand.read
PATCH  /members/{membership_id}                   users.manage   { role, can_approve_golden_set }
DELETE /members/{membership_id}                   users.manage   (cannot remove the last owner)
GET    /invitations                               users.manage
POST   /invitations                               users.manage   { email, role }
DELETE /invitations/{id}                          users.manage

# Search (command palette)
GET    /search?q=                                 brand.read     products by reference, name, SKU; projects by name

# Projects
GET    /projects?status=                          brand.read
POST   /projects                                  projects.manage
GET    /projects/{id}                             brand.read
PATCH  /projects/{id}                             project.lead
POST   /projects/{id}/archive                     project.lead
GET    /projects/{id}/members                     brand.read
PUT    /projects/{id}/members                     project.lead   (full list of {phase, user_id, role})
GET    /projects/{id}/board                       brand.read     products grouped by current_phase with phase status
GET    /projects/{id}/calendar                    brand.read

# Source documents
POST   /uploads/presign                           auth           { purpose, file_name, content_type, size }
POST   /projects/{id}/source-documents            project.edit_phase:data   { storage_key, file_name }
GET    /projects/{id}/source-documents            brand.read
GET    /source-documents/{id}                     brand.read
POST   /source-documents/{id}/retry               project.edit_phase:data

# Products
GET    /projects/{id}/products?phase=&status=&assignee=me   brand.read
POST   /projects/{id}/products                    project.edit_phase:data   (manual creation)
GET    /products/{id}                             brand.read
PATCH  /products/{id}                             product.edit_data
POST   /products/{id}/confirm-fields              product.edit_data  { keys: [] }
POST   /products/{id}/generate-copy               product.edit_data  { overwrite_manual: bool }
GET    /products/{id}/checklist                   brand.read     exit criteria of the current phase
GET    /products/{id}/phases                      brand.read
PATCH  /products/{id}/phases/{phase}              project.lead   { assignee_user_id, reviewer_user_id, due_date }
POST   /products/{id}/start                       product.edit_current_phase
POST   /products/{id}/submit                      product.edit_current_phase
POST   /products/{id}/review                      product.review_current_phase
       { decision: approved|changes_requested|sent_back, comment?, target_phase?, requirements_checked: [] }
POST   /products/{id}/publish                     product.review_current_phase (phase approval) or brand.admin
       { confirm_text }   confirm_text must equal internal_reference
GET    /products/{id}/history                     brand.read     reviews + audit entries for the product
POST   /products/{id}/exports                     brand.read (members+)  { channels: [] }
GET    /exports/{id}                              brand.read

# Variants
GET    /products/{id}/variants                    brand.read
POST   /products/{id}/variants                    product.edit_data
PATCH  /variants/{id}                             product.edit_data
DELETE /variants/{id}                             product.edit_data

# Assets
GET    /products/{id}/assets?status=              brand.read
POST   /products/{id}/assets                      product.edit_assets  { storage_key, shot_type }
GET    /assets/{id}                               brand.read     includes versions, latest QC per version, override
PATCH  /assets/{id}                               product.edit_assets  { status, shot_type, sort_order, alt_text }
POST   /assets/{id}/versions                      product.edit_assets  { storage_key }
POST   /assets/{id}/current-version               product.edit_assets  { version_id }
POST   /assets/{id}/remove-background             product.edit_assets
POST   /asset-versions/{id}/qc                    product.edit_assets
POST   /asset-versions/{id}/qc-override           qc.override    { reason }
GET    /asset-versions/{id}/download              brand.read     302 to presigned URL of the original

# Comments
GET    /products/{id}/comments?phase=&asset_version_id=   brand.read
POST   /products/{id}/comments                    product.comment
POST   /comments/{id}/resolve                     product.comment

# Studio
POST   /generations/preflight                     studio.use     same body as POST /generations; returns final_prompt + issues
POST   /generations                               studio.use
GET    /generations/{id}                          brand.read     includes resulting assets
GET    /generations?product_id=                   brand.read

# Library
GET    /reference-sets?status=                    brand.read
POST   /reference-sets                            library.manage
GET    /reference-sets/{id}                       brand.read
PATCH  /reference-sets/{id}                       library.manage
POST   /reference-sets/{id}/images                library.manage  { storage_key }
GET    /reference-images?kind=pose|style&tag=     brand.read
POST   /reference-images                          library.manage  { kind: pose|style, storage_key, name, tags }
PATCH  /reference-images/{id}                     library.manage
DELETE /reference-images/{id}                     library.manage  (only if unused by any generation; otherwise 409)

# Golden set
GET    /golden-set?garment_category=&status=      brand.read
POST   /golden-set                                golden.manage   { garment_category, shot_type, storage_key }
PATCH  /golden-set/{id}                           golden.manage   { crest_bbox } (draft only)
POST   /golden-set/{id}/approve                   golden.approve
POST   /golden-set/{id}/archive                   golden.manage

# Rights
GET    /rights-records                            rights.manage
POST   /rights-records                            rights.manage
PATCH  /rights-records/{id}                       rights.manage   (status → cleared requires notes ≥ 10 chars)

# Notifications
GET    /notifications?unread=                     auth
GET    /notifications/unread-count                auth
POST   /notifications/read                        auth   { ids: [] } or { all: true }
GET    /notification-preferences                  auth
PUT    /notification-preferences                  auth

# Jobs & audit
GET    /jobs/{id}                                 brand.read
GET    /jobs?status=failed                        brand.admin
POST   /jobs/{id}/retry                           brand.admin
GET    /audit-log?entity_type=&entity_id=&user_id=   brand.admin
```

### 13.4 DoD
- [ ] A CI test fails if any route lacks a declared permission.
- [ ] A CI test fails if any error response does not match the error contract.
- [ ] Cross-brand access returns 404, covered by a test for every resource type.
- [ ] TypeScript types are generated from the OpenAPI schema in CI (`packages/api-types`) and the web build fails on drift.

---

## 14. Permissions

### 14.1 Brand roles
| Capability | viewer | member | admin | owner |
|---|---|---|---|---|
| `brand.read` (see everything in the brand) | ✓ | ✓ | ✓ | ✓ |
| Act in projects according to project assignments | | ✓ | ✓ | ✓ |
| `projects.manage` (create projects) | | | ✓ | ✓ |
| Any phase action on any project (edit, submit, review, send back) | | | ✓ | ✓ |
| `library.manage` | | | ✓ | ✓ |
| `golden.manage` (upload, draw crest box, archive) | | | ✓ | ✓ |
| `golden.approve` | | | only with `can_approve_golden_set` | only with `can_approve_golden_set` |
| `rights.manage` | | | ✓ | ✓ |
| `qc.override` | | | ✓ | ✓ |
| `brand.admin` (failed jobs, audit log) | | | ✓ | ✓ |
| `users.manage` | | | | ✓ |
| `brand.manage` (settings, Shopify, go live) | | | | ✓ |

### 14.2 Project-level permissions
| Permission | Granted to |
|---|---|
| `project.lead` | The project's lead, admins, owners |
| `project.edit_phase:<phase>` | Editors of that phase in the project, the lead, admins, owners |
| `product.edit_current_phase` | `project.edit_phase:<current_phase>`, and the phase is not `in_review` |
| `product.edit_data` | `project.edit_phase:data` while `current_phase = data`; afterwards admins and owners only |
| `product.edit_assets` | `project.edit_phase:<current_phase>` while `current_phase` is `visuals` or `retouch` |
| `product.review_current_phase` | Per §3.3 |
| `product.comment` | Any member assigned to any phase of the project, the lead, admins, owners |
| `studio.use` | Editors of `visuals` in at least one active project, admins, owners. For a given product: `product.edit_assets` on that product |

### 14.3 Implementation
- One module `kitframe/auth/permissions.py` with `can(user, permission, resource=None) -> bool` and a FastAPI dependency `require(permission, resource_loader)`. The tables above must be readable directly from that file.
- Every repository query takes a `brand_id` argument; there is no query helper without it.
- The API returns, on product payloads, an `allowed_actions` array (e.g. `["submit","comment","upload_asset"]`) computed with the same `can()` function. The UI shows buttons only from this array; it never re-implements permission logic.

### 14.4 DoD
- [ ] Every cell in §14.1 and every row in §14.2 has a positive and a negative test.
- [ ] `allowed_actions` is tested to match `can()` for every action.

---

## 15. UX and UI

### 15.0 Principles (apply to every screen)
1. **One obvious next step.** Every product screen shows exactly one primary (wine) button: the next thing this user should do. Everything else is secondary.
2. **Say what is missing.** When an action is not possible, the button is disabled with a tooltip, and a "Qué falta" checklist says exactly why.
3. **Start from the task.** The home screen is the user's own tasks, not a dashboard.
4. **Never show an action the user cannot perform.** Buttons come from `allowed_actions` (§14.3).
5. **Plain Spanish.** No technical terms in the UI ("QC" is shown as "Control de calidad" on first appearance per screen, then "QC").

### 15.1 Design system
**Brand palette:** wine `#7D1A1D` (primary buttons, active nav, key highlights), carbon `#34393F` (primary text, sidebar), sand `#D4C1AC` (accents, badges, selection rings).

**Functional palette** (never replaced by brand colors):
```
success  #2F6B3A / subtle #E4EFE2      warning  #8A6A1F / subtle #F7EDD9
danger   #A6192E / subtle #F6E2E4      info     #2B5A8C / subtle #E4EBF3
text     #444444   muted #6B655C       border   #DCD5C9
surface  #FFFFFF   sunk  #FAF8F6       raised   #F6F1E9
```
QC: `pass → success`, `needs_review → warning`, `fail → danger`, `pending → muted with spinner`. Always with text and icon, never color alone.

**Phase status chips:** `todo` "Pendiente" (muted), `in_progress` "En curso" (info), `in_review` "En revisión" (warning), `changes_requested` "Cambios solicitados" (danger), `done` "Completada" (success).

**Typography:** Inter (400/500/600/700) for all UI; Lora only for the Mis tareas greeting and empty-state titles. Both via `next/font`. Scale: Tailwind defaults `text-xs` to `text-3xl`; line height 1.5 body, 1.2 headings.

**Spacing and shape:** Tailwind 4 px unit; cards `p-6`, rows `p-4`, grids `gap-4`; radius `rounded-lg` cards/inputs, `rounded-md` buttons, `rounded-full` chips/avatars; shadows `shadow-sm` at rest, `shadow-md` for overlays only.

**Icons:** `lucide-react`, stroke 1.75, 16 px inline, 20 px in buttons, 24 px in empty states.

**Components:** shadcn/ui as base. Tokens defined only in `tailwind.config.ts`.

**i18n:** `next-intl`; `messages/es.json` complete; `ca.json` and `en.json` exist with the same keys (fall back to `es`). User locale from `users.locale`. Dates in Europe/Madrid, format `d MMM yyyy`.

### 15.2 Shell
- **Sidebar** (carbon, 240 px, collapsible to 64 px, state saved in `localStorage` with try/catch): Kitframe wordmark with the small Gathered whale mark; brand switcher only if more than one membership. Nav:
  1. **Mis tareas** (`/tareas`) — badge with count of items needing the user's action
  2. **Proyectos** (`/proyectos`)
  3. **Estudio** (`/estudio`) — only with `studio.use`
  4. **Biblioteca** (`/biblioteca`)
  5. **Derechos** (`/derechos`) — admin/owner
  6. **Ajustes** (`/ajustes`) — bottom, with user menu (perfil, notificaciones, cerrar sesión)
- **Top bar** (56 px): breadcrumb; command palette (`Ctrl/Cmd+K`, calls `/search`); notification bell with unread count opening the inbox panel (grouped Hoy / Ayer / Esta semana / Anteriores; unread items with wine left border; "Marcar todo como leído").
- **Responsive:** ≥1280 px sidebar expanded; 768–1279 px collapsed; <768 px drawer. Board becomes a phase selector + single column. Studio stacks inputs above results.

### 15.3 Shared components (build once in `apps/web/components`, reuse everywhere)
| Component | States |
|---|---|
| `PhaseStepper` | 4 phases + published; current highlighted; each step shows its status chip |
| `StatusChip` | the five phase statuses |
| `QCBadge` | pass, needs_review, fail, pending, overridden |
| `QCBreakdown` | one row per check with measurement, threshold and result; draws detected crest box on the image |
| `ConfidenceDot` | ≥ threshold green, 0.5–threshold amber, < 0.5 red; tooltip with value and source quote |
| `WhatsMissing` | checklist from `/products/{id}/checklist` with links to fix each item |
| `PrimaryActionBar` | sticky footer with the single primary action and secondary actions |
| `ReviewPanel` | drawer: auto criteria (read-only), requirements to tick, comment, Aprobar / Solicitar cambios / Devolver a fase… |
| `AssetTile` | thumbnail, shot type, QC badge, status, hover actions; selected state with sand ring |
| `AssetViewer` | full-size image, zoom, versions list, QC breakdown, comments with annotations, actions |
| `UploadDropzone` | idle, drag-over (solid wine border), uploading with progress, error |
| `JobStatus` | queued, running (elapsed time after 10 s), completed, failed with retry |
| `UserPicker` | search project/brand members, avatar + name |
| `ConfirmDialog` | simple confirm, or typed confirmation for high-stakes actions |
| `EmptyState` | icon, one line, primary action |
| `Skeleton` | shaped like the content it replaces |
| `Toast` | success/info auto-dismiss 5 s; error persists; optional "Deshacer" |

### 15.4 Auth screens
- `/login`: centered card (400 px) on `surface-sunk`, logo lockup, email, password, "¿Has olvidado la contraseña?". Wrong credentials → single banner "Email o contraseña incorrectos". Rate-limited → banner with countdown.
- `/recuperar` and `/restablecer/[token]`: email form; new password form (min 12 chars, strength hint).
- `/invitacion/[token]`: shows brand and email; asks for name and password; logs in on success. Expired → clear message and "Pide a tu administrador una nueva invitación".

### 15.5 `/tareas` — Mis tareas (home)
- Header (Lora): "Hola, {nombre}" + one line summary ("Tienes 3 revisiones pendientes y 2 productos con cambios solicitados").
- Four sections, in this order, each hidden when empty:
  1. **Para revisar** — phases `in_review` where the user can review.
  2. **Cambios solicitados** — phases `changes_requested` assigned to the user (or where they are an editor and no assignee is set).
  3. **En curso** — `in_progress` assigned to the user.
  4. **Pendientes de empezar** — `todo` in the product's current phase, assigned to the user.
- Each row: thumbnail, reference + name, project, phase chip, due date (amber ≤ 2 days, red overdue), and a button with the action ("Revisar", "Ver cambios", "Continuar", "Empezar") that opens the product on the right tab.
- Filter by project. Sort by due date.
- Admins and owners also see a compact "Proyectos activos" card list with counts per phase and overdue count.
- Empty: "No tienes nada pendiente" + link to Proyectos.

### 15.6 Projects
**`/proyectos`**: cards for active projects (name, dates, lead, progress bar by phase, overdue count); toggle "Archivados"; "Nuevo proyecto" (admins/owners).

**`/proyectos/nuevo`** — 4-step wizard with a progress indicator; each step can be saved and completed later from project settings:
1. **Datos**: name, description, lead, dates.
2. **Equipo**: one block per phase (Datos de producto, Producción visual, Retoque y QC, Aprobación final); in each, `UserPicker` for Editores and Revisores (Aprobación only Revisores). Hint: "Si una fase no tiene revisores, revisará el responsable del proyecto." Default due date per phase.
3. **Requisitos**: list of requirements (add, edit, reorder, delete), with 3 example suggestions the user can accept.
4. **Fichas técnicas**: `UploadDropzone` for PDF/XLSX/images; each file becomes a row with `JobStatus`; can be skipped.

**`/proyectos/[id]`** — header (name, dates, lead, "Ajustes del proyecto") and tabs:
- **Tablero**: 5 columns (the four phases + Publicado). Cards: thumbnail, reference, status chip, assignee avatar, due date, QC summary (e.g. "4/5 QC OK"). **No drag and drop**: phases change only through the review flow. Click → product. Filters: assignee, status, "Solo míos", text.
- **Lista**: table with the same data, sortable, with bulk actions for leads: assign editor/reviewer and set due date for the selected products' current phase.
- **Fichas**: source documents with extraction status, products created, retry.
- **Equipo**: same editor as wizard step 2.
- **Requisitos**: same editor as wizard step 3.
- **Calendario**: horizontal timeline per product with phase bars (entered → due), sample arrival / must ship / sale date markers, today marker; rows at risk (must-ship within 7 days and not in approval) have danger background.

### 15.7 `/productos/[id]` — Product
**Header:** reference and name, project link, `PhaseStepper`, current phase status chip, assignee and reviewer (editable by lead via `UserPicker`), due date.

**`WhatsMissing` card** (right below the header, collapsible when everything is OK): exit criteria of the current phase with links ("Confirmar 2 campos", "Falta foto de espalda", "1 imagen no ha pasado el QC").

**Tabs:**
- **Datos**: taxonomy fields in schema order, inline edit, `ConfidenceDot`. Fields needing confirmation grouped first under "Por confirmar" with "Confirmar" per field and "Confirmar todos". Variants table (inline edit, add row). Source document link with a side-by-side viewer (document on the left, fields on the right).
- **Textos**: three columns es / ca / en with name, description, SEO title (counter /70), meta (counter /160), keywords; glossary warnings inline; "Regenerar textos".
- **Imágenes**:
  - One section per required shot type (from `required_shots`), then "Otras".
  - Empty required slot = dashed placeholder "Falta: {shot}" with **"Subir foto"** and **"Generar en Estudio"**.
  - Filled section: `AssetTile` grid; selected assets first and ringed; drag to reorder selected assets (this sets Shopify image order); filter chips Seleccionadas / Candidatas / Descartadas.
  - Tile click → `AssetViewer` (modal, full screen on mobile): image with zoom; right panel with versions, `QCBreakdown`, comments; actions: Seleccionar/Quitar selección, Cambiar tipo de toma, Quitar fondo, Subir nueva versión, Descargar, Repetir QC, Aprobar QC manualmente (admins), Comentar en la imagen, Descartar.
  - Alt text field (es required; ca/en optional) in the viewer.
- **Revisión**: timeline of reviews, change requests and comments for all phases (newest first); comment box with @mentions; resolved comments collapsed.
- **Publicación**: target store (staging/live, read-only), Shopify link when published, last publish result, "Exportar" (channel checkboxes → ZIP).

**`PrimaryActionBar`** (sticky bottom) — the primary button is decided by this table (computed from `allowed_actions`):

| Situation | Primary button |
|---|---|
| User is editor, phase `todo` | "Empezar" |
| User is editor, phase `in_progress` | "Enviar a revisión" (disabled with tooltip "Completa lo que falta" if criteria fail) |
| User is editor, phase `changes_requested` | "Reenviar a revisión" (+ banner with the reviewer's comment at the top of the page) |
| User is editor, phase `in_review` | none; banner "En revisión por {nombre}. No se puede editar hasta que responda." |
| User is reviewer, phase `in_review` | "Revisar" → opens `ReviewPanel` |
| User is reviewer, phase `approval` `in_review` | "Revisar y publicar" → `ReviewPanel` with "Aprobar y publicar" |
| Product `published`, admin/owner | "Volver a publicar" |
| No permitted action | no button; muted text "Solo lectura" |

**`ReviewPanel`** (right drawer): section "Comprobaciones automáticas" (read-only criteria, all green or the panel explains what is red), section "Requisitos del proyecto" (checkbox per requirement, all required for Aprobar), comment field (required for Solicitar cambios / Devolver), buttons **Aprobar** (primary), **Solicitar cambios**, and for approval reviewers **Devolver a fase…** (select). In approval, "Aprobar y publicar" opens `ConfirmDialog`: "Se publicará en la tienda {staging|live} ({dominio}). Escribe la referencia {ref} para confirmar." Then the bar shows `JobStatus` "Publicando…" (never optimistic).

### 15.8 `/estudio` — Studio
Layout at ≥1280 px: three areas.
- **Left panel (380 px, scrollable form):**
  1. Producto (combobox; preselected from URL) with phase chip; warning if not in `visuals`.
  2. Tipo de toma (select).
  3. Prenda: thumbnails of the product's real photos, click to toggle (max per provider), counter "2/4".
  4. Modelo: `ReferencePicker` showing active sets with cover photo; "Sin modelo"; "Crear modelo" link opens `/biblioteca/modelos/nuevo` in a new tab. Real-person sets show a rights chip; not-cleared ones are disabled with the reason.
  5. Pose: picker from the pose library + "Subir pose" inline (goes to library).
  6. Estilo: multi-picker (0–3) + "Subir referencia" inline.
  7. Prompt: textarea with placeholder "Describe la escena: fondo, encuadre, luz, actitud del modelo…" and 4 clickable example chips that insert text.
  8. Evitar: textarea "Qué no debe aparecer".
  9. Formato (aspect ratio buttons with small shape icons) and Variantes (1–4).
  10. "Prompt final" (collapsed, read-only, from preflight).
  11. Issues from preflight (danger box) above the primary button **"Generar"** (disabled while issues exist). Shows estimated cost if the provider reports cost.
- **Center (results):** current generation as a 2×2 grid; each tile shows `QCBadge` once QC finishes, and buttons "Añadir al producto", "Seleccionar", "Descartar"; click → `AssetViewer`. Button "Regenerar ajustando" above the grid.
- **Right panel (280 px, collapsible):** history of generations for this product; click to view; "Reutilizar ajustes".
- Empty state (no product): "Elige un producto para empezar" + product combobox.

### 15.9 `/biblioteca` — Library
Tabs:
- **Modelos**: grid of sets (cover, name, photo count, kind chip, rights chip). "Nuevo modelo" → `/biblioteca/modelos/nuevo`: step 1 name + kind (+ rights record picker/creator if real person); step 2 upload photos with the guidance text (§4.1), each photo shows validation result; step 3 summary + "Probar en el Estudio". Set detail: photos (add/remove), generations that used it, archive.
- **Poses**: grid, upload, rename, delete (blocked if used).
- **Estilos**: grid with tag filter, upload with tags.
- **Golden set**: grouped by category, one row per shot type showing the approved image (or "Sin referencia aprobada" warning) and any drafts. Upload → choose category + shot type → drawing step: draw the crest rectangle on the image (drag, resize handles, keyboard nudging) or tick "Esta prenda no tiene escudo" → save draft. Approvers see "Aprobar" with a `ConfirmDialog` explaining that it replaces the current reference for new QC runs. Non-admins see this tab read-only.

### 15.10 `/derechos` — Rights (admin/owner)
Dense table: subject, type, aliases, status chip (not_cleared danger, in_progress warning, cleared success, expired danger), valid until, notes, updated by/at. "Nuevo registro" dialog. Status change via row menu; changing to "Autorizado" requires notes (≥ 10 chars) and, if a valid-until date exists, shows it prominently. Rows expiring in 30 days get a warning icon.

### 15.11 `/ajustes`
Left sub-nav:
- **Marca** (owner): sections with explicit "Guardar" per section:
  - Taxonomía (field rows: label es/ca/en, key, type, required, enum values; add/remove/reorder; key immutable once products use it).
  - Glosario (do-not-translate chips, preferred terms table per locale, tone notes).
  - Reglas de generación (textarea with explanation of how it is used).
  - Tomas obligatorias (matrix category × shot type checkboxes).
  - Control de calidad (numeric inputs with plain explanations, e.g. "Diferencia de color máxima para aprobar automáticamente (ΔE)"; "Repetir QC de productos en Retoque y QC").
  - Canales de exportación (rows with preview of dimensions).
  - Shopify (staging and live connection forms, "Probar conexión" with results, active store indicator, "Pasar a tienda live" with typed confirmation; metafield mapping table).
- **Usuarios** (owner): members table (name, email, role, golden set approver toggle, last login), pending invitations, "Invitar".
- **Notificaciones** (everyone): table event × "Email" toggle, with descriptions.
- **Actividad** (admin/owner): audit log with filters (user, entity type, date).
- **Trabajos fallidos** (admin/owner): failed jobs with error, entity link, "Reintentar".
- **Mi perfil** (everyone): name, language, password.

### 15.12 Interaction rules
- **Confirmations:** low stakes (re-run QC, filters, select image) → immediate + toast. Medium (submit to review, discard asset, change assignee) → immediate + toast with "Deshacer" for 5 s where reversible (discard, assignment). High stakes (publish, go live, clear rights, approve golden set, QC override, delete) → `ConfirmDialog`, typed confirmation for publish and go live.
- **Optimistic updates** only for: select/unselect asset, reorder, mark notification read, resolve comment. Never for publishing, reviews or generation.
- **Errors:** field validation inline under the field; action results as toasts; page-level load failures as an inline error block with "Reintentar".
- **Unsaved changes:** forms with unsaved edits warn on navigation.
- **Loading:** skeletons shaped like content; no full-page spinners.

### 15.13 Accessibility
- WCAG 2.1 AA contrast for all text (verify wine on white and white on carbon).
- Full keyboard use: the board and lists are navigable with arrows/Tab; the crest box editor supports arrow-key nudging (Shift = 10×); annotations can be created with keyboard (focus image, Enter, arrows, Enter).
- Dialogs and drawers trap focus and return it on close.
- Every image has alt text (asset alt text, or "{shot type} de {referencia}").
- Status never conveyed by color alone.

### 15.14 DoD
- [ ] Every screen in §15.4–§15.11 is built against the real API with loading, empty, error and permission-restricted states.
- [ ] Every shared component in §15.3 exists once and is reused (checked by a final code search).
- [ ] The primary-action table in §15.7 is covered by component tests for every row.
- [ ] `axe-core` passes on Mis tareas, Tablero, Producto (all tabs), Estudio and Biblioteca.
- [ ] Layout verified at 1440, 1024, 768 and 375 px.
- [ ] A person who did not build the system completes the full path (§27) using only the UI, without help, and every friction point found is fixed.

---

## 16. Background and scheduled behavior summary
| Trigger | Job(s) |
|---|---|
| Source document registered | `extract_document` → creates/updates products → `generate_copy` for new products |
| Real photo uploaded / new version / background removed | thumbnails, `run_qc` |
| Generation created | `generate_images` → thumbnails + `run_qc` per image |
| Reference image uploaded | `validate_reference_image` |
| Golden image uploaded | reference color computation (inside the upload job) |
| Publish confirmed | `publish_shopify` |
| Export requested | `build_export` |
| Notification with email enabled | `send_email` |
| Daily 08:00 Europe/Madrid | `daily_due_dates`; also marks rights records past `valid_until` as `expired` |

---

## 17. Security
- **Transport:** HTTPS only (HSTS, 1 year). Internal traffic on a private network.
- **Passwords:** `argon2id` (memory 64 MiB, iterations 3, parallelism 2), minimum 12 chars, checked against a list of the 10,000 most common passwords.
- **Tokens:** access JWT (HS256, 15 min, contains `sub`, `tv` = token_version) kept in memory in the web app; refresh token opaque, 30 days, httpOnly + Secure + SameSite=Strict cookie scoped to `/api/v1/auth`, rotated on every use; reuse of a rotated token revokes the whole family. Logout revokes the family; password change increments `token_version`.
- **CSRF:** the refresh endpoint requires `X-Requested-With: kitframe`; CORS allows only the web origin.
- **Rate limits** (in Postgres, per window): login 5 per email and 20 per IP per 15 min; forgot-password 3 per email per hour; generation 30 per user per hour.
- **Uploads:** presigned URLs bound to content type and size; server-side magic-byte verification; images decoded with a size limit (max 100 megapixels) to prevent decompression bombs.
- **Secrets:** only from environment variables injected by the hosting platform's secret store; `.env` files only in local development and git-ignored. Shopify tokens encrypted with AES-256-GCM using `APP_ENCRYPTION_KEY` (32 bytes, base64), with key id stored alongside for rotation.
- **Headers:** CSP (self + storage domain for images), X-Content-Type-Options, Referrer-Policy strict-origin-when-cross-origin, frame-ancestors none.
- **Data protection (GDPR):** personal data = users (email, name), rights records, and **model reference photos of real people** (the most sensitive data in the system). Document in `docs/data-protection.md`: purpose, legal basis (to be confirmed by the client), retention, and processors (hosting, storage, image provider, LLM provider, email). Deactivating a user keeps their audit history but removes login. Deleting a real-person model set deletes its photos from storage (generations keep metadata, not the photos).
- **Rights gate** enforced in API and worker (§5.5).
- **Dependencies:** `pip-audit` and `npm audit --audit-level=high` in CI, failing on high/critical. Dependabot enabled.
- **Audit:** every state change writes `audit_log` in the same transaction as the change.

### 17.1 DoD
- [ ] No secrets in the git history (gitleaks in CI).
- [ ] Refresh rotation and reuse detection tested.
- [ ] Rate limits tested.
- [ ] Security headers verified on the deployed staging environment.
- [ ] `docs/data-protection.md` written and reviewed by Gathered.

---

## 18. Testing
| Level | Scope | Tools |
|---|---|---|
| Unit | Workflow transitions and criteria, permissions, prompt composition, rights matching, QC math, Shopify mapping, filename patterns | pytest |
| Integration | Every endpoint against a real Postgres (testcontainers) and a MinIO container; job handlers with fake providers | pytest, httpx |
| Frontend unit | Components, primary-action logic, form validation | Vitest, Testing Library |
| End to end | Full path (§27) on staging with the fake image provider, plus one nightly run with the real provider on one garment | Playwright |
| Accessibility | Key screens | axe-core in Playwright |
| Load | Board with 1,000 products; 20 concurrent users browsing; 10 concurrent generations | k6 |

Coverage: ≥ 80% lines on `kitframe/workflow`, `kitframe/auth`, `kitframe/qc`, `kitframe/studio`, `kitframe/shopify` (CI fails below 80% for these packages).

### 18.1 DoD
- [ ] CI blocks merges on any failing test, lint, type check or coverage drop.
- [ ] The e2e suite runs on every merge to `main` against staging.
- [ ] The load test results are recorded in `docs/performance.md` and meet §21.

---

## 19. Observability
- **Logs:** JSON, one line per event, with `request_id`, `user_id`, `brand_id`, `job_id`; to stdout, collected by the hosting platform, 30-day retention.
- **Errors:** Sentry (EU region) for web, API and worker, with release = git SHA. No PII in events (emails scrubbed).
- **Metrics:** `/metrics` (Prometheus format, protected by a token): request rate/latency/errors per route, job counts and duration per type, queue depth, QC result counts, generation cost per provider.
- **Uptime:** external check on `/readyz` every minute.
- **Alerts** (email to admins + Gathered on-call address): `/readyz` failing 3 minutes; any `publish_shopify` failure; BFL out of credits (HTTP 402) or Mistral/BFL authentication failure; failed jobs > 10 in 1 hour; queue depth > 200 for 10 minutes.

### 19.1 DoD
- [ ] A request can be followed by `request_id` across API and worker logs.
- [ ] Each alert has been triggered on purpose on staging and received.

---

## 20. Infrastructure and deployment
- **Environments:** `local` (docker compose), `staging`, `production`. Staging mirrors production at smaller size and uses the Shopify development store.
- **Hosting (provider = decision D3, EU region):**
  - Managed PostgreSQL 16 with daily backups, 14-day retention and point-in-time recovery.
  - S3-compatible bucket with versioning and server-side encryption; lifecycle rule deleting noncurrent versions after 30 days and export ZIPs after 7 days.
  - Containers for `web`, `api` (2 instances), `worker` (1 instance, 4 vCPU / 8 GB RAM minimum for QC and background removal) behind a TLS-terminating load balancer or reverse proxy (Caddy if on plain VMs).
- **Images:** one Dockerfile per app, multi-stage, non-root user, pinned base images; ML model weights downloaded at build time into the worker image (no downloads at runtime).
- **CI/CD (GitHub Actions):**
  ```
  pull_request: lint (ruff, mypy --strict on kitframe/, eslint, tsc) → tests → build images → gitleaks → pip-audit / npm audit
  push to main: all of the above → push images (tag = git SHA) → alembic upgrade on staging → deploy staging → e2e on staging
  manual workflow "deploy-production" (requires GitHub environment approval): alembic upgrade on production → deploy → smoke test (/readyz + login + load Mis tareas)
  ```
- **Migrations** must be backwards-compatible with the previous app version (expand/contract), so a deploy can be rolled back by redeploying the previous image without touching the database.
- **Runbooks** in `docs/runbooks/`: `deploy.md`, `rollback.md`, `backup-restore.md`, `rotate-secrets.md`, `incident.md`, `provider-accounts.md` (BFL and Mistral accounts, keys, credit top-up, switching FLUX.2 pro/max and Mistral models).
- **Targets:** RPO ≤ 24 h (≤ 5 min with PITR), RTO ≤ 4 h, validated by a real restore test.

### 20.1 Environment variables
```
APP_ENV=local|test|staging|production
APP_BASE_URL, API_BASE_URL
DATABASE_URL
S3_ENDPOINT, S3_REGION, S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY
JWT_SECRET (≥ 32 bytes), APP_ENCRYPTION_KEY (32 bytes base64)
BFL_API_KEY, BFL_API_BASE_URL=https://api.eu.bfl.ai/v1
MISTRAL_API_KEY, MISTRAL_API_BASE_URL=https://api.mistral.ai/v1
SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM
SHOPIFY_API_VERSION
SENTRY_DSN_API, SENTRY_DSN_WEB
METRICS_TOKEN
WORKER_CONCURRENCY=4
```
The app validates all required variables at startup (Pydantic settings) and refuses to start if any is missing or malformed.

### 20.2 DoD
- [ ] Staging and production deployed from CI only.
- [ ] Rollback performed once on staging following the runbook.
- [ ] Backup restored into a scratch database, timed, and documented.

---

## 21. Performance targets (p95, production size, measured by the load test)
| Operation | Target |
|---|---|
| Mis tareas load | < 1.0 s |
| Project board (200 products) | < 1.5 s |
| Product page | < 1.0 s |
| Any list endpoint | < 300 ms |
| Extraction of one sheet | < 90 s |
| QC of one image | < 15 s |
| Background removal of one image | < 30 s |
| Generation (4 variants) | provider latency + < 10 s of Kitframe overhead |
| Shopify publish (one product, 6 images) | < 60 s |

---

## 22. Repository layout
```
/kitframe
  /apps
    /web                 Next.js app
      /app               routes (§15)
      /components        shared components (§15.3)
      /messages          es.json, ca.json, en.json
    /api                 Python package `kitframe` (API + worker)
      /kitframe
        /api             FastAPI routers (one file per resource group of §13.3)
        /auth            tokens, passwords, permissions.py
        /workflow        transitions.py, criteria.py
        /studio          prompt.py, rights.py, service.py
        /providers
          /image         base.py, fake.py, bfl.py
          /llm           base.py, fake.py, mistral.py
        /qc              color.py, crest.py, resolution.py, runner.py
        /extraction      documents.py, schema.py, validate.py
        /content         copy.py, glossary.py
        /media           thumbnails.py, background.py, exports.py
        /shopify         client.py, mapping.py, publish.py
        /notifications   events.py, email.py, templates/
        /jobs            registry.py, handlers/
        /db              models.py, repositories/
        settings.py
      /migrations        alembic
      /scripts/spike     run_spike.py, gemini_client.py, review_sheet.py (§24)
      /tests
  /packages
    /api-types           generated TypeScript types
  /infra
    docker-compose.yml   local
    /docker              Dockerfiles
    /deploy              production/staging deployment config for provider D3
  /docs
    BUILD_SPEC.md        this file
    extraction-eval.md
    provider-spike.md
    performance.md
    data-protection.md
    /runbooks
```

---

## 23. Seed data (local and staging)
`kitframe seed` creates:
- Brand "FC Barcelona" with the example taxonomy (§12.2), glossary (`do_not_translate`: "Barça", "Blaugrana", "Spotify", "FC Barcelona", "Camp Nou"), generation rules, required shots, default QC config, provider config (`bfl` / `flux-2-pro` and `mistral` / `mistral-large-2512`, §5.7 and §8.1; `local` uses the `fake` providers unless `BFL_API_KEY` and `MISTRAL_API_KEY` are set), channel specs (`shopify` 2000×2000 jpg white primary; `instagram_feed` 1080×1350 jpg keep; `instagram_story` 1080×1920 jpg keep; `print_retail` 3000×3000 png transparent; `email` 1200×1200 jpg white).
- Users (password `Kitframe-dev-2026!`, local only): owner, admin, viewer, and members "datos@", "creativo@", "diseno@", "revisor@".
- One project "Demo 1ª equipación" with those members assigned per phase, 3 requirements, and 6 products spread across all phases, with fixture images, a golden set entry (jersey, product_front, with crest box) and QC runs covering pass, needs_review and fail.
- One synthetic model reference set (fixture photos), 3 poses, 3 style references, and one rights record not cleared ("Jugador Ejemplo").

Staging uses the same seed minus passwords (invitations sent to Gathered emails instead).

---

## 24. Validation spike (before building the Studio UI)
Purpose: confirm with real garments that FLUX.2 with reference images meets the quality bar without custom training or crest compositing, choose between `flux-2-pro` and `flux-2-max`, and tune the QC thresholds. The provider is already chosen (FLUX.2, §5.7); the spike only decides the tier and validates the approach.

**Tooling** (built by the implementer, in `apps/api/scripts/spike/`, never imported by the app):
- `run_spike.py`: reads a folder of garments and references, calls the **production** `bfl` adapter (§5.7) for each tier, and the spike-only Gemini client for comparison, saves every image with a CSV of inputs, seed, cost and latency, and runs the QC module (§7) on each result.
- `gemini_client.py`: a minimal client for Gemini 3 Pro Image ("Nano Banana Pro") through Vertex AI, used only as a quality benchmark. Model id and credentials from `SPIKE_GEMINI_MODEL` and `SPIKE_GOOGLE_APPLICATION_CREDENTIALS`. Only images of synthetic models and garments are sent to it.
- `review_sheet.py`: produces an HTML page with the images in random order and without provider names, and a form to score them, exporting the scores to CSV (blind review).

**Protocol** (results in `docs/provider-spike.md`):
1. Material: 10 real garments (at least 4 with a front crest, at least 3 striped blaugrana, 2 accessories), each with front and back product photos; 2 synthetic model reference sets (8 photos each); 3 poses; 2 style references.
2. Candidates: `flux-2-pro`, `flux-2-max` (both via the EU endpoint) and Gemini 3 Pro Image (benchmark only).
3. For each candidate and garment: 4 variants of `model_front` and 4 of `product_front`, with the prompt template of §5.4 and aspect ratio `4:5`.
4. Blind review by the client's golden set approver and one Gathered reviewer. Score each image: garment fidelity, crest correct (yes/no), color, model consistency across garments, realism, and final verdict "publishable yes/no".
5. Record QC results and their agreement with the human verdict, plus cost and latency per image.

**Decision rule:**
- A candidate **passes** if (a) ≥ 60% of its images are publishable and (b) no image judged publishable has a crest defect.
- If `flux-2-pro` passes → production uses `flux-2-pro`.
- Otherwise, if `flux-2-max` passes → production uses `flux-2-max` (configuration change only).
- If neither FLUX.2 tier passes, stop and escalate. Switching to Gemini (only possible if Google confirms EU processing and signs a DPA), crest compositing or custom training are new specification work (§1.4).
- QC thresholds are tuned so that QC `fail` never includes a human-publishable image and QC `pass` never includes a human-rejected one on this dataset; the tuned values become the brand default in `qc_config`.

---

## 25. Build order (dependencies, not calendar)
1. Repository, Docker, CI skeleton, settings, logging, Sentry (§11, §17, §19, §20, §22).
2. Data model and seed (§12, §23).
3. Auth, invitations, password reset, permissions (§14, §17).
4. Design system, shell, auth screens (§15.1–§15.4).
5. Projects, members, products, variants, phases and workflow engine with exit criteria (§3, §13).
6. Mis tareas, projects screens, product page (Datos, Textos, Revisión tabs) and review panel (§15.5–§15.7).
7. Uploads, source documents, extraction, copy generation (§8).
8. Assets, versions, background removal, comments and annotations, Imágenes tab and asset viewer (§6, §15.7).
9. Golden set and QC (§4.4, §7), Library screens (§15.9).
10. FLUX.2 adapter (§5.7) and validation spike (§24) → FLUX.2 tier and QC thresholds. It can run in parallel with steps 5–9 because it only needs the prompt template, the adapter and the QC module.
11. Rights (§15.10) and Studio (§5, §15.8).
12. Exports and Shopify publishing (§9), Publicación tab.
13. Notifications (§10), settings screens (§15.11), calendar.
14. Hardening: load test, security review, accessibility audit, alert tests, restore test, runbooks, then the system Definition of Done (§27).

---

## 26. Decisions required (cannot be settled by specification)
| # | Decision | Owner | Blocks |
|---|---|---|---|
| D1 | Image provider **decided: FLUX.2 by Black Forest Labs, EU endpoint (§5.7)**. Pending: create the BFL account, sign BFL's data processing terms and confirm API inputs are not used for training, buy credits, and choose `flux-2-pro` or `flux-2-max` with the spike (§24) | Gathered + client | Production use of the Studio (§5) |
| D2 | LLM provider **decided: Mistral, model `mistral-large-2512` (§8.1)**. Pending: create the Mistral account, sign Mistral's DPA and confirm EU processing and no training on API data, and run the extraction evaluation (§8.4) | Gathered | Production use of extraction and copy (§8) |
| D3 | Hosting provider and EU region for database, storage and containers | Gathered | Deployment (§20) |
| D4 | Final taxonomy fields, garment categories, required shots per category, Shopify metafield mapping | Client product + e-commerce teams | Seed and settings content (§12.2) |
| D5 | Named client-side golden set approver(s) and the initial golden images | Client | QC in production (§7) |
| D6 | Transactional email provider (EU) and sending domain | Gathered | Email notifications (§10) |
| D7 | Shopify development and live store access (custom app with scopes: products, files, translations, metafields read/write), and `ca`/`en` locales enabled | Client | Publishing (§9) |
| D8 | Legal basis and consent process for real-person model photos | Client legal | Use of `real_person` sets (§4.1, §17) |

Until each is resolved, the code is built behind the interfaces described; nothing else waits on them.

---

## 27. System Definition of Done
The system is ready for production when all of these are true:
- [ ] Every module DoD in this document is checked.
- [ ] Decisions D1–D7 are resolved and configured; D8 is resolved before any `real_person` set is used.
- [ ] The full path works on production with real data, performed by client users:
      create project and team → upload technical sheet → confirm extracted data and texts → submit and approve **Datos** → upload real photos and generate model images in the Studio → select images, submit and approve **Producción visual** → retouch, pass QC, submit and approve **Retoque y QC** → **Aprobar y publicar** to the staging store → owner switches to live → publish one real product to the live store.
- [ ] At least one change request and one send-back were exercised in that run.
- [ ] The golden set approver has approved the golden set and the QC thresholds from the spike.
- [ ] Alerts, backups (with a timed restore) and rollback have been tested.
- [ ] Load test meets §21; accessibility audit passes; dependency scans are clean; security headers verified.