"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/hooks/use-i18n";
import { EmptyState } from "@/components/kit/ui";

type Project = {
  id: string;
  name: string;
  description: string;
  status: string;
  counts?: Record<string, number>;
  product_count?: number;
  must_ship_date?: string | null;
};

export default function ProyectosPage() {
  const { t } = useI18n();
  const [projects, setProjects] = useState<Project[]>([]);
  const [showArchived, setShowArchived] = useState(false);

  useEffect(() => {
    api<{ data: Project[] }>(`/projects?status=${showArchived ? "archived" : "active"}`).then((r) =>
      setProjects(r.data),
    );
  }, [showArchived]);

  return (
    <div className="max-w-6xl mx-auto space-y-6 animate-fade-in">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-carbon">{t("nav.projects")}</h1>
        <div className="flex gap-2">
          <button
            type="button"
            className="text-sm px-3 py-2 rounded-md border border-border"
            onClick={() => setShowArchived((v) => !v)}
          >
            {showArchived ? t("projectsUi.viewActive") : t("projectsUi.archived")}
          </button>
          <Link href="/proyectos/nuevo" className="rounded-md bg-wine text-white text-sm px-3 py-2">
            {t("library.newProject")}
          </Link>
        </div>
      </div>

      {projects.length === 0 ? (
        <EmptyState
          title={t("projectsUi.noProjects")}
          action={
            <Link href="/proyectos/nuevo" className="text-wine font-medium">
              {t("library.createProject")}
            </Link>
          }
        />
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {projects.map((p) => {
            const total = p.product_count || 0;
            const done = p.counts?.published || 0;
            const pct = total ? Math.round((done / total) * 100) : 0;
            return (
              <Link
                key={p.id}
                href={`/proyectos/${p.id}`}
                className="block rounded-lg border border-border bg-surface p-6 hover:shadow-sm transition"
              >
                <h2 className="font-semibold text-lg text-carbon">{p.name}</h2>
                <p className="text-sm text-muted mt-1 line-clamp-2">
                  {p.description || t("projectsUi.noDescription")}
                </p>
                <div className="mt-4 h-2 rounded-full bg-raised overflow-hidden">
                  <div className="h-full bg-wine" style={{ width: `${pct}%` }} />
                </div>
                <div className="mt-2 text-xs text-muted flex justify-between">
                  <span>
                    {total} · {t("projectsUi.published")} {done}
                  </span>
                  {p.must_ship_date && <span>{p.must_ship_date}</span>}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
