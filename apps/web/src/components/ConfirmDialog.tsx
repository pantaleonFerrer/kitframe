"use client";

import { useEffect, useState, type ReactNode } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/hooks/use-i18n";

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel,
  variant = "default",
  typedConfirmation,
  onConfirm,
  loading,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "default" | "danger";
  typedConfirmation?: string;
  onConfirm: () => void | Promise<void>;
  loading?: boolean;
  children?: ReactNode;
}) {
  const { t } = useI18n();
  const [typed, setTyped] = useState("");
  const resolvedConfirm = confirmLabel ?? t("confirm.confirm");
  const resolvedCancel = cancelLabel ?? t("common.cancel");

  useEffect(() => {
    if (!open) setTyped("");
  }, [open]);

  const canConfirm = typedConfirmation
    ? typed.trim() === typedConfirmation
    : true;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? (
            <DialogDescription>{description}</DialogDescription>
          ) : null}
        </DialogHeader>
        {children}
        {typedConfirmation ? (
          <div className="space-y-2">
            <Label htmlFor="confirm-type">
              {t("confirm.typeToConfirm", { value: typedConfirmation })}
            </Label>
            <Input
              id="confirm-type"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
            />
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {resolvedCancel}
          </Button>
          <Button
            variant={variant === "danger" ? "danger" : "default"}
            disabled={!canConfirm || loading}
            onClick={() => void onConfirm()}
          >
            {loading ? t("confirm.working") : resolvedConfirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
