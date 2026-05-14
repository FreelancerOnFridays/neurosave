import type { ReactNode } from "react";

interface SettingsRowProps {
  label: string;
  hint?: string;
  children: ReactNode;
}

export function SettingsRow({ label, hint, children }: SettingsRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-b border-tg-hint/10 last:border-0">
      <div>
        <p className="text-sm font-medium text-tg-text">{label}</p>
        {hint && <p className="text-xs text-tg-hint mt-0.5">{hint}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
