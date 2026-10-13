"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { uploadViaPresign } from "@/lib/upload";
import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import { EmptyState, StatusChip } from "@/components/kit/ui";

type Task = {
  product_id: string;
  internal_reference: string;
  name?: string;
  project_id: string;
  phase: string;
  status: string;
  due_date?: string | null;
};

type ImageTask = {
  assignment_id: string;
  product_id: string;
  asset_id: string;
  internal_reference: string;
  name?: string;
  shot_type: string;
  phase: string;
  status: string;
  note: string;
  project_id: string;
};

export default function TareasPage() {
  const { user } = useAuth();
  const { te, t } = useI18n();
  const [data, setData] = useState<{
    para_revisar: Task[];
    cambios_solicitados: Task[];
    en_curso: Task[];
    pendientes: Task[];
    imagenes_asignadas: ImageTask[];
  } | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadTarget, setUploadTarget] = useState<ImageTask | null>(null);

  const load = () => api<NonNullable<typeof data>>("/tareas").then(setData);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!data) return <div className="text-muted">{t("common.loading")}</div>;

  const total =
    data.para_revisar.length +
    data.cambios_solicitados.length +
    data.en_curso.length +
    data.pendientes.length +
    (data.imagenes_asignadas?.length || 0);

  const sections = [
    {
      key: "para_revisar",
      title: t("tasksUi.toReview"),
      action: t("tasksUi.review"),
      items: data.para_revisar,
    },
    {
      key: "cambios",
      title: t("tasksUi.changesRequested"),
      action: t("tasksUi.seeChanges"),
      items: data.cambios_solicitados,
    },
    {
      key: "curso",
      title: t("tasksUi.inProgress"),
      action: t("tasksUi.continue"),
      items: data.en_curso,
    },
    {
      key: "pend",
      title: t("tasksUi.pending"),
      action: t("tasksUi.start"),
      items: data.pendientes,
    },
  ];

  const firstName = user?.name?.split(" ")[0] || "";

  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-fade-in">
      <header>
        <h1 className="font-serif text-3xl text-carbon">
          {t("tasksUi.greeting").replace("{name}", firstName)}
        </h1>
      </header>

      {total === 0 ? (
        <EmptyState
          title={t("tasksUi.nothingPending")}
          action={
            <Link href="/proyectos" className="text-wine font-medium">
              {t("nav.projects")}
            </Link>
          }
        />
      ) : (
        <>
          {(data.imagenes_asignadas || []).length > 0 && (
            <section>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-3">
                {t("tasksUi.assignedImages")}
              </h2>
              <ul className="bg-surface rounded-lg border border-border divide-y divide-border">
                {data.imagenes_asignadas.map((item) => (
                  <li key={item.assignment_id} className="p-4 flex flex-wrap items-center gap-4">
                    <div className="h-12 w-12 rounded-md bg-raised shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium truncate">
                        {item.internal_reference}
                        {item.name ? ` · ${item.name}` : ""} · {te("shotTypes", item.shot_type)}
                      </div>
                      <div className="text-xs text-muted mt-1">
                        {item.note || t("tasksUi.editPerReview")} ·{" "}
                        {te("assignmentStatus", item.status)}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Link
                        href={`/productos/${item.product_id}?tab=imagenes`}
                        className="rounded-md border border-border text-sm px-3 py-2"
                      >
                        {t("nav.product")}
                      </Link>
                      <button
                        type="button"
                        className="rounded-md bg-wine text-white text-sm px-3 py-2 disabled:opacity-50"
                        disabled={uploading === item.assignment_id}
                        onClick={() => {
                          setUploadTarget(item);
                          fileRef.current?.click();
                        }}
                      >
                        {uploading === item.assignment_id
                          ? t("tasksUi.uploading")
                          : t("tasksUi.uploadEdited")}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {sections
            .filter((s) => s.items.length > 0)
            .map((section) => (
              <section key={section.key}>
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-3">
                  {section.title}
                </h2>
                <ul className="bg-surface rounded-lg border border-border divide-y divide-border">
                  {section.items.map((item) => (
                    <li key={item.product_id} className="p-4 flex items-center gap-4">
                      <div className="h-12 w-12 rounded-md bg-raised shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="font-medium truncate">
                          {item.internal_reference}
                          {item.name ? ` · ${item.name}` : ""}
                        </div>
                        <div className="text-xs text-muted flex gap-2 mt-1 items-center">
                          <StatusChip status={item.status} />
                          {item.due_date && <span>{item.due_date}</span>}
                        </div>
                      </div>
                      <Link
                        href={`/productos/${item.product_id}`}
                        className="rounded-md bg-wine text-white text-sm px-3 py-2"
                      >
                        {section.action}
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
        </>
      )}

      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          const target = uploadTarget;
          e.target.value = "";
          if (!file || !target) return;
          setUploading(target.assignment_id);
          try {
            await api(`/assignments/${target.assignment_id}`, {
              method: "PATCH",
              body: JSON.stringify({ status: "in_progress" }),
            }).catch(() => undefined);
            const storage_key = await uploadViaPresign(file, "asset_version");
            await api(`/assets/${target.asset_id}/versions`, {
              method: "POST",
              body: JSON.stringify({ storage_key }),
            });
            await load();
          } finally {
            setUploading(null);
            setUploadTarget(null);
          }
        }}
      />
    </div>
  );
}
