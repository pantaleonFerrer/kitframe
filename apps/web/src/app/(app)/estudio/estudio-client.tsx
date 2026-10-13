"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useI18n } from "@/hooks/use-i18n";
import { QCBadge } from "@/components/kit/ui";

type Project = { id: string; name: string };
type Product = {
  id: string;
  internal_reference: string;
  name?: string | null;
  current_phase: string;
  garment_category?: string | null;
  project_id?: string;
  content?: { es?: { name?: string } };
};
type AssetRow = {
  id: string;
  shot_type: string;
  origin: string;
  status: string;
  current_version_id: string | null;
  url?: string | null;
};
type ModelSet = {
  id: string;
  name: string;
  kind: string;
  photo_count: number;
  cover_url?: string | null;
  rights_status?: string | null;
  usable: boolean;
};
type RefImage = {
  id: string;
  name: string;
  tags?: string[];
  url?: string | null;
  validation_status: string;
};

const SHOT_KEYS = [
  "product_front",
  "product_back",
  "product_detail",
  "model_front",
  "model_back",
  "lifestyle",
] as const;

const ISSUE_LABELS: Record<string, string> = {
  "studio.rights": "Derechos de imagen no liberados",
  "studio.too_many_references":
    "Este proveedor admite como máximo 8 imágenes de referencia; quita una referencia de estilo o una foto de prenda",
  "studio.prompt_short": "El prompt debe tener al menos 10 caracteres",
  provider_moderated:
    "El proveedor ha rechazado la imagen por sus filtros de contenido. Ajusta el prompt o las referencias.",
  provider_error: "Error del proveedor de imágenes. Inténtalo de nuevo.",
};

function Thumb({
  url,
  label,
  selected,
  disabled,
  onClick,
}: {
  url?: string | null;
  label: string;
  selected?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}) {
  const [broken, setBroken] = useState(false);
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`relative aspect-square rounded-md overflow-hidden border text-left disabled:opacity-40 ${
        selected ? "border-wine ring-2 ring-wine/30" : "border-border"
      }`}
    >
      {url && !broken ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt={label} className="h-full w-full object-cover" onError={() => setBroken(true)} />
      ) : (
        <div className="h-full w-full bg-raised flex items-end p-1.5">
          <span className="text-[10px] leading-tight text-muted">{label}</span>
        </div>
      )}
      {selected && (
        <span className="absolute top-1 right-1 rounded bg-wine text-white text-[10px] px-1.5 py-0.5">✓</span>
      )}
    </button>
  );
}

export default function EstudioClient() {
  const { te } = useI18n();
  const sp = useSearchParams();
  const preProduct = sp.get("product");
  const [projects, setProjects] = useState<Project[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [productId, setProductId] = useState(preProduct || "");
  const [product, setProduct] = useState<Product | null>(null);
  const [garments, setGarments] = useState<AssetRow[]>([]);
  const [garmentIds, setGarmentIds] = useState<string[]>([]);
  const [modelSets, setModelSets] = useState<ModelSet[]>([]);
  const [modelSetId, setModelSetId] = useState<string | null>(null);
  const [poses, setPoses] = useState<RefImage[]>([]);
  const [poseId, setPoseId] = useState<string | null>(null);
  const [styles, setStyles] = useState<RefImage[]>([]);
  const [styleIds, setStyleIds] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("");
  const [restrictions, setRestrictions] = useState("");
  const [shot, setShot] = useState(sp.get("shot") || "model_front");
  const [aspect, setAspect] = useState("4:5");
  const [variants, setVariants] = useState(4);
  const [finalPrompt, setFinalPrompt] = useState("");
  const [estimatedCost, setEstimatedCost] = useState<string | null>(null);
  const [issues, setIssues] = useState<
    { code?: string; message_key?: string; subjects?: string[]; blocking?: boolean }[]
  >([]);
  const [generationId, setGenerationId] = useState<string | null>(null);
  const [result, setResult] = useState<{
    status: string;
    assets: { id: string; status: string; url?: string | null; qc_result?: string | null }[];
    cost_eur?: string | null;
    error_detail?: string | null;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const needsModel = shot.startsWith("model_") || shot === "lifestyle";
  const modelPhotoCount = modelSets.find((m) => m.id === modelSetId)?.photo_count || 0;
  const modelRefsUsed = modelSetId ? Math.min(3, modelPhotoCount) : 0;
  const refCount = garmentIds.length + modelRefsUsed + (poseId ? 1 : 0) + styleIds.length;
  const atRefCap = refCount >= 8;

  useEffect(() => {
    api<{ data: Project[] }>("/projects").then((r) => setProjects(r.data));
    api<{ data: ModelSet[] }>("/reference-sets?status=active").then((r) => setModelSets(r.data));
    api<{ data: RefImage[] }>("/reference-images?kind=pose").then((r) => setPoses(r.data));
    api<{ data: RefImage[] }>("/reference-images?kind=style").then((r) => setStyles(r.data));
  }, []);

  useEffect(() => {
    if (projects.length === 0) return;
    Promise.all(
      projects.map((p) => api<{ data: Product[] }>(`/projects/${p.id}/products`)),
    ).then((lists) => {
      const all = lists.flatMap((r, i) =>
        r.data.map((prod) => ({ ...prod, project_id: projects[i].id })),
      );
      setProducts(all);
      if (!productId && all.length) {
        const visuals = all.find((p) => p.current_phase === "visuals");
        setProductId((visuals || all[0]).id);
      }
    });
  }, [projects, productId]);

  useEffect(() => {
    if (!productId) {
      setProduct(null);
      return;
    }
    api<Product>(`/products/${productId}`).then((p) => setProduct(p)).catch(() => setProduct(null));
  }, [productId]);

  useEffect(() => {
    if (!productId) return;
    api<{ data: AssetRow[] }>(`/products/${productId}/assets`).then((r) => {
      const real = r.data.filter((a) => a.origin === "real_photo" && a.current_version_id);
      setGarments(real);
      const preferred = ["product_front", "product_back", "product_detail"];
      const picked: string[] = [];
      for (const shotType of preferred) {
        const hit = real.find((a) => a.shot_type === shotType);
        if (hit?.current_version_id) picked.push(hit.current_version_id);
        if (picked.length >= 3) break;
      }
      if (picked.length === 0 && real[0]?.current_version_id) {
        picked.push(real[0].current_version_id);
      }
      setGarmentIds(picked.slice(0, 3));
      setResult(null);
      setGenerationId(null);
    });
  }, [productId]);

  useEffect(() => {
    if (!productId || prompt.length < 10 || garmentIds.length === 0) return;
    const t = setTimeout(() => {
      api<{
        final_prompt: string;
        issues: typeof issues;
        estimated_cost_eur: string | null;
      }>("/generations/preflight", {
        method: "POST",
        body: JSON.stringify({
          product_id: productId,
          garment_version_ids: garmentIds,
          target_shot_type: shot,
          model_set_id: modelSetId,
          pose_reference_id: poseId,
          style_reference_ids: styleIds,
          prompt,
          restrictions,
          aspect_ratio: aspect,
          variant_count: variants,
        }),
      })
        .then((r) => {
          setFinalPrompt(r.final_prompt);
          setIssues(r.issues || []);
          setEstimatedCost(r.estimated_cost_eur);
        })
        .catch(() => undefined);
    }, 500);
    return () => clearTimeout(t);
  }, [productId, prompt, restrictions, shot, aspect, variants, garmentIds, modelSetId, poseId, styleIds]);

  useEffect(() => {
    if (!generationId) return;
    const t = setInterval(() => {
      api<{
        status: string;
        assets: { id: string; status: string; url?: string | null; qc_result?: string | null }[];
        cost_eur?: string | null;
        error_detail?: string | null;
      }>(`/generations/${generationId}`).then((r) => {
        setResult(r);
        if (r.status === "completed" || r.status === "failed" || r.status === "blocked_rights") {
          clearInterval(t);
          if (r.status === "failed" && r.error_detail?.includes("provider_moderated")) {
            setApiError(ISSUE_LABELS.provider_moderated);
          } else if (r.status === "failed") {
            setApiError(ISSUE_LABELS.provider_error);
          }
        }
      });
    }, 3000);
    return () => clearInterval(t);
  }, [generationId]);

  const examples = useMemo(
    () => [
      "Fondo gris claro de estudio, luz suave frontal",
      "Modelo de pie, brazos relajados, encuadre tres cuartos",
      "Ambiente editorial limpio, sin props",
      "Luz natural lateral, actitud confiada",
    ],
    [],
  );

  const productName =
    product?.content?.es?.name ||
    products.find((p) => p.id === productId)?.name ||
    product?.internal_reference ||
    "";
  const productRef = product?.internal_reference || products.find((p) => p.id === productId)?.internal_reference;
  const phase = product?.current_phase || products.find((p) => p.id === productId)?.current_phase;
  const notInVisuals = phase && phase !== "visuals";

  if (!productId && products.length === 0) {
    return (
      <div className="max-w-lg mx-auto text-center py-20">
        <h1 className="font-serif text-2xl mb-3">Elige un producto para empezar</h1>
        <p className="text-muted">Crea o abre un producto en fase Producción visual.</p>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-7rem)] grid grid-cols-1 xl:grid-cols-[380px_1fr_280px] gap-4 animate-fade-in">
      <aside className="bg-surface border border-border rounded-lg p-4 overflow-auto space-y-4">
        <div className="space-y-2">
          <h1 className="font-semibold text-lg">Estudio</h1>
          {productRef && (
            <div className="rounded-md border border-border bg-raised p-3 space-y-1">
              <div className="text-[11px] uppercase tracking-wide text-muted">Trabajando en</div>
              <div className="font-medium leading-snug">
                {productRef}
                {productName && productName !== productRef ? ` · ${productName}` : ""}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span
                  className={`rounded px-1.5 py-0.5 ${
                    notInVisuals ? "bg-danger-subtle text-danger" : "bg-wine/10 text-wine"
                  }`}
                >
                  {te("phases", phase || "") || phase}
                </span>
                {product?.garment_category && (
                  <span className="text-muted">{te("garmentCategory", product.garment_category)}</span>
                )}
                <Link href={`/productos/${productId}`} className="text-wine underline-offset-2 hover:underline">
                  Abrir producto
                </Link>
              </div>
              {notInVisuals && (
                <p className="text-xs text-danger">
                  El producto no está en Producción visual. Solo admins pueden generar.
                </p>
              )}
            </div>
          )}
        </div>

        <label className="block text-sm">
          Producto
          <select
            className="mt-1 w-full border border-border rounded-md px-2 py-2"
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
          >
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.internal_reference}
                {p.name || p.content?.es?.name ? ` — ${p.name || p.content?.es?.name}` : ""} (
                {te("phases", p.current_phase) || p.current_phase})
              </option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          Tipo de toma
          <select
            className="mt-1 w-full border border-border rounded-md px-2 py-2"
            value={shot}
            onChange={(e) => setShot(e.target.value)}
          >
            {SHOT_KEYS.map((value) => (
              <option key={value} value={value}>
                {te("shotTypes", value)}
              </option>
            ))}
          </select>
        </label>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">Referencias de prenda</span>
            <span className="text-xs text-muted">
              {garmentIds.length}/3 · refs totales {refCount}/8
            </span>
          </div>
          <p className="text-[11px] text-muted leading-snug">
            Fotos reales de la prenda para generar (no son las imágenes definitivas del producto).
          </p>
          {garments.length === 0 ? (
            <p className="text-xs text-danger">
              No hay referencias de prenda. Súbelas en Producto → Referencias.
            </p>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {garments.map((g) => {
                const id = g.current_version_id!;
                const checked = garmentIds.includes(id);
                return (
                  <Thumb
                    key={g.id}
                    url={g.url}
                    label={te("shotTypes", g.shot_type) || g.shot_type}
                    selected={checked}
                    disabled={!checked && (garmentIds.length >= 3 || atRefCap)}
                    onClick={() => {
                      setGarmentIds((prev) =>
                        checked ? prev.filter((x) => x !== id) : [...prev, id].slice(0, 3),
                      );
                    }}
                  />
                );
              })}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">Modelo</span>
            <Link href="/biblioteca/modelos/nuevo" className="text-xs text-wine hover:underline">
              Crear modelo
            </Link>
          </div>
          {needsModel && !modelSetId && (
            <p className="text-xs text-muted">Recomendado para tomas de modelo / lifestyle.</p>
          )}
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setModelSetId(null)}
              className={`rounded-md border px-2 py-3 text-xs text-left ${
                modelSetId === null ? "border-wine ring-2 ring-wine/30" : "border-border"
              }`}
            >
              Sin modelo
            </button>
            {modelSets.map((m) => (
              <button
                key={m.id}
                type="button"
                disabled={!m.usable}
                title={!m.usable ? `Derechos: ${m.rights_status || "no liberados"}` : m.name}
                onClick={() => setModelSetId(m.id)}
                className={`rounded-md border overflow-hidden text-left disabled:opacity-40 ${
                  modelSetId === m.id ? "border-wine ring-2 ring-wine/30" : "border-border"
                }`}
              >
                <div className="aspect-[4/5] bg-raised relative">
                  {m.cover_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={m.cover_url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <div className="h-full w-full flex items-center justify-center text-[10px] text-muted p-2">
                      {m.name}
                    </div>
                  )}
                </div>
                <div className="p-1.5 space-y-0.5">
                  <div className="text-xs font-medium truncate">{m.name}</div>
                  <div className="text-[10px] text-muted flex gap-1 flex-wrap">
                    <span>{m.kind === "synthetic" ? "Sintético" : "Persona real"}</span>
                    <span>· {Math.min(3, m.photo_count)} fotos</span>
                    {m.kind === "real_person" && (
                      <span className={m.usable ? "text-wine" : "text-danger"}>
                        {m.usable ? "Autorizado" : m.rights_status || "Sin derechos"}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-sm font-medium">Pose</div>
          <div className="grid grid-cols-3 gap-2">
            <Thumb
              label="Sin pose"
              selected={poseId === null}
              onClick={() => setPoseId(null)}
            />
            {poses.map((p) => (
              <Thumb
                key={p.id}
                url={p.url}
                label={p.name || "Pose"}
                selected={poseId === p.id}
                disabled={poseId !== p.id && atRefCap}
                onClick={() => setPoseId(poseId === p.id ? null : p.id)}
              />
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">Estilo</span>
            <span className="text-xs text-muted">{styleIds.length}/2</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {styles.map((s) => {
              const checked = styleIds.includes(s.id);
              return (
                <Thumb
                  key={s.id}
                  url={s.url}
                  label={s.name || "Estilo"}
                  selected={checked}
                  disabled={!checked && (styleIds.length >= 2 || atRefCap)}
                  onClick={() => {
                    setStyleIds((prev) =>
                      checked ? prev.filter((x) => x !== s.id) : [...prev, s.id].slice(0, 2),
                    );
                  }}
                />
              );
            })}
          </div>
          {atRefCap && (
            <p className="text-xs text-danger">{ISSUE_LABELS["studio.too_many_references"]}</p>
          )}
        </div>

        <label className="block text-sm">
          Prompt
          <textarea
            className="mt-1 w-full border border-border rounded-md px-2 py-2 min-h-24"
            placeholder="Describe la escena: fondo, encuadre, luz, actitud del modelo…"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </label>
        <div className="flex flex-wrap gap-1">
          {examples.map((ex) => (
            <button
              key={ex}
              type="button"
              className="text-xs rounded-full bg-raised px-2 py-1"
              onClick={() => setPrompt(ex)}
            >
              {ex.slice(0, 28)}…
            </button>
          ))}
        </div>
        <label className="block text-sm">
          Evitar
          <textarea
            className="mt-1 w-full border border-border rounded-md px-2 py-2 min-h-16"
            value={restrictions}
            onChange={(e) => setRestrictions(e.target.value)}
          />
        </label>
        <div className="flex gap-2 flex-wrap">
          {["1:1", "4:5", "3:4", "2:3", "9:16", "16:9"].map((a) => (
            <button
              key={a}
              type="button"
              onClick={() => setAspect(a)}
              className={`text-xs border rounded-md px-2 py-1 ${aspect === a ? "border-wine text-wine" : "border-border"}`}
            >
              {a}
            </button>
          ))}
        </div>
        <label className="block text-sm">
          Variantes: {variants}
          <input
            type="range"
            min={1}
            max={4}
            value={variants}
            onChange={(e) => setVariants(Number(e.target.value))}
            className="w-full"
          />
        </label>
        {estimatedCost && (
          <p className="text-xs text-muted">Coste estimado: {estimatedCost} €</p>
        )}
        <details className="text-xs">
          <summary className="cursor-pointer text-muted">Prompt final</summary>
          <pre className="mt-2 whitespace-pre-wrap bg-raised p-2 rounded-md">{finalPrompt}</pre>
        </details>
        {(issues.length > 0 || apiError) && (
          <div className="rounded-md bg-danger-subtle text-danger text-sm p-3 space-y-1">
            {apiError && <div>{apiError}</div>}
            {issues.map((i, idx) => (
              <div key={idx}>
                {ISSUE_LABELS[i.message_key || ""] || i.message_key || "Revisa los datos"}{" "}
                {(i.subjects || []).join(", ")}
              </div>
            ))}
          </div>
        )}
        <button
          type="button"
          disabled={
            busy ||
            prompt.length < 10 ||
            garmentIds.length === 0 ||
            issues.some((i) => i.blocking)
          }
          className="w-full rounded-md bg-wine text-white py-2.5 disabled:opacity-50"
          onClick={async () => {
            setBusy(true);
            setApiError(null);
            try {
              const gen = await api<{ id: string; estimated_cost_eur?: string | null }>("/generations", {
                method: "POST",
                body: JSON.stringify({
                  product_id: productId,
                  garment_version_ids: garmentIds,
                  target_shot_type: shot,
                  model_set_id: modelSetId,
                  pose_reference_id: poseId,
                  style_reference_ids: styleIds,
                  prompt,
                  restrictions,
                  aspect_ratio: aspect,
                  variant_count: variants,
                }),
              });
              setGenerationId(gen.id);
              if (gen.estimated_cost_eur) setEstimatedCost(gen.estimated_cost_eur);
            } catch (e) {
              const err = e as Error & { code?: string };
              setApiError(ISSUE_LABELS[err.code || ""] || err.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Generar
        </button>
      </aside>

      <section className="bg-surface border border-border rounded-lg p-4 overflow-auto">
        <div className="flex items-center justify-between mb-3 gap-2">
          <div className="text-sm text-muted truncate">
            {productRef ? (
              <>
                Resultados para <span className="text-ink font-medium">{productRef}</span>
                {productName && productName !== productRef ? ` · ${productName}` : ""}
                <span className="text-muted font-normal"> · pasa a imágenes del producto al añadirlas</span>
              </>
            ) : (
              "Resultados"
            )}
          </div>
          {result?.cost_eur && (
            <p className="text-xs text-muted shrink-0">Coste estimado: {result.cost_eur} €</p>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: variants }).map((_, i) => {
            const asset = result?.assets?.[i];
            const generating =
              Boolean(generationId) &&
              result?.status !== "completed" &&
              result?.status !== "failed" &&
              result?.status !== "blocked_rights";
            return (
              <div
                key={asset?.id || `slot-${i}`}
                className="relative aspect-square rounded-lg bg-raised border border-border overflow-hidden flex flex-col"
              >
                {result?.status === "completed" && asset ? (
                  <>
                    {asset.url ? (
                      <img
                        src={asset.url}
                        alt={`Variante ${i + 1}`}
                        className="absolute inset-0 h-full w-full object-cover"
                      />
                    ) : (
                      <div className="flex-1 flex items-center justify-center text-xs text-muted">
                        Sin preview
                      </div>
                    )}
                    <div className="absolute left-2 top-2">
                      <QCBadge result={asset.qc_result || "pending"} />
                    </div>
                    <div className="absolute inset-x-0 bottom-0 flex gap-1 flex-wrap justify-center p-2 bg-gradient-to-t from-carbon/80 to-transparent">
                      <button
                        type="button"
                        className="text-xs rounded-md bg-wine text-white px-2 py-1"
                        onClick={() =>
                          void api(`/assets/${asset.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({ status: "candidate" }),
                          })
                        }
                      >
                        Añadir al producto
                      </button>
                      <button
                        type="button"
                        className="text-xs rounded-md border border-white/40 bg-white/90 px-2 py-1"
                        onClick={() =>
                          void api(`/assets/${asset.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({ status: "selected" }),
                          })
                        }
                      >
                        Seleccionar
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="flex-1 flex items-center justify-center text-xs text-muted">
                    {generating ? "Generando…" : "Sin resultados"}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <aside className="hidden xl:block bg-surface border border-border rounded-lg p-4 overflow-auto">
        <h2 className="font-medium text-sm mb-3">Historial</h2>
        <p className="text-xs text-muted">Las generaciones anteriores de este producto aparecerán aquí.</p>
      </aside>
    </div>
  );
}
