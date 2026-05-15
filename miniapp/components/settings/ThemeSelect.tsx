"use client";

import { motion } from "framer-motion";
import { useLang } from "@/contexts/LanguageContext";
import type { Theme } from "@/lib/types";

interface ThemeSelectProps {
  value: Theme;
  onChange: (theme: Theme) => void;
}

const THEMES: { key: Theme; icon: string }[] = [
  { key: "auto", icon: "⚙️" },
  { key: "light", icon: "☀️" },
  { key: "dark", icon: "🌙" },
];

export function ThemeSelect({ value, onChange }: ThemeSelectProps) {
  const { t } = useLang();
  const labels: Record<Theme, string> = {
    auto: t("theme_auto"),
    light: t("theme_light"),
    dark: t("theme_dark"),
  };

  return (
    <div className="relative flex bg-tg-secondary rounded-2xl p-1 w-full mt-2">
      <motion.div
        className="absolute top-1 bottom-1 rounded-xl bg-tg-bg shadow-sm"
        layoutId="theme-pill"
        style={{
          width: `${100 / THEMES.length}%`,
          left: `${(THEMES.findIndex((t) => t.key === value) * 100) / THEMES.length}%`,
        }}
        transition={{ type: "spring", stiffness: 400, damping: 30 }}
      />
      {THEMES.map(({ key, icon }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className="relative z-10 flex-1 flex flex-col items-center gap-0.5 py-2 transition-colors"
        >
          <span className="text-base leading-none">{icon}</span>
          <span
            className="text-xs font-medium"
            style={{
              color:
                value === key
                  ? "var(--tg-theme-text-color)"
                  : "var(--tg-theme-hint-color)",
            }}
          >
            {labels[key]}
          </span>
        </button>
      ))}
    </div>
  );
}
