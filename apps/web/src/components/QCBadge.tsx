"use client";

import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { QcStatus } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/hooks/use-i18n";
import type { MessageKey } from "@/lib/i18n";

const LABEL_KEYS: Record<QcStatus, MessageKey> = {
  pass: "status.pass",
  needs_review: "status.needs_review",
  fail: "status.fail",
  pending: "status.pending",
};

const VARIANTS: Record<
  QcStatus,
  "success" | "warning" | "danger" | "outline"
> = {
  pass: "success",
  needs_review: "warning",
  fail: "danger",
  pending: "outline",
};

export function QCBadge({
  status,
  className,
}: {
  status: QcStatus;
  className?: string;
}) {
  const { t } = useI18n();
  return (
    <Badge variant={VARIANTS[status]} className={cn("gap-1", className)}>
      {status === "pending" ? (
        <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.75} />
      ) : null}
      {t(LABEL_KEYS[status])}
    </Badge>
  );
}
