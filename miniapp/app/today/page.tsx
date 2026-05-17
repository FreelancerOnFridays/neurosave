"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import useSWR from "swr";
import { api } from "@/lib/api";
import { SwipeAction } from "@/components/ui/SwipeAction";
import { TimePickerSheet } from "@/components/ui/TimePickerSheet";
import { Spinner } from "@/components/ui/Spinner";
import { useTasks } from "@/hooks/useTasks";
import { useLang } from "@/contexts/LanguageContext";
import type { Task, CalendarEvent } from "@/lib/types";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Доброе утро";
  if (h < 18) return "Добрый день";
  return "Добрый вечер";
}

function todayStr(): string {
  return new Date().toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
}

function isToday(iso: string | null): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  const n = new Date();
  return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate();
}

function isOverdue(iso: string | null): boolean {
  return !!iso && new Date(iso) < new Date();
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

// ── Progress Ring ────────────────────────────────────────────────────────────

function ProgressRing({ done, total }: { done: number; total: number }) {
  const { t } = useLang();
  const r = 28;
  const circ = 2 * Math.PI * r;
  const pct = total === 0 ? 0 : Math.min(done / total, 1);
  const offset = circ * (1 - pct);

  return (
    <div className="flex flex-col items-center justify-center shrink-0 w-20">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle
          cx="36" cy="36" r={r}
          fill="none"
          stroke="var(--tg-theme-secondary-bg-color, #e5e5ea)"
          strokeWidth="5"
        />
        <circle
          cx="36" cy="36" r={r}
          fill="none"
          stroke="var(--tg-theme-button-color, #007aff)"
          strokeWidth="5"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 36 36)"
          style={{ transition: "stroke-dashoffset 0.5s ease" }}
        />
        <text
          x="36" y="33"
          textAnchor="middle"
          fill="var(--tg-theme-text-color, #000)"
          style={{ fontSize: 16, fontWeight: 700 }}
        >
          {done}
        </text>
        <text
          x="36" y="47"
          textAnchor="middle"
          fill="var(--tg-theme-hint-color, #8e8e93)"
          style={{ fontSize: 11 }}
        >
          из {total}
        </text>
      </svg>
      <p className="text-[10px] text-tg-hint mt-1 text-center">{t("today_progress_label")}</p>
    </div>
  );
}

// ── Priority Card ────────────────────────────────────────────────────────────

function PriorityItem({ task, onDone }: { task: Task; onDone: () => void }) {
  const overdue = isOverdue(task.deadline || task.reminder_time);
  const time = task.reminder_time || task.deadline;
  const borderColor = overdue ? "#ef4444" : "var(--tg-theme-button-color, #007aff)";

  return (
    <div className="flex items-center gap-2 py-1.5 pl-3 border-l-2" style={{ borderColor }}>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-tg-text truncate leading-tight">{task.description}</p>
        {time && (
          <p className="text-[10px] mt-0.5" style={{ color: overdue ? "#ef4444" : "var(--tg-theme-hint-color, #8e8e93)" }}>
            {fmtTime(time)}
          </p>
        )}
      </div>
      <button
        onClick={onDone}
        className="w-5 h-5 rounded-full border-2 border-tg-hint/30 flex-shrink-0 transition-colors hover:border-tg-accent/60"
      />
    </div>
  );
}

// ── Timeline Item ────────────────────────────────────────────────────────────

interface TimelineTaskProps {
  task: Task;
  timeStr: string;
  onDone: () => void;
  onDelete: () => void;
  onSetReminder: (iso: string) => void;
}

function TimelineTask({ task, timeStr, onDone, onDelete, onSetReminder }: TimelineTaskProps) {
  const { t } = useLang();
  const [reminderSheet, setReminderSheet] = useState(false);
  const overdue = task.status === "open" && isOverdue(task.deadline || task.reminder_time);
  const isDone = task.status === "done";

  return (
    <>
      <SwipeAction
        actions={[
          { label: t("swipe_delete"), color: "var(--tg-theme-destructive-text-color, #ff3b30)", onClick: onDelete },
          { label: t("swipe_add_reminder"), color: "var(--tg-theme-link-color, #007aff)", onClick: () => setReminderSheet(true) },
        ]}
      >
        <div className="flex items-center gap-3 py-2.5">
          <div
            className="text-right shrink-0 w-12"
            style={{ color: overdue ? "#ef4444" : "var(--tg-theme-hint-color, #8e8e93)" }}
          >
            <span className="text-xs font-medium">{timeStr}</span>
          </div>

          <div className="flex-1 min-w-0">
            <p
              className="text-sm text-tg-text leading-snug"
              style={{ textDecoration: isDone ? "line-through" : "none", opacity: isDone ? 0.5 : 1 }}
            >
              {task.description}
            </p>
            {task.is_personal ? null : (
              task.assignee_name && (
                <p className="text-xs text-tg-hint mt-0.5">{task.assignee_name}</p>
              )
            )}
          </div>

          {task.status === "open" && (
            <button
              onClick={onDone}
              className="w-6 h-6 rounded-full border-2 border-tg-hint/30 flex-shrink-0 transition-colors hover:border-tg-accent/60 flex items-center justify-center"
            />
          )}
          {isDone && (
            <span className="text-sm shrink-0">✅</span>
          )}
        </div>
      </SwipeAction>
      <TimePickerSheet
        open={reminderSheet}
        title={t("reminder_add_title")}
        onConfirm={(iso) => { setReminderSheet(false); onSetReminder(iso); }}
        onCancel={() => setReminderSheet(false)}
      />
    </>
  );
}

function TimelineCalendarEvent({ event, timeStr }: { event: CalendarEvent; timeStr: string }) {
  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className="text-right shrink-0 w-12">
        <span className="text-xs font-medium" style={{ color: "var(--tg-theme-hint-color, #8e8e93)" }}>{timeStr}</span>
      </div>
      <div
        className="flex-1 min-w-0 flex items-center gap-2 px-3 py-1.5 rounded-xl"
        style={{ background: "rgba(0, 122, 255, 0.08)" }}
      >
        <span className="text-sm">📅</span>
        <p className="text-sm text-tg-text truncate">{event.title}</p>
      </div>
    </div>
  );
}

// ── Untimed Task Card ────────────────────────────────────────────────────────

function UntimeTaskCard({ task, onDone, onDelete }: { task: Task; onDone: () => void; onDelete: () => void }) {
  const { t } = useLang();
  const isDone = task.status === "done";

  return (
    <SwipeAction
      actions={[
        { label: t("swipe_delete"), color: "var(--tg-theme-destructive-text-color, #ff3b30)", onClick: onDelete },
      ]}
    >
      <div className="flex items-center gap-3 py-2 px-3 rounded-xl bg-tg-secondary">
        <p
          className="flex-1 text-sm text-tg-text"
          style={{ textDecoration: isDone ? "line-through" : "none", opacity: isDone ? 0.5 : 1 }}
        >
          {task.description}
        </p>
        {task.status === "open" && (
          <button
            onClick={onDone}
            className="w-6 h-6 rounded-full border-2 border-tg-hint/30 flex-shrink-0"
          />
        )}
      </div>
    </SwipeAction>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

const itemVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 400, damping: 28 } },
};

export default function TodayPage() {
  const { tasks, isLoading, updateStatus, setReminder, deleteTask } = useTasks();
  const { t } = useLang();
  const [captureText, setCaptureText] = useState("");
  const [capturing, setCapturing] = useState(false);
  const captureRef = useRef<HTMLInputElement>(null);

  const { data: calEvents = [] } = useSWR<CalendarEvent[]>(
    "/api/integrations/calendar/today",
    api.integrations.calendarToday,
    { refreshInterval: 300_000 }
  );

  if (isLoading) return <Spinner />;

  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const todayEnd = todayStart + 86_400_000;

  function isForToday(t: Task): boolean {
    const ref = t.reminder_time || t.deadline;
    if (!ref) return false;
    const ms = new Date(ref).getTime();
    return ms >= todayStart && ms < todayEnd;
  }

  const todayTasks = tasks.filter((t) => isForToday(t) && t.status !== "cancelled");
  const doneTasks = todayTasks.filter((t) => t.status === "done");
  const openTimedTasks = todayTasks.filter((t) => t.status === "open" && (t.reminder_time || t.deadline));
  const untimedTasks = tasks.filter((t) => !t.reminder_time && !t.deadline && t.status === "open" && t.is_personal);

  const doneCount = doneTasks.length;
  const totalCount = todayTasks.length;

  // Priority: top 3 open tasks by nearest time
  const priority = [...openTimedTasks]
    .sort((a, b) => {
      const aT = new Date(a.reminder_time || a.deadline!).getTime();
      const bT = new Date(b.reminder_time || b.deadline!).getTime();
      return aT - bT;
    })
    .slice(0, 3);

  // Timeline: all today tasks + calendar events sorted by time
  type TimelineEntry =
    | { kind: "task"; task: Task; timeMs: number; timeStr: string }
    | { kind: "cal"; event: CalendarEvent; timeMs: number; timeStr: string };

  const timedItems: TimelineEntry[] = [
    ...todayTasks
      .filter((t) => t.reminder_time || t.deadline)
      .map((task): TimelineEntry => {
        const ref = task.reminder_time || task.deadline!;
        return { kind: "task", task, timeMs: new Date(ref).getTime(), timeStr: fmtTime(ref) };
      }),
    ...calEvents.map((ev): TimelineEntry => ({
      kind: "cal",
      event: ev,
      timeMs: new Date(ev.start).getTime(),
      timeStr: fmtTime(ev.start),
    })),
  ].sort((a, b) => a.timeMs - b.timeMs);

  async function handleCapture() {
    const text = captureText.trim();
    if (!text || capturing) return;
    setCapturing(true);
    try {
      await api.tasks.create({ description: text });
      setCaptureText("");
    } catch {
      // silently ignore
    } finally {
      setCapturing(false);
    }
  }

  return (
    <div className="flex flex-col min-h-screen pb-24 px-4">
      {/* Header */}
      <div className="pt-5 pb-3">
        <p className="text-xs text-tg-hint">{todayStr()}</p>
        <h1 className="text-2xl font-bold text-tg-text mt-0.5">{greeting()}</h1>
      </div>

      {/* Quick capture */}
      <div className="flex gap-2 mb-5">
        <input
          ref={captureRef}
          type="text"
          value={captureText}
          onChange={(e) => setCaptureText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleCapture()}
          placeholder={t("today_quick_capture_placeholder")}
          className="flex-1 px-4 py-2.5 text-sm rounded-2xl border border-tg-hint/20 bg-tg-secondary text-tg-text outline-none focus:border-tg-accent/40 transition-colors"
        />
        <button
          onClick={handleCapture}
          disabled={!captureText.trim() || capturing}
          className="w-10 h-10 rounded-2xl flex items-center justify-center text-lg font-bold transition-opacity disabled:opacity-30"
          style={{
            background: "var(--tg-theme-button-color, #007aff)",
            color: "var(--tg-theme-button-text-color, #fff)",
          }}
        >
          +
        </button>
      </div>

      {/* Progress + Priority */}
      {totalCount > 0 && (
        <div className="flex gap-4 mb-5 items-start">
          <ProgressRing done={doneCount} total={totalCount} />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-tg-hint uppercase tracking-wider mb-2">
              {t("today_priority_section")}
            </p>
            {priority.length === 0 ? (
              <p className="text-xs text-tg-hint">{t("today_all_done")}</p>
            ) : (
              <div className="space-y-2">
                {priority.map((task) => (
                  <PriorityItem
                    key={task.id}
                    task={task}
                    onDone={() => updateStatus(task.id, "done")}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Timeline */}
      {timedItems.length > 0 && (
        <div className="mb-4">
          <p className="text-xs font-semibold text-tg-hint uppercase tracking-wider mb-1">
            {t("today_timeline_section")}
          </p>
          <div className="divide-y divide-tg-hint/10">
            <AnimatePresence>
              {timedItems.map((item, idx) => (
                <motion.div
                  key={item.kind === "task" ? `task-${item.task.id}` : `cal-${item.event.id}-${idx}`}
                  variants={itemVariants}
                  initial="hidden"
                  animate="visible"
                >
                  {item.kind === "task" ? (
                    <TimelineTask
                      task={item.task}
                      timeStr={item.timeStr}
                      onDone={() => updateStatus(item.task.id, "done")}
                      onDelete={() => deleteTask(item.task.id)}
                      onSetReminder={(iso) => setReminder(item.task.id, iso)}
                    />
                  ) : (
                    <TimelineCalendarEvent event={item.event} timeStr={item.timeStr} />
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Untimemed personal tasks */}
      {untimedTasks.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-tg-hint uppercase tracking-wider mb-2">
            {t("today_anytime_group")}
          </p>
          <div className="space-y-2">
            {untimedTasks.map((task) => (
              <UntimeTaskCard
                key={task.id}
                task={task}
                onDone={() => updateStatus(task.id, "done")}
                onDelete={() => deleteTask(task.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {timedItems.length === 0 && untimedTasks.length === 0 && totalCount === 0 && (
        <div className="flex flex-col items-center justify-center flex-1 text-center pt-12">
          <p className="text-4xl mb-3">✅</p>
          <p className="text-sm text-tg-hint">{t("empty_tasks")}</p>
        </div>
      )}
    </div>
  );
}
