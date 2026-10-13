"use client";

import { cn } from "@/lib/utils";
import { type WorkflowStep } from "@/lib/types";
import { useI18n } from "@/hooks/use-i18n";
import type { MessageKey } from "@/lib/i18n";

const STEP_KEYS: Record<WorkflowStep, MessageKey> = {
  technical_sheet: "workflow.technical_sheet",
  visual_production: "workflow.visual_production",
  retouch_qc: "workflow.retouch_qc",
  approval: "workflow.approval",
  published: "workflow.published",
};

export function StepPill({
  step,
  className,
}: {
  step: WorkflowStep;
  className?: string;
}) {
  const { t } = useI18n();
  const label = t(STEP_KEYS[step]);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full bg-sand/50 px-2.5 py-0.5 text-xs font-medium text-carbon",
        className,
      )}
    >
      {label}
    </span>
  );
}

export function useWorkflowLabel() {
  const { t } = useI18n();
  return (step: WorkflowStep | string) => {
    if (step in STEP_KEYS) {
      return t(STEP_KEYS[step as WorkflowStep]);
    }
    return step;
  };
}
