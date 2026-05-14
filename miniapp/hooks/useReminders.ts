"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import type { Reminder, ReminderCreate } from "@/lib/types";

export function useReminders() {
  const { data, error, isLoading, mutate } = useSWR<Reminder[]>(
    "/api/reminders",
    api.reminders.list,
    { refreshInterval: 30_000 }
  );

  const deleteReminder = async (id: string) => {
    const optimistic = (data ?? []).filter((r) => r.id !== id);
    await mutate(
      async () => {
        await api.reminders.delete(id);
        return optimistic;
      },
      { optimisticData: optimistic, rollbackOnError: true }
    );
  };

  const createReminder = async (body: ReminderCreate) => {
    await api.reminders.create(body);
    await mutate();
  };

  return {
    reminders: data ?? [],
    isLoading,
    error,
    deleteReminder,
    createReminder,
  };
}
