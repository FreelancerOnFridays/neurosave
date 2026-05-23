"use client";

import { Card } from "@/components/ui/Card";
import { useLang } from "@/contexts/LanguageContext";
import { openTgProfile } from "@/lib/telegram";
import type { Inquiry } from "@/lib/types";

const CATEGORY_COLORS: Record<string, string> = {
  Urgent: "#ff3b30",
  Team: "#34c759",
  Sales: "#007aff",
  Spam: "#8e8e93",
  Normal: "#5ac8fa",
};

// Labels that map to built-in categories — don't show as duplicate chips
const CATEGORY_LABEL_KEYS = new Set(["команда", "team", "срочно", "urgent", "продажи", "sales", "спам", "spam"]);

interface InquiryCardProps {
  inquiry: Inquiry;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}


export function InquiryCard({ inquiry }: InquiryCardProps) {
  const { t } = useLang();
  const color = inquiry.category
    ? (CATEGORY_COLORS[inquiry.category] ?? "#8e8e93")
    : "#8e8e93";

  return (
    <Card>
      <div className="flex items-start gap-3">
        <span
          className="mt-1 h-2.5 w-2.5 rounded-full shrink-0"
          style={{ backgroundColor: color }}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {inquiry.caller_username ? (
                <button
                  onClick={() => openTgProfile(inquiry.caller_username)}
                  className="text-sm font-semibold text-tg-accent underline underline-offset-2"
                >
                  {inquiry.caller_name ?? `@${inquiry.caller_username}`}
                </button>
              ) : (
                <p className="text-sm font-semibold text-tg-text">
                  {inquiry.caller_name ?? t("unknown_contact")}
                </p>
              )}
            </div>
            <span className="text-xs text-tg-hint shrink-0">
              {formatTime(inquiry.created_at)}
            </span>
          </div>
          {inquiry.summary && (
            <p className="text-xs text-tg-hint mt-0.5 leading-relaxed">
              {inquiry.summary}
            </p>
          )}
          {(inquiry.caller_labels ?? []).filter(l => !CATEGORY_LABEL_KEYS.has(l.toLowerCase())).length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {(inquiry.caller_labels ?? []).filter(l => !CATEGORY_LABEL_KEYS.has(l.toLowerCase())).map((l) => (
                <span
                  key={l}
                  className="inline-flex items-center text-[10px] px-2 py-0.5 rounded-full font-medium"
                  style={{
                    background: "var(--tg-theme-button-color, #007aff)",
                    color: "var(--tg-theme-button-text-color, #fff)",
                    opacity: 0.8,
                  }}
                >
                  {l}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
