"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("owner@kitframe.local");
  const [password, setPassword] = useState("Kitframe-dev-2026!");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  return (
    <div className="min-h-screen bg-sunk flex items-center justify-center p-4">
      <form
        className="w-full max-w-[400px] bg-surface rounded-lg shadow-sm border border-border p-8 animate-rise"
        onSubmit={async (e) => {
          e.preventDefault();
          setLoading(true);
          setError(null);
          try {
            await login(email, password);
            router.push("/tareas");
          } catch {
            setError("Email o contraseña incorrectos");
          } finally {
            setLoading(false);
          }
        }}
      >
        <div className="flex items-center gap-3 mb-6">
          <div className="h-10 w-10 rounded-full bg-wine text-white flex items-center justify-center font-serif text-xl">
            K
          </div>
          <div>
            <div className="font-semibold text-carbon">Kitframe</div>
            <div className="text-xs text-muted">Gathered</div>
          </div>
        </div>
        <h1 className="text-lg font-medium mb-4">Entrar en Kitframe</h1>
        {error && (
          <div className="mb-3 rounded-md bg-danger-subtle text-danger text-sm px-3 py-2">{error}</div>
        )}
        <label className="block text-sm mb-1">Email</label>
        <input
          className="w-full rounded-md border border-border px-3 py-2 mb-3"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          type="email"
          required
        />
        <label className="block text-sm mb-1">Contraseña</label>
        <input
          className="w-full rounded-md border border-border px-3 py-2 mb-4"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
          required
        />
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-md bg-wine text-white py-2.5 font-medium hover:opacity-95 disabled:opacity-60"
        >
          {loading ? "Entrando…" : "Entrar"}
        </button>
        <Link href="/recuperar" className="block text-sm text-wine mt-4 text-center">
          ¿Has olvidado la contraseña?
        </Link>
      </form>
    </div>
  );
}
