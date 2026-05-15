"use client";

import { useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useLang } from "@/contexts/LanguageContext";

interface FilterBarProps {
  filterDate: string | null;
  onDateChange: (date: string | null) => void;
  hasReminder: boolean | null;
  onHasReminderChange: (v: boolean | null) => void;
  showReminderFilter?: boolean;
}

export function FilterBar({
  filterDate,
  onDateChange,
  hasReminder,
  onHasReminderChange,
  showReminderFilter = true,
}: FilterBarProps) {
  const { t } = useLang();
  const dateInputRef = useRef<HTMLInputElement>(null);

  const activeStyle = {
    background: "var(--tg-theme-button-color, #007aff)",
    color: "var(--tg-theme-button-text-color, #ffffff)",
  };
  const inactiveStyle = {
    background: "var(--tg-theme-secondary-bg-color, #f2f2f7)",
    color: "var(--tg-theme-hint-color, #8e8e93)",
  };

  return (
    <div className="flex gap-2 mb-4 flex-wrap">
      {/* Date filter chip — clicking opens native date picker */}
      <div className="relative">
        <button
          onClick={() => {
            if (filterDate) {
              onDateChange(null);
            } else {
              dateInputRef.current?.showPicker?.();
              dateInputRef.current?.click();
            }
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors"
          style={filterDate ? activeStyle : inactiveStyle}
        >
          <span>📅</span>
          {filterDate ? (
            <>
              <span>
                {new Date(filterDate + "T00:00:00").toLocaleDateString("ru-RU", {
                  day: "numeric",
                  month: "short",
                })}
              </span>
              <span
                className="ml-1 opacity-80"
                onClick={(e) => {
                  e.stopPropagation();
                  onDateChange(null);
                }}
              >
                ✕
              </span>
            </>
          ) : (
            <span>{t("tasks_filter_date")}</span>
          )}
        </button>
        <input
          ref={dateInputRef}
          type="date"
          className="absolute inset-0 opacity-0 w-full cursor-pointer"
          value={filterDate ?? ""}
          onChange={(e) => onDateChange(e.target.value || null)}
          tabIndex={-1}
        />
      </div>

      {/* Has reminder filter — only for personal tasks */}
      <AnimatePresence>
        {showReminderFilter && (
          <motion.button
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            onClick={() => onHasReminderChange(hasReminder ? null : true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors"
            style={hasReminder ? activeStyle : inactiveStyle}
          >
            <span>⏰</span>
            <span>{t("tasks_filter_reminders")}</span>
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}
