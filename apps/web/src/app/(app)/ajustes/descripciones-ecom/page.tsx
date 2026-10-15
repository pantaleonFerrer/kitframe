"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/hooks/use-i18n";
import { SettingsSection } from "../_components/ui";

type FillStart = {
  job_id: string;
  pending_count: number;
  pending_refs: string[];
};

type FillJob = {
  id: string;
  status: string;
  error_detail?: string | null;
  pending_count?: number;
  filled_count?: number;
  original_filename?: string;
  download_url?: string | null;
};

type RecentJob = {
  id: string;
  status: string;
  pending_count?: number;
  filled_count?: number;
  original_filename?: string;
  created_at: string;
  error_detail?: string | null;
};

export default function DescripcionesEcomPage() {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [job, setJob] = useState<FillJob | null>(null);
  const [recent, setRecent] = useState<RecentJob[]>([]);

  const loadRecent = useCallback(async () => {
    try {
      const res = await api<{ data: RecentJob[] }>("/tools/ecom-descriptions/recent");
      setRecent(res.data || []);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

  async function runFill() {
    if (!file) {
      setMsg(t("settings.ecomExcelNoFile"));
      return;
    }
    setBusy(true);
    setMsg(null);
    setJob(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const started = await api<FillStart>("/tools/ecom-descriptions/fill", {
        method: "POST",
        body,
      });
      setMsg(`${t("settings.ecomExcelPending")}: ${started.pending_count}`);

      let last: FillJob | null = null;
      for (let i = 0; i < 180; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        last = await api<FillJob>(`/tools/ecom-descriptions/jobs/${started.job_id}`);
        setJob(last);
        if (last.status === "completed") {
          setMsg(t("settings.ecomExcelDone"));
          break;
        }
        if (last.status === "failed") {
          setMsg(last.error_detail || t("settings.ecomExcelFailed"));
          break;
        }
      }
      if (last && last.status !== "completed" && last.status !== "failed") {
        setMsg(t("settings.ecomExcelFailed"));
      }
      await loadRecent();
    } catch (e) {
      setMsg((e as Error).message || t("settings.ecomExcelFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <SettingsSection title={t("settings.ecomExcelTitle")} description={t("settings.ecomExcelDesc")}>
        <div className="space-y-4">
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              className="rounded-md border border-border px-3 py-2 text-sm"
              onClick={() => inputRef.current?.click()}
              disabled={busy}
            >
              {t("settings.ecomExcelChoose")}
            </button>
            <span className="text-sm text-muted">
              {file ? file.name : t("settings.ecomExcelHint")}
            </span>
          </div>
          <button
            type="button"
            className="rounded-md bg-wine text-white px-4 py-2 text-sm disabled:opacity-50"
            disabled={busy || !file}
            onClick={() => void runFill()}
          >
            {busy ? t("settings.ecomExcelRunning") : t("settings.ecomExcelRun")}
          </button>
          {msg && <p className="text-sm text-muted">{msg}</p>}
          {job?.status === "completed" && job.download_url && (
            <div className="space-y-2">
              {typeof job.filled_count === "number" && (
                <p className="text-sm">
                  {t("settings.ecomExcelFilled")}: {job.filled_count}
                </p>
              )}
              <a
                href={job.download_url}
                className="inline-flex rounded-md border border-border px-4 py-2 text-sm hover:bg-raised"
              >
                {t("settings.ecomExcelDownload")}
              </a>
            </div>
          )}
        </div>
      </SettingsSection>

      {recent.length > 0 && (
        <SettingsSection title={t("settings.ecomExcelRecent")} description="">
          <ul className="divide-y divide-border text-sm">
            {recent.map((r) => (
              <li key={r.id} className="py-2 flex flex-wrap gap-x-4 gap-y-1">
                <span className="font-medium">{r.original_filename || r.id.slice(0, 8)}</span>
                <span className="text-muted">{r.status}</span>
                {typeof r.filled_count === "number" && (
                  <span className="text-muted">
                    {t("settings.ecomExcelFilled")}: {r.filled_count}
                  </span>
                )}
                <span className="text-muted">{new Date(r.created_at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </SettingsSection>
      )}
    </div>
  );
}
