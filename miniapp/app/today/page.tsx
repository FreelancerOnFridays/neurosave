"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { PageHeader } from "@/components/layout/PageHeader";
import { TodaySummaryCard } from "@/components/today/TodaySummary";
import { SwipeAction } from "@/components/ui/SwipeAction";
import { TimePickerSheet } from "@/components/ui/TimePickerSheet";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { useTasks } from "@/hooks/useTasks";
import { useLang } from "@/contexts/LanguageContext";
import { openTgProfile } from "@/lib/telegram";
import type { Task, TodaySummary } from "@/lib/types";

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

function isOverdue(iso: string | null): boolean {
  if (!iso) return false;
  return new Date(iso) < new Date();
}

function formatTime(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

interface PersonalTaskCardProps {
  task: Task;
  onDone: () => void;
  onDelete: () => void;
  onSetReminder: (time: string) => void;
  onDeleteReminder: () => void;
}

function PersonalTaskCard({ task, onDone, onDelete, onSetReminder, onDeleteReminder }: PersonalTaskCardProps) {
  const { t } = useLang();
  const [reminderSheet, setReminderSheet] = useState<"add" | "edit" | null>(null);
  const hasReminder = !!task.reminder_time;

  const actions = [
    {
      label: t("swipe_delete"),
      color: "var(--tg-theme-destructive-text-color, #ff3b30)",
      onClick: onDelete,
    },
    {
      label: hasReminder ? t("swipe_edit_reminder") : t("swipe_add_reminder"),
      color: "var(--tg-theme-link-color, #007aff)",
      onClick: () => setReminderSheet(hasReminder ? "edit" : "add"),
    },
  ];

  return (
    <>
      <SwipeAction actions={actions}>
        <div className="bg-tg-secondary rounded-2xl p-4">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-medium text-tg-text flex-1">{task.description}</p>
            <button
              onClick={onDone}
              className="w-6 h-6 rounded-full border-2 border-tg-hint/30 flex items-center justify-center flex-shrink-0 hover:border-tg-accent/60 transition-colors"
            />
          </div>
          {(task.deadline || task.reminder_time) && (
            <div className="flex items-center gap-2 mt-2">
              {task.deadline && (
                <span className="text-xs text-tg-hint">
                  📅 {formatTime(task.deadline)}
                </span>
              )}
              {task.reminder_time && (
                <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-tg-accent/10 text-tg-accent">
                  ⏰ {formatTime(task.reminder_time)}
                </span>
              )}
            </div>
          )}
        </div>
      </SwipeAction>

      <TimePickerSheet
        open={reminderSheet !== null}
        title={reminderSheet === "edit" ? t("reminder_edit_title") : t("reminder_add_title")}
        initialValue={task.reminder_time ?? undefined}
        onConfirm={(iso) => { setReminderSheet(null); onSetReminder(iso); }}
        onCancel={() => setReminderSheet(null)}
      />
    </>
  );
}

interface DelegatedTaskCardProps {
  task: Task;
  onDelete: () => void;
  onNudge: () => void;
}

function DelegatedTaskCard({ task, onDelete, onNudge }: DelegatedTaskCardProps) {
  const { t } = useLang();
  const overdue = isOverdue(task.deadline);

  const actions = [
    {
      label: t("swipe_delete"),
      color: "var(--tg-theme-destructive-text-color, #ff3b30)",
      onClick: onDelete,
    },
    {
      label: t("swipe_remind"),
      color: "var(--tg-theme-link-color, #007aff)",
      onClick: onNudge,
    },
  ];

  return (
    <SwipeAction actions={actions}>
      <div
        className="bg-tg-secondary rounded-2xl p-4 cursor-pointer"
        onClick={() => task.assignee_username && openTgProfile(task.assignee_username)}
      >
        <p className="text-sm font-medium text-tg-text">{task.description}</p>
        <div className="flex items-center gap-2 mt-1.5">
          {task.assignee_name && (
            <span className="text-xs text-tg-hint">{task.assignee_name}</span>
          )}
          {task.deadline && (
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${
                overdue
                  ? "bg-red-500/10 text-red-500"
                  : "bg-tg-accent/10 text-tg-accent"
              }`}
            >
              {formatTime(task.deadline)}
            </span>
          )}
        </div>
      </div>
    </SwipeAction>
  );
}

const listVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};
const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 400, damping: 28 } },
};

export default function TodayPage() {
  const { tasks, isLoading, error, updateStatus, setReminder, deleteReminder, nudge, deleteTask } = useTasks();
  const { t } = useLang();

  if (isLoading) return <Spinner />;
  if (error) return <EmptyState icon="⚠️" message={`${t("error_loading")}: ${error.message}`} />;

  const now = new Date();
  const personalToday = tasks.filter(
    (t) => t.is_personal && t.status === "open" && isToday(t.deadline || t.reminder_time)
  );
  const delegatedToday = tasks.filter(
    (t) => !t.is_personal && t.status === "open" && isToday(t.deadline)
  );

  const summary: TodaySummary = {
    personal_count: personalToday.length,
    delegated_count: delegatedToday.length,
    overdue_count: tasks.filter(
      (t) => t.status === "open" && t.deadline && new Date(t.deadline) < now
    ).length,
    with_reminders_count: tasks.filter(
      (t) => t.status === "open" && !!t.reminder_time
    ).length,
  };

  return (
    <div>
      <PageHeader title={`📅 ${todayStr()}`} />

      <TodaySummaryCard summary={summary} />

      <section className="mb-6">
        <h2 className="text-xs font-semibold text-tg-hint uppercase tracking-wider mb-3">
          {t("today_my_section")} ({personalToday.length})
        </h2>
        {personalToday.length === 0 ? (
          <EmptyState icon="✅" message={t("empty_tasks")} />
        ) : (
          <motion.div
            className="flex flex-col gap-2"
            variants={listVariants}
            initial="hidden"
            animate="visible"
          >
            {personalToday.map((task) => (
              <motion.div key={task.id} variants={itemVariants}>
                <PersonalTaskCard
                  task={task}
                  onDone={() => updateStatus(task.id, "done")}
                  onDelete={() => deleteTask(task.id)}
                  onSetReminder={(iso) => setReminder(task.id, iso)}
                  onDeleteReminder={() => deleteReminder(task.id)}
                />
              </motion.div>
            ))}
          </motion.div>
        )}
      </section>

      <section>
        <h2 className="text-xs font-semibold text-tg-hint uppercase tracking-wider mb-3">
          {t("today_delegated_section")} ({delegatedToday.length})
        </h2>
        {delegatedToday.length === 0 ? (
          <EmptyState icon="📌" message={t("empty_tasks")} />
        ) : (
          <motion.div
            className="flex flex-col gap-2"
            variants={listVariants}
            initial="hidden"
            animate="visible"
          >
            {delegatedToday.map((task) => (
              <motion.div key={task.id} variants={itemVariants}>
                <DelegatedTaskCard
                  task={task}
                  onDelete={() => deleteTask(task.id)}
                  onNudge={() => nudge(task.id)}
                />
              </motion.div>
            ))}
          </motion.div>
        )}
      </section>
    </div>
  );
}
