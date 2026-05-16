"use client";

import { useEffect, useState } from "react";
import { setInitData } from "@/lib/api";

// Synchronous init so initData is available before any SWR hooks fire
if (typeof window !== "undefined") {
  const initData = window.Telegram?.WebApp?.initData ?? "";
  console.log("[TG] initData length:", initData.length, "| first 20 chars:", initData.slice(0, 20));
  if (initData) setInitData(initData);
}

export function useTelegram() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
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
