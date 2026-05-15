"use client";

import { useSettings } from "@/hooks/useSettings";
import { useTheme } from "@/hooks/useTheme";
import type { Theme } from "@/lib/types";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const { settings } = useSettings();
  useTheme((settings?.theme as Theme) ?? "auto");
  return <>{children}</>;
}
