"use client";

import { useEffect } from "react";
import type { Theme } from "@/lib/types";

declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        colorScheme?: "light" | "dark";
        ready: () => void;
        expand: () => void;
        initData?: string;
        onEvent?: (event: string, cb: () => void) => void;
        offEvent?: (event: string, cb: () => void) => void;
      };
    };
  }
}

const DARK_VARS: Record<string, string> = {
  "--tg-theme-bg-color": "#1c1c1e",
  "--tg-theme-secondary-bg-color": "#2c2c2e",
  "--tg-theme-text-color": "#ffffff",
  "--tg-theme-hint-color": "#8e8e93",
  "--tg-theme-link-color": "#0a84ff",
  "--tg-theme-button-color": "#0a84ff",
  "--tg-theme-button-text-color": "#ffffff",
  "--tg-theme-destructive-text-color": "#ff453a",
};

const LIGHT_VARS: Record<string, string> = {
  "--tg-theme-bg-color": "#ffffff",
  "--tg-theme-secondary-bg-color": "#f2f2f7",
  "--tg-theme-text-color": "#000000",
  "--tg-theme-hint-color": "#8e8e93",
  "--tg-theme-link-color": "#007aff",
  "--tg-theme-button-color": "#007aff",
  "--tg-theme-button-text-color": "#ffffff",
  "--tg-theme-destructive-text-color": "#ff3b30",
};

function applyVars(resolved: "light" | "dark") {
  const vars = resolved === "dark" ? DARK_VARS : LIGHT_VARS;
  const el = document.documentElement;
  for (const [key, val] of Object.entries(vars)) {
    el.style.setProperty(key, val);
  }
  el.setAttribute("data-theme", resolved);
}

function clearVars() {
  const el = document.documentElement;
  for (const key of Object.keys(DARK_VARS)) {
    el.style.removeProperty(key);
  }
  el.removeAttribute("data-theme");
}

export function useTheme(theme: Theme | undefined) {
  useEffect(() => {
    if (typeof document === "undefined") return;

    if (theme === "dark") {
      applyVars("dark");
      return;
    }

    if (theme === "light") {
      applyVars("light");
      return;
    }

    // Auto mode — follow Telegram's colorScheme, react to changes
    const apply = () => {
      const scheme = window.Telegram?.WebApp?.colorScheme;
      if (scheme) {
        applyVars(scheme);
      } else {
        clearVars(); // Let Telegram's own CSS variables take effect
      }
    };

    apply();
    window.Telegram?.WebApp?.onEvent?.("themeChanged", apply);
    return () => {
      window.Telegram?.WebApp?.offEvent?.("themeChanged", apply);
    };
  }, [theme]);
}
