export type Locale = "ca" | "es" | "en";

export const LOCALES: { code: Locale; label: string; nativeLabel: string }[] = [
  { code: "es", label: "Spanish", nativeLabel: "Español" },
  { code: "ca", label: "Catalan", nativeLabel: "Català" },
  { code: "en", label: "English", nativeLabel: "English" },
];

export const DEFAULT_LOCALE: Locale = "es";

export function isLocale(value: string | null | undefined): value is Locale {
  return value === "ca" || value === "es" || value === "en";
}
