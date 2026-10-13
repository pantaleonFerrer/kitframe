# Provider onboarding (BFL + Mistral) — Kitframe v4.1

See also:
- [onboard-image-provider.md](./onboard-image-provider.md) — FLUX.2 / Black Forest Labs EU
- [onboard-llm-provider.md](./onboard-llm-provider.md) — Mistral Large

## Principles
- Real adapters: `kitframe/providers/image/bfl.py` and `kitframe/providers/llm/mistral.py`.
- `fake` is allowed only when `APP_ENV` is `local` or `test`.
- Staging/production startup fails if `fake` is configured, or if `BFL_API_BASE_URL` host ≠ `api.eu.bfl.ai`.
- Active model/provider live in `brands.provider_config`; API keys only in env secrets.
- CI never calls real providers (`respx` fixtures).
