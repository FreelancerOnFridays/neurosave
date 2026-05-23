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

  const defaultStatus: GhostStatus = {
    is_active: false,
    away_message: null,
    activated_at: null,
    silent_mode: false,
    auto_off_at: null,
    excluded_contact_ids: [],
    excluded_labels: [],
  };

  const toggle = async (active: boolean, awayMessage?: string | null) => {
    const optimistic: GhostStatus = {
      is_active: active,
      away_message: awayMessage ?? status?.away_message ?? null,
      activated_at: active ? new Date().toISOString() : null,
      silent_mode: status?.silent_mode ?? false,
      auto_off_at: status?.auto_off_at ?? null,
      excluded_contact_ids: status?.excluded_contact_ids ?? [],
      excluded_labels: status?.excluded_labels ?? [],
    };
    await mutateStatus(
      async () => {
        const updated = await api.ghost.update({
          is_active: active,
          away_message: awayMessage,
          silent_mode: status?.silent_mode ?? false,
        });
        return updated;
      },
      { optimisticData: optimistic, rollbackOnError: true }
    );
    await mutateInquiries();
  };

  const saveAwayMessage = async (msg: string) => {
    if (!status) return;
    await api.ghost.update({
      is_active: status.is_active,
      away_message: msg,
      silent_mode: status.silent_mode,
    });
    await mutateStatus();
  };

  const setSilentMode = async (silent: boolean) => {
    if (!status) {
      await api.ghost.update({ is_active: false, silent_mode: silent });
    } else {
      await api.ghost.setSilent(silent);
    }
    await mutateStatus();
  };

  const generateReply = async (): Promise<string> => {
    const res = await api.ghost.generateReply();
    return res.text;
  };

  const setExclusions = async (contact_ids: number[], labels: string[]) => {
    const updated = await api.ghost.setExclusions(contact_ids, labels);
    await mutateStatus(updated, false);
  };

  const setAutoOff = async (auto_off_at: string | null) => {
    const updated = await api.ghost.setAutoOff(auto_off_at);
    await mutateStatus(updated, false);
  };

  return {
    status: status ?? defaultStatus,
    inquiries: inquiries ?? [],
    isLoading: statusLoading || inquiriesLoading,
    error: statusError as Error | undefined,
    toggle,
    saveAwayMessage,
    setSilentMode,
    generateReply,
    setExclusions,
    setAutoOff,
  };
}
