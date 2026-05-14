"use client";

import { useLang } from "@/contexts/LanguageContext";
import type { TaskStatus } from "@/lib/types";

const CLASSES: Record<TaskStatus, string> = {
  open: "bg-tg-accent/15 text-tg-accent",
  done: "bg-team/15 text-team",
  cancelled: "bg-tg-hint/15 text-tg-hint",
};

const KEY: Record<TaskStatus, "status_open" | "status_done" | "status_cancelled"> = {
  open: "status_open",
  done: "status_done",
  cancelled: "status_cancelled",
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  const { t } = useLang();
  return (
    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${CLASSES[status]}`}>
      {t(KEY[status])}
    </span>
  );
}
