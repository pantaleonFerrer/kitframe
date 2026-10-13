import { ca } from "./messages/ca";
import { en } from "./messages/en";
import { es } from "./messages/es";
import type { Messages } from "./messages/types";
import type { Locale } from "./types";

export const catalogs: Record<Locale, Messages> = { ca, es, en };

type Primitive = string | number | boolean;

type DotNestedKeys<T, Prefix extends string = ""> = {
  [K in keyof T & string]: T[K] extends string
    ? `${Prefix}${K}`
    : T[K] extends object
      ? DotNestedKeys<T[K], `${Prefix}${K}.`>
      : never;
}[keyof T & string];

export type MessageKey = {
  [K in keyof Messages]: DotNestedKeys<Messages[K], `${K & string}.`>;
}[keyof Messages];

function resolveMessageValue(section: unknown, path: string[]): string | undefined {
  let value: unknown = section;
  for (const part of path) {
    if (!value || typeof value !== "object") return undefined;
    value = (value as Record<string, unknown>)[part];
  }
  return typeof value === "string" ? value : undefined;
}

export function getMessage(locale: Locale, key: MessageKey): string {
  const parts = key.split(".");
  const section = parts[0] as keyof Messages;
  const path = parts.slice(1);
  const value =
    resolveMessageValue(catalogs[locale][section], path) ??
    (locale !== "es" ? resolveMessageValue(catalogs.es[section], path) : undefined);
  return value ?? key;
}

export function interpolate(
  template: string,
  params?: Record<string, Primitive>,
): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, name: string) => {
    const value = params[name];
    return value === undefined || value === null ? "" : String(value);
  });
}

export function pluralize(template: string, n: number): string {
  const parts = template.split("|");
  if (parts.length < 2) return interpolate(template, { n });
  return interpolate(n === 1 ? parts[0] : parts[1], { n });
}

export function translate(
  locale: Locale,
  key: MessageKey,
  params?: Record<string, Primitive>,
): string {
  const raw = getMessage(locale, key);
  if (params && "n" in params && raw.includes("|")) {
    return pluralize(raw, Number(params.n));
  }
  return interpolate(raw, params);
}

/** Translate a dynamic enum value from a catalog section (e.g. roles.owner). */
export type EnumSection = {
  [K in keyof Messages]: Messages[K] extends Record<string, string> ? K : never;
}[keyof Messages];

export function translateEnum(
  locale: Locale,
  section: EnumSection,
  value: string | null | undefined,
): string {
  if (!value) return "";
  const key = `${section}.${value}` as MessageKey;
  const label = getMessage(locale, key);
  return label === key ? value : label;
}

export type { Messages, Locale };
export { LOCALES, DEFAULT_LOCALE, isLocale } from "./types";
export {
  getStoredLocale,
  setStoredLocale,
  resolveInitialLocale,
} from "./storage";
