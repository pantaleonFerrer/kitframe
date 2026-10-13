"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { uploadViaPresign } from "@/lib/upload";

type Rights = { id: string; subject_name: string; status: string };

export default function NuevoModeloPage() {
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"synthetic" | "real_person">("synthetic");
  const [notes, setNotes] = useState("");
  const [rightsId, setRightsId] = useState("");
  const [rights, setRights] = useState<Rights[]>([]);
  const [setId, setSetId] = useState<string | null>(null);
  const [photos, setPhotos] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<{ data: Rights[] }>("/rights-records")
      .then((r) => setRights(r.data))
      .catch(() => setRights([]));
  }, []);

  const createSet = async () => {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { name, kind, notes };
      if (kind === "real_person") {
        if (!rightsId) {
          setError("Selecciona un registro de derechos para personas reales.");
          setBusy(false);
          return;
        }
        body.rights_record_id = rightsId;
      }
      const created = await api<{ id: string }>("/reference-sets", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setSetId(created.id);
      setStep(2);
    } catch (e) {
      const err = e as Error & { status?: number; code?: string };
      if (err.status === 403 || err.code === "forbidden") {
        setError("No tienes permiso para crear modelos. Necesitas rol admin o owner.");
      } else {
        setError(err.message || "No se pudo crear el modelo");
      }
    } finally {
      setBusy(false);
    }
  };

  const uploadPhotos = async (files: FileList | null) => {
    if (!files || !setId) return;
    setBusy(true);
    setError(null);
    try {
      for (const file of Array.from(files)) {
        const storage_key = await uploadViaPresign(file, "reference");
        const img = await api<{ id: string; name: string }>(`/reference-sets/${setId}/images`, {
          method: "POST",
          body: JSON.stringify({ storage_key, name: file.name }),
        });
        setPhotos((prev) => [...prev, { id: img.id, name: img.name || file.name }]);
      }
    } catch (e) {
      setError((e as Error).message || "Error al subir fotos");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-in">
      <div className="text-sm">
        <Link href="/biblioteca" className="text-wine">
          ← Biblioteca
        </Link>
      </div>
      <header>
        <h1 className="text-2xl font-semibold text-carbon">Nuevo modelo</h1>
        <p className="text-sm text-muted mt-1">
          Paso {step} de 3 · Conjunto de fotos de referencia para el Estudio
        </p>
      </header>

      {error && <div className="rounded-lg bg-danger-subtle text-danger p-3 text-sm">{error}</div>}

      {step === 1 && (
        <div className="bg-surface border border-border rounded-lg p-5 space-y-4">
          <label className="block text-sm">
            Nombre
            <input
              className="mt-1 w-full border border-border rounded-md px-3 py-2"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Modelo estudio A"
              required
            />
          </label>
          <label className="block text-sm">
            Tipo
            <select
              className="mt-1 w-full border border-border rounded-md px-3 py-2"
              value={kind}
              onChange={(e) => setKind(e.target.value as "synthetic" | "real_person")}
            >
              <option value="synthetic">Sintético / IA</option>
              <option value="real_person">Persona real</option>
            </select>
          </label>
          {kind === "real_person" && (
            <label className="block text-sm">
              Registro de derechos
              <select
                className="mt-1 w-full border border-border rounded-md px-3 py-2"
                value={rightsId}
                onChange={(e) => setRightsId(e.target.value)}
              >
                <option value="">Selecciona…</option>
                {rights.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.subject_name} ({r.status})
                  </option>
                ))}
              </select>
              <span className="text-xs text-muted mt-1 block">
                Solo se podrá usar en el Estudio cuando el estado sea liberado.
              </span>
            </label>
          )}
          <label className="block text-sm">
            Notas
            <textarea
              className="mt-1 w-full border border-border rounded-md px-3 py-2 min-h-20"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="rounded-md bg-wine text-white px-4 py-2 text-sm disabled:opacity-50"
            disabled={busy || !name.trim()}
            onClick={() => void createSet()}
          >
            {busy ? "Creando…" : "Continuar"}
          </button>
        </div>
      )}

      {step === 2 && setId && (
        <div className="bg-surface border border-border rounded-lg p-5 space-y-4">
          <p className="text-sm text-muted">
            Sube entre 5 y 15 fotos de la misma persona: de frente, de perfil y de tres cuartos, con
            buena luz y sin gafas de sol. Mínimo recomendado: 3 fotos válidas.
          </p>
          {photos.length > 0 && photos.length < 5 && (
            <p className="text-xs text-warning">
              Pocas fotos: los resultados serán menos consistentes ({photos.length}/5).
            </p>
          )}
          <ul className="text-sm space-y-1">
            {photos.map((p) => (
              <li key={p.id} className="border-b border-border/60 py-1">
                {p.name}
              </li>
            ))}
          </ul>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => void uploadPhotos(e.target.files)}
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-md border border-border px-4 py-2 text-sm"
              disabled={busy}
              onClick={() => fileRef.current?.click()}
            >
              {busy ? "Subiendo…" : "Subir fotos"}
            </button>
            <button
              type="button"
              className="rounded-md bg-wine text-white px-4 py-2 text-sm disabled:opacity-50"
              disabled={photos.length < 1}
              onClick={() => setStep(3)}
            >
              Continuar
            </button>
          </div>
        </div>
      )}

      {step === 3 && setId && (
        <div className="bg-surface border border-border rounded-lg p-5 space-y-4">
          <p className="text-sm">
            Modelo <span className="font-medium">{name}</span> creado con {photos.length} fotos.
          </p>
          <div className="flex flex-wrap gap-2">
            <Link href="/estudio" className="rounded-md bg-wine text-white px-4 py-2 text-sm">
              Probar en el Estudio
            </Link>
            <Link href="/biblioteca" className="rounded-md border border-border px-4 py-2 text-sm">
              Volver a Biblioteca
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
