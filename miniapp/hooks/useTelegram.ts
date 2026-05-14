"use client";

import { useEffect, useState } from "react";
import { setInitData } from "@/lib/api";

export function useTelegram() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    // @ts-expect-error - Telegram injects this global
    const WebApp = window.Telegram?.WebApp;
    if (!WebApp) {
      setReady(true);
      return;
    }
    WebApp.ready();
    WebApp.expand();
    setInitData(WebApp.initData ?? "");
    setReady(true);
  }, []);

  return { ready };
}
