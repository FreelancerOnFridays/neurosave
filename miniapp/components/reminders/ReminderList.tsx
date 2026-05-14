"use client";

import { EmptyState } from "@/components/ui/EmptyState";
import { ReminderCard } from "./ReminderCard";
import { useLang } from "@/contexts/LanguageContext";
import type { Reminder } from "@/lib/types";

interface ReminderListProps {
  reminders: Reminder[];
  onDelete: (id: string) => void;
}

export function ReminderList({ reminders, onDelete }: ReminderListProps) {
  const { t } = useLang();

  if (reminders.length === 0) {
    return <EmptyState icon="✅" message={t("empty_reminders")} />;
  }
  return (
    <div className="flex flex-col gap-2">
      {reminders.map((r) => (
        <ReminderCard key={r.id} reminder={r} onDelete={onDelete} />
      ))}
    </div>
  );
}
