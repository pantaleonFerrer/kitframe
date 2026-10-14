"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { uploadViaPresign } from "@/lib/upload";
import { useI18n } from "@/hooks/use-i18n";
import {
  PhaseStepper,
  PrimaryActionBar,
  StatusChip,
  WhatsMissing,
} from "@/components/kit/ui";
import { ReviewImageWorkspace } from "@/components/review/ReviewImageWorkspace";

type Product = {
  id: string;
  project_id: string;
  internal_reference: string;
  current_phase: string;
  structured_data: Record<string, unknown>;
  field_confidence: Record<string, number>;
  confirmed_fields: string[];
  content: Record<string, Record<string, unknown>>;
  allowed_actions: string[];
  phases: { phase: string; status: string }[];
};

type Asset = {
  id: string;
  shot_type: string;
  status: string;
  origin?: string;
  url?: string | null;
  current_version_id?: string | null;
};

type Editor = {
  user_id: string;
  name: string;
  email: string;
};

type AssignmentDraft = {
  asset_id: string;
  assigned_to: string;
  note: string;
};

type ProductAssignment = {
  id: string;
  asset_id: string;
  assigned_to: string;
  assignee_name?: string | null;
  status: string;
  note: string;
  shot_type?: string | null;
};

type ReviewSummary = {
  id: string;
  decision: string;
  comment?: string | null;
  phase?: string | null;
  reviewer_name?: string | null;
  created_at: string;
  is_open: boolean;
  comment_count: number;
  version_count: number;
};

type ReviewDetail = {
  id: string;
  decision: string;
  comment?: string | null;
  phase?: string | null;
  phase_status?: string | null;
  reviewer_name?: string | null;
  created_at: string;
  is_open: boolean;
  awaiting_resubmit?: boolean;
  can_reply: boolean;
  can_upload: boolean;
  can_decide: boolean;
  closing?: {
    id: string;
    decision: string;
    comment?: string | null;
    reviewer_name?: string | null;
    created_at: string;
  } | null;
  comments: {
    id: string;
    body: string;
    author_name?: string | null;
    author_id: string;
    created_at: string;
    asset_version_id?: string | null;
    annotation?: {
      x: number;
      y: number;
      w: number;
      h: number;
      color?: string;
    } | null;
  }[];
  versions: {
    id: string;
    asset_id: string;
    shot_type?: string | null;
    version_number: number;
    url?: string | null;
    author_name?: string | null;
    created_at: string;
  }[];
  assignments: ProductAssignment[];
};

const SHOT_OPTIONS = [
  "product_front",
  "product_back",
  "product_detail",
  "model_front",
  "model_back",
  "lifestyle",
] as const;

const CONTENT_LOCALES = ["es", "ca", "en", "fr", "de", "it", "pt", "zh"] as const;
type ContentLocale = (typeof CONTENT_LOCALES)[number];
type LocaleCopy = {
  name: string;
  description: string;
  seo_title: string;
  seo_meta: string;
  seo_keywords: string;
};

function contentToDraft(content: Record<string, Record<string, unknown>> | undefined) {
  const draft = {} as Record<ContentLocale, LocaleCopy>;
  for (const loc of CONTENT_LOCALES) {
    const c = content?.[loc] || {};
    const keywords = c.seo_keywords;
    draft[loc] = {
      name: String(c.name || ""),
      description: String(c.description || ""),
      seo_title: String(c.seo_title || ""),
      seo_meta: String(c.seo_meta || ""),
      seo_keywords: Array.isArray(keywords)
        ? keywords.map(String).join(", ")
        : String(keywords || ""),
    };
  }
  return draft;
}

export default function ProductoPage() {
  const params = useParams<{ id: string }>();
  const { te, t } = useI18n();
  const [product, setProduct] = useState<Product | null>(null);
  const [tab, setTab] = useState("datos");
  const [checklist, setChecklist] = useState<{ criteria: { code: string; ok: boolean }[]; ok: boolean } | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [editors, setEditors] = useState<Editor[]>([]);
  const [assignments, setAssignments] = useState<ProductAssignment[]>([]);
  const [selectedAssets, setSelectedAssets] = useState<Record<string, boolean>>({});
  const [defaultEditor, setDefaultEditor] = useState("");
  const [assetEditors, setAssetEditors] = useState<Record<string, string>>({});
  const [assetNotes, setAssetNotes] = useState<Record<string, string>>({});
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadTarget, setUploadTarget] = useState<string | null>(null);
  const [reviews, setReviews] = useState<ReviewSummary[]>([]);
  const [activeReviewId, setActiveReviewId] = useState<string | null>(null);
  const [reviewDetail, setReviewDetail] = useState<ReviewDetail | null>(null);
  const [threadComment, setThreadComment] = useState("");
  const [postingComment, setPostingComment] = useState(false);
  const [newShotType, setNewShotType] = useState<string>("product_front");
  const newAssetRef = useRef<HTMLInputElement>(null);
  const revisionAssetRef = useRef<HTMLInputElement>(null);
  const [revisionUploadAssetId, setRevisionUploadAssetId] = useState<string | null>(null);
  const [decideComment, setDecideComment] = useState("");
  const [workspaceComments, setWorkspaceComments] = useState<ReviewDetail["comments"]>([]);
  const [copyDraft, setCopyDraft] = useState<Record<ContentLocale, LocaleCopy> | null>(null);
  const [copyBusy, setCopyBusy] = useState<"save" | "generate" | "translate" | null>(null);
  const [copyMsg, setCopyMsg] = useState<string | null>(null);
  const [sourceLocale, setSourceLocale] = useState<ContentLocale>("es");
  const [overwriteManual, setOverwriteManual] = useState(false);

  const loadReviewDetail = async (reviewId: string) => {
    const d = await api<ReviewDetail>(`/products/${params.id}/reviews/${reviewId}`);
    setReviewDetail(d);
    setActiveReviewId(reviewId);
    setWorkspaceComments(d.comments || []);
  };

  const loadWorkspaceComments = async (reviewId: string | null) => {
    if (!reviewId) {
      setWorkspaceComments([]);
      return;
    }
    try {
      const d = await api<ReviewDetail>(`/products/${params.id}/reviews/${reviewId}`);
      setWorkspaceComments(d.comments || []);
    } catch {
      setWorkspaceComments([]);
    }
  };

  const load = async () => {
    const p = await api<Product>(`/products/${params.id}`);
    setProduct(p);
    setCopyDraft(contentToDraft(p.content));
    const [c, a, e, asg, revs] = await Promise.all([
      api<{ criteria: { code: string; ok: boolean }[]; ok: boolean }>(`/products/${params.id}/checklist`),
      api<{ data: Asset[] }>(`/products/${params.id}/assets`).catch(() => ({ data: [] as Asset[] })),
      api<{ data: Editor[] }>(`/products/${params.id}/editors`).catch(() => ({ data: [] as Editor[] })),
      api<{ data: ProductAssignment[] }>(`/products/${params.id}/assignments`).catch(() => ({
        data: [] as ProductAssignment[],
      })),
      api<{ data: ReviewSummary[] }>(`/products/${params.id}/reviews`).catch(() => ({
        data: [] as ReviewSummary[],
      })),
    ]);
    setChecklist(c);
    setAssets(a.data);
    setEditors(e.data);
    setAssignments(asg.data);
    setReviews(revs.data || []);
    if (e.data[0] && !defaultEditor) setDefaultEditor(e.data[0].user_id);
    if (activeReviewId) {
      await loadReviewDetail(activeReviewId).catch(() => setReviewDetail(null));
    }
  };

  useEffect(() => {
    void load();
    if (typeof window !== "undefined") {
      const q = new URLSearchParams(window.location.search);
      const tabQ = q.get("tab");
      if (tabQ) setTab(tabQ);
      const reviewQ = q.get("review");
      if (reviewQ) {
        setTab("revision");
        void loadReviewDetail(reviewQ).catch(() => undefined);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  useEffect(() => {
    if (tab !== "revision") return;
    if (activeReviewId) return;
    const open = reviews.find((r) => r.is_open);
    void loadWorkspaceComments(open?.id || null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, reviews, activeReviewId]);

  const phaseStatus = useMemo(() => {
    if (!product) return "todo";
    return product.phases.find((p) => p.phase === product.current_phase)?.status || "todo";
  }, [product]);

  const openAssignments = useMemo(
    () => assignments.filter((a) => a.status === "open" || a.status === "in_progress"),
    [assignments],
  );

  if (!product) return <div className="text-muted">{t("common.loading")}</div>;

  const statuses = Object.fromEntries(product.phases.map((p) => [p.phase, p.status]));
  const canSubmit = product.allowed_actions.includes("submit");
  const canStart = product.allowed_actions.includes("start");
  const canReview = product.allowed_actions.includes("review");
  const canPublish = product.allowed_actions.includes("publish");
  const canUpload = product.allowed_actions.includes("upload_asset");
  const latestChangeRequest = reviews.find((r) => r.is_open && r.decision === "changes_requested");
  const workspaceReviewId =
    activeReviewId || latestChangeRequest?.id || reviews.find((r) => r.is_open)?.id || null;
  const canAnnotateImages = Boolean(
    (reviewDetail?.can_reply || canReview) &&
      (phaseStatus === "in_review" || Boolean(workspaceReviewId)),
  );

  let primary: React.ReactNode = null;
  let hint = t("reviewUi.readOnly");
  if (phaseStatus === "todo" && canStart) {
    primary = (
      <button
        type="button"
        className="rounded-md bg-wine text-white px-4 py-2"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          await api(`/products/${product.id}/start`, { method: "POST" });
          await load();
          setBusy(false);
        }}
      >
        {t("tasksUi.start")}
      </button>
    );
    hint = "";
  } else if ((phaseStatus === "in_progress" || phaseStatus === "changes_requested") && canSubmit) {
    primary = (
      <button
        type="button"
        className="rounded-md bg-wine text-white px-4 py-2 disabled:opacity-50"
        disabled={busy || !checklist?.ok}
        title={!checklist?.ok ? t("reviewUi.completeMissing") : undefined}
        onClick={async () => {
          setBusy(true);
          try {
            await api(`/products/${product.id}/submit`, { method: "POST" });
            await load();
          } catch (e) {
            console.error(e);
          }
          setBusy(false);
        }}
      >
        {phaseStatus === "changes_requested"
          ? t("reviewUi.resendToReview")
          : t("reviewUi.sendToReview")}
      </button>
    );
    hint = !checklist?.ok ? t("reviewUi.completeMissing") : "";
  } else if (phaseStatus === "in_review" && canReview) {
    primary = (
      <button type="button" className="rounded-md bg-wine text-white px-4 py-2" onClick={() => setReviewOpen(true)}>
        {product.current_phase === "approval" ? t("reviewUi.reviewPublish") : t("reviewUi.reviewAction")}
      </button>
    );
    hint = "";
  } else if (phaseStatus === "in_review") {
    hint = t("phaseStatus.in_review");
  }

  const es = product.content?.es || {};

  const buildAssignments = (): AssignmentDraft[] =>
    Object.entries(selectedAssets)
      .filter(([, on]) => on)
      .map(([assetId]) => ({
        asset_id: assetId,
        assigned_to: assetEditors[assetId] || defaultEditor,
        note: assetNotes[assetId] || comment,
      }))
      .filter((a) => a.assigned_to);

  const uploadEdited = async (assetId: string, file: File) => {
    setUploadingId(assetId);
    try {
      const storage_key = await uploadViaPresign(file, "asset_version");
      await api(`/assets/${assetId}/versions`, {
        method: "POST",
        body: JSON.stringify({ storage_key }),
      });
      await load();
    } finally {
      setUploadingId(null);
      setUploadTarget(null);
    }
  };

  return (
    <div className="max-w-6xl mx-auto animate-fade-in">
      <div className="mb-2 text-sm">
        <Link href={`/proyectos/${product.project_id}`} className="text-wine">
          ← Proyecto
        </Link>
      </div>
      <header className="space-y-3 mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold text-carbon">{product.internal_reference}</h1>
          <StatusChip status={phaseStatus} />
        </div>
        <div className="text-lg text-muted">{String(es.name || "")}</div>
        <PhaseStepper current={product.current_phase} statuses={statuses} />
      </header>

      {checklist && <WhatsMissing criteria={checklist.criteria} />}

      {phaseStatus === "changes_requested" && latestChangeRequest?.comment && (
        <div className="mb-4 rounded-lg border border-danger/30 bg-danger-subtle p-4 text-sm">
          <div className="font-medium text-danger mb-1">Cambios solicitados</div>
          <p className="text-carbon">{latestChangeRequest.comment}</p>
          <p className="text-xs text-muted mt-2">
            {latestChangeRequest.reviewer_name || "Revisor"} ·{" "}
            {new Date(latestChangeRequest.created_at).toLocaleString()}
          </p>
          <button
            type="button"
            className="mt-2 text-sm text-wine underline"
            onClick={() => {
              setTab("revision");
              void loadReviewDetail(latestChangeRequest.id);
            }}
          >
            Abrir revisión
          </button>
        </div>
      )}

      {openAssignments.length > 0 && (
        <div className="mb-4 rounded-lg border border-border bg-raised/40 p-4 text-sm space-y-2">
          <div className="font-medium">Imágenes asignadas a editores</div>
          <ul className="space-y-1 text-muted">
            {openAssignments.map((a) => (
              <li key={a.id}>
                {te("shotTypes", a.shot_type || "") || a.shot_type || a.asset_id.slice(0, 8)} →{" "}
                {a.assignee_name || a.assigned_to}
                {a.note ? ` · ${a.note}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex gap-1 border-b border-border mb-4 overflow-x-auto">
        {(
          [
            { id: "datos", labelKey: "nav.data" as const },
            { id: "textos", labelKey: "nav.copy" as const },
            { id: "imagenes", labelKey: "nav.productImages" as const },
            { id: "referencias", labelKey: "nav.references" as const },
            { id: "revision", labelKey: "nav.review" as const },
            { id: "publicacion", labelKey: "nav.publish" as const },
          ] as const
        ).map((tabItem) => (
          <button
            key={tabItem.id}
            type="button"
            onClick={() => setTab(tabItem.id)}
            className={`px-3 py-2 text-sm whitespace-nowrap ${
              tab === tabItem.id ? "border-b-2 border-wine text-wine" : "text-muted"
            }`}
          >
            {t(tabItem.labelKey)}
          </button>
        ))}
      </div>

      {tab === "datos" && (
        <div className="bg-surface border border-border rounded-lg p-6 space-y-3">
          {Object.entries(product.structured_data || {}).map(([k, v]) => (
            <div key={k} className="grid md:grid-cols-3 gap-2 text-sm border-b border-border pb-2">
              <div className="text-muted">{k}</div>
              <div className="md:col-span-2 font-medium">{String(v)}</div>
            </div>
          ))}
          <Link href={`/estudio?product=${product.id}`} className="inline-block text-wine text-sm mt-2">
            Generar en Estudio →
          </Link>
        </div>
      )}

      {tab === "textos" && copyDraft && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h3 className="font-medium">{t("productCopy.title")}</h3>
              <p className="text-xs text-muted mt-1">es · ca · en · fr · de · it · pt · zh</p>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-xs text-muted">
                {t("productCopy.sourceLocale")}
                <select
                  className="mt-1 block border border-border rounded-md px-2 py-2 text-sm"
                  value={sourceLocale}
                  onChange={(e) => setSourceLocale(e.target.value as ContentLocale)}
                >
                  {CONTENT_LOCALES.map((loc) => (
                    <option key={loc} value={loc}>
                      {loc}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2 text-xs text-muted px-1 pb-2">
                <input
                  type="checkbox"
                  checked={overwriteManual}
                  onChange={(e) => setOverwriteManual(e.target.checked)}
                />
                {t("productCopy.overwriteHint")}
              </label>
              <button
                type="button"
                className="rounded-md bg-wine text-white px-3 py-2 text-sm disabled:opacity-50"
                disabled={!!copyBusy}
                onClick={async () => {
                  setCopyBusy("generate");
                  setCopyMsg(null);
                  try {
                    const { job_id } = await api<{ job_id: string }>(
                      `/products/${product.id}/generate-copy`,
                      {
                        method: "POST",
                        body: JSON.stringify({
                          mode: "generate",
                          overwrite_manual: overwriteManual,
                          source_locale: sourceLocale,
                        }),
                      },
                    );
                    for (let i = 0; i < 60; i++) {
                      await new Promise((r) => setTimeout(r, 1000));
                      const job = await api<{ status: string; error_detail?: string }>(
                        `/jobs/${job_id}`,
                      );
                      if (job.status === "completed") {
                        await load();
                        setCopyMsg(t("productCopy.jobDone"));
                        break;
                      }
                      if (job.status === "failed") {
                        setCopyMsg(job.error_detail || t("productCopy.jobFailed"));
                        break;
                      }
                    }
                  } catch (e) {
                    setCopyMsg((e as Error).message || t("productCopy.jobFailed"));
                  } finally {
                    setCopyBusy(null);
                  }
                }}
              >
                {copyBusy === "generate" ? t("productCopy.generating") : t("productCopy.generate")}
              </button>
              <button
                type="button"
                className="rounded-md border border-border px-3 py-2 text-sm disabled:opacity-50"
                disabled={!!copyBusy}
                onClick={async () => {
                  setCopyBusy("translate");
                  setCopyMsg(null);
                  try {
                    // Persist source edits first so translate uses latest text
                    const content: Record<string, Record<string, unknown>> = {
                      ...(product.content || {}),
                    };
                    for (const loc of CONTENT_LOCALES) {
                      const d = copyDraft[loc];
                      const prev = content[loc] || {};
                      content[loc] = {
                        ...prev,
                        name: d.name,
                        description: d.description,
                        seo_title: d.seo_title,
                        seo_meta: d.seo_meta,
                        seo_keywords: d.seo_keywords
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                        manually_edited: prev.manually_edited || [],
                      };
                    }
                    await api(`/products/${product.id}`, {
                      method: "PATCH",
                      body: JSON.stringify({ content }),
                    });
                    const { job_id } = await api<{ job_id: string }>(
                      `/products/${product.id}/generate-copy`,
                      {
                        method: "POST",
                        body: JSON.stringify({
                          mode: "translate",
                          overwrite_manual: overwriteManual,
                          source_locale: sourceLocale,
                        }),
                      },
                    );
                    for (let i = 0; i < 60; i++) {
                      await new Promise((r) => setTimeout(r, 1000));
                      const job = await api<{ status: string; error_detail?: string }>(
                        `/jobs/${job_id}`,
                      );
                      if (job.status === "completed") {
                        await load();
                        setCopyMsg(t("productCopy.jobDone"));
                        break;
                      }
                      if (job.status === "failed") {
                        setCopyMsg(job.error_detail || t("productCopy.jobFailed"));
                        break;
                      }
                    }
                  } catch (e) {
                    setCopyMsg((e as Error).message || t("productCopy.jobFailed"));
                  } finally {
                    setCopyBusy(null);
                  }
                }}
              >
                {copyBusy === "translate" ? t("productCopy.translating") : t("productCopy.translate")}
              </button>
              <button
                type="button"
                className="rounded-md border border-border px-3 py-2 text-sm disabled:opacity-50"
                disabled={!!copyBusy}
                onClick={async () => {
                  setCopyBusy("save");
                  setCopyMsg(null);
                  try {
                    const content: Record<string, Record<string, unknown>> = {
                      ...(product.content || {}),
                    };
                    for (const loc of CONTENT_LOCALES) {
                      const d = copyDraft[loc];
                      const prev = (content[loc] || {}) as Record<string, unknown>;
                      const manual = new Set<string>(
                        Array.isArray(prev.manually_edited)
                          ? (prev.manually_edited as string[])
                          : [],
                      );
                      for (const field of ["name", "description", "seo_title", "seo_meta", "seo_keywords"] as const) {
                        const nextVal =
                          field === "seo_keywords"
                            ? d.seo_keywords
                                .split(",")
                                .map((s) => s.trim())
                                .filter(Boolean)
                            : d[field];
                        const prevVal =
                          field === "seo_keywords"
                            ? Array.isArray(prev.seo_keywords)
                              ? (prev.seo_keywords as string[]).join(", ")
                              : String(prev.seo_keywords || "")
                            : String(prev[field] || "");
                        const comparable =
                          field === "seo_keywords"
                            ? (nextVal as string[]).join(", ")
                            : String(nextVal || "");
                        if (comparable !== prevVal) manual.add(field);
                      }
                      content[loc] = {
                        ...prev,
                        name: d.name,
                        description: d.description,
                        seo_title: d.seo_title,
                        seo_meta: d.seo_meta,
                        seo_keywords: d.seo_keywords
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                        manually_edited: Array.from(manual),
                      };
                    }
                    const updated = await api<Product>(`/products/${product.id}`, {
                      method: "PATCH",
                      body: JSON.stringify({ content }),
                    });
                    setProduct(updated);
                    setCopyDraft(contentToDraft(updated.content));
                    setCopyMsg(t("productCopy.saved"));
                  } catch (e) {
                    setCopyMsg((e as Error).message || t("productCopy.jobFailed"));
                  } finally {
                    setCopyBusy(null);
                  }
                }}
              >
                {copyBusy === "save" ? t("productCopy.saving") : t("productCopy.save")}
              </button>
            </div>
          </div>
          {copyMsg && <p className="text-sm text-muted">{copyMsg}</p>}
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
            {CONTENT_LOCALES.map((loc) => {
              const c = copyDraft[loc];
              return (
                <div
                  key={loc}
                  className="bg-surface border border-border rounded-lg p-4 space-y-3 text-sm"
                >
                  <div className="font-semibold uppercase text-muted">{loc}</div>
                  <label className="block">
                    <span className="text-xs text-muted">{t("productCopy.name")}</span>
                    <input
                      className="mt-1 w-full border border-border rounded-md px-2 py-1.5"
                      value={c.name}
                      onChange={(e) =>
                        setCopyDraft((d) =>
                          d ? { ...d, [loc]: { ...d[loc], name: e.target.value } } : d,
                        )
                      }
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs text-muted">{t("productCopy.description")}</span>
                    <textarea
                      className="mt-1 w-full border border-border rounded-md px-2 py-1.5 min-h-24"
                      value={c.description}
                      onChange={(e) =>
                        setCopyDraft((d) =>
                          d ? { ...d, [loc]: { ...d[loc], description: e.target.value } } : d,
                        )
                      }
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs text-muted">
                      {t("productCopy.seoTitle")} ({c.seo_title.length}/70)
                    </span>
                    <input
                      className="mt-1 w-full border border-border rounded-md px-2 py-1.5"
                      value={c.seo_title}
                      onChange={(e) =>
                        setCopyDraft((d) =>
                          d ? { ...d, [loc]: { ...d[loc], seo_title: e.target.value } } : d,
                        )
                      }
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs text-muted">
                      {t("productCopy.seoMeta")} ({c.seo_meta.length}/160)
                    </span>
                    <textarea
                      className="mt-1 w-full border border-border rounded-md px-2 py-1.5 min-h-16"
                      value={c.seo_meta}
                      onChange={(e) =>
                        setCopyDraft((d) =>
                          d ? { ...d, [loc]: { ...d[loc], seo_meta: e.target.value } } : d,
                        )
                      }
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs text-muted">
                      {t("productCopy.seoKeywords")} · {t("productCopy.keywordsHint")}
                    </span>
                    <input
                      className="mt-1 w-full border border-border rounded-md px-2 py-1.5"
                      value={c.seo_keywords}
                      onChange={(e) =>
                        setCopyDraft((d) =>
                          d ? { ...d, [loc]: { ...d[loc], seo_keywords: e.target.value } } : d,
                        )
                      }
                    />
                  </label>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {tab === "imagenes" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-medium">{t("reviewUi.productImagesTitle")}</h3>
              <p className="text-xs text-muted mt-1 max-w-xl">{t("reviewUi.productImagesDesc")}</p>
            </div>
            <Link
              href={`/estudio?product=${product.id}`}
              className="rounded-md bg-wine text-white px-4 py-2 text-sm"
            >
              {t("reviewUi.generateInStudio")}
            </Link>
          </div>
          {assets.filter((a) => a.origin !== "real_photo").length === 0 ? (
            <div className="bg-surface border border-dashed border-border rounded-lg p-8 text-center text-sm text-muted">
              {t("reviewUi.noFinals")}{" "}
              <button
                type="button"
                className="text-wine underline"
                onClick={() => setTab("referencias")}
              >
                {t("reviewUi.goToRefs")}
              </button>
              .
            </div>
          ) : (
            <ul className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {assets
                .filter((a) => a.origin !== "real_photo")
                .map((asset) => {
                  const mine = openAssignments.find((a) => a.asset_id === asset.id);
                  return (
                    <li
                      key={asset.id}
                      className="bg-surface border border-border rounded-lg overflow-hidden"
                    >
                      <div className="aspect-square bg-raised">
                        {asset.url ? (
                          <img
                            src={asset.url}
                            alt={asset.shot_type}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-muted text-sm">
                            {t("reviewUi.noPreview")}
                          </div>
                        )}
                      </div>
                      <div className="p-3 space-y-2 text-sm">
                        <div className="font-medium">{te("shotTypes", asset.shot_type)}</div>
                        <div className="text-xs text-muted">
                          {te("assetStatus", asset.status)}
                        </div>
                        {mine && (
                          <div className="text-xs text-wine">
                            {t("reviewUi.assigned")}: {mine.note || t("reviewUi.editPerReview")}
                          </div>
                        )}
                        {(canUpload || mine) && (
                          <button
                            type="button"
                            className="w-full rounded-md border border-border py-1.5 text-sm disabled:opacity-50"
                            disabled={uploadingId === asset.id}
                            onClick={() => {
                              setUploadTarget(asset.id);
                              fileRef.current?.click();
                            }}
                          >
                            {uploadingId === asset.id
                              ? t("reviewUi.uploading")
                              : t("reviewUi.uploadEdited")}
                          </button>
                        )}
                      </div>
                    </li>
                  );
                })}
            </ul>
          )}
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              const id = uploadTarget;
              e.target.value = "";
              if (!file || !id) return;
              await uploadEdited(id, file);
            }}
          />
        </div>
      )}

      {tab === "referencias" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-medium">{t("reviewUi.refsTitle")}</h3>
              <p className="text-xs text-muted mt-1 max-w-xl">{t("reviewUi.refsDesc")}</p>
            </div>
            <div className="flex flex-wrap gap-2 items-center">
              {canUpload && (
                <>
                  <select
                    className="border border-border rounded-md px-2 py-2 text-sm"
                    value={newShotType}
                    onChange={(e) => setNewShotType(e.target.value)}
                  >
                    {(["product_front", "product_back", "product_detail"] as const).map((s) => (
                      <option key={s} value={s}>
                        {te("shotTypes", s)}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="rounded-md border border-border px-3 py-2 text-sm"
                    disabled={uploadingId === "new-ref"}
                    onClick={() => newAssetRef.current?.click()}
                  >
                    {uploadingId === "new-ref" ? t("reviewUi.uploading") : t("reviewUi.uploadRef")}
                  </button>
                </>
              )}
              <Link
                href={`/estudio?product=${product.id}`}
                className="rounded-md bg-wine text-white px-4 py-2 text-sm"
              >
                {t("reviewUi.useInStudio")}
              </Link>
            </div>
          </div>
          {assets.filter((a) => a.origin === "real_photo").length === 0 ? (
            <div className="bg-surface border border-dashed border-border rounded-lg p-8 text-center text-sm text-muted">
              {t("reviewUi.noRefs")}
            </div>
          ) : (
            <ul className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {assets
                .filter((a) => a.origin === "real_photo")
                .map((asset) => (
                  <li
                    key={asset.id}
                    className="bg-surface border border-border rounded-lg overflow-hidden"
                  >
                    <div className="aspect-square bg-raised">
                      {asset.url ? (
                        <img
                          src={asset.url}
                          alt={asset.shot_type}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-muted text-sm">
                          {t("reviewUi.noPreview")}
                        </div>
                      )}
                    </div>
                    <div className="p-3 space-y-1 text-sm">
                      <div className="font-medium">{te("shotTypes", asset.shot_type)}</div>
                      <div className="text-xs text-muted">{t("reviewUi.onlyForGenerate")}</div>
                    </div>
                  </li>
                ))}
            </ul>
          )}
          <input
            ref={newAssetRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file || !product) return;
              setUploadingId("new-ref");
              try {
                const storage_key = await uploadViaPresign(file, "asset");
                await api(`/products/${product.id}/assets`, {
                  method: "POST",
                  body: JSON.stringify({
                    storage_key,
                    shot_type: newShotType || "product_front",
                  }),
                });
                await load();
              } finally {
                setUploadingId(null);
              }
            }}
          />
        </div>
      )}

      {tab === "revision" && (
        <div className="space-y-4">
          {(phaseStatus === "in_review" || reviewDetail?.is_open || assets.some((a) => a.origin !== "real_photo")) && (
            <div className="bg-surface border border-border rounded-lg p-4">
              <ReviewImageWorkspace
                productId={product.id}
                reviewId={workspaceReviewId}
                phase={product.current_phase}
                assets={assets}
                comments={activeReviewId && reviewDetail ? reviewDetail.comments : workspaceComments}
                canAnnotate={canAnnotateImages}
                canBulkDecide={canReview}
                onChanged={async () => {
                  await load();
                  if (!activeReviewId && workspaceReviewId) {
                    await loadWorkspaceComments(workspaceReviewId);
                  }
                }}
                shotLabel={(shot) => te("shotTypes", shot) || shot}
                statusLabel={(status) => te("assetStatus", status) || status}
              />
            </div>
          )}

          {!activeReviewId || !reviewDetail ? (
            <div className="bg-surface border border-border rounded-lg p-4 space-y-4">
              <div>
                <h3 className="font-medium">{t("reviewUi.reviewsTitle")}</h3>
                <p className="text-xs text-muted mt-1">{t("reviewUi.reviewsDesc")}</p>
              </div>
              {reviews.length === 0 ? (
                <p className="text-sm text-muted">{t("reviewUi.noReviews")}</p>
              ) : (
                <ul className="divide-y divide-border">
                  {reviews.map((r) => (
                    <li key={r.id}>
                      <button
                        type="button"
                        className="w-full text-left py-3 px-1 hover:bg-raised/60 rounded-md transition-colors"
                        onClick={() => void loadReviewDetail(r.id)}
                      >
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="font-medium">
                            {te("reviewDecision", r.decision) || r.decision}
                          </span>
                          {r.is_open && (
                            <span className="text-xs rounded-full bg-warning-subtle text-warning px-2 py-0.5">
                              {t("reviewUi.open")}
                            </span>
                          )}
                          {r.phase && (
                            <span className="text-xs text-muted">{te("phases", r.phase)}</span>
                          )}
                        </div>
                        <p className="text-sm text-muted mt-1 line-clamp-2">
                          {r.comment || t("reviewUi.noComment")}
                        </p>
                        <div className="text-xs text-muted mt-1 flex flex-wrap gap-3">
                          <span>{r.reviewer_name || t("reviewUi.reviewer")}</span>
                          <span>{new Date(r.created_at).toLocaleString()}</span>
                          <span>
                            {r.comment_count} {t("reviewUi.comments")}
                          </span>
                          <span>
                            {r.version_count} {t("reviewUi.versions")}
                          </span>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  className="text-sm text-wine"
                  onClick={() => {
                    setActiveReviewId(null);
                    setReviewDetail(null);
                  }}
                >
                  {t("reviewUi.backToReviews")}
                </button>
                {reviewDetail.is_open && (
                  <span className="text-xs rounded-full bg-warning-subtle text-warning px-2 py-0.5">
                    {t("reviewUi.open")}
                  </span>
                )}
              </div>

              <div className="bg-surface border border-border rounded-lg p-4 space-y-2">
                <div className="flex flex-wrap gap-2 text-sm items-center">
                  <span className="font-semibold">
                    {te("reviewDecision", reviewDetail.decision) || reviewDetail.decision}
                  </span>
                  {reviewDetail.phase && (
                    <span className="text-muted">{te("phases", reviewDetail.phase)}</span>
                  )}
                </div>
                <p className="text-sm">{reviewDetail.comment}</p>
                <p className="text-xs text-muted">
                  {reviewDetail.reviewer_name || t("reviewUi.reviewer")} ·{" "}
                  {new Date(reviewDetail.created_at).toLocaleString()}
                </p>
                {reviewDetail.awaiting_resubmit && (
                  <p className="text-xs text-warning">{t("reviewUi.awaitingResubmit")}</p>
                )}
                {reviewDetail.closing && (
                  <div className="mt-2 rounded-md bg-success-subtle text-success p-3 text-sm">
                    {t("reviewUi.closed")}: {te("reviewDecision", reviewDetail.closing.decision)} ·{" "}
                    {reviewDetail.closing.reviewer_name || t("reviewUi.reviewer")} ·{" "}
                    {new Date(reviewDetail.closing.created_at).toLocaleString()}
                    {reviewDetail.closing.comment ? ` — ${reviewDetail.closing.comment}` : ""}
                  </div>
                )}
              </div>

              {reviewDetail.assignments.length > 0 && (
                <div className="bg-surface border border-border rounded-lg p-4 space-y-2">
                  <h4 className="font-medium text-sm">{t("tasksUi.assignedImages")}</h4>
                  <ul className="text-sm space-y-1 text-muted">
                    {reviewDetail.assignments.map((a) => (
                      <li key={a.id}>
                        {te("shotTypes", a.shot_type || "") || a.shot_type} →{" "}
                        {a.assignee_name || a.assigned_to} · {te("assignmentStatus", a.status)}
                        {a.note ? ` · ${a.note}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {reviewDetail.can_upload && (
                <div className="bg-surface border border-border rounded-lg p-4 space-y-2">
                  <div className="flex flex-wrap gap-2 items-end">
                    <label className="text-sm">
                      <span className="text-xs text-muted">{t("reviewUi.uploadEdited")}</span>
                      <select
                        className="mt-1 block border border-border rounded-md px-2 py-2 text-sm"
                        value={newShotType}
                        onChange={(e) => setNewShotType(e.target.value)}
                      >
                        {SHOT_OPTIONS.map((s) => (
                          <option key={s} value={s}>
                            {te("shotTypes", s)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      type="button"
                      className="rounded-md border border-border px-3 py-2 text-sm"
                      onClick={() => newAssetRef.current?.click()}
                    >
                      {t("reviewUi.uploadEdited")}
                    </button>
                  </div>
                  {assets.filter((a) => a.origin !== "real_photo").length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {assets
                        .filter((a) => a.origin !== "real_photo")
                        .map((asset) => (
                          <button
                            key={asset.id}
                            type="button"
                            className="text-xs rounded-md border border-border px-2 py-1"
                            disabled={uploadingId === asset.id}
                            onClick={() => {
                              setRevisionUploadAssetId(asset.id);
                              revisionAssetRef.current?.click();
                            }}
                          >
                            {te("shotTypes", asset.shot_type)}
                          </button>
                        ))}
                    </div>
                  )}
                  <input
                    ref={newAssetRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={async (e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (!file) return;
                      setUploadingId("new");
                      try {
                        const storage_key = await uploadViaPresign(file, "asset");
                        await api(`/products/${product.id}/assets`, {
                          method: "POST",
                          body: JSON.stringify({ storage_key, shot_type: newShotType }),
                        });
                        await load();
                      } finally {
                        setUploadingId(null);
                      }
                    }}
                  />
                  <input
                    ref={revisionAssetRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={async (e) => {
                      const file = e.target.files?.[0];
                      const id = revisionUploadAssetId;
                      e.target.value = "";
                      if (!file || !id) return;
                      await uploadEdited(id, file);
                      setRevisionUploadAssetId(null);
                    }}
                  />
                </div>
              )}

              <div className="bg-surface border border-border rounded-lg p-4 space-y-3">
                <h4 className="font-medium text-sm">{t("reviewUi.threadTitle")}</h4>
                {reviewDetail.comments.filter((c) => !c.annotation).length === 0 ? (
                  <p className="text-sm text-muted">{t("reviewUi.noComment")}</p>
                ) : (
                  <ul className="space-y-3">
                    {reviewDetail.comments
                      .filter((c) => !c.annotation)
                      .map((c) => (
                        <li key={c.id} className="border-l-2 border-border pl-3">
                          <div className="text-xs text-muted">
                            {c.author_name || t("reviewUi.reviewer")} ·{" "}
                            {new Date(c.created_at).toLocaleString()}
                          </div>
                          <p className="text-sm mt-0.5 whitespace-pre-wrap">{c.body}</p>
                        </li>
                      ))}
                  </ul>
                )}
                {reviewDetail.can_reply && (
                  <div className="space-y-2 border-t border-border pt-3">
                    <textarea
                      className="w-full border border-border rounded-md p-3 min-h-24 text-sm"
                      placeholder={t("reviewUi.replyPlaceholder")}
                      value={threadComment}
                      onChange={(e) => setThreadComment(e.target.value)}
                    />
                    <button
                      type="button"
                      className="rounded-md bg-wine text-white px-3 py-2 text-sm disabled:opacity-50"
                      disabled={postingComment || !threadComment.trim()}
                      onClick={async () => {
                        setPostingComment(true);
                        try {
                          await api(`/products/${product.id}/comments`, {
                            method: "POST",
                            body: JSON.stringify({
                              body: threadComment.trim(),
                              phase: product.current_phase,
                              review_id: reviewDetail.id,
                            }),
                          });
                          setThreadComment("");
                          await load();
                        } finally {
                          setPostingComment(false);
                        }
                      }}
                    >
                      {postingComment ? t("common.loading") : t("reviewUi.sendReply")}
                    </button>
                  </div>
                )}
              </div>

              {reviewDetail.can_decide && (
                <div className="bg-surface border border-wine/30 rounded-lg p-4 space-y-3">
                  <h4 className="font-medium text-sm">{t("reviewUi.decideComment")}</h4>
                  <textarea
                    className="w-full border border-border rounded-md p-3 min-h-20 text-sm"
                    placeholder={t("reviewUi.decideComment")}
                    value={decideComment}
                    onChange={(e) => setDecideComment(e.target.value)}
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="rounded-md bg-wine text-white px-3 py-2 text-sm"
                      onClick={async () => {
                        await api(`/products/${product.id}/review`, {
                          method: "POST",
                          body: JSON.stringify({
                            decision: "approved",
                            requirements_checked: [],
                          }),
                        });
                        setDecideComment("");
                        setActiveReviewId(null);
                        setReviewDetail(null);
                        await load();
                      }}
                    >
                      {t("reviewUi.approve")}
                    </button>
                    <button
                      type="button"
                      className="rounded-md border border-border px-3 py-2 text-sm"
                      onClick={async () => {
                        await api(`/products/${product.id}/review`, {
                          method: "POST",
                          body: JSON.stringify({
                            decision: "changes_requested",
                            comment: decideComment,
                            requirements_checked: [],
                          }),
                        });
                        setDecideComment("");
                        await load();
                        const open = (
                          await api<{ data: ReviewSummary[] }>(`/products/${product.id}/reviews`)
                        ).data.find((r) => r.is_open);
                        if (open) await loadReviewDetail(open.id);
                      }}
                    >
                      {t("reviewUi.requestChanges")}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {tab === "publicacion" && (
        <div className="bg-surface border border-border rounded-lg p-6 text-sm text-muted space-y-3">
          <p>Estado de publicación de Shopify.</p>
          {product.current_phase === "published" ? (
            <p className="text-success font-medium">Producto publicado.</p>
          ) : (
            <p>Aún no publicado. La publicación se lanza desde la fase de aprobación.</p>
          )}
        </div>
      )}

      <PrimaryActionBar primary={primary} hint={hint} />

      {reviewOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <button type="button" className="absolute inset-0 bg-black/30" onClick={() => setReviewOpen(false)} />
          <div className="relative w-full max-w-lg bg-surface h-full p-6 shadow-md overflow-auto space-y-4">
            <h2 className="font-semibold text-lg">Revisión</h2>
            {checklist && <WhatsMissing criteria={checklist.criteria} />}
            <textarea
              className="w-full border border-border rounded-md p-3 min-h-24 text-sm"
              placeholder="Comentario (obligatorio para solicitar cambios)"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />

            {assets.length > 0 && (
              <div className="space-y-3 border-t border-border pt-4">
                <div>
                  <h3 className="font-medium text-sm">Asignar imágenes a editores</h3>
                  <p className="text-xs text-muted mt-1">
                    Selecciona las imágenes que necesitan retoque y el editor responsable.
                  </p>
                </div>
                {editors.length > 0 && (
                  <label className="block text-sm">
                    <span className="text-muted text-xs">Editor por defecto</span>
                    <select
                      className="mt-1 w-full border border-border rounded-md px-2 py-2 text-sm"
                      value={defaultEditor}
                      onChange={(e) => setDefaultEditor(e.target.value)}
                    >
                      {editors.map((ed) => (
                        <option key={ed.user_id} value={ed.user_id}>
                          {ed.name} ({ed.email})
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {editors.length === 0 && (
                  <p className="text-xs text-danger">
                    No hay editores en el proyecto. Asigna rol editor en Usuarios o en el equipo del proyecto.
                  </p>
                )}
                <ul className="space-y-3 max-h-72 overflow-auto">
                  {assets.filter((a) => a.origin !== "real_photo").length === 0 ? (
                    <li className="text-sm text-muted p-2">
                      No hay imágenes del producto para asignar. Primero genera en el Estudio y
                      añádelas al producto (las referencias de prenda no se asignan a editores).
                    </li>
                  ) : null}
                  {assets
                    .filter((a) => a.origin !== "real_photo")
                    .map((asset) => {
                    const on = !!selectedAssets[asset.id];
                    return (
                      <li key={asset.id} className="border border-border rounded-md p-2 space-y-2">
                        <label className="flex gap-3 items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={on}
                            onChange={(e) =>
                              setSelectedAssets((s) => ({ ...s, [asset.id]: e.target.checked }))
                            }
                          />
                          <div className="h-12 w-12 rounded bg-raised overflow-hidden shrink-0">
                            {asset.url ? (
                              <img src={asset.url} alt="" className="w-full h-full object-cover" />
                            ) : null}
                          </div>
                          <div className="text-sm min-w-0">
                            <div className="font-medium truncate">{te("shotTypes", asset.shot_type)}</div>
                            <div className="text-xs text-muted">{te("assetStatus", asset.status)}</div>
                          </div>
                        </label>
                        {on && (
                          <div className="pl-7 space-y-2">
                            <select
                              className="w-full border border-border rounded-md px-2 py-1.5 text-sm"
                              value={assetEditors[asset.id] || defaultEditor}
                              onChange={(e) =>
                                setAssetEditors((s) => ({ ...s, [asset.id]: e.target.value }))
                              }
                            >
                              {editors.map((ed) => (
                                <option key={ed.user_id} value={ed.user_id}>
                                  {ed.name}
                                </option>
                              ))}
                            </select>
                            <input
                              className="w-full border border-border rounded-md px-2 py-1.5 text-sm"
                              placeholder="Nota específica (opcional)"
                              value={assetNotes[asset.id] || ""}
                              onChange={(e) =>
                                setAssetNotes((s) => ({ ...s, [asset.id]: e.target.value }))
                              }
                            />
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            <div className="flex flex-col gap-2 pt-2">
              <button
                type="button"
                className="rounded-md bg-wine text-white py-2"
                onClick={async () => {
                  if (product.current_phase === "approval" && canPublish) {
                    await api(`/products/${product.id}/publish`, {
                      method: "POST",
                      body: JSON.stringify({ confirm_text: product.internal_reference }),
                    });
                  } else {
                    await api(`/products/${product.id}/review`, {
                      method: "POST",
                      body: JSON.stringify({
                        decision: "approved",
                        requirements_checked: [],
                        assignments: buildAssignments(),
                      }),
                    });
                  }
                  setReviewOpen(false);
                  await load();
                }}
              >
                {product.current_phase === "approval" ? "Aprobar y publicar" : "Aprobar"}
              </button>
              <button
                type="button"
                className="rounded-md border border-border py-2"
                onClick={async () => {
                  const drafts = buildAssignments();
                  await api(`/products/${product.id}/review`, {
                    method: "POST",
                    body: JSON.stringify({
                      decision: "changes_requested",
                      comment,
                      requirements_checked: [],
                      assignments: drafts,
                    }),
                  });
                  setReviewOpen(false);
                  setSelectedAssets({});
                  await load();
                }}
              >
                Solicitar cambios
                {Object.values(selectedAssets).some(Boolean)
                  ? ` (${Object.values(selectedAssets).filter(Boolean).length} imágenes)`
                  : ""}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
