"use client";

import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

export function SettingsSection({
  title,
  description,
  children,
  onSave,
  saving,
  message,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  onSave?: () => void | Promise<void>;
  saving?: boolean;
  message?: string | null;
}) {
  return (
    <section className="bg-surface border border-border rounded-lg p-5 space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h3 className="font-semibold text-base">{title}</h3>
          {description && <p className="text-sm text-muted mt-1">{description}</p>}
        </div>
        {onSave && (
          <button
            type="button"
            disabled={saving}
            onClick={() => void onSave()}
            className="rounded-md bg-wine text-white px-3 py-1.5 text-sm disabled:opacity-50"
          >
            {saving ? "Guardando…" : "Guardar"}
          </button>
        )}
      </div>
      {children}
      {message && <p className="text-xs text-wine">{message}</p>}
    </section>
  );
}

export function FieldLabel({ children }: { children: ReactNode }) {
  return <label className="block text-sm space-y-1">{children}</label>;
}

export function FieldInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full border border-border rounded-md px-2 py-1.5 text-sm ${props.className || ""}`}
    />
  );
}

export function FieldSelect(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`w-full border border-border rounded-md px-2 py-1.5 text-sm ${props.className || ""}`}
    />
  );
}

export function FieldArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`w-full border border-border rounded-md px-2 py-1.5 text-sm min-h-24 ${props.className || ""}`}
    />
  );
}
