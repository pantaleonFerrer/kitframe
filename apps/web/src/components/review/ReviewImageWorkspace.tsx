"use client";

import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/hooks/use-i18n";
import {
  ImageAnnotator,
  type AnnotatedComment,
  type AnnotationRect,
} from "./ImageAnnotator";

export type ReviewAsset = {
  id: string;
  shot_type: string;
  status: string;
  origin?: string;
  url?: string | null;
  current_version_id?: string | null;
};

type ViewMode = "thumbs" | "boxes" | "panel";

type Props = {
  productId: string;
  reviewId?: string | null;
  phase?: string | null;
  assets: ReviewAsset[];
  comments: AnnotatedComment[];
  canAnnotate?: boolean;
  canBulkDecide?: boolean;
  onChanged: () => Promise<void> | void;
  shotLabel: (shot: string) => string;
  statusLabel: (status: string) => string;
};

export function ReviewImageWorkspace({
  productId,
  reviewId,
  phase,
  assets,
  comments,
  canAnnotate = false,
  canBulkDecide = false,
  onChanged,
  shotLabel,
  statusLabel,
}: Props) {
  const { t } = useI18n();
  const [viewMode, setViewMode] = useState<ViewMode>("boxes");
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [activeId, setActiveId] = useState<string | null>(assets[0]?.id ?? null);
  const [bulkComment, setBulkComment] = useState("");
  const [showBulkComment, setShowBulkComment] = useState(false);
  const [busy, setBusy] = useState(false);

  const productAssets = useMemo(
    () => assets.filter((a) => a.origin !== "real_photo"),
    [assets],
  );

  const selectedIds = useMemo(
    () => productAssets.filter((a) => selected[a.id]).map((a) => a.id),
    [productAssets, selected],
  );

  const commentsByVersion = useMemo(() => {
    const map = new Map<string, AnnotatedComment[]>();
    for (const c of comments) {
      if (!c.asset_version_id) continue;
      const list = map.get(c.asset_version_id) || [];
      list.push(c);
      map.set(c.asset_version_id, list);
    }
    return map;
  }, [comments]);

  const active = productAssets.find((a) => a.id === activeId) || productAssets[0] || null;
  const activeComments = active?.current_version_id
    ? commentsByVersion.get(active.current_version_id) || []
    : [];

  const toggle = (id: string) => {
    setSelected((s) => ({ ...s, [id]: !s[id] }));
  };

  const selectAll = () => {
    const all = Object.fromEntries(productAssets.map((a) => [a.id, true]));
    setSelected(all);
  };

  const clearSelection = () => setSelected({});

  const patchStatus = async (
    status: "selected" | "discarded",
    ids: string[] = selectedIds,
  ) => {
    if (ids.length === 0) return;
    setBusy(true);
    try {
      await Promise.all(
        ids.map((id) =>
          api(`/assets/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ status }),
          }),
        ),
      );
      clearSelection();
      await onChanged();
    } finally {
      setBusy(false);
    }
  };

  const submitBulkComment = async () => {
    if (!bulkComment.trim() || selectedIds.length === 0) return;
    setBusy(true);
    try {
      const targets = productAssets.filter((a) => selected[a.id] && a.current_version_id);
      await Promise.all(
        targets.map((a) =>
          api(`/products/${productId}/comments`, {
            method: "POST",
            body: JSON.stringify({
              body: bulkComment.trim(),
              phase: phase || undefined,
              review_id: reviewId || undefined,
              asset_version_id: a.current_version_id,
            }),
          }),
        ),
      );
      setBulkComment("");
      setShowBulkComment(false);
      clearSelection();
      await onChanged();
    } finally {
      setBusy(false);
    }
  };

  const submitAnnotation = async (payload: {
    body: string;
    annotation: AnnotationRect;
  }) => {
    if (!active?.current_version_id) return;
    await api(`/products/${productId}/comments`, {
      method: "POST",
      body: JSON.stringify({
        body: payload.body,
        phase: phase || undefined,
        review_id: reviewId || undefined,
        asset_version_id: active.current_version_id,
        annotation: payload.annotation,
      }),
    });
    await onChanged();
  };

  if (productAssets.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-6 text-sm text-muted">
        {t("reviewUi.noProductImages")}
      </div>
    );
  }

  const gridClass =
    viewMode === "thumbs"
      ? "grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2"
      : "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3";

  const tile = (asset: ReviewAsset) => {
    const versionComments = asset.current_version_id
      ? commentsByVersion.get(asset.current_version_id) || []
      : [];
    const on = !!selected[asset.id];
    const isActive = active?.id === asset.id;
    return (
      <div
        key={asset.id}
        className={`relative rounded-lg border overflow-hidden bg-surface ${
          isActive ? "border-wine ring-2 ring-wine/20" : "border-border"
        }`}
      >
        <label className="absolute top-2 left-2 z-10 flex items-center gap-1 rounded bg-carbon/70 px-1.5 py-0.5 text-white text-[10px]">
          <input
            type="checkbox"
            checked={on}
            onChange={() => toggle(asset.id)}
          />
          {t("reviewUi.select")}
        </label>
        <button
          type="button"
          className="block w-full text-left"
          onClick={() => {
            setActiveId(asset.id);
            if (viewMode !== "panel") setViewMode("panel");
          }}
        >
          <div className={viewMode === "thumbs" ? "aspect-square bg-raised" : "aspect-[4/5] bg-raised"}>
            {asset.url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={asset.url} alt="" className="h-full w-full object-cover" />
            ) : (
              <div className="h-full w-full flex items-center justify-center text-xs text-muted">
                {t("reviewUi.noPreview")}
              </div>
            )}
          </div>
          {viewMode !== "thumbs" && (
            <div className="p-2 text-xs space-y-0.5">
              <div className="font-medium">{shotLabel(asset.shot_type)}</div>
              <div className="text-muted">
                {statusLabel(asset.status)} · {versionComments.length}{" "}
                {t("reviewUi.commentsCount")}
              </div>
            </div>
          )}
        </button>
      </div>
    );
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div>
          <h3 className="font-medium text-sm">{t("reviewUi.imagesTitle")}</h3>
          <p className="text-xs text-muted">{t("reviewUi.imagesDesc")}</p>
        </div>
        <div className="flex rounded-md border border-border overflow-hidden text-xs">
          {(
            [
              ["thumbs", "reviewUi.viewThumbs"],
              ["boxes", "reviewUi.viewBoxes"],
              ["panel", "reviewUi.viewPanel"],
            ] as const
          ).map(([mode, key]) => (
            <button
              key={mode}
              type="button"
              className={`px-3 py-1.5 ${viewMode === mode ? "bg-wine text-white" : "bg-surface"}`}
              onClick={() => setViewMode(mode)}
            >
              {t(key)}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        <button type="button" className="underline text-wine" onClick={selectAll}>
          {t("reviewUi.selectAll")}
        </button>
        <button type="button" className="underline text-muted" onClick={clearSelection}>
          {t("reviewUi.clearSelection")}
        </button>
        <span className="text-muted">
          {selectedIds.length} {t("reviewUi.selectedCount")}
        </span>
      </div>

      {viewMode === "panel" ? (
        <div className="grid lg:grid-cols-2 gap-4">
          <div className={gridClass}>{productAssets.map(tile)}</div>
          <div className="rounded-lg border border-border bg-surface p-3 space-y-3 min-h-[24rem]">
            {active ? (
              <>
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="font-medium text-sm">{shotLabel(active.shot_type)}</div>
                    <div className="text-xs text-muted">{statusLabel(active.status)}</div>
                  </div>
                  {canBulkDecide && (
                    <div className="flex gap-1">
                      <button
                        type="button"
                        className="rounded-md border border-border px-2 py-1 text-xs"
                        disabled={busy}
                        onClick={() => void patchStatus("selected", [active.id])}
                      >
                        {t("reviewUi.approveImage")}
                      </button>
                      <button
                        type="button"
                        className="rounded-md border border-border px-2 py-1 text-xs"
                        disabled={busy}
                        onClick={() => void patchStatus("discarded", [active.id])}
                      >
                        {t("reviewUi.rejectImage")}
                      </button>
                    </div>
                  )}
                </div>
                {active.url ? (
                  <ImageAnnotator
                    src={active.url}
                    alt={shotLabel(active.shot_type)}
                    comments={activeComments}
                    canAnnotate={canAnnotate}
                    onSubmitAnnotation={submitAnnotation}
                  />
                ) : (
                  <p className="text-sm text-muted">{t("reviewUi.noPreview")}</p>
                )}
              </>
            ) : (
              <p className="text-sm text-muted">{t("reviewUi.pickImage")}</p>
            )}
          </div>
        </div>
      ) : (
        <div className={gridClass}>{productAssets.map(tile)}</div>
      )}

      {selectedIds.length > 0 && (
        <div className="sticky bottom-3 z-20 rounded-lg border border-border bg-surface shadow-md p-3 space-y-2">
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-sm font-medium">
              {selectedIds.length} {t("reviewUi.selectedCount")}
            </span>
            <button
              type="button"
              className="rounded-md bg-wine text-white px-3 py-1.5 text-sm disabled:opacity-50"
              disabled={busy}
              onClick={() => setShowBulkComment((v) => !v)}
            >
              {t("reviewUi.bulkComment")}
            </button>
            {canBulkDecide && (
              <>
                <button
                  type="button"
                  className="rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void patchStatus("selected")}
                >
                  {t("reviewUi.bulkApprove")}
                </button>
                <button
                  type="button"
                  className="rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void patchStatus("discarded")}
                >
                  {t("reviewUi.bulkReject")}
                </button>
              </>
            )}
          </div>
          {showBulkComment && (
            <div className="space-y-2">
              <textarea
                className="w-full border border-border rounded-md px-3 py-2 text-sm min-h-20"
                value={bulkComment}
                onChange={(e) => setBulkComment(e.target.value)}
                placeholder={t("reviewUi.bulkCommentPlaceholder")}
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  className="rounded-md border border-border px-3 py-1.5 text-sm"
                  onClick={() => setShowBulkComment(false)}
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="button"
                  className="rounded-md bg-wine text-white px-3 py-1.5 text-sm disabled:opacity-50"
                  disabled={busy || !bulkComment.trim()}
                  onClick={() => void submitBulkComment()}
                >
                  {t("reviewUi.sendComments")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
