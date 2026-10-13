import { Suspense } from "react";
import EstudioClient from "./estudio-client";

export default function EstudioPage() {
  return (
    <Suspense fallback={<div className="text-muted">Cargando estudio…</div>}>
      <EstudioClient />
    </Suspense>
  );
}
