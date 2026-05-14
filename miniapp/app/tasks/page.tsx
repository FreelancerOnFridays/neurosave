"use client";

import { PageHeader } from "@/components/layout/PageHeader";
import { TaskList } from "@/components/tasks/TaskList";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { useTasks } from "@/hooks/useTasks";
import { useLang } from "@/contexts/LanguageContext";

export default function TasksPage() {
  const { tasks, isLoading, error, updateStatus, nudge } = useTasks();
  const { t } = useLang();

  if (isLoading) return <Spinner />;
  if (error) return <EmptyState icon="⚠️" message={`${t("error_loading")}: ${error.message}`} />;

  return (
    <div>
      <PageHeader title="📌 Задачи" subtitle={t("tasks_subtitle")} />
      <TaskList
        tasks={tasks}
        onDone={(id) => updateStatus(id, "done")}
        onCancel={(id) => updateStatus(id, "cancelled")}
        onNudge={nudge}
      />
    </div>
  );
}
