"use client";

import { useCallback, useRef, useState } from "react";
import { useI18n } from "@/hooks/use-i18n";

export type AnnotationRect = {
  x: number;
  y: number;
  w: number;
  h: number;
  color?: string;
};

export type AnnotatedComment = {
  id: string;
  body: string;
  author_name?: string | null;
  created_at: string;
  asset_version_id?: string | null;
  annotation?: AnnotationRect | null;
};

const COLORS = ["#7A1F2B", "#0B6E4F", "#1D4E89", "#C45C26", "#5C4B8A"] as const;

type Props = {
  src: string;
  alt: string;
  comments: AnnotatedComment[];
  canAnnotate?: boolean;
  onSubmitAnnotation?: (payload: {
    body: string;
    annotation: AnnotationRect;
  }) => Promise<void> | void;
};

export function ImageAnnotator({
  src,
  alt,
  comments,
  canAnnotate = false,
  onSubmitAnnotation,
}: Props) {
  const { t } = useI18n();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [color, setColor] = useState<string>(COLORS[0]);
  const [drawing, setDrawing] = useState(false);
  const [start, setStart] = useState<{ x: number; y: number } | null>(null);
  const [draft, setDraft] = useState<AnnotationRect | null>(null);
  const [pending, setPending] = useState<AnnotationRect | null>(null);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);

  const annotated = comments.filter((c) => c.annotation);

  const toNorm = useCallback((clientX: number, clientY: number) => {
    const el = wrapRef.current;
    if (!el) return { x: 0, y: 0 };
    const r = el.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (clientY - r.top) / r.height)),
    };
  }, []);

  const onPointerDown = (e: React.PointerEvent) => {
    if (!canAnnotate || pending) return;
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    const p = toNorm(e.clientX, e.clientY);
    setDrawing(true);
    setStart(p);
    setDraft({ x: p.x, y: p.y, w: 0, h: 0, color });
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!drawing || !start) return;
    const p = toNorm(e.clientX, e.clientY);
    const x = Math.min(start.x, p.x);
    const y = Math.min(start.y, p.y);
    const w = Math.abs(p.x - start.x);
    const h = Math.abs(p.y - start.y);
    setDraft({ x, y, w, h, color });
  };

  const onPointerUp = () => {
    if (!drawing || !draft) {
      setDrawing(false);
      setStart(null);
      return;
    }
    setDrawing(false);
    setStart(null);
    if (draft.w < 0.02 || draft.h < 0.02) {
      setDraft(null);
      return;
    }
    setPending(draft);
    setDraft(null);
  };

  const submit = async () => {
    if (!pending || !body.trim() || !onSubmitAnnotation) return;
    setBusy(true);
    try {
      await onSubmitAnnotation({ body: body.trim(), annotation: pending });
      setPending(null);
      setBody("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      {canAnnotate && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted">{t("reviewUi.annotationColor")}</span>
          {COLORS.map((c) => (
            <button
              key={c}
              type="button"
              aria-label={c}
              onClick={() => setColor(c)}
              className={`h-5 w-5 rounded-full border-2 ${
                color === c ? "border-carbon scale-110" : "border-transparent"
              }`}
              style={{ backgroundColor: c }}
            />
          ))}
          <span className="text-muted ml-2">{t("reviewUi.drawHint")}</span>
        </div>
      )}

      <div
        ref={wrapRef}
        className={`relative aspect-square bg-raised rounded-lg overflow-hidden border border-border ${
          canAnnotate && !pending ? "cursor-crosshair" : ""
        }`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => {
          if (drawing) onPointerUp();
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} className="absolute inset-0 h-full w-full object-contain pointer-events-none" />
        {annotated.map((c, i) => {
          const a = c.annotation!;
          const active = activeId === c.id;
          return (
            <button
              key={c.id}
              type="button"
              className="absolute border-2 bg-transparent"
              style={{
                left: `${a.x * 100}%`,
                top: `${a.y * 100}%`,
                width: `${a.w * 100}%`,
                height: `${a.h * 100}%`,
                borderColor: a.color || COLORS[0],
                boxShadow: active ? `0 0 0 2px ${a.color || COLORS[0]}` : undefined,
              }}
              onClick={(e) => {
                e.stopPropagation();
                setActiveId(c.id);
              }}
              title={c.body}
            >
              <span
                className="absolute -top-2 -left-2 h-5 w-5 rounded-full text-[10px] text-white flex items-center justify-center"
                style={{ backgroundColor: a.color || COLORS[0] }}
              >
                {i + 1}
              </span>
            </button>
          );
        })}
        {draft && (
          <div
            className="absolute border-2 pointer-events-none"
            style={{
              left: `${draft.x * 100}%`,
              top: `${draft.y * 100}%`,
              width: `${draft.w * 100}%`,
              height: `${draft.h * 100}%`,
              borderColor: draft.color,
              backgroundColor: `${draft.color}22`,
            }}
          />
        )}
        {pending && (
          <div
            className="absolute border-2 border-dashed pointer-events-none"
            style={{
              left: `${pending.x * 100}%`,
              top: `${pending.y * 100}%`,
              width: `${pending.w * 100}%`,
              height: `${pending.h * 100}%`,
              borderColor: pending.color,
              backgroundColor: `${pending.color}33`,
            }}
          />
        )}
      </div>

      {pending && (
        <div className="rounded-lg border border-border bg-surface p-3 space-y-2">
          <p className="text-xs text-muted">{t("reviewUi.annotationPrompt")}</p>
          <textarea
            className="w-full border border-border rounded-md px-3 py-2 text-sm min-h-20"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={t("reviewUi.commentPlaceholder")}
            autoFocus
          />
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              className="rounded-md border border-border px-3 py-1.5 text-sm"
              onClick={() => {
                setPending(null);
                setBody("");
              }}
            >
              {t("common.cancel")}
            </button>
            <button
              type="button"
              className="rounded-md bg-wine text-white px-3 py-1.5 text-sm disabled:opacity-50"
              disabled={busy || !body.trim()}
              onClick={() => void submit()}
            >
              {busy ? t("common.loading") : t("reviewUi.saveAnnotation")}
            </button>
          </div>
        </div>
      )}

      {annotated.length > 0 && (
        <ul className="space-y-2 max-h-48 overflow-auto">
          {annotated.map((c, i) => (
            <li key={c.id}>
              <button
                type="button"
                className={`w-full text-left rounded-md border px-3 py-2 text-sm ${
                  activeId === c.id ? "border-wine bg-wine/5" : "border-border"
                }`}
                onClick={() => setActiveId(c.id)}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="h-5 w-5 rounded-full text-[10px] text-white flex items-center justify-center shrink-0"
                    style={{ backgroundColor: c.annotation?.color || COLORS[0] }}
                  >
                    {i + 1}
                  </span>
                  <span className="font-medium truncate">{c.author_name || "—"}</span>
                  <span className="text-xs text-muted ml-auto">
                    {new Date(c.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="mt-1 text-muted">{c.body}</p>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
