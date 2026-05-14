"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import type { Task, TaskStatus } from "@/lib/types";

export function useTasks() {
  const { data, error, isLoading, mutate } = useSWR<Task[]>(
    "/api/tasks",
    api.tasks.list,
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

  const nudge = async (id: number) => {
    await api.tasks.nudge(id);
  };

  return { tasks: data ?? [], isLoading, error, updateStatus, nudge };
}
