"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { useI18n } from "@/hooks/use-i18n";
import { isLocale, LOCALES, type Locale } from "@/lib/i18n";
import { FieldInput, FieldLabel, FieldSelect, SettingsSection } from "../_components/ui";

export default function PerfilPage() {
  const { user, refreshMe } = useAuth();
  const { t, setLocale } = useI18n();
  const [name, setName] = useState("");
  const [locale, setLocaleDraft] = useState<Locale>("es");
  const [currentPassword, setCurrentPassword] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) return;
    setName(user.name);
    setLocaleDraft(isLocale(user.locale) ? user.locale : "es");
  }, [user]);

  if (!user) {
    return <div className="text-sm text-muted p-6">{t("common.loading")}</div>;
  }

  const nameLabel = locale === "en" ? "Name" : locale === "ca" ? "Nom" : "Nombre";
  const passwordTitle = locale === "en" ? "Password" : locale === "ca" ? "Contrasenya" : "Contraseña";
  const passwordDesc =
    locale === "en"
      ? "Minimum 12 characters. Changing it signs out other sessions."
      : locale === "ca"
        ? "Mínim 12 caràcters. En canviar-la es tanquen altres sessions."
        : "Mínimo 12 caracteres. Al cambiarla se cierran otras sesiones.";
  const currentPwdLabel =
    locale === "en" ? "Current password" : locale === "ca" ? "Contrasenya actual" : "Contraseña actual";
  const newPwdLabel =
    locale === "en" ? "New password" : locale === "ca" ? "Contrasenya nova" : "Nueva contraseña";
  const passwordSaved =
    locale === "en"
      ? "Password updated"
      : locale === "ca"
        ? "Contrasenya actualitzada"
        : "Contraseña actualizada";

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">{t("nav.myProfile")}</h2>
        <p className="text-sm text-muted mt-1">{user.email}</p>
      </div>

      <SettingsSection
        title={t("settings.languageTitle")}
        description={t("settings.languageHint")}
        onSave={async () => {
          setSaving(true);
          try {
            await api("/me", {
              method: "PATCH",
              body: JSON.stringify({ name, locale }),
              skipBrand: true,
            });
            setLocale(locale);
            await refreshMe();
            setMessage(t("settings.languageSaved"));
          } catch (e) {
            setMessage((e as Error).message);
          } finally {
            setSaving(false);
          }
        }}
        saving={saving}
        message={message}
      >
        <div className="grid md:grid-cols-2 gap-3">
          <FieldLabel>
            {nameLabel}
            <FieldInput value={name} onChange={(e) => setName(e.target.value)} />
          </FieldLabel>
          <FieldLabel>
            {t("settings.chooseLanguage")}
            <FieldSelect
              value={locale}
              onChange={(e) => setLocaleDraft(e.target.value as Locale)}
            >
              {LOCALES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.nativeLabel}
                </option>
              ))}
            </FieldSelect>
          </FieldLabel>
        </div>
      </SettingsSection>

      <SettingsSection
        title={passwordTitle}
        description={passwordDesc}
        onSave={async () => {
          setSaving(true);
          try {
            await api("/me", {
              method: "PATCH",
              body: JSON.stringify({
                current_password: currentPassword,
                password,
              }),
              skipBrand: true,
            });
            setCurrentPassword("");
            setPassword("");
            setMessage(passwordSaved);
            await refreshMe();
          } catch (e) {
            setMessage((e as Error).message);
          } finally {
            setSaving(false);
          }
        }}
        saving={saving}
      >
        <div className="grid md:grid-cols-2 gap-3">
          <FieldLabel>
            {currentPwdLabel}
            <FieldInput
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
          </FieldLabel>
          <FieldLabel>
            {newPwdLabel}
            <FieldInput
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={12}
            />
          </FieldLabel>
        </div>
      </SettingsSection>
    </div>
  );
}
