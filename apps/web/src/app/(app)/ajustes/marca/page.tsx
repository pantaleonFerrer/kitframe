"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/hooks/use-i18n";
import { FieldArea, FieldInput, FieldLabel, FieldSelect, SettingsSection } from "../_components/ui";

type TaxField = {
  key: string;
  label: { es?: string; ca?: string; en?: string };
  type: string;
  required?: boolean;
  values?: string[];
};

type Brand = {
  id: string;
  name: string;
  taxonomy_schema: { fields?: TaxField[] };
  glossary: {
    do_not_translate?: string[];
    preferred?: Record<string, Record<string, string>>;
    tone?: string;
  };
  generation_rules: string;
  required_shots: Record<string, string[]>;
  qc_config: {
    resolution?: { min_short_side_px?: number; min_short_side_px_generated?: number };
    color?: { clusters?: number; pass_max_delta_e?: number; review_max_delta_e?: number };
    crest?: {
      pass_min_confidence?: number;
      review_min_confidence?: number;
      position_tolerance?: number;
    };
    extraction?: { confirm_below_confidence?: number };
  };
  provider_config?: {
    image?: { provider?: string; model?: string; price_per_image_eur?: number };
    llm?: { provider?: string; model?: string };
  };
  shopify_metafields?: { namespace: string; key: string; field: string }[];
  active_shopify_environment: string;
};

type Channel = {
  channel: string;
  width_px: number;
  height_px: number;
  format: string;
  quality: number;
  background: string;
  color_profile: string;
  filename_pattern: string;
  is_primary: boolean;
};

type ShopifyState = {
  active_environment: string;
  connections: {
    environment: string;
    store_domain: string;
    last_checked_at?: string | null;
    last_check_ok?: boolean | null;
    last_check_detail?: unknown;
  }[];
};

const SHOTS = [
  "product_front",
  "product_back",
  "product_detail",
  "model_front",
  "model_back",
  "lifestyle",
];
const CATEGORIES = ["jersey", "training", "leisure", "accessories"];
const FIELD_TYPES = ["string", "text", "number", "boolean", "enum", "list"];

export default function MarcaPage() {
  const { te } = useI18n();
  const [brand, setBrand] = useState<Brand | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [shopify, setShopify] = useState<ShopifyState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);

  // editable copies
  const [name, setName] = useState("");
  const [fields, setFields] = useState<TaxField[]>([]);
  const [doNotTranslate, setDoNotTranslate] = useState<string[]>([]);
  const [newTerm, setNewTerm] = useState("");
  const [tone, setTone] = useState("");
  const [preferred, setPreferred] = useState<Record<string, Record<string, string>>>({
    es: {},
    ca: {},
    en: {},
  });
  const [rules, setRules] = useState("");
  const [requiredShots, setRequiredShots] = useState<Record<string, string[]>>({});
  const [qc, setQc] = useState<Brand["qc_config"]>({});
  const [imageModel, setImageModel] = useState("flux-2-pro");
  const [pricePerImage, setPricePerImage] = useState("0.06");
  const [llmModel, setLlmModel] = useState("mistral-large-2512");
  const [stagingDomain, setStagingDomain] = useState("");
  const [stagingToken, setStagingToken] = useState("");
  const [liveDomain, setLiveDomain] = useState("");
  const [liveToken, setLiveToken] = useState("");
  const [activateEnv, setActivateEnv] = useState("live");
  const [activateConfirm, setActivateConfirm] = useState("");
  const [metafields, setMetafields] = useState<{ namespace: string; key: string; field: string }[]>(
    [],
  );

  const flash = (key: string, text: string) => {
    setMsg((m) => ({ ...m, [key]: text }));
    setTimeout(() => setMsg((m) => ({ ...m, [key]: "" })), 3000);
  };

  const load = useCallback(async () => {
    try {
      const [b, ch, sh] = await Promise.all([
        api<Brand>("/brand"),
        api<{ data: Channel[] }>("/brand/channel-specs"),
        api<ShopifyState>("/brand/shopify").catch(() => null),
      ]);
      setBrand(b);
      setName(b.name);
      setFields(b.taxonomy_schema?.fields || []);
      setDoNotTranslate(b.glossary?.do_not_translate || []);
      setTone(b.glossary?.tone || "");
      setPreferred({
        es: b.glossary?.preferred?.es || {},
        ca: b.glossary?.preferred?.ca || {},
        en: b.glossary?.preferred?.en || {},
      });
      setRules(b.generation_rules || "");
      setRequiredShots(b.required_shots || {});
      setQc(b.qc_config || {});
      setImageModel(b.provider_config?.image?.model || "flux-2-pro");
      setPricePerImage(String(b.provider_config?.image?.price_per_image_eur ?? "0.06"));
      setLlmModel(b.provider_config?.llm?.model || "mistral-large-2512");
      setMetafields(b.shopify_metafields || []);
      setChannels(ch.data);
      if (sh) {
        setShopify(sh);
        const st = sh.connections.find((c) => c.environment === "staging");
        const lv = sh.connections.find((c) => c.environment === "live");
        setStagingDomain(st?.store_domain || "");
        setLiveDomain(lv?.store_domain || "");
      }
      setError(null);
    } catch (e) {
      setError((e as Error).message || "No se pudo cargar la marca");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const patchBrand = async (key: string, body: Record<string, unknown>) => {
    setSaving(key);
    try {
      const b = await api<Brand>("/brand", { method: "PATCH", body: JSON.stringify(body) });
      setBrand(b);
      flash(key, "Guardado");
    } catch (e) {
      flash(key, (e as Error).message || "Error al guardar");
    } finally {
      setSaving(null);
    }
  };

  if (error) {
    return (
      <div className="bg-danger-subtle text-danger rounded-lg p-4 space-y-2">
        <p>{error}</p>
        <button type="button" className="underline text-sm" onClick={() => void load()}>
          Reintentar
        </button>
      </div>
    );
  }

  if (!brand) {
    return <div className="text-sm text-muted p-6">Cargando marca…</div>;
  }

  const conn = (env: string) => shopify?.connections.find((c) => c.environment === env);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">Marca</h2>
        <p className="text-sm text-muted mt-1">
          Configuración de {brand.name}. Cada bloque se guarda por separado.
        </p>
      </div>

      <SettingsSection
        title="Nombre"
        onSave={() => patchBrand("name", { name })}
        saving={saving === "name"}
        message={msg.name}
      >
        <FieldLabel>
          Nombre de la marca
          <FieldInput value={name} onChange={(e) => setName(e.target.value)} />
        </FieldLabel>
      </SettingsSection>

      <SettingsSection
        title="Taxonomía"
        description="Campos estructurados del producto. La clave no debería cambiarse si ya hay productos."
        onSave={() => patchBrand("taxonomy", { taxonomy_schema: { fields } })}
        saving={saving === "taxonomy"}
        message={msg.taxonomy}
      >
        <div className="space-y-3">
          {fields.map((f, idx) => (
            <div key={`${f.key}-${idx}`} className="border border-border rounded-md p-3 space-y-2">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <FieldLabel>
                  Clave
                  <FieldInput
                    value={f.key}
                    onChange={(e) => {
                      const next = [...fields];
                      next[idx] = { ...f, key: e.target.value };
                      setFields(next);
                    }}
                  />
                </FieldLabel>
                <FieldLabel>
                  Tipo
                  <FieldSelect
                    value={f.type}
                    onChange={(e) => {
                      const next = [...fields];
                      next[idx] = { ...f, type: e.target.value };
                      setFields(next);
                    }}
                  >
                    {FIELD_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {te("fieldTypes", t)}
                      </option>
                    ))}
                  </FieldSelect>
                </FieldLabel>
                <FieldLabel>
                  Etiqueta ES
                  <FieldInput
                    value={f.label?.es || ""}
                    onChange={(e) => {
                      const next = [...fields];
                      next[idx] = { ...f, label: { ...f.label, es: e.target.value } };
                      setFields(next);
                    }}
                  />
                </FieldLabel>
                <FieldLabel>
                  Etiqueta CA
                  <FieldInput
                    value={f.label?.ca || ""}
                    onChange={(e) => {
                      const next = [...fields];
                      next[idx] = { ...f, label: { ...f.label, ca: e.target.value } };
                      setFields(next);
                    }}
                  />
                </FieldLabel>
                <FieldLabel>
                  Etiqueta EN
                  <FieldInput
                    value={f.label?.en || ""}
                    onChange={(e) => {
                      const next = [...fields];
                      next[idx] = { ...f, label: { ...f.label, en: e.target.value } };
                      setFields(next);
                    }}
                  />
                </FieldLabel>
                <label className="flex items-center gap-2 text-sm mt-6">
                  <input
                    type="checkbox"
                    checked={!!f.required}
                    onChange={(e) => {
                      const next = [...fields];
                      next[idx] = { ...f, required: e.target.checked };
                      setFields(next);
                    }}
                  />
                  Obligatorio
                </label>
                {f.type === "enum" && (
                  <div className="md:col-span-2">
                    <FieldLabel>
                      Valores (coma)
                      <FieldInput
                        value={(f.values || []).join(", ")}
                        onChange={(e) => {
                          const next = [...fields];
                          next[idx] = {
                            ...f,
                            values: e.target.value
                              .split(",")
                              .map((x) => x.trim())
                              .filter(Boolean),
                          };
                          setFields(next);
                        }}
                      />
                    </FieldLabel>
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="text-xs border rounded-md px-2 py-1"
                  disabled={idx === 0}
                  onClick={() => {
                    if (idx === 0) return;
                    const next = [...fields];
                    [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
                    setFields(next);
                  }}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="text-xs border rounded-md px-2 py-1"
                  disabled={idx === fields.length - 1}
                  onClick={() => {
                    if (idx >= fields.length - 1) return;
                    const next = [...fields];
                    [next[idx + 1], next[idx]] = [next[idx], next[idx + 1]];
                    setFields(next);
                  }}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="text-xs text-danger border border-danger/30 rounded-md px-2 py-1"
                  onClick={() => setFields(fields.filter((_, i) => i !== idx))}
                >
                  Eliminar
                </button>
              </div>
            </div>
          ))}
          <button
            type="button"
            className="text-sm rounded-md border px-3 py-1.5"
            onClick={() =>
              setFields([
                ...fields,
                {
                  key: `campo_${fields.length + 1}`,
                  label: { es: "Nuevo campo", ca: "Nou camp", en: "New field" },
                  type: "string",
                  required: false,
                },
              ])
            }
          >
            Añadir campo
          </button>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Glosario"
        description="Términos que no se traducen y preferencias por idioma."
        onSave={() =>
          patchBrand("glossary", {
            glossary: {
              do_not_translate: doNotTranslate,
              preferred,
              tone,
            },
          })
        }
        saving={saving === "glossary"}
        message={msg.glossary}
      >
        <div className="space-y-3">
          <div className="flex flex-wrap gap-1">
            {doNotTranslate.map((t) => (
              <button
                key={t}
                type="button"
                className="text-xs rounded-full bg-raised px-2 py-1"
                onClick={() => setDoNotTranslate(doNotTranslate.filter((x) => x !== t))}
                title="Quitar"
              >
                {t} ×
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <FieldInput
              placeholder="Añadir término"
              value={newTerm}
              onChange={(e) => setNewTerm(e.target.value)}
            />
            <button
              type="button"
              className="rounded-md border px-3 text-sm"
              onClick={() => {
                const t = newTerm.trim();
                if (t && !doNotTranslate.includes(t)) setDoNotTranslate([...doNotTranslate, t]);
                setNewTerm("");
              }}
            >
              Añadir
            </button>
          </div>
          <FieldLabel>
            Tono
            <FieldArea value={tone} onChange={(e) => setTone(e.target.value)} />
          </FieldLabel>
          {(["es", "ca", "en"] as const).map((loc) => (
            <FieldLabel key={loc}>
              Preferidos ({loc}) — clave=valor por línea
              <FieldArea
                value={Object.entries(preferred[loc] || {})
                  .map(([k, v]) => `${k}=${v}`)
                  .join("\n")}
                onChange={(e) => {
                  const map: Record<string, string> = {};
                  for (const line of e.target.value.split("\n")) {
                    const [k, ...rest] = line.split("=");
                    if (k?.trim()) map[k.trim()] = rest.join("=").trim();
                  }
                  setPreferred({ ...preferred, [loc]: map });
                }}
              />
            </FieldLabel>
          ))}
        </div>
      </SettingsSection>

      <SettingsSection
        title="Reglas de generación"
        description="Se anteponen al prompt del Estudio. El usuario no las edita por generación."
        onSave={() => patchBrand("rules", { generation_rules: rules })}
        saving={saving === "rules"}
        message={msg.rules}
      >
        <FieldArea value={rules} onChange={(e) => setRules(e.target.value)} />
      </SettingsSection>

      <SettingsSection
        title="Tomas obligatorias"
        description="Matriz categoría × tipo de toma para la checklist de Imágenes."
        onSave={() => patchBrand("shots", { required_shots: requiredShots })}
        saving={saving === "shots"}
        message={msg.shots}
      >
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted">
                <th className="p-2">Categoría</th>
                {SHOTS.map((s) => (
                  <th key={s} className="p-2 text-xs font-normal">
                    {te("shotTypes", s)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CATEGORIES.map((cat) => (
                <tr key={cat} className="border-t border-border">
                  <td className="p-2 font-medium">{te("garmentCategory", cat)}</td>
                  {SHOTS.map((s) => {
                    const checked = (requiredShots[cat] || []).includes(s);
                    return (
                      <td key={s} className="p-2">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => {
                            const cur = new Set(requiredShots[cat] || []);
                            if (checked) cur.delete(s);
                            else cur.add(s);
                            setRequiredShots({ ...requiredShots, [cat]: [...cur] });
                          }}
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Control de calidad"
        description="Umbrales usados en QC automático."
        onSave={() => patchBrand("qc", { qc_config: qc })}
        saving={saving === "qc"}
        message={msg.qc}
      >
        <div className="grid md:grid-cols-2 gap-3">
          <FieldLabel>
            Resolución mínima (fotos reales, px lado corto)
            <FieldInput
              type="number"
              value={qc.resolution?.min_short_side_px ?? 2000}
              onChange={(e) =>
                setQc({
                  ...qc,
                  resolution: {
                    ...qc.resolution,
                    min_short_side_px: Number(e.target.value),
                  },
                })
              }
            />
          </FieldLabel>
          <FieldLabel>
            Resolución mínima generadas (px lado corto)
            <FieldInput
              type="number"
              value={qc.resolution?.min_short_side_px_generated ?? 1440}
              onChange={(e) =>
                setQc({
                  ...qc,
                  resolution: {
                    ...qc.resolution,
                    min_short_side_px_generated: Number(e.target.value),
                  },
                })
              }
            />
          </FieldLabel>
          <FieldLabel>
            ΔE máxima para aprobar automáticamente
            <FieldInput
              type="number"
              step="0.1"
              value={qc.color?.pass_max_delta_e ?? 3}
              onChange={(e) =>
                setQc({
                  ...qc,
                  color: { ...qc.color, pass_max_delta_e: Number(e.target.value) },
                })
              }
            />
          </FieldLabel>
          <FieldLabel>
            ΔE máxima para revisión manual
            <FieldInput
              type="number"
              step="0.1"
              value={qc.color?.review_max_delta_e ?? 6}
              onChange={(e) =>
                setQc({
                  ...qc,
                  color: { ...qc.color, review_max_delta_e: Number(e.target.value) },
                })
              }
            />
          </FieldLabel>
          <FieldLabel>
            Confianza mínima del escudo (pass)
            <FieldInput
              type="number"
              step="0.01"
              value={qc.crest?.pass_min_confidence ?? 0.8}
              onChange={(e) =>
                setQc({
                  ...qc,
                  crest: { ...qc.crest, pass_min_confidence: Number(e.target.value) },
                })
              }
            />
          </FieldLabel>
          <FieldLabel>
            Confianza mínima del escudo (revisar)
            <FieldInput
              type="number"
              step="0.01"
              value={qc.crest?.review_min_confidence ?? 0.55}
              onChange={(e) =>
                setQc({
                  ...qc,
                  crest: { ...qc.crest, review_min_confidence: Number(e.target.value) },
                })
              }
            />
          </FieldLabel>
        </div>
        <button
          type="button"
          className="text-sm rounded-md border px-3 py-1.5"
          onClick={async () => {
            setSaving("qcrerun");
            try {
              await api("/brand/qc/rerun", { method: "POST", body: "{}" });
              flash("qc", "QC reencolado para productos en retoque");
            } catch (e) {
              flash("qc", (e as Error).message);
            } finally {
              setSaving(null);
            }
          }}
        >
          Repetir QC de productos en Retoque
        </button>
      </SettingsSection>

      <SettingsSection
        title="Generación (proveedores)"
        description="Modelo de imagen y LLM. Las API keys van en el entorno del servidor."
        onSave={() => {
          const imageProvider =
            imageModel === "fake-v1"
              ? "fake"
              : brand.provider_config?.image?.provider === "bfl" ||
                  imageModel.startsWith("flux-")
                ? "bfl"
                : brand.provider_config?.image?.provider || "fake";
          const llmProvider =
            llmModel === "fake-llm"
              ? "fake"
              : llmModel.startsWith("mistral-")
                ? "mistral"
                : brand.provider_config?.llm?.provider || "fake";
          return patchBrand("provider", {
            provider_config: {
              image: {
                provider: imageProvider,
                model: imageModel,
                safety_tolerance: 2,
                output_format: "png",
                price_per_image_eur: Number(pricePerImage),
              },
              llm: {
                provider: llmProvider,
                model: llmModel,
              },
            },
          });
        }}
        saving={saving === "provider"}
        message={msg.provider}
      >
        <div className="grid md:grid-cols-2 gap-3">
          <FieldLabel>
            Modelo imagen
            <FieldSelect value={imageModel} onChange={(e) => setImageModel(e.target.value)}>
              <option value="flux-2-pro">flux-2-pro</option>
              <option value="flux-2-max">flux-2-max</option>
              <option value="fake-v1">fake-v1 (local)</option>
            </FieldSelect>
          </FieldLabel>
          <FieldLabel>
            Coste estimado € / imagen
            <FieldInput value={pricePerImage} onChange={(e) => setPricePerImage(e.target.value)} />
          </FieldLabel>
          <FieldLabel>
            Modelo LLM
            <FieldSelect value={llmModel} onChange={(e) => setLlmModel(e.target.value)}>
              <option value="mistral-large-2512">mistral-large-2512</option>
              <option value="mistral-medium-2604">mistral-medium-2604</option>
              <option value="fake-llm">fake-llm (local)</option>
            </FieldSelect>
          </FieldLabel>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Canales de exportación"
        description="Dimensiones y formato por canal."
        onSave={async () => {
          setSaving("channels");
          try {
            const res = await api<{ data: Channel[] }>("/brand/channel-specs", {
              method: "PUT",
              body: JSON.stringify(channels),
            });
            setChannels(res.data);
            flash("channels", "Guardado");
          } catch (e) {
            flash("channels", (e as Error).message);
          } finally {
            setSaving(null);
          }
        }}
        saving={saving === "channels"}
        message={msg.channels}
      >
        <div className="space-y-3">
          {channels.map((c, idx) => (
            <div key={c.channel + idx} className="border border-border rounded-md p-3 grid md:grid-cols-4 gap-2">
              <FieldLabel>
                Canal
                <FieldInput
                  value={c.channel}
                  onChange={(e) => {
                    const next = [...channels];
                    next[idx] = { ...c, channel: e.target.value };
                    setChannels(next);
                  }}
                />
              </FieldLabel>
              <FieldLabel>
                Ancho
                <FieldInput
                  type="number"
                  value={c.width_px}
                  onChange={(e) => {
                    const next = [...channels];
                    next[idx] = { ...c, width_px: Number(e.target.value) };
                    setChannels(next);
                  }}
                />
              </FieldLabel>
              <FieldLabel>
                Alto
                <FieldInput
                  type="number"
                  value={c.height_px}
                  onChange={(e) => {
                    const next = [...channels];
                    next[idx] = { ...c, height_px: Number(e.target.value) };
                    setChannels(next);
                  }}
                />
              </FieldLabel>
              <FieldLabel>
                Formato
                <FieldSelect
                  value={c.format}
                  onChange={(e) => {
                    const next = [...channels];
                    next[idx] = { ...c, format: e.target.value };
                    setChannels(next);
                  }}
                >
                  <option value="jpg">jpg</option>
                  <option value="png">png</option>
                  <option value="webp">webp</option>
                </FieldSelect>
              </FieldLabel>
              <FieldLabel>
                Fondo
                <FieldSelect
                  value={c.background}
                  onChange={(e) => {
                    const next = [...channels];
                    next[idx] = { ...c, background: e.target.value };
                    setChannels(next);
                  }}
                >
                  <option value="white">white</option>
                  <option value="transparent">transparent</option>
                  <option value="keep">keep</option>
                </FieldSelect>
              </FieldLabel>
              <FieldLabel>
                Patrón nombre
                <FieldInput
                  value={c.filename_pattern}
                  onChange={(e) => {
                    const next = [...channels];
                    next[idx] = { ...c, filename_pattern: e.target.value };
                    setChannels(next);
                  }}
                />
              </FieldLabel>
              <label className="flex items-center gap-2 text-sm mt-6">
                <input
                  type="checkbox"
                  checked={c.is_primary}
                  onChange={(e) => {
                    const next = channels.map((row, i) => ({
                      ...row,
                      is_primary: i === idx ? e.target.checked : false,
                    }));
                    setChannels(next);
                  }}
                />
                Primario
              </label>
              <div className="text-xs text-muted mt-6">
                Preview: {c.width_px}×{c.height_px} {c.format}
              </div>
            </div>
          ))}
          <button
            type="button"
            className="text-sm rounded-md border px-3 py-1.5"
            onClick={() =>
              setChannels([
                ...channels,
                {
                  channel: `channel_${channels.length + 1}`,
                  width_px: 1080,
                  height_px: 1080,
                  format: "jpg",
                  quality: 90,
                  background: "white",
                  color_profile: "sRGB",
                  filename_pattern: "{reference}-{shot}-{index}-{channel}",
                  is_primary: false,
                },
              ])
            }
          >
            Añadir canal
          </button>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Shopify"
        description={`Tienda activa: ${shopify?.active_environment || brand.active_shopify_environment}`}
      >
        <div className="grid md:grid-cols-2 gap-4">
          {(["staging", "live"] as const).map((env) => {
            const isStaging = env === "staging";
            const domain = isStaging ? stagingDomain : liveDomain;
            const setDomain = isStaging ? setStagingDomain : setLiveDomain;
            const token = isStaging ? stagingToken : liveToken;
            const setToken = isStaging ? setStagingToken : setLiveToken;
            const c = conn(env);
            return (
              <div key={env} className="border border-border rounded-md p-3 space-y-2">
                <div className="font-medium">{te("environment", env)}</div>
                {c && (
                  <p className="text-xs text-muted">
                    Última prueba:{" "}
                    {c.last_check_ok === true ? "OK" : c.last_check_ok === false ? "Falló" : "—"}{" "}
                    {c.last_checked_at ? `(${new Date(c.last_checked_at).toLocaleString()})` : ""}
                  </p>
                )}
                <FieldLabel>
                  Dominio
                  <FieldInput value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="tienda.myshopify.com" />
                </FieldLabel>
                <FieldLabel>
                  Access token
                  <FieldInput
                    type="password"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="shpat_…"
                  />
                </FieldLabel>
                <div className="flex gap-2 flex-wrap">
                  <button
                    type="button"
                    className="text-sm rounded-md bg-wine text-white px-3 py-1.5"
                    onClick={async () => {
                      setSaving(`shopify-${env}`);
                      try {
                        const res = await api<ShopifyState>(`/brand/shopify/${env}`, {
                          method: "PUT",
                          body: JSON.stringify({ store_domain: domain, access_token: token || "placeholder" }),
                        });
                        setShopify(res);
                        flash("shopify", `Conexión ${env} guardada`);
                        setToken("");
                      } catch (e) {
                        flash("shopify", (e as Error).message);
                      } finally {
                        setSaving(null);
                      }
                    }}
                  >
                    Guardar {env}
                  </button>
                  <button
                    type="button"
                    className="text-sm rounded-md border px-3 py-1.5"
                    onClick={async () => {
                      try {
                        const res = await api<{ ok: boolean; detail: unknown }>(
                          `/brand/shopify/${env}/test`,
                          { method: "POST", body: "{}" },
                        );
                        flash("shopify", res.ok ? `Prueba ${env} OK` : `Prueba ${env} falló`);
                        await load();
                      } catch (e) {
                        flash("shopify", (e as Error).message);
                      }
                    }}
                  >
                    Probar conexión
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        <div className="border border-border rounded-md p-3 space-y-2 mt-3">
          <div className="font-medium">Pasar a tienda activa</div>
          <div className="grid md:grid-cols-2 gap-2">
            <FieldSelect value={activateEnv} onChange={(e) => setActivateEnv(e.target.value)}>
              <option value="staging">{te("environment", "staging")}</option>
              <option value="live">{te("environment", "live")}</option>
            </FieldSelect>
            <FieldInput
              placeholder="Escribe el dominio exacto para confirmar"
              value={activateConfirm}
              onChange={(e) => setActivateConfirm(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="text-sm rounded-md border border-danger/40 text-danger px-3 py-1.5"
            onClick={async () => {
              try {
                await api("/brand/shopify/activate", {
                  method: "POST",
                  body: JSON.stringify({ environment: activateEnv, confirm_text: activateConfirm }),
                });
                flash("shopify", `Activa: ${activateEnv}`);
                setActivateConfirm("");
                await load();
              } catch (e) {
                flash("shopify", (e as Error).message);
              }
            }}
          >
            Activar tienda
          </button>
        </div>
        <div className="space-y-2 mt-3">
          <div className="font-medium text-sm">Metafields</div>
          {metafields.map((m, idx) => (
            <div key={idx} className="grid grid-cols-3 gap-2">
              <FieldInput
                placeholder="namespace"
                value={m.namespace}
                onChange={(e) => {
                  const next = [...metafields];
                  next[idx] = { ...m, namespace: e.target.value };
                  setMetafields(next);
                }}
              />
              <FieldInput
                placeholder="key"
                value={m.key}
                onChange={(e) => {
                  const next = [...metafields];
                  next[idx] = { ...m, key: e.target.value };
                  setMetafields(next);
                }}
              />
              <FieldInput
                placeholder="field Kitframe"
                value={m.field}
                onChange={(e) => {
                  const next = [...metafields];
                  next[idx] = { ...m, field: e.target.value };
                  setMetafields(next);
                }}
              />
            </div>
          ))}
          <div className="flex gap-2">
            <button
              type="button"
              className="text-sm border rounded-md px-3 py-1.5"
              onClick={() => setMetafields([...metafields, { namespace: "custom", key: "", field: "" }])}
            >
              Añadir metafield
            </button>
            <button
              type="button"
              className="text-sm rounded-md bg-wine text-white px-3 py-1.5"
              onClick={() => patchBrand("shopify", { shopify_metafields: metafields })}
            >
              Guardar metafields
            </button>
          </div>
        </div>
        {msg.shopify && <p className="text-xs text-wine">{msg.shopify}</p>}
      </SettingsSection>
    </div>
  );
}
