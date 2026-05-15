"use client";

import { motion } from "framer-motion";
import { useLang } from "@/contexts/LanguageContext";
import type { TodaySummary } from "@/lib/types";

interface TodaySummaryProps {
  summary: TodaySummary;
}

interface StatChipProps {
  label: string;
  count: number;
  color: string;
  delay: number;
}

function StatChip({ label, count, color, delay }: StatChipProps) {
  return (
    <motion.div
      className="flex-1 min-w-0 rounded-2xl p-3 flex flex-col items-center gap-1"
      style={{ backgroundColor: color }}
      initial={{ opacity: 0, y: 12, scale: 0.92 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay, type: "spring", stiffness: 400, damping: 28 }}
    >
      <motion.span
        className="text-2xl font-bold text-tg-text tabular-nums"
        initial={{ scale: 0.6 }}
        animate={{ scale: 1 }}
        transition={{ delay: delay + 0.05, type: "spring", stiffness: 500, damping: 20 }}
      >
        {count}
      </motion.span>
      <span className="text-[10px] font-medium text-tg-hint text-center leading-tight">{label}</span>
    </motion.div>
  );
}

export function TodaySummaryCard({ summary }: TodaySummaryProps) {
  const { t } = useLang();
  return (
    <div className="flex gap-2 mb-6">
      <StatChip label={t("today_summary_personal")} count={summary.personal_count} color="rgba(0,122,255,0.08)" delay={0} />
      <StatChip label={t("today_summary_delegated")} count={summary.delegated_count} color="rgba(52,199,89,0.08)" delay={0.05} />
      <StatChip label={t("today_summary_overdue")} count={summary.overdue_count} color="rgba(255,59,48,0.08)" delay={0.1} />
      <StatChip label={t("today_summary_reminders")} count={summary.with_reminders_count} color="rgba(142,142,147,0.08)" delay={0.15} />
    </div>
  );
}
