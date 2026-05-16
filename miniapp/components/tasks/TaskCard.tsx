"use client";

import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "./StatusBadge";
import { useLang } from "@/contexts/LanguageContext";
import { openTgProfile } from "@/lib/telegram";
import type { Task } from "@/lib/types";

interface TaskCardProps {
  task: Task;
  onDone: (id: number) => void;
  onCancel: (id: number) => void;
  onNudge: (id: number) => void;
}

function deadlineBadge(deadline: string | null): {
  label: string;
  classes: string;
} | null {
  if (!deadline) return null;
  const d = new Date(deadline);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const dDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = dDay.getTime() - today.getTime();
  const label = d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  if (diff < 0)
    return { label, classes: "bg-tg-destructive/15 text-tg-destructive" };
  if (diff === 0)
    return {
      label: `${d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`,
      classes: "bg-urgent/15 text-urgent",
    };
  return { label, classes: "bg-tg-hint/10 text-tg-hint" };
}


export function TaskCard({ task, onDone, onCancel, onNudge }: TaskCardProps) {
  const [expanded, setExpanded] = useState(false);
  const { t } = useLang();
  const badge = deadlineBadge(task.deadline);

  return (
    <Card>
      <div
        className="flex items-start justify-between gap-2 cursor-pointer"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="flex-1 min-w-0">
          <p className="text-tg-text text-sm font-medium leading-snug">
            {task.description}
          </p>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            {task.assignee_username ? (
              <button
                onClick={(e) => { e.stopPropagation(); openTgProfile(task.assignee_username); }}
                className="text-xs text-tg-accent underline underline-offset-2"
              >
                → {task.assignee_name ?? `@${task.assignee_username}`}
              </button>
            ) : task.assignee_name ? (
              <p className="text-xs text-tg-hint">→ {task.assignee_name}</p>
            ) : null}
            {task.team_label && (
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-tg-accent/10 text-tg-accent leading-none">
                {task.team_label}
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end shrink-0 gap-1">
          <StatusBadge status={task.status} />
          {badge && (
            <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${badge.classes}`}>
              {badge.label}
            </span>
          )}
        </div>
      </div>

      {expanded && task.status === "open" && (
        <div className="flex gap-2 mt-3 pt-3 border-t border-tg-hint/10">
          <button
            onClick={() => onDone(task.id)}
            className="flex-1 text-xs font-medium py-1.5 rounded-xl bg-team/15 text-team"
          >
            {t("task_done")}
          </button>
          <button
            onClick={() => onNudge(task.id)}
            className="flex-1 text-xs font-medium py-1.5 rounded-xl bg-tg-accent/10 text-tg-accent"
          >
            {t("task_nudge")}
          </button>
          <button
            onClick={() => onCancel(task.id)}
            className="flex-1 text-xs font-medium py-1.5 rounded-xl bg-tg-hint/10 text-tg-hint"
          >
            {t("task_cancel")}
          </button>
        </div>
      )}
    </Card>
  );
}
