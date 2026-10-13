# Checklist demo Kitframe (contrato)

## Arranque (antes de la reunión)

```bash
make demo
```

Debe mostrar `IMAGE_PROVIDER=bfl` y `endpoint=AWS`.

Login: `owner@kitframe.local` / `Kitframe-dev-2026!`

El seed **sube 30 imágenes reales a S3** (camisetas, modelo, poses, estilos). Si ves thumbs rotas:

```bash
make seed
```

## Guion (8–10 min)

1. Proyecto Demo → producto **FCB-DEMO-002** (fase visuals) — fotos de prenda visibles.
2. Biblioteca → modelo sintético demo con cover.
3. Estudio: prenda + modelo + prompt (“fondo estudio gris, luz suave”) → Generar.
4. Esperar ~1–2 min → ver 4 variantes → Seleccionar / Añadir.
5. Producto → Enviar a revisión → Aprobar.
6. **Parar.** No demos Shopify ni LLM/copy.

## Si falla

| Síntoma | Fix |
|---|---|
| Thumbs rotas | `make seed` (re-sube fixtures a S3) |
| Generando… infinito | Worker caído → reiniciar `make demo` |
| Error al subir | `bash scripts/set-s3-cors.sh` |
| Provider fake | `.env` → `IMAGE_PROVIDER=bfl` + `make seed` |
