"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import type { GmailThread } from "@/lib/types";

function parseDate(raw: string): string {
  if (!raw) return "";
  try {
    const d = new Date(raw);
    if (isNaN(d.getTime())) return raw;
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const days = Math.floor(diff / 86400000);
    if (days === 0) return d.toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
    if (days === 1) return "вчера";
    return d.toLocaleDateString("ru", { day: "numeric", month: "short" });
  } catch {
    return raw;
  }
}

function senderName(from_: string): string {
  const match = from_.match(/^"?([^"<]+)"?\s*</);
  return match ? match[1].trim() : from_.replace(/<.*>/, "").trim() || from_;
}

export function GmailWorkspace() {
  const { t } = useLang();
  const { data: threads, isLoading } = useSWR<GmailThread[]>(
    "/api/integrations/gmail/threads",
    () => api.integrations.gmailThreads(30),
    { refreshInterval: 60_000 }
  );

  const botUsername = "neurosavebot";

  return (
    <div className="space-y-4">
      <a
        href={`https://t.me/${botUsername}?start=compose_email`}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-medium"
        style={{
          background: "var(--tg-theme-button-color, #007aff)",
          color: "var(--tg-theme-button-text-color, #fff)",
        }}
      >
        ✉️ {t("gmail_compose")}
      </a>

      <p className="text-xs font-semibold text-tg-hint uppercase tracking-wide">
        {t("gmail_recent_threads")}
      </p>

      {isLoading && (
        <p className="text-sm text-tg-hint text-center py-4">Загрузка…</p>
      )}

      {!isLoading && (!threads || threads.length === 0) && (
        <p className="text-sm text-tg-hint text-center py-6">{t("gmail_no_threads")}</p>
      )}

      {threads && threads.length > 0 && (
        <div className="space-y-1">
          {threads.map((thread) => (
            <div
              key={thread.id}
              className="flex items-start gap-3 px-3 py-2.5 rounded-xl"
              style={{ background: "var(--tg-theme-secondary-bg-color, #f2f2f7)" }}
            >
              <span className="text-base leading-none mt-0.5 shrink-0">
                {thread.is_reply ? "📨" : "📤"}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-xs font-semibold text-tg-text truncate flex-1">
                    {senderName(thread.from_)}
                  </span>
                  {thread.is_reply && (
                    <span
                      className="shrink-0 text-xs px-1.5 py-0.5 rounded-full font-medium"
                      style={{
                        background: "rgba(52, 199, 89, 0.15)",
                        color: "#34c759",
                      }}
                    >
                      {t("gmail_inbox_reply")}
                    </span>
                  )}
                  <span className="text-xs text-tg-hint shrink-0">{parseDate(thread.date)}</span>
                </div>
                <p className="text-xs font-medium text-tg-text truncate">{thread.subject}</p>
                {thread.snippet && (
                  <p className="text-xs text-tg-hint truncate mt-0.5">{thread.snippet}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
