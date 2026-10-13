"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/hooks/use-i18n";
import type { MessageKey } from "@/lib/i18n";

const LINKS: { href: string; labelKey: MessageKey }[] = [
  { href: "/ajustes/marca", labelKey: "settings.brand" },
  { href: "/ajustes/usuarios", labelKey: "settings.users" },
  { href: "/ajustes/notificaciones", labelKey: "settings.notifications" },
  { href: "/ajustes/actividad", labelKey: "nav.activity" },
  { href: "/ajustes/trabajos", labelKey: "nav.failedJobs" },
  { href: "/ajustes/perfil", labelKey: "nav.myProfile" },
];

export default function AjustesLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { t } = useI18n();
  return (
    <div className="flex gap-6 animate-fade-in">
      <aside className="w-48 shrink-0 space-y-1">
        <h1 className="text-lg font-semibold mb-3">{t("settings.title")}</h1>
        {LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`block rounded-md px-3 py-2 text-sm ${pathname === l.href ? "bg-wine text-white" : "hover:bg-raised"}`}
          >
            {t(l.labelKey)}
          </Link>
        ))}
      </aside>
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  );
}
