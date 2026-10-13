"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, setAccessToken, setBrandId } from "@/lib/api";

export default function InvitacionPage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [info, setInfo] = useState<{ brand_name: string; email: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    api<{ brand_name: string; email: string }>(`/invitations/${token}`, { skipBrand: true })
      .then(setInfo)
      .catch(() =>
        setError("Esta invitación ha caducado. Pide a tu administrador una nueva invitación."),
      );
  }, [token]);

  if (error) {
    return <div className="min-h-screen flex items-center justify-center p-6 text-danger">{error}</div>;
  }
  if (!info) {
    return <div className="min-h-screen flex items-center justify-center">Cargando…</div>;
  }

  return (
    <div className="min-h-screen bg-sunk flex items-center justify-center p-4">
      <form
        className="w-full max-w-[400px] bg-surface border rounded-lg p-8 space-y-3"
        onSubmit={async (e) => {
          e.preventDefault();
          const data = await api<{
            access_token: string;
            user: { memberships: { brand_id: string }[] };
          }>(`/invitations/${token}/accept`, {
            method: "POST",
            body: JSON.stringify({ name, password }),
            skipBrand: true,
          });
          setAccessToken(data.access_token);
          setBrandId(data.user.memberships[0]?.brand_id || null);
          router.push("/tareas");
        }}
      >
        <h1 className="text-lg font-medium">Aceptar invitación</h1>
        <p className="text-sm text-muted">
          {info.brand_name} · {info.email}
        </p>
        <input
          className="w-full border rounded-md px-3 py-2"
          placeholder="Nombre"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="w-full border rounded-md px-3 py-2"
          type="password"
          minLength={12}
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button className="w-full rounded-md bg-wine text-white py-2">Crear cuenta y entrar</button>
      </form>
    </div>
  );
}
