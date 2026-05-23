"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import useSWR from "swr";
import { PageHeader } from "@/components/layout/PageHeader";
import { SegmentedControl } from "@/components/tasks/SegmentedControl";
import { FilterBar } from "@/components/tasks/FilterBar";
import { SwipeAction } from "@/components/ui/SwipeAction";
import { TimePickerSheet } from "@/components/ui/TimePickerSheet";
import { NudgePreviewSheet } from "@/components/tasks/NudgePreviewSheet";
import { StatusBadge } from "@/components/tasks/StatusBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { useTasks } from "@/hooks/useTasks";
import { useLang } from "@/contexts/LanguageContext";
import { openTgProfile } from "@/lib/telegram";
import { api } from "@/lib/api";
import type { Task } from "@/lib/types";

type TabMode = "personal" | "delegated";

function isDateOnly(iso: string): boolean {
  const d = new Date(iso);
  return d.getUTCHours() === 0 && d.getUTCMinutes() === 0 && d.getUTCSeconds() === 0;
}

function formatDeadlineLabel(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const today = now.toDateString() === d.toDateString();
  if (isDateOnly(iso)) {
    return today ? "сегодня" : d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  }
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  return today ? `до ${time} сегодня` : `${d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}, ${time}`;
}

function isOverdue(iso: string | null): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  if (isDateOnly(iso)) {
    const today = new Date();
    const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const deadlineStart = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    return deadlineStart < todayStart;
  }
  return d < new Date();
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
  nudgeLoading?: boolean;
}

function TaskCard({ task, mode, onDone, onCancel, onNudge, onDelete, onSetReminder, onDeleteReminder, nudgeLoading }: TaskCardProps) {
  const { t } = useLang();
  const [reminderSheet, setReminderSheet] = useState<"add" | "edit" | null>(null);
  const overdue = isOverdue(task.deadline);
  const hasReminder = !!task.reminder_time;
  const isOpen = task.status === "open";
  const reminderFuture = !!task.reminder_time && new Date(task.reminder_time) > new Date();

  const accentStrip =
    task.status === "done"
      ? "bg-team"
      : task.status !== "open"
      ? "bg-tg-hint/30"
      : overdue
      ? "bg-tg-destructive"
      : "bg-tg-accent";

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
        <div className="bg-tg-secondary rounded-2xl overflow-hidden flex">
          <div className={`w-1 shrink-0 ${accentStrip}`} />
          <div className="flex-1 p-4 min-w-0">
            <div className="flex items-start gap-2">
              <p className="flex-1 text-sm font-semibold text-tg-text leading-snug">{task.description}</p>
              <StatusBadge status={task.status} />
            </div>

            <div className="flex flex-col gap-0.5 mt-1.5">
              {mode === "delegated" && (task.assignee_name || task.assignee_username) && (
                task.assignee_username ? (
                  <button
                    onClick={(e) => { e.stopPropagation(); openTgProfile(task.assignee_username); }}
                    className="text-xs text-tg-accent underline underline-offset-2 self-start"
                  >
                    {task.assignee_name ?? `@${task.assignee_username}`}
                  </button>
                ) : (
                  <span className="text-xs text-tg-hint">{task.assignee_name}</span>
                )
              )}
              {task.deadline && (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs leading-none">📅</span>
                  <span className={`text-xs font-medium ${overdue && isOpen ? "text-tg-destructive" : "text-tg-hint"}`}>
                    Дедлайн:
                  </span>
                  <span className={`text-xs ${overdue && isOpen ? "text-tg-destructive" : "text-tg-hint"}`}>
                    {formatDeadlineLabel(task.deadline)}
                  </span>
                  {overdue && isOpen && (
                    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-md bg-tg-destructive/15 text-tg-destructive leading-none">
                      Просрочено
                    </span>
                  )}
                </div>
              )}
              {reminderFuture && (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs leading-none">⏰</span>
                  <span className="text-xs font-medium text-tg-accent">Напомню:</span>
                  <span className="text-xs text-tg-accent">
                    {new Date(task.reminder_time!).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
              )}
            </div>

            {isOpen && (
              <div className="flex gap-1.5 mt-3">
                <button
                  onClick={(e) => { e.stopPropagation(); onDone(); }}
                  className="flex-1 text-xs py-2 rounded-xl bg-team/10 text-team font-semibold"
                >
                  {t("task_done")}
                </button>
                {mode === "delegated" && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onNudge(); }}
                    disabled={nudgeLoading}
                    className="text-xs px-4 py-2 rounded-xl bg-tg-accent/10 text-tg-accent font-semibold disabled:opacity-50"
                  >
                    {nudgeLoading ? "…" : "🔔"}
                  </button>
                )}
                <button
                  onClick={(e) => { e.stopPropagation(); onCancel(); }}
                  className="text-xs px-4 py-2 rounded-xl bg-tg-hint/10 text-tg-hint font-semibold"
                >
                  ✕
                </button>
              </div>
            )}
          </div>
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
  const [activeLabel, setActiveLabel] = useState<string | null>(null);
  const [nudgeSheet, setNudgeSheet] = useState<{ task: Task; text: string } | null>(null);
  const [nudgeLoadingId, setNudgeLoadingId] = useState<number | null>(null);

  const mode: TabMode = tabIndex === 0 ? "personal" : "delegated";

  const { tasks: rawTasks, isLoading, error, updateStatus, setReminder, deleteReminder, nudge, deleteTask } = useTasks({
    type: mode,
    has_reminder: (mode === "personal" && hasReminder === true) ? true : undefined,
    date: filterDate ?? undefined,
  });

  const handleNudgeClick = async (task: Task) => {
    setNudgeLoadingId(task.id);
    try {
      const { text } = await api.tasks.nudgePreview(task.id);
      setNudgeSheet({ task, text });
    } catch {
      // fallback: send immediately without preview
      await nudge(task.id);
    } finally {
      setNudgeLoadingId(null);
    }
  };

  const handleNudgeSend = async (text: string) => {
    if (!nudgeSheet) return;
    await api.tasks.nudge(nudgeSheet.task.id, text);
    setNudgeSheet(null);
  };

  const { data: allLabels = [] } = useSWR<string[]>("/api/contacts/labels", api.contacts.getLabels);

  // Filter by label (only meaningful for delegated tasks with team_label)
  const tasks = activeLabel
    ? rawTasks.filter((t) => t.team_label === activeLabel)
    : rawTasks;

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
          setActiveLabel(null);
        }}
      />

      <FilterBar
        filterDate={filterDate}
        onDateChange={setFilterDate}
        hasReminder={hasReminder}
        onHasReminderChange={setHasReminder}
        showReminderFilter={mode === "personal"}
      />

      {/* Label filter — shown for delegated tab when labels exist */}
      {mode === "delegated" && allLabels.length > 0 && (
        <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
          <button
            onClick={() => setActiveLabel(null)}
            className="text-xs px-3 py-1.5 rounded-full whitespace-nowrap shrink-0 transition-colors"
            style={
              !activeLabel
                ? { background: "var(--tg-theme-button-color,#007aff)", color: "var(--tg-theme-button-text-color,#fff)" }
                : { background: "var(--tg-theme-secondary-bg-color,#f2f2f7)", color: "var(--tg-theme-hint-color,#8e8e93)" }
            }
          >
            {t("labels_filter")}
          </button>
          {allLabels.map((label) => (
            <button
              key={label}
              onClick={() => setActiveLabel(activeLabel === label ? null : label)}
              className="text-xs px-3 py-1.5 rounded-full whitespace-nowrap shrink-0 transition-colors"
              style={
                activeLabel === label
                  ? { background: "var(--tg-theme-button-color,#007aff)", color: "var(--tg-theme-button-text-color,#fff)" }
                  : { background: "var(--tg-theme-secondary-bg-color,#f2f2f7)", color: "var(--tg-theme-hint-color,#8e8e93)" }
              }
            >
              {label}
            </button>
          ))}
        </div>
      )}

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
                    onNudge={() => handleNudgeClick(task)}
                    onDelete={() => deleteTask(task.id)}
                    onSetReminder={mode === "personal" ? (iso) => setReminder(task.id, iso) : undefined}
                    onDeleteReminder={mode === "personal" ? () => deleteReminder(task.id) : undefined}
                    nudgeLoading={nudgeLoadingId === task.id}
                  />
                </motion.div>
              ))}
            </motion.div>
          )}
        </motion.div>
      </AnimatePresence>

      <NudgePreviewSheet
        task={nudgeSheet}
        onClose={() => setNudgeSheet(null)}
        onSend={handleNudgeSend}
      />
    </div>
  );
}
