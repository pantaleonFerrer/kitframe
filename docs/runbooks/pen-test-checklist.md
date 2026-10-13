# Penetration test checklist

Use this before declaring the system complete (BUILD_SPEC Section 25). Engage an external tester for the final pass; this checklist is the internal readiness gate and the scope sheet to hand them.

## Scope

- In scope: web UI, `/v1` API, AI service (as called via API), auth cookies/JWT, Shopify webhooks, object storage signed access, admin settings
- Out of scope: third-party provider internals (Fal.ai, Shopify admin), Hetzner hypervisor, physical access

## Auth and session

- [ ] Brute-force / rate limits on login
- [ ] Refresh cookie flags (`Secure`, `HttpOnly`, `SameSite`) in production
- [ ] JWT secret strength; no default/dev secrets in staging or production
- [ ] Password reset and logout invalidate refresh tokens
- [ ] Role matrix enforced server-side (owner/admin/editor/viewer)

## Multi-tenant / brand isolation

- [ ] Cross-brand IDOR on products, assets, briefs, board
- [ ] Admin actions audit-logged

## Uploads and assets

- [ ] Malicious file upload (polyglot, oversized, unexpected MIME)
- [ ] Direct MinIO bucket listing denied publicly
- [ ] Signed URL expiry honored

## Injection and request safety

- [ ] SQL injection on search/filter endpoints
- [ ] XSS on board, comments/notes, glossary terms
- [ ] SSRF via extraction/URL fields toward cloud metadata
- [ ] Path traversal on export/download

## Webhooks and integrations

- [ ] Shopify webhook signature required (`SHOPIFY_WEBHOOK_SECRET`)
- [ ] Replay resistance where applicable

## Infrastructure

- [ ] SSH limited to `allowed_ssh_cidrs`
- [ ] Postgres and MinIO not exposed on public NICs
- [ ] TLS termination correct (no mixed content)
- [ ] Secrets not in terraform state outputs or CI logs

## AI / generation

- [ ] Rights gate cannot be bypassed by calling AI service directly from the public internet (AI should be private-network only)
- [ ] Prompt/input size limits

## Exit criteria

- [ ] No open critical or high findings
- [ ] Medium findings ticketed with owners and due dates
- [ ] Retest evidence attached to the release record
