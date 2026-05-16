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
          integration={data.notion}
          label="Notion"
          icon="📝"
          description="Сохранение заметок, задач и итогов встреч прямо из чата с ботом"
          onAuthUrl={api.integrations.notionAuthUrl}
          onDisconnect={api.integrations.notionDisconnect}
          onRefresh={() => mutate()}
        />
      </div>
    </Card>
  );
}
