"use client";

import { useState } from "react";
import useSWR from "swr";
import { Card } from "@/components/ui/Card";
import { IntegrationCard } from "./IntegrationCard";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import type { IntegrationsStatus } from "@/lib/types";

export function IntegrationsSection() {
  const { t } = useLang();
  const [showUris, setShowUris] = useState(false);
  const { data, mutate } = useSWR<IntegrationsStatus>(
    "/api/integrations/status",
    api.integrations.status,
    { refreshInterval: 10_000 }
  );
  const { data: uriData } = useSWR(
    showUris ? "/api/integrations/redirect-uris" : null,
    api.integrations.redirectUris
  );

  if (!data) return null;

  return (
    <Card className="mt-4">
      <p className="text-sm font-semibold text-tg-text mb-3">🔗 {t("settings_integrations_title")}</p>
      <IntegrationCard
        integration={data.google_calendar}
        label="Google Calendar"
        icon="📅"
        description="Синхронизация дедлайнов задач с Google Calendar"
        onAuthUrl={api.integrations.googleAuthUrl}
        onDisconnect={api.integrations.googleDisconnect}
        onRefresh={() => mutate()}
      />
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
      </div>
      <div className="mt-3">
        <IntegrationCard
          integration={data.google_docs}
          label="Google Docs & Sheets"
          icon="📄"
          description="Создание документов и таблиц прямо из чата с ботом"
          onAuthUrl={api.integrations.googleDocsAuthUrl}
          onDisconnect={api.integrations.googleDocsDisconnect}
          onRefresh={() => mutate()}
        />
      </div>

      {/* Redirect URI helper for Google OAuth */}
      <div className="mt-4 pt-3 border-t border-tg-hint/10">
        <button
          onClick={() => setShowUris((v) => !v)}
          className="flex items-center gap-1.5 text-xs text-tg-hint hover:text-tg-text transition-colors"
        >
          <span>{showUris ? "▲" : "▼"}</span>
          <span>{t("gmail_redirect_hint").split(":")[0]}</span>
        </button>
        {showUris && (
          <div className="mt-2 space-y-1">
            <p className="text-xs text-tg-hint leading-relaxed">
              {t("gmail_redirect_hint")}
            </p>
            {uriData?.redirect_uris.map((uri) => (
              <div
                key={uri}
                className="px-2 py-1.5 rounded-lg text-xs font-mono break-all select-all"
                style={{ background: "var(--tg-theme-secondary-bg-color, #f2f2f7)" }}
              >
                {uri}
              </div>
            ))}
            {!uriData && (
              <p className="text-xs text-tg-hint italic">Загрузка…</p>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
