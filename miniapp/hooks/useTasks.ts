"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import type { Task, TaskStatus } from "@/lib/types";

interface TaskFilters {
  type?: "personal" | "delegated" | "all";
  has_reminder?: boolean;
  date?: string;
}

export function useTasks(filters?: TaskFilters) {
  const params = {
    type: filters?.type,
    has_reminder: filters?.has_reminder,
    date: filters?.date,
  };
  const key = `/api/tasks?${JSON.stringify(params)}`;

  const { data, error, isLoading, mutate } = useSWR<Task[]>(
    key,
    () => api.tasks.list(params),
    { refreshInterval: 30_000 }
  );

  const updateStatus = async (id: number, status: TaskStatus) => {
    const optimistic = (data ?? []).map((t) =>
      t.id === id ? { ...t, status } : t
    );
    await mutate(
      async () => {
        const updated = await api.tasks.updateStatus(id, status);
        return (data ?? []).map((t) => (t.id === id ? updated : t));
      },
      { optimisticData: optimistic, rollbackOnError: true }
    );
  };

  const setReminder = async (id: number, reminder_time: string | null) => {
    const updated = await api.tasks.setReminder(id, reminder_time);
    await mutate(
      (data ?? []).map((t) => (t.id === id ? updated : t)),
      false
    );
  };

  const deleteReminder = async (id: number) => {
    const updated = await api.tasks.deleteReminder(id);
    await mutate(
      (data ?? []).map((t) => (t.id === id ? updated : t)),
      false
    );
  };

  const nudge = async (id: number) => {
    await api.tasks.nudge(id);
  };

  const deleteTask = async (id: number) => {
    await api.tasks.delete(id);
    await mutate(
      (data ?? []).filter((t) => t.id !== id),
      false
    );
  };

  return {
    tasks: data ?? [],
    isLoading,
    error,
    updateStatus,
    setReminder,
    deleteReminder,
    nudge,
    deleteTask,
  };
}
