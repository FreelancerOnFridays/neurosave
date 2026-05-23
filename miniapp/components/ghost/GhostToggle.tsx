"use client";

import { Toggle } from "@/components/ui/Toggle";
import { useLang } from "@/contexts/LanguageContext";

interface GhostToggleProps {
  isActive: boolean;
  activatedAt: string | null;
  onToggle: (active: boolean) => void;
  disabled?: boolean;
}

function formatSince(iso: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay =
      d.getDate() === now.getDate() &&
      d.getMonth() === now.getMonth() &&
      d.getFullYear() === now.getFullYear();
    const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    if (sameDay) return time;
    const date = d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
    return `${date}, ${time}`;
  } catch {
    return "";
  }
}

export function GhostToggle({
  isActive,
  activatedAt,
  onToggle,
  disabled,
}: GhostToggleProps) {
  const { t } = useLang();
  const since = formatSince(activatedAt);

  return (
    <div
      className={`rounded-3xl p-6 flex flex-col items-center gap-3 transition-colors duration-300 ${
        isActive ? "bg-tg-accent/10" : "bg-tg-secondary"
      }`}
    >
      <span
        className={`text-6xl transition-all duration-500 ${
          isActive ? "animate-pulse" : "opacity-40"
        }`}
      >
        👻
      </span>
      <div className="flex items-center gap-3">
        <span className="text-sm font-semibold text-tg-text">
          {isActive ? t("ghost_active") : t("ghost_inactive")}
        </span>
        <Toggle checked={isActive} onChange={onToggle} disabled={disabled} />
      </div>
      {isActive && since && (
        <p className="text-xs text-tg-hint">{t("ghost_since")} {since}</p>
      )}
    </div>
  );
}
