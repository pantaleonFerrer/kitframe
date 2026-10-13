# Onboard Mistral LLM — BUILD_SPEC §8.1 / D2

## Checklist
1. Create a Mistral account; sign DPA; confirm EU processing and no training on API data.
2. Set secrets:
   - `MISTRAL_API_KEY`
   - `MISTRAL_API_BASE_URL=https://api.mistral.ai/v1`
3. Set `LLM_PROVIDER=mistral` in staging/production (never `fake`).
4. Brand config (`provider_config.llm`):
   ```json
   { "provider": "mistral", "model": "mistral-large-2512" }
   ```
   Always a pinned id (never `-latest`). Escalate to `mistral-medium-2604` only after extraction eval (§8.4).
5. Run extraction evaluation on ≥5 real sheets; record in `docs/extraction-eval.md` (target ≥95% required-field accuracy).
6. CI uses `respx` fixtures only — never call Mistral from CI.
