"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";

export default function NuevoProyectoPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [requirements, setRequirements] = useState([
    "El escudo debe verse nítido",
    "Fondo gris claro en las fotos de modelo",
    "Colores fieles a la prenda real",
  ]);
  const [saving, setSaving] = useState(false);

  const create = async () => {
    setSaving(true);
    try {
      const project = await api<{ id: string }>("/projects", {
        method: "POST",
        body: JSON.stringify({
          name,
          description,
          lead_user_id: user?.id,
          requirements: requirements.filter(Boolean).map((text) => ({ text })),
        }),
      });
      router.push(`/proyectos/${project.id}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-in">
      <h1 className="text-2xl font-semibold">Nuevo proyecto</h1>
      <div className="flex gap-2 text-sm">
        {[1, 2, 3, 4].map((n) => (
          <span
            key={n}
            className={`rounded-full px-3 py-1 ${step === n ? "bg-wine text-white" : "bg-raised text-muted"}`}
          >
            Paso {n}
          </span>
        ))}
      </div>

      {step === 1 && (
        <div className="bg-surface border border-border rounded-lg p-6 space-y-4">
          <h2 className="font-medium">Datos</h2>
          <input
            className="w-full border border-border rounded-md px-3 py-2"
            placeholder="Nombre del proyecto"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <textarea
            className="w-full border border-border rounded-md px-3 py-2 min-h-28"
            placeholder="Descripción"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <button
            type="button"
            disabled={!name}
            className="rounded-md bg-wine text-white px-4 py-2 disabled:opacity-50"
            onClick={() => setStep(2)}
          >
            Continuar
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="bg-surface border border-border rounded-lg p-6 space-y-3">
          <h2 className="font-medium">Equipo</h2>
          <p className="text-sm text-muted">
            Podrás asignar editores y revisores por fase después de crear el proyecto. Si una fase no
            tiene revisores, revisará el responsable del proyecto.
          </p>
          <div className="flex gap-2">
            <button type="button" className="rounded-md border px-4 py-2" onClick={() => setStep(1)}>
              Atrás
            </button>
            <button type="button" className="rounded-md bg-wine text-white px-4 py-2" onClick={() => setStep(3)}>
              Continuar
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="bg-surface border border-border rounded-lg p-6 space-y-3">
          <h2 className="font-medium">Requisitos</h2>
          {requirements.map((r, i) => (
            <input
              key={i}
              className="w-full border border-border rounded-md px-3 py-2"
              value={r}
              onChange={(e) => {
                const next = [...requirements];
                next[i] = e.target.value;
                setRequirements(next);
              }}
            />
          ))}
          <button
            type="button"
            className="text-sm text-wine"
            onClick={() => setRequirements((r) => [...r, ""])}
          >
            + Añadir requisito
          </button>
          <div className="flex gap-2 pt-2">
            <button type="button" className="rounded-md border px-4 py-2" onClick={() => setStep(2)}>
              Atrás
            </button>
            <button type="button" className="rounded-md bg-wine text-white px-4 py-2" onClick={() => setStep(4)}>
              Continuar
            </button>
          </div>
        </div>
      )}

      {step === 4 && (
        <div className="bg-surface border border-border rounded-lg p-6 space-y-3">
          <h2 className="font-medium">Fichas técnicas</h2>
          <p className="text-sm text-muted">
            Puedes subir fichas después desde la pestaña Fichas del proyecto.
          </p>
          <div className="flex gap-2">
            <button type="button" className="rounded-md border px-4 py-2" onClick={() => setStep(3)}>
              Atrás
            </button>
            <button
              type="button"
              disabled={saving}
              className="rounded-md bg-wine text-white px-4 py-2"
              onClick={create}
            >
              {saving ? "Creando…" : "Crear proyecto"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
