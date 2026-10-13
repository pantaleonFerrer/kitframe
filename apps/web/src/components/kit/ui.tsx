"use client";

import { cn } from "@/lib/utils";
import { useI18n } from "@/hooks/use-i18n";

const PHASE_KEYS = ["data", "visuals", "retouch", "approval", "published"] as const;

export function PhaseStepper({
  current,
  statuses,
}: {
  current: string;
  statuses?: Record<string, string>;
}) {
  const { te } = useI18n();
  const idx = PHASE_KEYS.findIndex((p) => p === current);
  return (
    <ol className="flex flex-wrap gap-2">
      {PHASE_KEYS.map((key, i) => {
        const active = key === current;
        const done = i < idx || current === "published";
        const status = statuses?.[key];
        return (
          <li
            key={key}
            className={cn(
              "rounded-full px-3 py-1 text-xs border",
              active && "bg-wine text-white border-wine",
              done && !active && "bg-success-subtle text-success border-success/30",
              !active && !done && "bg-raised text-muted border-border",
            )}
          >
            {te("phases", key)}
            {status ? ` · ${te("phaseStatus", status)}` : ""}
          </li>
        );
      })}
    </ol>
  );
}

export function StatusChip({ status }: { status: string }) {
  const { te } = useI18n();
  const map: Record<string, string> = {
    todo: "bg-raised text-muted",
    in_progress: "bg-info-subtle text-info",
    in_review: "bg-warning-subtle text-warning",
    changes_requested: "bg-danger-subtle text-danger",
    done: "bg-success-subtle text-success",
  };
  return (
    <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", map[status] || "bg-raised")}>
      {te("phaseStatus", status) || status}
    </span>
  );
}

export function QCBadge({ result }: { result?: string | null }) {
  const { te } = useI18n();
  const map: Record<string, string> = {
    pass: "bg-success-subtle text-success",
    needs_review: "bg-warning-subtle text-warning",
    fail: "bg-danger-subtle text-danger",
    pending: "bg-raised text-muted",
    overridden: "bg-info-subtle text-info",
  };
  const key = result || "pending";
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs", map[key])}>
      {te("status", key) || key}
    </span>
  );
}

export function EmptyState({
  title,
  action,
}: {
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-surface p-10 text-center animate-fade-in">
      <p className="font-serif text-xl text-carbon mb-4">{title}</p>
      {action}
    </div>
  );
}

export function WhatsMissing({
  criteria,
}: {
  criteria: { code: string; ok: boolean; message_key?: string; details?: Record<string, unknown> }[];
}) {
  const missing = criteria.filter((c) => !c.ok);
  if (missing.length === 0) return null;
  return (
    <div className="rounded-lg border border-warning/30 bg-warning-subtle p-4 mb-4">
      <h3 className="font-medium text-sm mb-2">Qué falta</h3>
      <ul className="space-y-1 text-sm">
        {missing.map((c) => (
          <li key={c.code} className="flex gap-2">
            <span className="text-warning">•</span>
            <span>{c.code.replace(/_/g, " ")}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PrimaryActionBar({
  primary,
  secondary,
  hint,
}: {
  primary?: React.ReactNode;
  secondary?: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="sticky bottom-0 z-10 -mx-4 md:-mx-6 mt-8 border-t border-border bg-surface/95 backdrop-blur px-4 md:px-6 py-3 flex items-center gap-3">
      <div className="flex-1 text-sm text-muted">{hint}</div>
      <div className="flex items-center gap-2">
        {secondary}
        {primary}
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-raised", className)} />;
}
