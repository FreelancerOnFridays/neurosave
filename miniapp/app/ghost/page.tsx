"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { PageHeader } from "@/components/layout/PageHeader";
import { GhostToggle } from "@/components/ghost/GhostToggle";
import { InquiryList } from "@/components/ghost/InquiryList";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { Toggle } from "@/components/ui/Toggle";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { useGhost } from "@/hooks/useGhost";
import { useLang } from "@/contexts/LanguageContext";

export default function GhostPage() {
  const { status, inquiries, isLoading, error, toggle, saveAwayMessage, setSilentMode, generateReply } = useGhost();
  const { t } = useLang();
  const [awayMsg, setAwayMsg] = useState<string>("");
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    if (status.away_message != null) setAwayMsg(status.away_message);
  }, [status.away_message]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const text = await generateReply();
      setAwayMsg(text);
      await saveAwayMessage(text);
    } finally {
      setGenerating(false);
    }
  };

  if (isLoading) return <Spinner />;
  if (error) return <EmptyState icon="⚠️" message={`${t("error_loading")}: ${error.message}`} />;

  return (
    <div>
      <PageHeader title={`👻 ${t("nav_ghost")}`} />

      <GhostToggle
        isActive={status.is_active}
        activatedAt={status.activated_at}
        onToggle={(active) => toggle(active, awayMsg || null)}
      />

      <motion.div
        className="mt-5"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1, type: "spring", stiffness: 400, damping: 28 }}
      >
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs font-semibold text-tg-hint uppercase tracking-wider">
            {t("ghost_away_label")}
          </label>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors"
            style={{
              background: "var(--tg-theme-link-color, #007aff)20",
              color: "var(--tg-theme-link-color, #007aff)",
            }}
          >
            {generating ? (
              <span className="inline-block animate-spin">⟳</span>
            ) : null}
            <span>{generating ? t("ghost_generating") : t("ghost_generate_btn")}</span>
          </button>
        </div>
        <textarea
          value={awayMsg}
          onChange={(e) => setAwayMsg(e.target.value)}
          onBlur={() => saveAwayMessage(awayMsg)}
          rows={3}
          placeholder="Сейчас занят, отвечу позже..."
          className="w-full rounded-2xl bg-tg-secondary text-tg-text text-sm p-3 resize-none outline-none border border-tg-hint/10 focus:border-tg-accent/40 placeholder:text-tg-hint"
        />
      </motion.div>

      <motion.div
        className="mt-4 flex items-center justify-between px-4 py-3 rounded-2xl bg-tg-secondary"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.18, type: "spring", stiffness: 400, damping: 28 }}
      >
        <div className="flex items-center gap-2">
          <span className="text-sm text-tg-text">{t("ghost_silent_label")}</span>
          <InfoTooltip text={t("ghost_silent_tooltip")} />
        </div>
        <Toggle
          checked={status.silent_mode}
          onChange={(v) => setSilentMode(v)}
        />
      </motion.div>

      <motion.div
        className="mt-6"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.26, type: "spring", stiffness: 400, damping: 28 }}
      >
        <h2 className="text-xs font-semibold text-tg-hint uppercase tracking-wider mb-3">
          {t("ghost_inquiries_section")} ({inquiries.length})
        </h2>
        <InquiryList inquiries={inquiries} />
      </motion.div>
    </div>
  );
}
