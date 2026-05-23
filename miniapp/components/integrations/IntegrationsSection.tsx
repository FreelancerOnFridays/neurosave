"use client";

import useSWR from "swr";
import { Card } from "@/components/ui/Card";
import { IntegrationCard } from "./IntegrationCard";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import type { IntegrationsStatus } from "@/lib/types";

export function IntegrationsSection() {
  const { t } = useLang();
  const { data, mutate } = useSWR<IntegrationsStatus>(
    "/api/integrations/status",
    api.integrations.status,
    { refreshInterval: 10_000 }
  );
  const { data: notifData, mutate: mutateNotif } = useSWR(
    data?.gmail.connected ? "/api/integrations/gmail/notifications" : null,
    api.integrations.gmailNotifications
  );

  async function toggleGmailNotifications() {
    if (!notifData) return;
    const next = !notifData.enabled;
    await api.integrations.setGmailNotifications(next);
    await mutateNotif({ enabled: next }, false);
  }

  if (!data) return null;

  return (
    <Card className="mt-4">
      <p className="text-sm font-semibold text-tg-text mb-3">🔗 {t("settings_integrations_title")}</p>

      {/* Google Calendar — coming soon */}
      <div className="flex items-center gap-3 py-2 opacity-50">
        <span className="text-2xl">📅</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-tg-text">Google Calendar</p>
          <p className="text-xs text-tg-hint mt-0.5">Синхронизация дедлайнов задач с Google Calendar</p>
        </div>
        <span
          className="shrink-0 text-xs font-medium px-2 py-0.5 rounded-full"
          style={{ background: "var(--tg-theme-secondary-bg-color)", color: "var(--tg-theme-hint-color)" }}
        >
          {t("calendar_coming_soon")}
        </span>
      </div>

      <div className="mt-3">
        <IntegrationCard
          integration={data.gmail}
          label="Gmail"
          icon="✉️"
          description="Отправка писем и файлов прямо из чата с ботом"
          onAuthUrl={api.integrations.gmailAuthUrl}
          onDisconnect={api.integrations.gmailDisconnect}
          onRefresh={() => mutate()}
        />
        {data.gmail.connected && notifData !== undefined && (
          <div className="mt-3 mx-1 flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="text-sm text-tg-text">{t("gmail_notifications_toggle")}</p>
              <p className="text-xs text-tg-hint mt-0.5 leading-snug">{t("gmail_notifications_hint")}</p>
            </div>
            <button
              onClick={toggleGmailNotifications}
              role="switch"
              aria-checked={notifData.enabled}
              style={{
                flexShrink: 0,
                width: 51,
                height: 31,
                borderRadius: 999,
                padding: 2,
                background: notifData.enabled ? "var(--tg-theme-button-color, #2AABEE)" : "rgba(120,120,128,0.32)",
                border: "none",
                cursor: "pointer",
                transition: "background 0.2s",
                display: "flex",
                alignItems: "center",
              }}
            >
              <span
                style={{
                  display: "block",
                  width: 27,
                  height: 27,
                  borderRadius: "50%",
                  background: "#fff",
                  boxShadow: "0 2px 4px rgba(0,0,0,0.3)",
                  transform: notifData.enabled ? "translateX(20px)" : "translateX(0)",
                  transition: "transform 0.2s",
                }}
              />
            </button>
          </div>
        )}
      </div>
    </Card>
  );
}
