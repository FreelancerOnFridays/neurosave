"use client";

import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { LanguageSelect } from "@/components/settings/LanguageSelect";
import { TimezoneSelect } from "@/components/settings/TimezoneSelect";
import { ThemeSelect } from "@/components/settings/ThemeSelect";
import { SettingsRow } from "@/components/settings/SettingsRow";
import { Toggle } from "@/components/ui/Toggle";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Card } from "@/components/ui/Card";
import { ContactsSection } from "@/components/contacts/ContactsSection";
import { IntegrationsSection } from "@/components/integrations/IntegrationsSection";
import { useSettings } from "@/hooks/useSettings";
import { useLang } from "@/contexts/LanguageContext";
import { api } from "@/lib/api";
import type { Theme } from "@/lib/types";

export default function SettingsPage() {
  const { settings, isLoading, error, update } = useSettings();
  const { lang, setLang, t } = useLang();
  const [tutorialState, setTutorialState] = useState<"idle" | "loading" | "done">("idle");

  if (isLoading) return <Spinner />;
  if (error || !settings)
    return <EmptyState icon="⚠️" message={`${t("error_loading")}: ${error?.message ?? ""}`} />;

  return (
    <div>
      <PageHeader title={`⚙️ ${t("nav_settings")}`} />

      <Card>
        <SettingsRow label={t("settings_language")}>
          <LanguageSelect
            value={lang}
            onChange={(l) => {
              setLang(l);         // instant UI update
              update({ language: l }); // persist to backend
            }}
          />
        </SettingsRow>

        <SettingsRow label={t("settings_timezone")}>
          <TimezoneSelect
            value={settings.timezone}
            onChange={(tz) => update({ timezone: tz })}
          />
        </SettingsRow>

        <SettingsRow label={t("settings_brief_time")} hint={t("settings_brief_hint")}>
          <input
            type="time"
            defaultValue={settings.brief_time}
            onBlur={(e) => update({ brief_time: e.target.value })}
            className="text-sm text-right bg-transparent text-tg-text outline-none border-b border-tg-hint/20 focus:border-tg-accent/50 pb-0.5"
          />
        </SettingsRow>

        <SettingsRow label={t("settings_brief_toggle")}>
          <Toggle
            checked={settings.brief_enabled}
            onChange={(v) => update({ brief_enabled: v })}
          />
        </SettingsRow>

        <div className="py-3">
          <p className="text-sm font-medium text-tg-text">{t("settings_theme")}</p>
          <ThemeSelect
            value={(settings.theme as Theme) ?? "auto"}
            onChange={(v) => update({ theme: v })}
          />
        </div>
      </Card>

      <ContactsSection />
      <IntegrationsSection />

      <Card className="mt-4">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-medium text-tg-text">📖 {t("settings_send_tutorial")}</p>
            <p className="text-xs text-tg-hint mt-0.5">{t("settings_send_tutorial_hint")}</p>
          </div>
          <button
            disabled={tutorialState !== "idle"}
            onClick={async () => {
              setTutorialState("loading");
              try {
                await api.bot.sendTutorial();
                setTutorialState("done");
                setTimeout(() => setTutorialState("idle"), 3000);
              } catch {
                setTutorialState("idle");
              }
            }}
            className="shrink-0 text-sm font-medium px-4 py-1.5 rounded-xl transition-opacity disabled:opacity-50"
            style={{
              background: "var(--tg-theme-button-color, #007aff)",
              color: "var(--tg-theme-button-text-color, #fff)",
            }}
          >
            {tutorialState === "loading"
              ? t("settings_tutorial_sending")
              : tutorialState === "done"
              ? t("settings_tutorial_sent")
              : "→"}
          </button>
        </div>
      </Card>

      <Card className="mt-4">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-medium text-tg-text">💬 {t("settings_contact_support")}</p>
            <p className="text-xs text-tg-hint mt-0.5">{t("settings_contact_support_hint")}</p>
          </div>
          <button
            onClick={() => {
              const WebApp = (window as any)?.Telegram?.WebApp;
              if (WebApp?.openLink) {
                WebApp.openLink("https://t.me/lg1lx");
              } else {
                window.open("https://t.me/lg1lx", "_blank");
              }
            }}
            className="shrink-0 text-sm font-medium px-4 py-1.5 rounded-xl transition-opacity"
            style={{
              background: "var(--tg-theme-button-color, #007aff)",
              color: "var(--tg-theme-button-text-color, #fff)",
            }}
          >
            {t("settings_contact_support_btn")}
          </button>
        </div>
      </Card>

      <p className="mt-6 mb-2 text-center text-xs text-tg-hint">NeuroSave v0.11 · Beta</p>
    </div>
  );
}
