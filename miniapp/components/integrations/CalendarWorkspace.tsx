"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import type { CalendarEvent } from "@/lib/types";

function formatTime(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  if (iso.length === 10) return "весь день";
  return d.toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
}

function dayLabel(iso: string) {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? iso : iso);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const eventDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round((eventDay.getTime() - today.getTime()) / 86400000);
  if (diff === 0) return "Сегодня, " + d.toLocaleDateString("ru", { day: "numeric", month: "long" });
  if (diff === 1) return "Завтра, " + d.toLocaleDateString("ru", { day: "numeric", month: "long" });
  return d.toLocaleDateString("ru", { weekday: "long", day: "numeric", month: "long" });
}

function groupByDay(events: CalendarEvent[]) {
  const groups: { label: string; events: CalendarEvent[] }[] = [];
  const seen = new Map<string, number>();
  for (const ev of events) {
    const dayKey = ev.start.slice(0, 10);
    if (!seen.has(dayKey)) {
      seen.set(dayKey, groups.length);
      groups.push({ label: dayLabel(ev.start), events: [] });
    }
    groups[seen.get(dayKey)!].events.push(ev);
  }
  return groups;
}

export function CalendarWorkspace() {
  const { t } = useLang();
  const { data: events } = useSWR<CalendarEvent[]>(
    "/api/integrations/google-calendar/events",
    () => api.integrations.calendarEvents(7),
    { refreshInterval: 60_000 }
  );

  if (!events) {
    return <p className="text-sm text-tg-hint text-center py-4">Загрузка…</p>;
  }

  if (events.length === 0) {
    return (
      <p className="text-sm text-tg-hint text-center py-6">{t("calendar_no_events")}</p>
    );
  }

  const groups = groupByDay(events);

  return (
    <div className="space-y-4">
      <p className="text-xs font-semibold text-tg-hint uppercase tracking-wide">
        {t("calendar_upcoming")}
      </p>
      {groups.map((group) => (
        <div key={group.label}>
          <p className="text-xs font-semibold text-tg-hint mb-1.5 capitalize">{group.label}</p>
          <div className="space-y-1">
            {group.events.map((ev) => {
              const startTime = formatTime(ev.start);
              const endTime = ev.end ? formatTime(ev.end) : null;
              const timeLabel = endTime && endTime !== startTime ? `${startTime}–${endTime}` : startTime;
              const inner = (
                <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-tg-secondary transition-colors">
                  <span className="text-base leading-none">📅</span>
                  <span className="flex-1 text-sm text-tg-text">{ev.title}</span>
                  <span className="text-xs text-tg-hint shrink-0">{timeLabel}</span>
                </div>
              );
              return ev.url ? (
                <a key={ev.id} href={ev.url} target="_blank" rel="noopener noreferrer">
                  {inner}
                </a>
              ) : (
                <div key={ev.id}>{inner}</div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
