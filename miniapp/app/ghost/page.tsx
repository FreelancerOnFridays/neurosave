"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { PageHeader } from "@/components/layout/PageHeader";
import { GhostToggle } from "@/components/ghost/GhostToggle";
import { GhostExclusions } from "@/components/ghost/GhostExclusions";
import { InquiryList } from "@/components/ghost/InquiryList";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { Toggle } from "@/components/ui/Toggle";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { useGhost } from "@/hooks/useGhost";
import { useLang } from "@/contexts/LanguageContext";

function formatAutoOff(iso: string): string {
  try {
    const d = new Date(iso);
    const date = d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
    const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    return `${date}, ${time}`;
  } catch {
    return iso;
  }
}

function toDatetimeLocal(iso: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return "";
  }
}

export default function GhostPage() {
  const { status, inquiries, isLoading, error, toggle, saveAwayMessage, setSilentMode, generateReply, setExclusions, setAutoOff } = useGhost();
  const { t } = useLang();
  const [awayMsg, setAwayMsg] = useState<string>("");
  const [generating, setGenerating] = useState(false);
  const [savingAutoOff, setSavingAutoOff] = useState(false);
  const [editingAutoOff, setEditingAutoOff] = useState(false);
  const [autoOffDraft, setAutoOffDraft] = useState("");

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
        className="mt-2 rounded-2xl bg-tg-secondary overflow-hidden"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.22, type: "spring", stiffness: 400, damping: 28 }}
      >
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-sm text-tg-text">{t("ghost_auto_off_label")}</span>
          <div className="flex items-center gap-2">
            {status.auto_off_at && !editingAutoOff && (
              <button
                onClick={async () => {
                  setSavingAutoOff(true);
                  try { await setAutoOff(null); } finally { setSavingAutoOff(false); }
                }}
                disabled={savingAutoOff}
                className="text-xs text-red-400 px-2 py-1 rounded-lg bg-red-400/10"
              >
                {t("ghost_auto_off_clear")}
              </button>
            )}
            {!editingAutoOff && (
              <button
                onClick={() => {
                  setAutoOffDraft(toDatetimeLocal(status.auto_off_at));
                  setEditingAutoOff(true);
                }}
                className="text-xs font-medium px-3 py-1.5 rounded-xl"
                style={{
                  background: "var(--tg-theme-link-color, #007aff)20",
                  color: "var(--tg-theme-link-color, #007aff)",
                }}
              >
                {status.auto_off_at ? formatAutoOff(status.auto_off_at) : "＋ " + t("ghost_auto_off_not_set")}
              </button>
            )}
          </div>
        </div>
        {editingAutoOff && (
          <div className="px-4 pb-3 flex flex-col gap-2">
            <input
              type="datetime-local"
              value={autoOffDraft}
              onChange={(e) => setAutoOffDraft(e.target.value)}
              className="w-full rounded-xl bg-tg-bg text-tg-text text-sm px-3 py-2 outline-none border border-tg-hint/20 focus:border-tg-accent/40"
            />
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  if (!autoOffDraft) return;
                  setSavingAutoOff(true);
                  try {
                    const iso = new Date(autoOffDraft).toISOString();
                    await setAutoOff(iso);
                    setEditingAutoOff(false);
                  } finally {
                    setSavingAutoOff(false);
                  }
                }}
                disabled={savingAutoOff || !autoOffDraft}
                className="flex-1 text-sm font-medium py-2 rounded-xl"
                style={{
                  background: "var(--tg-theme-link-color, #007aff)",
                  color: "#fff",
                  opacity: savingAutoOff || !autoOffDraft ? 0.5 : 1,
                }}
              >
                {savingAutoOff ? "…" : t("reminder_confirm")}
              </button>
              <button
                onClick={() => setEditingAutoOff(false)}
                disabled={savingAutoOff}
                className="flex-1 text-sm font-medium py-2 rounded-xl bg-tg-hint/10 text-tg-hint"
              >
                {t("reminder_cancel")}
              </button>
            </div>
          </div>
        )}
      </motion.div>

      <motion.div
        className="mt-2 flex items-center justify-between px-4 py-3 rounded-2xl bg-tg-secondary"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 0.5, y: 0 }}
        transition={{ delay: 0.26, type: "spring", stiffness: 400, damping: 28 }}
      >
        <div className="flex items-center gap-2 flex-1 min-w-0 mr-3">
          <span className="text-sm text-tg-text">{t("ghost_ai_dialog_label")}</span>
          <InfoTooltip text={t("ghost_ai_dialog_tooltip")} />
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-tg-hint/15 text-tg-hint whitespace-nowrap">soon</span>
          <Toggle checked={false} onChange={() => {}} disabled />
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.26, type: "spring", stiffness: 400, damping: 28 }}
      >
        <GhostExclusions
          excludedContactIds={status.excluded_contact_ids}
          excludedLabels={status.excluded_labels}
          onUpdate={setExclusions}
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
