"use client";

import type { Lang } from "@/lib/i18n";

interface LanguageSelectProps {
  value: Lang;
  onChange: (lang: Lang) => void;
}

const LANG_LABELS: Record<Lang, string> = {
  ru: "RU",
  en: "EN",
  ua: "UA",
};

export function LanguageSelect({ value, onChange }: LanguageSelectProps) {
  return (
    <div className="flex rounded-xl overflow-hidden border border-tg-hint/20">
      {(["ru", "ua", "en"] as const).map((lang) => (
        <button
          key={lang}
          onClick={() => onChange(lang)}
          className={`px-4 py-1.5 text-sm font-semibold transition-colors ${
            value === lang
              ? "bg-tg-btn text-tg-btn-text"
              : "text-tg-hint bg-transparent"
          }`}
        >
          {LANG_LABELS[lang]}
        </button>
      ))}
    </div>
  );
}
