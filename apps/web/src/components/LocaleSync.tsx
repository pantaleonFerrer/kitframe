"use client";

import { useEffect } from "react";
import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import { isLocale } from "@/lib/i18n";

/** Keep UI locale in sync with the signed-in user's profile language. */
export function LocaleSync() {
  const { user } = useAuth();
  const { locale, setLocale } = useI18n();

  useEffect(() => {
    if (!user?.locale || !isLocale(user.locale)) return;
    if (user.locale === locale) return;
    setLocale(user.locale);
  }, [user?.locale, locale, setLocale]);

  return null;
}
