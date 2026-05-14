import { Card } from "@/components/ui/Card";
import { SwipeAction } from "@/components/ui/SwipeAction";
import type { Reminder } from "@/lib/types";

interface ReminderCardProps {
  reminder: Reminder;
  onDelete: (id: string) => void;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function ReminderCard({ reminder, onDelete }: ReminderCardProps) {
  const timeStr = formatTime(reminder.reminder_time_iso);

  return (
    <SwipeAction onDelete={() => onDelete(reminder.id)}>
      <Card>
        <div className="flex items-center justify-between gap-3">
          <p className="text-tg-text text-sm font-medium leading-snug flex-1">
            {reminder.reminder_text}
          </p>
          <div className="flex flex-col items-end shrink-0 gap-0.5">
            {timeStr && (
              <span className="text-xs font-semibold text-tg-accent bg-tg-accent/10 px-2 py-0.5 rounded-full">
                {timeStr}
              </span>
            )}
            {reminder.lead_description && (
              <span className="text-[10px] text-tg-hint">
                {reminder.lead_description}
              </span>
            )}
          </div>
        </div>
      </Card>
    </SwipeAction>
  );
}
