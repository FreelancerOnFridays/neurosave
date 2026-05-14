"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import type { GhostStatus, Inquiry } from "@/lib/types";

export function useGhost() {
  const {
    data: status,
    error: statusError,
    isLoading: statusLoading,
    mutate: mutateStatus,
  } = useSWR<GhostStatus>("/api/ghost", api.ghost.status, {
    refreshInterval: 15_000,
  });

  const {
    data: inquiries,
    isLoading: inquiriesLoading,
    mutate: mutateInquiries,
  } = useSWR<Inquiry[]>("/api/ghost/inquiries", api.ghost.inquiries, {
    refreshInterval: 15_000,
  });

  const toggle = async (active: boolean, awayMessage?: string | null) => {
    const optimistic: GhostStatus = {
      is_active: active,
      away_message: awayMessage ?? status?.away_message ?? null,
      activated_at: active ? new Date().toISOString() : null,
    };
    await mutateStatus(
      async () => {
        const updated = await api.ghost.update({
          is_active: active,
          away_message: awayMessage,
        });
        return updated;
      },
      { optimisticData: optimistic, rollbackOnError: true }
    );
    await mutateInquiries();
  };

  const saveAwayMessage = async (msg: string) => {
    if (!status) return;
    await api.ghost.update({ is_active: status.is_active, away_message: msg });
    await mutateStatus();
  };

  return {
    status: status ?? { is_active: false, away_message: null, activated_at: null },
    inquiries: inquiries ?? [],
    isLoading: statusLoading || inquiriesLoading,
    error: statusError as Error | undefined,
    toggle,
    saveAwayMessage,
  };
}
