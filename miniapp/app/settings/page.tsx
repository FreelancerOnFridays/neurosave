"use client";

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
import type { Theme } from "@/lib/types";

export default function SettingsPage() {
  const { settings, isLoading, error, update } = useSettings();
  const { lang, setLang, t } = useLang();

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
    </div>
  );
}
