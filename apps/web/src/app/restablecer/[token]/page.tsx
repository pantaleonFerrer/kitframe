"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function RestablecerPage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [password, setPassword] = useState("");
  return (
    <div className="min-h-screen bg-sunk flex items-center justify-center p-4">
      <form
        className="w-full max-w-[400px] bg-surface border rounded-lg p-8"
        onSubmit={async (e) => {
          e.preventDefault();
          await api("/auth/reset-password", {
            method: "POST",
            body: JSON.stringify({ token, password }),
            skipBrand: true,
          });
          router.push("/login");
        }}
      >
        <h1 className="text-lg font-medium mb-4">Nueva contraseña</h1>
        <input
          className="w-full border rounded-md px-3 py-2 mb-3"
          type="password"
          minLength={12}
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button className="w-full rounded-md bg-wine text-white py-2">Guardar contraseña</button>
      </form>
    </div>
  );
}
