"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { PageHeader } from "@/components/layout/PageHeader";
import { SegmentedControl } from "@/components/tasks/SegmentedControl";
import { FilterBar } from "@/components/tasks/FilterBar";
import { SwipeAction } from "@/components/ui/SwipeAction";
import { TimePickerSheet } from "@/components/ui/TimePickerSheet";
import { StatusBadge } from "@/components/tasks/StatusBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { useTasks } from "@/hooks/useTasks";
import { useLang } from "@/contexts/LanguageContext";
import { openTgProfile } from "@/lib/telegram";
import type { Task } from "@/lib/types";

type TabMode = "personal" | "delegated";

function formatDeadline(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const today = now.toDateString() === d.toDateString();
  if (today) return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function isOverdue(iso: string | null): boolean {
  return !!iso && new Date(iso) < new Date();
}

interface TaskCardProps {
  task: Task;
  mode: TabMode;
  onDone: () => void;
  onCancel: () => void;
  onNudge: () => void;
  onDelete: () => void;
  onSetReminder?: (iso: string) => void;
  onDeleteReminder?: () => void;
}

function TaskCard({ task, mode, onDone, onCancel, onNudge, onDelete, onSetReminder, onDeleteReminder }: TaskCardProps) {
  const { t } = useLang();
  const [reminderSheet, setReminderSheet] = useState<"add" | "edit" | null>(null);
  const overdue = isOverdue(task.deadline);
  const hasReminder = !!task.reminder_time;
  const isOpen = task.status === "open";

  const swipeActions =
    mode === "personal"
      ? [
          {
            label: t("swipe_delete"),
            color: "var(--tg-theme-destructive-text-color, #ff3b30)",
            onClick: onDelete,
          },
          ...(isOpen
            ? [
                {
                  label: hasReminder ? t("swipe_edit_reminder") : t("swipe_add_reminder"),
                  color: "var(--tg-theme-link-color, #007aff)",
                  onClick: () => setReminderSheet(hasReminder ? "edit" : "add"),
                },
              ]
            : []),
        ]
      : [
          {
            label: t("swipe_delete"),
            color: "var(--tg-theme-destructive-text-color, #ff3b30)",
            onClick: onDelete,
          },
          ...(isOpen
            ? [
                {
                  label: t("swipe_remind"),
                  color: "var(--tg-theme-link-color, #007aff)",
                  onClick: onNudge,
                },
              ]
            : []),
        ];

  return (
    <>
      <SwipeAction actions={swipeActions}>
        <div className="bg-tg-secondary rounded-2xl p-4">
          <div className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-tg-text leading-snug">{task.description}</p>
              <div className="flex items-center flex-wrap gap-1.5 mt-1.5">
                {mode === "delegated" && (task.assignee_name || task.assignee_username) && (
                  task.assignee_username ? (
                    <button
                      onClick={(e) => { e.stopPropagation(); openTgProfile(task.assignee_username); }}
                      className="text-xs text-tg-accent underline underline-offset-2"
                    >
                      {task.assignee_name ?? `@${task.assignee_username}`}
                    </button>
                  ) : (
                    <span className="text-xs text-tg-hint">{task.assignee_name}</span>
                  )
                )}
                {task.deadline && (
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      overdue && isOpen
                        ? "bg-red-500/10 text-red-500"
                        : "bg-tg-hint/10 text-tg-hint"
                    }`}
                  >
                    {overdue && isOpen ? "🔴 " : "📅 "}{formatDeadline(task.deadline)}
                  </span>
                )}
                {task.reminder_time && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-tg-accent/10 text-tg-accent">
                    ⏰ {new Date(task.reminder_time).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                )}
              </div>
            </div>
            <StatusBadge status={task.status} />
          </div>

          {isOpen && (
            <div className="flex gap-2 mt-3">
              <button
                onClick={(e) => { e.stopPropagation(); onDone(); }}
                className="text-xs px-3 py-1.5 rounded-xl bg-team/10 text-team font-medium"
              >
                {t("task_done")}
              </button>
              {mode === "delegated" && (
                <button
                  onClick={(e) => { e.stopPropagation(); onNudge(); }}
                  className="text-xs px-3 py-1.5 rounded-xl bg-tg-accent/10 text-tg-accent font-medium"
                >
                  {t("task_nudge")}
                </button>
              )}
              <button
                onClick={(e) => { e.stopPropagation(); onCancel(); }}
                className="text-xs px-3 py-1.5 rounded-xl bg-tg-hint/10 text-tg-hint font-medium"
              >
                {t("task_cancel")}
              </button>
            </div>
          )}
        </div>
      </SwipeAction>

      {mode === "personal" && (
        <TimePickerSheet
          open={reminderSheet !== null}
          title={reminderSheet === "edit" ? t("reminder_edit_title") : t("reminder_add_title")}
          initialValue={task.reminder_time ?? undefined}
          onConfirm={(iso) => { setReminderSheet(null); onSetReminder?.(iso); }}
          onCancel={() => setReminderSheet(null)}
        />
      )}
    </>
  );
}

const listVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.04 } },
};
const itemVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 400, damping: 28 } },
};

export default function TasksPage() {
  const [tabIndex, setTabIndex] = useState(0);
  const [filterDate, setFilterDate] = useState<string | null>(null);
  const [hasReminder, setHasReminder] = useState<boolean | null>(null);

  const mode: TabMode = tabIndex === 0 ? "personal" : "delegated";

  const { tasks, isLoading, error, updateStatus, setReminder, deleteReminder, nudge, deleteTask } = useTasks({
    type: mode,
    has_reminder: (mode === "personal" && hasReminder === true) ? true : undefined,
    date: filterDate ?? undefined,
  });

  const { t } = useLang();

  const tabs = [t("tasks_my_tasks"), t("tasks_delegated_tasks")];

  if (isLoading) return <Spinner />;
  if (error) return <EmptyState icon="⚠️" message={`${t("error_loading")}: ${error.message}`} />;

  return (
    <div>
      <PageHeader title={`📌 ${t("tasks_subtitle")}`} />

      <SegmentedControl
        segments={tabs}
        activeIndex={tabIndex}
        onChange={(i) => {
          setTabIndex(i);
          setHasReminder(null);
          setFilterDate(null);
        }}
      />

      <FilterBar
        filterDate={filterDate}
        onDateChange={setFilterDate}
        hasReminder={hasReminder}
        onHasReminderChange={setHasReminder}
        showReminderFilter={mode === "personal"}
      />

      <AnimatePresence mode="wait">
        <motion.div
          key={mode}
          initial={{ opacity: 0, x: tabIndex === 0 ? -12 : 12 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: tabIndex === 0 ? 12 : -12 }}
          transition={{ duration: 0.18 }}
        >
          {tasks.length === 0 ? (
            <EmptyState icon={mode === "personal" ? "✅" : "📌"} message={t("empty_tasks")} />
          ) : (
            <motion.div
              className="flex flex-col gap-2"
              variants={listVariants}
              initial="hidden"
              animate="visible"
            >
              {tasks.map((task) => (
                <motion.div key={task.id} variants={itemVariants}>
                  <TaskCard
                    task={task}
                    mode={mode}
                    onDone={() => updateStatus(task.id, "done")}
                    onCancel={() => updateStatus(task.id, "cancelled")}
                    onNudge={() => nudge(task.id)}
                    onDelete={() => deleteTask(task.id)}
                    onSetReminder={mode === "personal" ? (iso) => setReminder(task.id, iso) : undefined}
                    onDeleteReminder={mode === "personal" ? () => deleteReminder(task.id) : undefined}
                  />
                </motion.div>
              ))}
            </motion.div>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
