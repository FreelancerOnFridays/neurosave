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
        onRefresh={() => mutate()}
      />
    </Card>
  );
}
