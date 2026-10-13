"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/hooks/use-i18n";

type Rights = {
  id: string;
  subject_name: string;
  subject_type: string;
  aliases: string[];
  status: string;
  valid_until?: string | null;
  notes: string;
};

export default function DerechosPage() {
  const { te } = useI18n();
  const [rows, setRows] = useState<Rights[]>([]);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");

  const load = () => api<{ data: Rights[] }>("/rights-records").then((r) => setRows(r.data));
  useEffect(() => {
    load().catch(() => setRows([]));
  }, []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Derechos</h1>
      </div>
      <form
        className="bg-surface border border-border rounded-lg p-4 flex flex-wrap gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          await api("/rights-records", {
            method: "POST",
            body: JSON.stringify({
              subject_type: "player",
              subject_name: name,
              notes,
              status: "not_cleared",
            }),
          });
          setName("");
          setNotes("");
          await load();
        }}
      >
        <input
          className="border border-border rounded-md px-3 py-2 text-sm"
          placeholder="Sujeto"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <input
          className="border border-border rounded-md px-3 py-2 text-sm flex-1"
          placeholder="Notas"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
        <button className="rounded-md bg-wine text-white px-3 py-2 text-sm">Nuevo registro</button>
      </form>
      <table className="w-full text-sm bg-surface border border-border rounded-lg overflow-hidden">
        <thead className="bg-raised text-left">
          <tr>
            <th className="p-3">Sujeto</th>
            <th className="p-3">Tipo</th>
            <th className="p-3">Estado</th>
            <th className="p-3">Válido hasta</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-border">
              <td className="p-3 font-medium">{r.subject_name}</td>
              <td className="p-3">{te("subjectType", r.subject_type)}</td>
              <td className="p-3">
                <span
                  className={
                    r.status === "cleared"
                      ? "text-success"
                      : r.status === "expired" || r.status === "not_cleared"
                        ? "text-danger"
                        : "text-warning"
                  }
                >
                  {te("rightsStatus", r.status)}
                </span>
              </td>
              <td className="p-3 text-muted">{r.valid_until || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
