"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { FieldInput, FieldLabel, FieldSelect, SettingsSection } from "../_components/ui";

type AuditRow = {
  id: string;
  user_id?: string | null;
  entity_type: string;
  entity_id: string;
  action: string;
  detail?: unknown;
  created_at: string;
};

export default function ActividadPage() {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [entityType, setEntityType] = useState("");
  const [userId, setUserId] = useState("");

  const load = useCallback(async () => {
    try {
      const qs = new URLSearchParams();
      if (entityType) qs.set("entity_type", entityType);
      if (userId) qs.set("user_id", userId);
      const res = await api<{ data: AuditRow[] }>(`/audit-log?${qs.toString()}`);
      setRows(res.data);
      setError(null);
    } catch (e) {
      setError((e as Error).message || "Sin permiso (admin/owner)");
    }
  }, [entityType, userId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">Actividad</h2>
        <p className="text-sm text-muted mt-1">Registro de auditoría de la marca.</p>
      </div>

      {error ? (
        <div className="bg-danger-subtle text-danger rounded-lg p-4 space-y-2">
          <p>{error}</p>
          <button type="button" className="underline text-sm" onClick={() => void load()}>
            Reintentar
          </button>
        </div>
      ) : (
        <SettingsSection title="Filtros">
          <div className="grid md:grid-cols-3 gap-2 items-end">
            <FieldLabel>
              Tipo de entidad
              <FieldSelect value={entityType} onChange={(e) => setEntityType(e.target.value)}>
                <option value="">Todos</option>
                {[
                  "product",
                  "project",
                  "asset",
                  "generation",
                  "brand",
                  "membership",
                  "rights_record",
                  "golden_set_image",
                ].map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </FieldSelect>
            </FieldLabel>
            <FieldLabel>
              User ID
              <FieldInput value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="uuid" />
            </FieldLabel>
            <button
              type="button"
              className="rounded-md border px-3 py-2 text-sm"
              onClick={() => void load()}
            >
              Aplicar
            </button>
          </div>
          <div className="overflow-auto max-h-[60vh]">
            <table className="w-full text-sm mt-3">
              <thead>
                <tr className="text-left text-muted border-b border-border">
                  <th className="py-2 pr-2">Fecha</th>
                  <th className="py-2 pr-2">Acción</th>
                  <th className="py-2 pr-2">Entidad</th>
                  <th className="py-2">Detalle</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-6 text-muted text-center">
                      Sin entradas todavía.
                    </td>
                  </tr>
                ) : (
                  rows.map((r) => (
                    <tr key={r.id} className="border-b border-border/50 align-top">
                      <td className="py-2 pr-2 whitespace-nowrap text-xs">
                        {new Date(r.created_at).toLocaleString()}
                      </td>
                      <td className="py-2 pr-2">{r.action}</td>
                      <td className="py-2 pr-2 text-xs">
                        {r.entity_type}
                        <br />
                        <span className="text-muted break-all">{r.entity_id}</span>
                      </td>
                      <td className="py-2 text-xs">
                        <pre className="whitespace-pre-wrap max-w-md">
                          {r.detail ? JSON.stringify(r.detail, null, 0) : "—"}
                        </pre>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </SettingsSection>
      )}
    </div>
  );
}
