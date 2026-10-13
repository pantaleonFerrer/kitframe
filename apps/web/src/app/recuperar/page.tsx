"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function RecuperarPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  return (
    <div className="min-h-screen bg-sunk flex items-center justify-center p-4">
      <form
        className="w-full max-w-[400px] bg-surface border border-border rounded-lg p-8"
        onSubmit={async (e) => {
          e.preventDefault();
          await api("/auth/forgot-password", {
            method: "POST",
            body: JSON.stringify({ email }),
            skipBrand: true,
          });
          setSent(true);
        }}
      >
        <h1 className="text-lg font-medium mb-2">Recuperar contraseña</h1>
        <p className="text-sm text-muted mb-4">Te enviaremos un enlace si el email existe.</p>
        {sent ? (
          <p className="text-sm text-success">Si el email existe, recibirás instrucciones.</p>
        ) : (
          <>
            <input
              className="w-full border rounded-md px-3 py-2 mb-3"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <button className="w-full rounded-md bg-wine text-white py-2">Enviar enlace</button>
          </>
        )}
        <Link href="/login" className="block text-center text-sm text-wine mt-4">
          Volver
        </Link>
      </form>
    </div>
  );
}
