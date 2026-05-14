"use client";

import { useCallback, useRef } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { AppSettings } from "@/lib/types";

export function useSettings() {
  const { data, error, isLoading, mutate } = useSWR<AppSettings>(
    "/api/settings",
    api.settings.get
  );

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const update = useCallback(
    (patch: Partial<AppSettings>) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(async () => {
        await mutate(api.settings.update(patch), {
          optimisticData: data ? { ...data, ...patch } : undefined,
          rollbackOnError: true,
        });
      }, 500);
    },
    [data, mutate]
  );

  return {
    settings: data,
    isLoading,
    error,
    update,
  };
}
