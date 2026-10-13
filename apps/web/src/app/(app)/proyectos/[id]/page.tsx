"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useI18n } from "@/hooks/use-i18n";
import { StatusChip } from "@/components/kit/ui";

const TABS = ["tablero", "lista", "fichas", "equipo", "requisitos", "calendario"] as const;

export default function ProyectoDetailPage() {
  const params = useParams<{ id: string }>();
  const { t, te } = useI18n();
  const [tab, setTab] = useState<(typeof TABS)[number]>("tablero");
  const [project, setProject] = useState<{ id: string; name: string; description: string; requirements: { id: string; text: string }[] } | null>(null);
  const [board, setBoard] = useState<Record<string, { id: string; internal_reference: string; name?: string; phase_status: string; due_date?: string | null }[]>>({});

  useEffect(() => {
    api<typeof project extends null ? never : NonNullable<typeof project>>(`/projects/${params.id}`).then(setProject);
    api<{ columns: typeof board }>(`/projects/${params.id}/board`).then((r) => setBoard(r.columns));
  }, [params.id]);

  if (!project) return <div className="text-muted">{t("common.loading")}</div>;

  const columns = ["data", "visuals", "retouch", "approval", "published"] as const;

  return (
    <div className="space-y-6 animate-fade-in">
      <header>
        <h1 className="text-2xl font-semibold text-carbon">{project.name}</h1>
        <p className="text-muted text-sm mt-1">{project.description}</p>
      </header>
      <div className="flex gap-1 overflow-x-auto border-b border-border">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm capitalize ${tab === t ? "border-b-2 border-wine text-wine" : "text-muted"}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "tablero" && (
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          {columns.map((col) => (
            <div key={col} className="bg-raised/60 rounded-lg p-2 min-h-64">
              <h3 className="text-xs font-semibold uppercase text-muted px-2 py-2">
                {te("phases", col) || col}
              </h3>
              <div className="space-y-2">
                {(board[col] || []).map((card) => (
                  <Link
                    key={card.id}
                    href={`/productos/${card.id}`}
                    className="block rounded-md bg-surface border border-border p-3 hover:shadow-sm"
                  >
                    <div className="font-medium text-sm">{card.internal_reference}</div>
                    <div className="text-xs text-muted truncate">{card.name}</div>
                    <div className="mt-2">
                      <StatusChip status={card.phase_status} />
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "lista" && (
        <table className="w-full text-sm bg-surface border border-border rounded-lg overflow-hidden">
          <thead className="bg-raised text-left">
            <tr>
              <th className="p-3">Referencia</th>
              <th className="p-3">Fase</th>
              <th className="p-3">Estado</th>
              <th className="p-3">Vence</th>
            </tr>
          </thead>
          <tbody>
            {columns.flatMap((col) =>
              (board[col] || []).map((card) => (
                <tr key={card.id} className="border-t border-border">
                  <td className="p-3">
                    <Link href={`/productos/${card.id}`} className="text-wine">
                      {card.internal_reference}
                    </Link>
                  </td>
                  <td className="p-3">{te("phases", col) || col}</td>
                  <td className="p-3">
                    <StatusChip status={card.phase_status} />
                  </td>
                  <td className="p-3 text-muted">{card.due_date || "—"}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      )}

      {tab === "requisitos" && (
        <ul className="bg-surface border border-border rounded-lg divide-y">
          {(project.requirements || []).map((r) => (
            <li key={r.id} className="p-4 text-sm">
              {r.text}
            </li>
          ))}
        </ul>
      )}

      {(tab === "fichas" || tab === "equipo" || tab === "calendario") && (
        <div className="bg-surface border border-border rounded-lg p-6 text-sm text-muted">
          Gestiona {tab} desde esta pestaña. Los datos se cargan desde la API del proyecto.
        </div>
      )}
    </div>
  );
}
