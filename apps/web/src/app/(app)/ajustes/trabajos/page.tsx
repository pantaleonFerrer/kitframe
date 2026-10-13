"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/hooks/use-i18n";
import { SettingsSection } from "../_components/ui";

type Job = {
  id: string;
  type: string;
  status: string;
  entity_type?: string | null;
  entity_id?: string | null;
  attempts: number;
  error_code?: string | null;
  error_detail?: string | null;
  created_at: string;
  finished_at?: string | null;
};

export default function TrabajosPage() {
  const { te } = useI18n();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api<{ data: Job[] }>("/jobs?status=failed");
      setJobs(res.data);
      setError(null);
    } catch (e) {
      setError((e as Error).message || "Sin permiso (admin/owner)");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold">Trabajos fallidos</h2>
          <p className="text-sm text-muted mt-1">Jobs con error. Puedes reencolarlos.</p>
        </div>
        <button type="button" className="text-sm rounded-md border px-3 py-1.5" onClick={() => void load()}>
          Actualizar
        </button>
      </div>

      {error ? (
        <div className="bg-danger-subtle text-danger rounded-lg p-4 space-y-2">
          <p>{error}</p>
          <button type="button" className="underline text-sm" onClick={() => void load()}>
            Reintentar
          </button>
        </div>
      ) : (
        <SettingsSection title="Fallidos" message={message}>
          {jobs.length === 0 ? (
            <p className="text-sm text-muted">No hay trabajos fallidos.</p>
          ) : (
            <ul className="space-y-3">
              {jobs.map((j) => (
                <li key={j.id} className="border border-border rounded-md p-3 space-y-2">
                  <div className="flex items-start justify-between gap-2 flex-wrap">
                    <div>
                      <div className="font-medium text-sm">{j.type}</div>
                      <div className="text-xs text-muted">
                        {te("status", j.status) || j.status} · {j.entity_type} {j.entity_id} · intentos{" "}
                        {j.attempts} · {new Date(j.created_at).toLocaleString()}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="text-sm rounded-md bg-wine text-white px-3 py-1.5"
                      onClick={async () => {
                        try {
                          await api(`/jobs/${j.id}/retry`, { method: "POST", body: "{}" });
                          setMessage(`Reencolado ${j.id}`);
                          await load();
                        } catch (e) {
                          setMessage((e as Error).message);
                        }
                      }}
                    >
                      Reintentar
                    </button>
                  </div>
                  <pre className="text-xs bg-raised rounded-md p-2 whitespace-pre-wrap text-danger">
                    {j.error_code ? `${j.error_code}: ` : ""}
                    {j.error_detail || "Sin detalle"}
                  </pre>
                </li>
              ))}
            </ul>
          )}
        </SettingsSection>
      )}
    </div>
  );
}
