"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/hooks/use-i18n";

const TABS = ["modelos", "poses", "estilos", "golden"] as const;

export default function BibliotecaPage() {
  const { te } = useI18n();
  const [tab, setTab] = useState<(typeof TABS)[number]>("modelos");
  const [sets, setSets] = useState<
    { id: string; name: string; kind: string; photo_count: number; cover_url?: string | null }[]
  >([]);
  const [poses, setPoses] = useState<{ id: string; name: string }[]>([]);
  const [styles, setStyles] = useState<{ id: string; name: string; tags: string[] }[]>([]);
  const [golden, setGolden] = useState<
    { id: string; garment_category: string; shot_type: string; status: string }[]
  >([]);

  useEffect(() => {
    if (tab === "modelos") api<{ data: typeof sets }>("/reference-sets").then((r) => setSets(r.data));
    if (tab === "poses") api<{ data: typeof poses }>("/reference-images?kind=pose").then((r) => setPoses(r.data));
    if (tab === "estilos") api<{ data: typeof styles }>("/reference-images?kind=style").then((r) => setStyles(r.data));
    if (tab === "golden") api<{ data: typeof golden }>("/golden-set").then((r) => setGolden(r.data));
  }, [tab]);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-2xl font-semibold text-carbon">Biblioteca</h1>
        {tab === "modelos" && (
          <Link href="/biblioteca/modelos/nuevo" className="rounded-md bg-wine text-white px-3 py-2 text-sm">
            Nuevo modelo
          </Link>
        )}
      </div>
      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm capitalize ${tab === t ? "border-b-2 border-wine text-wine" : "text-muted"}`}
          >
            {t === "golden" ? "Golden set" : t}
          </button>
        ))}
      </div>

      {tab === "modelos" && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sets.length === 0 && (
            <div className="col-span-full text-sm text-muted">
              No hay modelos.{" "}
              <Link href="/biblioteca/modelos/nuevo" className="text-wine">
                Crear el primero
              </Link>
            </div>
          )}
          {sets.map((s) => (
            <div key={s.id} className="rounded-lg border border-border bg-surface p-4">
              <div className="h-36 rounded-md bg-raised mb-3 overflow-hidden">
                {s.cover_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={s.cover_url} alt="" className="w-full h-full object-cover" />
                ) : null}
              </div>
              <div className="font-medium">{s.name}</div>
              <div className="text-xs text-muted mt-1">
                {s.kind === "real_person" ? "Persona real" : "Sintético"} · {s.photo_count} fotos
              </div>
            </div>
          ))}
        </div>
      )}
      {tab === "poses" && (
        <div className="grid sm:grid-cols-3 gap-3">
          {poses.map((p) => (
            <div key={p.id} className="rounded-lg border border-border bg-surface p-3">
              <div className="aspect-[3/4] bg-raised rounded-md mb-2" />
              <div className="text-sm">{p.name}</div>
            </div>
          ))}
        </div>
      )}
      {tab === "estilos" && (
        <div className="grid sm:grid-cols-3 gap-3">
          {styles.map((s) => (
            <div key={s.id} className="rounded-lg border border-border bg-surface p-3">
              <div className="aspect-square bg-raised rounded-md mb-2" />
              <div className="text-sm font-medium">{s.name}</div>
              <div className="text-xs text-muted">{(s.tags || []).join(", ")}</div>
            </div>
          ))}
        </div>
      )}
      {tab === "golden" && (
        <div className="space-y-2">
          {golden.map((g) => (
            <div key={g.id} className="rounded-lg border border-border bg-surface p-4 flex justify-between">
              <div>
                <div className="font-medium">
                  {te("garmentCategory", g.garment_category)} · {te("shotTypes", g.shot_type)}
                </div>
                <div className="text-xs text-muted">{te("status", g.status) || g.status}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
