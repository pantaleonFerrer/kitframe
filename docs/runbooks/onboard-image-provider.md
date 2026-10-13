# Onboard BFL (FLUX.2) image provider — BUILD_SPEC §5.7 / D1

## Checklist
1. Create a Black Forest Labs account and buy credits.
2. Sign BFL data processing terms; confirm API inputs are **not** used for training.
3. Prefer the **EU** endpoint only: `https://api.eu.bfl.ai/v1` (`api.eu.bfl.ai`).
4. Set secrets:
   - `BFL_API_KEY`
   - `BFL_API_BASE_URL=https://api.eu.bfl.ai/v1`
5. Set `IMAGE_PROVIDER=bfl` in staging/production (never `fake`).
6. Brand config (`Ajustes → Marca → Generación` / `provider_config.image`):
   ```json
   { "provider": "bfl", "model": "flux-2-pro", "safety_tolerance": 2, "output_format": "png", "price_per_image_eur": 0.06 }
   ```
7. Run the spike (`scripts/spike_flux2.py`) to choose `flux-2-pro` vs `flux-2-max` (§24).
8. Startup refuses any non-EU BFL host in staging/production.
9. CI uses `respx` fixtures only — never call BFL from CI.
