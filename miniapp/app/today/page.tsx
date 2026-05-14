"use client";

import { PageHeader } from "@/components/layout/PageHeader";
import { ReminderList } from "@/components/reminders/ReminderList";
import { TaskList } from "@/components/tasks/TaskList";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { useReminders } from "@/hooks/useReminders";
import { useTasks } from "@/hooks/useTasks";
import { useLang } from "@/contexts/LanguageContext";

function todayStr() {
  return new Date().toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

function isToday(iso: string | null): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

export default function TodayPage() {
  const { reminders, isLoading: rLoading, error: rError, deleteReminder } = useReminders();
  const { tasks, isLoading: tLoading, error: tError, updateStatus, nudge } = useTasks();
  const { t } = useLang();

  if (rLoading || tLoading) return <Spinner />;
  if (rError || tError) {
    const msg = (rError ?? tError)?.message ?? "";
    return <EmptyState icon="⚠️" message={`${t("error_loading")}: ${msg}`} />;
  }

  const todayReminders = reminders.filter((r) => isToday(r.reminder_time_iso));
  const todayTasks = tasks.filter((t) => t.status === "open" && isToday(t.deadline));

  return (
    <div>
      <PageHeader title={`📅 ${todayStr()}`} />

      <section className="mb-6">
        <h2 className="text-xs font-semibold text-tg-hint uppercase tracking-wider mb-3">
          {t("today_reminders_section")} ({todayReminders.length})
        </h2>
        <ReminderList reminders={todayReminders} onDelete={deleteReminder} />
      </section>

      <section>
        <h2 className="text-xs font-semibold text-tg-hint uppercase tracking-wider mb-3">
          {t("today_delegated_section")} ({todayTasks.length})
        </h2>
        <TaskList
          tasks={todayTasks}
          onDone={(id) => updateStatus(id, "done")}
          onCancel={(id) => updateStatus(id, "cancelled")}
          onNudge={nudge}
        />
      </section>
    </div>
  );
}
