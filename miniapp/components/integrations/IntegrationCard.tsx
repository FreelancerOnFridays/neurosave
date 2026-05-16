"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { IntegrationStatus } from "@/lib/types";

interface Props {
  integration: IntegrationStatus;
  label: string;
  icon: string;
  description: string;
  onRefresh: () => void;
}

export function IntegrationCard({ integration, label, icon, description, onRefresh }: Props) {
  const [loading, setLoading] = useState(false);

  async function handleConnect() {
    setLoading(true);
    try {
      const { url } = await api.integrations.googleAuthUrl();
      try {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const WebApp = require("@twa-dev/sdk").default;
        if (WebApp?.openLink) {
          WebApp.openLink(url);
          return;
        }
      } catch {
        // not in Telegram context
      }
      window.open(url, "_blank");
    } catch (e) {
      console.error("Failed to get auth URL", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleDisconnect() {
    setLoading(true);
    try {
      await api.integrations.googleDisconnect();
      onRefresh();
    } catch (e) {
      console.error("Failed to disconnect", e);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex items-start gap-3 py-3 border-b border-tg-hint/10 last:border-0">
      <span className="text-2xl leading-none mt-0.5">{icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <p className="text-sm font-medium text-tg-text">{label}</p>
          {integration.connected && (
            <span
              className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full leading-none"
              style={{ background: "var(--tg-theme-accent-text-color, #34c759)22", color: "var(--tg-theme-accent-text-color, #34c759)" }}
            >
              Connected
            </span>
          )}
        </div>
        {integration.connected && integration.email ? (
          <p className="text-xs text-tg-hint truncate">{integration.email}</p>
        ) : (
          <p className="text-xs text-tg-hint leading-relaxed">{description}</p>
        )}
      </div>
      {integration.connected ? (
        <button
          onClick={handleDisconnect}
          disabled={loading}
          className="shrink-0 text-xs underline disabled:opacity-40"
          style={{ color: "var(--tg-theme-hint-color)" }}
        >
          {loading ? "..." : "Отключить"}
        </button>
      ) : (
        <button
          onClick={handleConnect}
          disabled={loading}
          className="shrink-0 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors disabled:opacity-40"
          style={{
            background: "var(--tg-theme-button-color, #007aff)",
            color: "var(--tg-theme-button-text-color, #fff)",
          }}
        >
          {loading ? "..." : "Подключить"}
        </button>
      )}
    </div>
  );
}
