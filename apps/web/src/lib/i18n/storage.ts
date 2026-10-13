import { DEFAULT_LOCALE, isLocale, type Locale } from "./types";

const LOCALE_KEY = "kitframe_locale";

export function getStoredLocale(): Locale | null {
  if (typeof window === "undefined") return null;
  const value = localStorage.getItem(LOCALE_KEY);
  return isLocale(value) ? value : null;
}

export function setStoredLocale(locale: Locale): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(LOCALE_KEY, locale);
}

export function detectBrowserLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  const lang = (navigator.language || "").toLowerCase();
  if (lang.startsWith("es")) return "es";
  if (lang.startsWith("ca")) return "ca";
  if (lang.startsWith("en")) return "en";
  return DEFAULT_LOCALE;
}

export function resolveInitialLocale(): Locale {
  return getStoredLocale() ?? detectBrowserLocale();
}
