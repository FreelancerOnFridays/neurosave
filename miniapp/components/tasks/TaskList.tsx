"use client";

import { EmptyState } from "@/components/ui/EmptyState";
import { TaskCard } from "./TaskCard";
import { useLang } from "@/contexts/LanguageContext";
import type { Task } from "@/lib/types";

interface TaskListProps {
  tasks: Task[];
  onDone: (id: number) => void;
  onCancel: (id: number) => void;
  onNudge: (id: number) => void;
}

function Section({
  title,
  tasks,
  onDone,
  onCancel,
  onNudge,
}: { title: string; tasks: Task[] } & Omit<TaskListProps, "tasks">) {
  if (tasks.length === 0) return null;
  return (
    <div className="mb-5">
      <h2 className="text-xs font-semibold text-tg-hint uppercase tracking-wider mb-2">
        {title} ({tasks.length})
      </h2>
      <div className="flex flex-col gap-2">
        {tasks.map((t) => (
          <TaskCard key={t.id} task={t} onDone={onDone} onCancel={onCancel} onNudge={onNudge} />
        ))}
      </div>
    </div>
  );
}

function isOverdue(t: Task) {
  return t.status === "open" && t.deadline !== null && new Date(t.deadline) < new Date();
}

function isDueToday(t: Task) {
  if (!t.deadline || t.status !== "open") return false;
  const d = new Date(t.deadline);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate() &&
    !isOverdue(t)
  );
}

export function TaskList({ tasks, onDone, onCancel, onNudge }: TaskListProps) {
  const { t } = useLang();

  const overdue = tasks.filter(isOverdue);
  const today = tasks.filter(isDueToday);
  const upcoming = tasks.filter((t) => t.status === "open" && !isOverdue(t) && !isDueToday(t));
  const done = tasks.filter((t) => t.status !== "open");

  if (tasks.length === 0) {
    return <EmptyState icon="📌" message={t("empty_tasks")} />;
  }

  return (
    <div>
      <Section title={t("sec_overdue")} tasks={overdue} onDone={onDone} onCancel={onCancel} onNudge={onNudge} />
      <Section title={t("sec_today")} tasks={today} onDone={onDone} onCancel={onCancel} onNudge={onNudge} />
      <Section title={t("sec_upcoming")} tasks={upcoming} onDone={onDone} onCancel={onCancel} onNudge={onNudge} />
      <Section title={t("sec_done")} tasks={done} onDone={onDone} onCancel={onCancel} onNudge={onNudge} />
    </div>
  );
}
