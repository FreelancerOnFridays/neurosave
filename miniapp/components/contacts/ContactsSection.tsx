"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card } from "@/components/ui/Card";
import { useLang } from "@/contexts/LanguageContext";
import { useContacts } from "@/hooks/useContacts";
import { useSettings } from "@/hooks/useSettings";
import { api } from "@/lib/api";
import type { TKey } from "@/lib/i18n";

type AuthStep = "phone" | "code" | "password";

interface AuthState {
  step: AuthStep;
  hint: string;
}

function formatLastSync(iso: string | null, t: (k: TKey) => string, timezone: string): string {
  if (!iso) return t("contacts_never_synced");
  try {
    const d = new Date(iso);
    return `${t("contacts_last_sync")}: ${d.toLocaleString("ru-RU", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: timezone,
    })}`;
  } catch {
    return iso;
  }
}

export function ContactsSection() {
  const { t } = useLang();
  const { settings } = useSettings();
  const timezone = settings?.timezone ?? "UTC";
  const { status, contacts, folders, syncing, syncingFolder, syncAll, syncFolder, mutateStatus } =
    useContacts();

  const [auth, setAuth] = useState<AuthState | null>(null);
  const [inputVal, setInputVal] = useState("");
  const [loading, setLoading] = useState(false);

  const configured = status?.telethon_configured ?? false;
  const authorized = status?.telethon_authorized ?? false;

  async function handleConnect() {
    setLoading(true);
    try {
      const res = await api.sync.start();
      setAuth({ step: "phone", hint: res.message });
      setInputVal("");
    } catch (e) {
      setAuth({ step: "phone", hint: String(e) });
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit() {
    if (!inputVal.trim() || loading) return;
    setLoading(true);
    try {
      const res = await api.sync.input(inputVal.trim());
      setInputVal("");
      if (res.done) {
        setAuth(null);
        await mutateStatus();
        return;
      }
      const nextStep = (res.next_step as AuthStep | null) ?? auth?.step ?? "phone";
      setAuth({ step: nextStep, hint: res.message });
    } catch (e) {
      setAuth((prev) => prev ? { ...prev, hint: String(e) } : null);
    } finally {
      setLoading(false);
    }
  }

  async function handleCancel() {
    try {
      await api.sync.disconnect();
    } catch {}
    setAuth(null);
    setInputVal("");
  }

  async function handleDisconnect() {
    await api.sync.disconnect();
    await mutateStatus();
  }

  const inputType =
    auth?.step === "password" ? "password" : auth?.step === "code" ? "text" : "tel";
  const inputPlaceholder =
    auth?.step === "password"
      ? t("sync_password_placeholder")
      : auth?.step === "code"
      ? t("sync_code_placeholder")
      : t("sync_phone_placeholder");

  return (
    <Card className="mt-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-semibold text-tg-text">{t("settings_contacts_title")}</p>
        {contacts.length > 0 && (
          <span className="text-xs text-tg-hint">
            {contacts.length} {t("contacts_count")}
          </span>
        )}
      </div>

      {/* Not configured */}
      {!configured && (
        <p className="text-xs text-tg-hint leading-relaxed">
          ⚠️ {t("contacts_not_configured")}
        </p>
      )}

      {/* Not authorized — connect button */}
      {configured && !authorized && !auth && (
        <div className="space-y-3">
          <p className="text-xs text-tg-hint leading-relaxed">
            🔗 {t("sync_not_auth_hint")}
          </p>
          <button
            onClick={handleConnect}
            disabled={loading}
            className="w-full py-2.5 rounded-xl text-sm font-medium transition-opacity disabled:opacity-40"
            style={{
              background: "var(--tg-theme-button-color, #007aff)",
              color: "var(--tg-theme-button-text-color, #fff)",
            }}
          >
            {loading ? t("sync_submitting") : t("sync_connect_btn")}
          </button>
        </div>
      )}

      {/* Auth flow — step-by-step form */}
      {configured && !authorized && auth && (
        <div className="space-y-3">
          <p className="text-xs text-tg-hint leading-relaxed whitespace-pre-wrap">
            {auth.hint}
          </p>
          <input
            type={inputType}
            inputMode={auth.step === "code" ? "numeric" : undefined}
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder={inputPlaceholder}
            autoFocus
            className="w-full px-3 py-2.5 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors"
          />
          <div className="flex gap-2">
            <button
              onClick={handleSubmit}
              disabled={loading || !inputVal.trim()}
              className="flex-1 py-2.5 rounded-xl text-sm font-medium transition-opacity disabled:opacity-40"
              style={{
                background: "var(--tg-theme-button-color, #007aff)",
                color: "var(--tg-theme-button-text-color, #fff)",
              }}
            >
              {loading ? t("sync_submitting") : t("sync_continue_btn")}
            </button>
            <button
              onClick={handleCancel}
              disabled={loading}
              className="py-2.5 px-4 rounded-xl text-sm text-tg-hint transition-opacity disabled:opacity-40"
              style={{ background: "var(--tg-theme-secondary-bg-color, #f2f2f7)" }}
            >
              {t("sync_cancel_btn")}
            </button>
          </div>
        </div>
      )}

      {/* Authorized — sync UI */}
      {authorized && (
        <>
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-medium" style={{ color: "var(--tg-theme-accent-text-color, #34c759)" }}>
              ✅ {t("sync_connected_label")}
            </p>
            <button
              onClick={handleDisconnect}
              className="text-xs underline"
              style={{ color: "var(--tg-theme-hint-color)" }}
            >
              {t("sync_disconnect_btn")}
            </button>
          </div>

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-tg-hint">
              {formatLastSync(status?.last_sync ?? null, t, timezone)}
            </p>
            <button
              onClick={syncAll}
              disabled={syncing}
              className="shrink-0 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors disabled:opacity-40"
              style={{
                background: "var(--tg-theme-button-color, #007aff)",
                color: "var(--tg-theme-button-text-color, #fff)",
              }}
            >
              {syncing ? t("contacts_syncing") : t("contacts_sync_now")}
            </button>
          </div>

          <AnimatePresence>
            {folders.length > 0 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-4 overflow-hidden"
              >
                <p className="text-xs font-medium text-tg-hint mb-2 uppercase tracking-wide">
                  {t("contacts_folders_title")}
                </p>
                <div className="flex flex-col gap-1">
                  {folders.map((folder) => (
                    <div
                      key={folder.name}
                      className="flex items-center justify-between py-2 border-b border-tg-hint/10 last:border-0"
                    >
                      <span className="text-sm text-tg-text">📁 {folder.name}</span>
                      <button
                        onClick={() => syncFolder(folder.name)}
                        disabled={syncingFolder !== null}
                        className="text-xs px-2.5 py-1 rounded-lg transition-colors disabled:opacity-40"
                        style={{
                          background: "var(--tg-theme-secondary-bg-color, #f2f2f7)",
                          color: "var(--tg-theme-hint-color, #8e8e93)",
                        }}
                      >
                        {syncingFolder === folder.name
                          ? t("contacts_syncing")
                          : t("contacts_folder_sync")}
                      </button>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
            {folders.length === 0 && status && (
              <p className="text-xs text-tg-hint mt-3">{t("contacts_no_folders")}</p>
            )}
          </AnimatePresence>
        </>
      )}
    </Card>
  );
}
