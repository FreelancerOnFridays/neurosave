"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { PageHeader } from "@/components/layout/PageHeader";
import { GoogleDocsWorkspace } from "@/components/integrations/GoogleDocsWorkspace";
import { CalendarWorkspace } from "@/components/integrations/CalendarWorkspace";
import { GmailWorkspace } from "@/components/integrations/GmailWorkspace";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import type { IntegrationsStatus } from "@/lib/types";

const WORKSPACE_KEY = "integrations_active_pill";

type PillId = "google_docs" | "google_calendar" | "gmail";

const ALL_PILLS: { id: PillId; label: string; icon: string }[] = [
  { id: "google_docs", label: "Docs & Sheets", icon: "📄" },
  { id: "google_calendar", label: "Calendar", icon: "📅" },
  { id: "gmail", label: "Gmail", icon: "✉️" },
];

function connectedPills(status: IntegrationsStatus) {
  return ALL_PILLS.filter((p) => {
    if (p.id === "google_docs") return status.google_docs.connected;
    if (p.id === "google_calendar") return status.google_calendar.connected;
    if (p.id === "gmail") return status.gmail.connected;
    return false;
  });
}

export default function IntegrationsPage() {
  const { t } = useLang();
  const { data } = useSWR<IntegrationsStatus>(
    "/api/integrations/status",
    api.integrations.status,
    { refreshInterval: 15_000 }
  );

  const pills = data ? connectedPills(data) : [];

  const [active, setActive] = useState<PillId | null>(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem(WORKSPACE_KEY) as PillId) || null;
    }
    return null;
  });

  useEffect(() => {
    if (pills.length > 0 && (!active || !pills.find((p) => p.id === active))) {
      const saved = typeof window !== "undefined" ? (localStorage.getItem(WORKSPACE_KEY) as PillId) : null;
      const first = (saved && pills.find((p) => p.id === saved)) ? saved : pills[0].id;
      setActive(first);
    }
  }, [pills, active]);

  function selectPill(id: PillId) {
    setActive(id);
    localStorage.setItem(WORKSPACE_KEY, id);
  }

  return (
    <div className="flex flex-col min-h-screen pb-20">
      <PageHeader title={t("nav_integrations")} />
      <div className="flex-1 px-4 pt-2">
        {!data && (
          <p className="text-sm text-tg-hint text-center mt-8">Загрузка…</p>
        )}
        {data && pills.length === 0 && (
          <div className="flex flex-col items-center justify-center mt-16 gap-3">
            <span className="text-4xl">🔗</span>
            <p className="text-sm font-medium text-tg-text">{t("integrations_empty")}</p>
            <p className="text-xs text-tg-hint text-center max-w-48">{t("integrations_connect_hint")}</p>
          </div>
        )}
        {data && pills.length > 0 && (
          <>
            <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
              {pills.map((pill) => (
                <button
                  key={pill.id}
                  onClick={() => selectPill(pill.id)}
                  className="shrink-0 flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors"
                  style={
                    active === pill.id
                      ? {
                          background: "var(--tg-theme-button-color, #007aff)",
                          color: "var(--tg-theme-button-text-color, #fff)",
                        }
                      : {
                          background: "var(--tg-theme-secondary-bg-color, #f2f2f7)",
                          color: "var(--tg-theme-text-color)",
                        }
                  }
                >
                  <span>{pill.icon}</span>
                  <span>{pill.label}</span>
                </button>
              ))}
            </div>

            <div className="mt-4">
              {active === "google_docs" && <GoogleDocsWorkspace />}
              {active === "google_calendar" && <CalendarWorkspace />}
              {active === "gmail" && <GmailWorkspace />}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
