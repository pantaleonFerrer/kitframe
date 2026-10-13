"use client";

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { QcStatus } from "@/lib/types";
import { QCBadge } from "@/components/QCBadge";

export function AssetTile({
  src,
  alt,
  qcStatus,
  actions,
  selected,
  onClick,
  className,
}: {
  src?: string | null;
  alt: string;
  qcStatus?: QcStatus;
  actions?: ReactNode;
  selected?: boolean;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(e) => {
        if (!onClick) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className={cn(
        "group relative aspect-square overflow-hidden rounded-lg border border-border bg-surface-raised shadow-sm transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wine/40",
        selected && "ring-2 ring-sand",
        onClick && "cursor-pointer",
        className,
      )}
    >
      {src ? (
        <img src={src} alt={alt} className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-xs text-muted">
          No image
        </div>
      )}
      {qcStatus ? (
        <div className="absolute left-2 top-2">
          <QCBadge status={qcStatus} />
        </div>
      ) : null}
      {actions ? (
        <div className="absolute inset-x-0 bottom-0 translate-y-full bg-carbon/80 p-2 opacity-0 transition-all group-hover:translate-y-0 group-hover:opacity-100 group-focus-within:translate-y-0 group-focus-within:opacity-100">
          <div className="flex flex-wrap gap-1">{actions}</div>
        </div>
      ) : null}
    </div>
  );
}
