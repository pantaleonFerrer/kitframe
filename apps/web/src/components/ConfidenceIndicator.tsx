"use client";

import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import { useI18n } from "@/hooks/use-i18n";

export function ConfidenceIndicator({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  const { t } = useI18n();
  const color =
    value >= 0.9 ? "bg-success" : value >= 0.7 ? "bg-warning" : "bg-danger";
  const label =
    value >= 0.9
      ? t("confidence.high")
      : value >= 0.7
        ? t("confidence.medium")
        : t("confidence.low");

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              "inline-flex h-2.5 w-2.5 rounded-full",
              color,
              className,
            )}
            aria-label={`${label}: ${Math.round(value * 100)}%`}
          />
        </TooltipTrigger>
        <TooltipContent>
          {label} ({Math.round(value * 100)}%)
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
