"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Bell,
  BookImage,
  Briefcase,
  CheckSquare,
  Clapperboard,
  LogOut,
  Menu,
  Scale,
  Settings,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { MessageKey } from "@/lib/i18n";

const NAV: {
  href: string;
  labelKey: MessageKey;
  icon: typeof CheckSquare;
  needStudio?: boolean;
  admin?: boolean;
}[] = [
  { href: "/tareas", labelKey: "nav.myTasks", icon: CheckSquare },
  { href: "/proyectos", labelKey: "nav.projects", icon: Briefcase },
  { href: "/estudio", labelKey: "nav.studio", icon: Clapperboard, needStudio: true },
  { href: "/biblioteca", labelKey: "nav.library", icon: BookImage },
  { href: "/derechos", labelKey: "nav.rights", icon: Scale, admin: true },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout, brandId, switchBrand } = useAuth();
  const { t, locale } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [inboxOpen, setInboxOpen] = useState(false);
  const [notifs, setNotifs] = useState<
    { id: string; event_type: string; payload: { link?: string; title?: string }; created_at: string; read_at: string | null }[]
  >([]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = localStorage.getItem("kitframe_sidebar");
    if (saved === "1") setCollapsed(true);
  }, []);

  useEffect(() => {
    if (!user && !loading) router.replace("/login");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user || !brandId) return;
    const load = () => {
      api<{ count: number }>("/notifications/unread-count")
        .then((r) => setUnread(r.count))
        .catch(() => undefined);
    };
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [user, brandId]);

  if (loading || !user) {
    return (
      <div className="min-h-screen bg-sunk flex items-center justify-center text-muted">
        {t("common.loading")}
      </div>
    );
  }

  const role = user.memberships.find((m) => m.brand_id === brandId)?.role;
  const canStudio = role !== "viewer";
  const isAdmin = role === "admin" || role === "owner";

  const toggleCollapse = () => {
    setCollapsed((c) => {
      localStorage.setItem("kitframe_sidebar", !c ? "1" : "0");
      return !c;
    });
  };

  const openInbox = async () => {
    setInboxOpen(true);
    const data = await api<{ data: typeof notifs }>("/notifications");
    setNotifs(data.data);
  };

  return (
    <div className="min-h-screen bg-sunk text-ink flex">
      <aside
        className={cn(
          "bg-carbon text-white flex flex-col transition-all shrink-0",
          collapsed ? "w-16" : "w-60",
          "hidden md:flex",
        )}
      >
        <div className="h-14 flex items-center gap-2 px-4 border-b border-white/10">
          <div className="h-8 w-8 rounded-full bg-wine flex items-center justify-center font-serif text-lg">
            K
          </div>
          {!collapsed && (
            <div>
              <div className="font-semibold leading-tight">Kitframe</div>
              <div className="text-[10px] text-sand tracking-wide">Gathered</div>
            </div>
          )}
        </div>
        {user.memberships.length > 1 && !collapsed && (
          <select
            className="m-3 rounded-md bg-white/10 text-sm px-2 py-1"
            value={brandId || ""}
            onChange={(e) => switchBrand(e.target.value)}
          >
            {user.memberships.map((m) => (
              <option key={m.brand_id} value={m.brand_id}>
                {m.brand_name}
              </option>
            ))}
          </select>
        )}
        <nav className="flex-1 p-2 space-y-1">
          {NAV.filter((n) => (!n.admin || isAdmin) && (!n.needStudio || canStudio)).map((item) => {
            const Icon = item.icon;
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm",
                  active ? "bg-wine text-white" : "text-white/80 hover:bg-white/10",
                )}
              >
                <Icon size={20} strokeWidth={1.75} />
                {!collapsed && <span>{t(item.labelKey)}</span>}
                {item.href === "/tareas" && unread > 0 && !collapsed && (
                  <span className="ml-auto text-xs bg-sand text-carbon rounded-full px-1.5">
                    {unread}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
        <div className="p-2 border-t border-white/10 space-y-1">
          <Link
            href="/ajustes"
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm",
              pathname.startsWith("/ajustes") ? "bg-wine" : "hover:bg-white/10",
            )}
          >
            <Settings size={20} strokeWidth={1.75} />
            {!collapsed && t("nav.settings")}
          </Link>
          <button
            type="button"
            onClick={() => logout().then(() => router.push("/login"))}
            className="w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-white/10"
          >
            <LogOut size={20} strokeWidth={1.75} />
            {!collapsed && t("common.logOut")}
          </button>
          <button type="button" onClick={toggleCollapse} className="w-full text-xs text-white/50 py-2">
            {collapsed ? "»" : "«"}
          </button>
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <div className="absolute left-0 top-0 bottom-0 w-60 bg-carbon text-white p-4">
            <button className="mb-4" onClick={() => setMobileOpen(false)}>
              <X />
            </button>
            {NAV.filter((n) => (!n.admin || isAdmin) && (!n.needStudio || canStudio)).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="block py-2"
                onClick={() => setMobileOpen(false)}
              >
                {t(item.labelKey)}
              </Link>
            ))}
            <Link href="/ajustes" className="block py-2" onClick={() => setMobileOpen(false)}>
              {t("nav.settings")}
            </Link>
          </div>
        </div>
      )}

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-14 bg-surface border-b border-border flex items-center px-4 gap-3">
          <button type="button" className="md:hidden" onClick={() => setMobileOpen(true)}>
            <Menu size={20} />
          </button>
          <div className="text-sm text-muted truncate flex-1">Kitframe</div>
          <button
            type="button"
            className="relative p-2 rounded-md hover:bg-raised"
            onClick={() => void openInbox()}
            aria-label={t("inbox.title")}
          >
            <Bell size={20} strokeWidth={1.75} />
            {unread > 0 && (
              <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-wine" />
            )}
          </button>
        </header>
        <main className="flex-1 overflow-auto p-4 md:p-6">{children}</main>
      </div>

      {inboxOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <button
            type="button"
            className="absolute inset-0 bg-black/30"
            onClick={() => setInboxOpen(false)}
          />
          <div className="relative w-full max-w-md bg-surface h-full shadow-md p-4 overflow-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold">{t("inbox.title")}</h2>
              <button
                type="button"
                className="text-sm text-wine"
                onClick={() =>
                  api("/notifications/read", { method: "POST", body: JSON.stringify({ all: true }) }).then(
                    () => setUnread(0),
                  )
                }
              >
                {t("inbox.markAllRead")}
              </button>
            </div>
            <ul className="space-y-2">
              {notifs.map((n) => (
                <li
                  key={n.id}
                  className={cn(
                    "rounded-lg border border-border p-3 text-sm",
                    !n.read_at && "border-l-4 border-l-wine",
                  )}
                >
                  <div className="font-medium">{n.payload.title || n.event_type}</div>
                  <div className="text-muted text-xs mt-1">
                    {new Date(n.created_at).toLocaleString(
                      locale === "en" ? "en-GB" : locale === "ca" ? "ca-ES" : "es-ES",
                    )}
                  </div>
                </li>
              ))}
              {notifs.length === 0 && (
                <li className="text-muted text-sm">{t("inbox.empty")}</li>
              )}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
