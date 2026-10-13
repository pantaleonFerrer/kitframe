"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { SettingsSection } from "../_components/ui";

const LABELS: Record<string, string> = {
  phase_assigned: "Te asignan una fase",
  submitted_for_review: "Producto enviado a revisión",
  changes_requested: "Cambios solicitados",
  phase_approved: "Fase aprobada",
  sent_back: "Producto devuelto a una fase anterior",
  mentioned: "Te mencionan en un comentario",
  generation_completed: "Generación del Estudio completada",
  generation_failed: "Generación del Estudio fallida",
  qc_needs_review: "QC requiere revisión",
  publish_succeeded: "Publicación correcta",
  publish_failed: "Publicación fallida",
  due_soon: "Fecha límite próxima",
  overdue: "Fecha límite vencida",
  golden_set_pending: "Golden set pendiente de aprobación",
  extraction_completed: "Extracción completada",
  extraction_failed: "Extracción fallida",
  asset_assigned: "Imagen asignada para editar",
};

type Pref = { event_type: string; email_enabled: boolean };

export default function NotificacionesAjustesPage() {
  const [prefs, setPrefs] = useState<Pref[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api<{ data: Pref[] }>("/notification-preferences");
      setPrefs(res.data);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <div className="bg-danger-subtle text-danger rounded-lg p-4">
        {error}
        <button type="button" className="block underline text-sm mt-2" onClick={() => void load()}>
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">Notificaciones</h2>
        <p className="text-sm text-muted mt-1">Elige qué eventos quieres recibir por email.</p>
      </div>
      <SettingsSection
        title="Email"
        onSave={async () => {
          setSaving(true);
          try {
            const res = await api<{ data: Pref[] }>("/notification-preferences", {
              method: "PUT",
              body: JSON.stringify({ preferences: prefs }),
            });
            setPrefs(res.data);
            setMessage("Preferencias guardadas");
          } catch (e) {
            setMessage((e as Error).message);
          } finally {
            setSaving(false);
          }
        }}
        saving={saving}
        message={message}
      >
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted border-b border-border">
              <th className="py-2">Evento</th>
              <th className="py-2 w-24">Email</th>
            </tr>
          </thead>
          <tbody>
            {prefs.map((p) => (
              <tr key={p.event_type} className="border-b border-border/50">
                <td className="py-2 pr-2">
                  <div className="font-medium">{LABELS[p.event_type] || p.event_type}</div>
                  <div className="text-xs text-muted">{p.event_type}</div>
                </td>
                <td className="py-2">
                  <input
                    type="checkbox"
                    checked={p.email_enabled}
                    onChange={(e) =>
                      setPrefs(
                        prefs.map((x) =>
                          x.event_type === p.event_type
                            ? { ...x, email_enabled: e.target.checked }
                            : x,
                        ),
                      )
                    }
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SettingsSection>
    </div>
  );
}
