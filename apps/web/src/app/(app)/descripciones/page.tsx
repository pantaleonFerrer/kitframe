"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/hooks/use-i18n";

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="bg-surface border border-border rounded-lg p-5 space-y-4">
      <div>
        <h2 className="font-semibold text-base">{title}</h2>
        {description ? <p className="text-sm text-muted mt-1">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

type PendingRow = {
  ref: string;
  title: string;
  collection: string;
  product_type: string;
};

type Preview = {
  filename: string;
  pending_count: number;
  pending: PendingRow[];
  image_naming_hint: string;
};

type ProductNotes = {
  fit: string;
  care: string;
  measures: string;
  extra: string;
};

type FillStart = {
  job_id: string;
  pending_count: number;
  pending_refs: string[];
  images_per_ref: Record<string, number>;
  unmatched_images: string[];
};

type JobProgress = {
  stage?: string | null;
  current?: number | null;
  total?: number | null;
  current_ref?: string | null;
  message?: string | null;
  filled_refs?: string[];
  failed_ref?: string | null;
};

type FillJob = {
  id: string;
  status: string;
  error_detail?: string | null;
  pending_count?: number;
  filled_count?: number;
  original_filename?: string;
  download_url?: string | null;
  progress?: JobProgress;
  pending_refs?: string[];
};

type RecentJob = {
  id: string;
  status: string;
  pending_count?: number;
  filled_count?: number;
  original_filename?: string;
  created_at: string;
  error_detail?: string | null;
  progress?: JobProgress;
};

const emptyNotes = (): ProductNotes => ({
  fit: "",
  care: "",
  measures: "",
  extra: "",
});

function matchRef(filename: string, refs: string[]): string | null {
  const stem = filename.replace(/\.[^.]+$/, "");
  const ordered = [...refs].sort((a, b) => b.length - a.length);
  for (const ref of ordered) {
    const re = new RegExp(`^${ref.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:$|[_\-\s.].*)`, "i");
    if (re.test(stem)) return ref;
  }
  return null;
}

export default function DescripcionesEcomPage() {
  const { t } = useI18n();
  const excelRef = useRef<HTMLInputElement>(null);
  const imagesRef = useRef<HTMLInputElement>(null);

  const [excel, setExcel] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [images, setImages] = useState<File[]>([]);
  const [notes, setNotes] = useState<Record<string, ProductNotes>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [job, setJob] = useState<FillJob | null>(null);
  const [recent, setRecent] = useState<RecentJob[]>([]);

  const refs = useMemo(() => preview?.pending.map((p) => p.ref) || [], [preview]);

  const imagesByRef = useMemo(() => {
    const map: Record<string, File[]> = Object.fromEntries(refs.map((r) => [r, [] as File[]]));
    const unmatched: File[] = [];
    for (const f of images) {
      const ref = matchRef(f.name, refs);
      if (!ref) {
        unmatched.push(f);
        continue;
      }
      if (map[ref].length < 8) map[ref].push(f);
    }
    return { map, unmatched };
  }, [images, refs]);

  const missingImageRefs = useMemo(
    () => refs.filter((r) => (imagesByRef.map[r] || []).length === 0),
    [refs, imagesByRef],
  );

  const loadRecent = useCallback(async () => {
    try {
      const res = await api<{ data: RecentJob[] }>("/tools/ecom-descriptions/recent");
      setRecent(res.data || []);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

  async function onExcelChosen(file: File | null) {
    setExcel(file);
    setPreview(null);
    setImages([]);
    setNotes({});
    setJob(null);
    setMsg(null);
    if (!file) return;
    setPreviewing(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await api<Preview>("/tools/ecom-descriptions/preview", {
        method: "POST",
        body,
      });
      setPreview(res);
      const next: Record<string, ProductNotes> = {};
      for (const row of res.pending) next[row.ref] = emptyNotes();
      setNotes(next);
      if (res.pending_count === 0) {
        setMsg(t("settings.ecomExcelNoPending"));
      } else {
        setMsg(`${t("settings.ecomExcelPending")}: ${res.pending_count}`);
      }
    } catch (e) {
      setMsg((e as Error).message || t("settings.ecomExcelFailed"));
    } finally {
      setPreviewing(false);
    }
  }

  function addImages(files: FileList | File[] | null) {
    if (!files) return;
    const list = Array.from(files).filter((f) => f.type.startsWith("image/"));
    setImages((prev) => {
      const names = new Set(prev.map((p) => `${p.name}:${p.size}`));
      const next = [...prev];
      for (const f of list) {
        const key = `${f.name}:${f.size}`;
        if (!names.has(key)) {
          next.push(f);
          names.add(key);
        }
      }
      return next.slice(0, 40);
    });
  }

  function updateNote(ref: string, field: keyof ProductNotes, value: string) {
    setNotes((prev) => ({
      ...prev,
      [ref]: { ...(prev[ref] || emptyNotes()), [field]: value },
    }));
  }

  async function runFill() {
    if (!excel || !preview) {
      setMsg(t("settings.ecomExcelNoFile"));
      return;
    }
    if (missingImageRefs.length > 0) {
      setMsg(
        `${t("settings.ecomExcelMissingPhotos")}: ${missingImageRefs.join(", ")}`,
      );
      return;
    }
    setBusy(true);
    setMsg(t("settings.ecomExcelUploading"));
    setJob(null);
    try {
      const body = new FormData();
      body.append("file", excel);
      for (const img of images) {
        body.append("images", img);
      }
      const notesPayload: Record<string, Partial<ProductNotes>> = {};
      for (const ref of refs) {
        const n = notes[ref] || emptyNotes();
        const trimmed: Partial<ProductNotes> = {};
        for (const k of ["fit", "care", "measures", "extra"] as const) {
          if (n[k].trim()) trimmed[k] = n[k].trim();
        }
        if (Object.keys(trimmed).length) notesPayload[ref] = trimmed;
      }
      body.append("notes_json", JSON.stringify(notesPayload));

      const started = await api<FillStart>("/tools/ecom-descriptions/fill", {
        method: "POST",
        body,
      });
      setMsg(
        `${t("settings.ecomExcelPending")}: ${started.pending_count}` +
          (started.unmatched_images?.length
            ? ` · ${t("settings.ecomExcelUnmatched")}: ${started.unmatched_images.join(", ")}`
            : ""),
      );

      let last: FillJob | null = null;
      for (let i = 0; i < 600; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        last = await api<FillJob>(`/tools/ecom-descriptions/jobs/${started.job_id}`);
        setJob(last);
        const p = last.progress;
        if (p?.message) {
          setMsg(p.message);
        } else if (last.status === "running") {
          setMsg(t("settings.ecomExcelRunning"));
        }
        if (last.status === "completed") {
          setMsg(t("settings.ecomExcelDone"));
          break;
        }
        if (last.status === "failed") {
          setMsg(last.error_detail || t("settings.ecomExcelFailed"));
          break;
        }
      }
      if (last && last.status !== "completed" && last.status !== "failed") {
        setMsg(t("settings.ecomExcelTimeout"));
      }
      await loadRecent();
    } catch (e) {
      const err = e as Error & { details?: { missing_images?: string[] } };
      const missing = err.details?.missing_images;
      if (Array.isArray(missing) && missing.length) {
        setMsg(`${t("settings.ecomExcelMissingPhotos")}: ${missing.join(", ")}`);
      } else {
        setMsg(err.message || t("settings.ecomExcelFailed"));
      }
    } finally {
      setBusy(false);
    }
  }

  const progressPct = useMemo(() => {
    const p = job?.progress;
    const total = p?.total || preview?.pending_count || 0;
    const current = p?.current || 0;
    if (!total) return 0;
    if (job?.status === "completed") return 100;
    return Math.min(100, Math.round((current / total) * 100));
  }, [job, preview]);

  return (
    <div className="space-y-6 animate-fade-in max-w-4xl">
      <header className="space-y-2">
        <h1 className="text-xl font-semibold">{t("settings.ecomExcelTitle")}</h1>
        <p className="text-sm text-muted">{t("settings.ecomExcelDesc")}</p>
        <ol className="list-decimal list-inside text-sm text-muted space-y-1">
          <li>{t("settings.ecomExcelStep1")}</li>
          <li>{t("settings.ecomExcelStep2")}</li>
          <li>{t("settings.ecomExcelStep3")}</li>
        </ol>
      </header>

      <Section title={t("settings.ecomExcelStepExcel")} description={t("settings.ecomExcelHint")}>
        <input
          ref={excelRef}
          type="file"
          accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="hidden"
          onChange={(e) => void onExcelChosen(e.target.files?.[0] || null)}
        />
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="rounded-md border border-border px-3 py-2 text-sm"
            onClick={() => excelRef.current?.click()}
            disabled={busy || previewing}
          >
            {t("settings.ecomExcelChoose")}
          </button>
          <span className="text-sm text-muted">
            {previewing
              ? t("settings.ecomExcelParsing")
              : excel
                ? excel.name
                : t("settings.ecomExcelHint")}
          </span>
        </div>
        {preview && preview.pending_count > 0 && (
          <p className="text-sm">
            {t("settings.ecomExcelPending")}: <strong>{preview.pending_count}</strong>
            {" · "}
            {preview.pending.map((p) => p.ref).join(", ")}
          </p>
        )}
      </Section>

      {preview && preview.pending_count > 0 && (
        <Section
          title={t("settings.ecomExcelStepPhotos")}
          description={t("settings.ecomExcelPhotosHint")}
        >
          <input
            ref={imagesRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            multiple
            className="hidden"
            onChange={(e) => {
              addImages(e.target.files);
              e.target.value = "";
            }}
          />
          <div
            className="rounded-md border border-dashed border-border px-4 py-8 text-center text-sm text-muted cursor-pointer hover:bg-raised"
            onClick={() => imagesRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              addImages(e.dataTransfer.files);
            }}
          >
            <p>{t("settings.ecomExcelDropPhotos")}</p>
            <p className="mt-1 text-xs">{t("settings.ecomExcelPhotosNaming")}</p>
          </div>
          {images.length > 0 && (
            <p className="text-sm text-muted">
              {images.length} {t("settings.ecomExcelPhotosSelected")}
              {imagesByRef.unmatched.length > 0 && (
                <span className="text-wine">
                  {" · "}
                  {t("settings.ecomExcelUnmatched")}:{" "}
                  {imagesByRef.unmatched.map((f) => f.name).join(", ")}
                </span>
              )}
            </p>
          )}
          {missingImageRefs.length > 0 && (
            <p className="text-sm text-wine">
              {t("settings.ecomExcelMissingPhotos")}: {missingImageRefs.join(", ")}
            </p>
          )}

          <div className="space-y-4 pt-2">
            {preview.pending.map((row) => {
              const imgs = imagesByRef.map[row.ref] || [];
              const n = notes[row.ref] || emptyNotes();
              return (
                <div
                  key={row.ref}
                  className="rounded-md border border-border p-4 space-y-3"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div>
                      <p className="font-medium text-sm">{row.ref}</p>
                      <p className="text-xs text-muted">
                        {row.title || "—"}
                        {row.collection ? ` · ${row.collection}` : ""}
                      </p>
                    </div>
                    <span
                      className={`text-xs ${imgs.length ? "text-muted" : "text-wine"}`}
                    >
                      {imgs.length
                        ? `${imgs.length} ${t("settings.ecomExcelPhotoCount")}`
                        : t("settings.ecomExcelNeedsPhoto")}
                    </span>
                  </div>
                  {imgs.length > 0 && (
                    <ul className="flex flex-wrap gap-2 text-xs text-muted">
                      {imgs.map((f) => (
                        <li
                          key={`${f.name}-${f.size}`}
                          className="rounded border border-border px-2 py-1"
                        >
                          {f.name}
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="text-xs text-muted">{t("settings.ecomExcelNotesHint")}</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="text-xs space-y-1">
                      <span className="text-muted">{t("settings.ecomExcelNoteFit")}</span>
                      <input
                        className="w-full rounded-md border border-border bg-transparent px-2 py-1.5 text-sm"
                        value={n.fit}
                        onChange={(e) => updateNote(row.ref, "fit", e.target.value)}
                        disabled={busy}
                      />
                    </label>
                    <label className="text-xs space-y-1">
                      <span className="text-muted">{t("settings.ecomExcelNoteCare")}</span>
                      <input
                        className="w-full rounded-md border border-border bg-transparent px-2 py-1.5 text-sm"
                        value={n.care}
                        onChange={(e) => updateNote(row.ref, "care", e.target.value)}
                        disabled={busy}
                      />
                    </label>
                    <label className="text-xs space-y-1 sm:col-span-2">
                      <span className="text-muted">{t("settings.ecomExcelNoteMeasures")}</span>
                      <input
                        className="w-full rounded-md border border-border bg-transparent px-2 py-1.5 text-sm"
                        value={n.measures}
                        onChange={(e) => updateNote(row.ref, "measures", e.target.value)}
                        disabled={busy}
                      />
                    </label>
                    <label className="text-xs space-y-1 sm:col-span-2">
                      <span className="text-muted">{t("settings.ecomExcelNoteExtra")}</span>
                      <textarea
                        className="w-full rounded-md border border-border bg-transparent px-2 py-1.5 text-sm min-h-[60px]"
                        value={n.extra}
                        onChange={(e) => updateNote(row.ref, "extra", e.target.value)}
                        disabled={busy}
                      />
                    </label>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <button
              type="button"
              className="rounded-md bg-wine text-white px-4 py-2 text-sm disabled:opacity-50"
              disabled={busy || missingImageRefs.length > 0}
              onClick={() => void runFill()}
            >
              {busy ? t("settings.ecomExcelRunning") : t("settings.ecomExcelRun")}
            </button>
          </div>

          {(busy || job) && (
            <div className="space-y-2">
              <div className="h-2 rounded-full bg-raised overflow-hidden">
                <div
                  className="h-full bg-wine transition-all duration-500"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <p className="text-sm text-muted">
                {job?.progress?.current_ref
                  ? `${job.progress.current_ref} · ${job.progress.current ?? 0}/${job.progress.total ?? "?"}`
                  : null}
                {msg ? (job?.progress?.current_ref ? ` — ${msg}` : msg) : null}
              </p>
              {job?.progress?.filled_refs && job.progress.filled_refs.length > 0 && (
                <p className="text-xs text-muted">
                  {t("settings.ecomExcelFilled")}: {job.progress.filled_refs.join(", ")}
                </p>
              )}
            </div>
          )}

          {msg && !busy && !job && <p className="text-sm text-muted">{msg}</p>}
          {msg && job?.status === "failed" && (
            <p className="text-sm text-wine">{msg}</p>
          )}

          {job?.status === "completed" && job.download_url && (
            <div className="space-y-2">
              {typeof job.filled_count === "number" && (
                <p className="text-sm">
                  {t("settings.ecomExcelFilled")}: {job.filled_count}
                </p>
              )}
              <a
                href={job.download_url}
                className="inline-flex rounded-md border border-border px-4 py-2 text-sm hover:bg-raised"
              >
                {t("settings.ecomExcelDownload")}
              </a>
            </div>
          )}
        </Section>
      )}

      {msg && !preview && <p className="text-sm text-muted px-1">{msg}</p>}

      {recent.length > 0 && (
        <Section title={t("settings.ecomExcelRecent")}>
          <ul className="divide-y divide-border text-sm">
            {recent.map((r) => (
              <li key={r.id} className="py-2 flex flex-wrap gap-x-4 gap-y-1">
                <span className="font-medium">{r.original_filename || r.id.slice(0, 8)}</span>
                <span className="text-muted">{r.status}</span>
                {typeof r.filled_count === "number" && (
                  <span className="text-muted">
                    {t("settings.ecomExcelFilled")}: {r.filled_count}
                  </span>
                )}
                {r.progress?.message && r.status === "running" && (
                  <span className="text-muted">{r.progress.message}</span>
                )}
                <span className="text-muted">{new Date(r.created_at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
