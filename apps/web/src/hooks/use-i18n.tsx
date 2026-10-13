"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  DEFAULT_LOCALE,
  resolveInitialLocale,
  setStoredLocale,
  translate,
  translateEnum,
  type EnumSection,
  type Locale,
  type MessageKey,
} from "@/lib/i18n";

type TranslateFn = (
  key: MessageKey,
  params?: Record<string, string | number | boolean>,
) => string;

type LocaleContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: TranslateFn;
  te: (section: EnumSection, value: string | null | undefined) => string;
  formatRelative: (date: string | Date) => string;
  ready: boolean;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

function relativeWith(t: TranslateFn, date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  const diff = Date.now() - d.getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return t("common.justNow");
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return t("common.minutesAgo", { n: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t("common.hoursAgo", { n: hours });
  const days = Math.floor(hours / 24);
  if (days === 1) return t("common.yesterday");
  if (days < 7) return t("common.daysAgo", { n: days });
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const initial = resolveInitialLocale();
    setLocaleState(initial);
    document.documentElement.lang = initial;
    setReady(true);
  }, []);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    setStoredLocale(next);
    document.documentElement.lang = next;
  }, []);

  const t = useCallback<TranslateFn>(
    (key, params) => translate(locale, key, params),
    [locale],
  );

  const te = useCallback(
    (section: EnumSection, value: string | null | undefined) =>
      translateEnum(locale, section, value),
    [locale],
  );

  const formatRelative = useCallback(
    (date: string | Date) => relativeWith(t, date),
    [t],
  );

  const value = useMemo(
    () => ({ locale, setLocale, t, te, formatRelative, ready }),
    [locale, setLocale, t, te, formatRelative, ready],
  );

  return (
    <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    throw new Error("useI18n must be used within LocaleProvider");
  }
  return ctx;
}
