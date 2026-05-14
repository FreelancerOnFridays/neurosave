"use client";

interface LanguageSelectProps {
  value: "ru" | "en";
  onChange: (lang: "ru" | "en") => void;
}

export function LanguageSelect({ value, onChange }: LanguageSelectProps) {
  return (
    <div className="flex rounded-xl overflow-hidden border border-tg-hint/20">
      {(["ru", "en"] as const).map((lang) => (
        <button
          key={lang}
          onClick={() => onChange(lang)}
          className={`px-4 py-1.5 text-sm font-semibold transition-colors ${
            value === lang
              ? "bg-tg-btn text-tg-btn-text"
              : "text-tg-hint bg-transparent"
          }`}
        >
          {lang.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
