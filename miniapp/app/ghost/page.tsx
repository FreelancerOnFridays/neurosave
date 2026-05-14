"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { GhostToggle } from "@/components/ghost/GhostToggle";
import { InquiryList } from "@/components/ghost/InquiryList";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { useGhost } from "@/hooks/useGhost";
import { useLang } from "@/contexts/LanguageContext";

export default function GhostPage() {
  const { status, inquiries, isLoading, error, toggle, saveAwayMessage } = useGhost();
  const { t } = useLang();
  const [awayMsg, setAwayMsg] = useState<string>("");

  useEffect(() => {
    if (status.away_message != null) setAwayMsg(status.away_message);
  }, [status.away_message]);

  if (isLoading) return <Spinner />;
  if (error) return <EmptyState icon="⚠️" message={`${t("error_loading")}: ${error.message}`} />;

  return (
    <div>
      <PageHeader title="👻 Ghost" />

      <GhostToggle
        isActive={status.is_active}
        activatedAt={status.activated_at}
        onToggle={(active) => toggle(active, awayMsg || null)}
      />

      <div className="mt-5">
        <label className="block text-xs font-semibold text-tg-hint uppercase tracking-wider mb-2">
          {t("ghost_away_label")}
        </label>
        <textarea
          value={awayMsg}
          onChange={(e) => setAwayMsg(e.target.value)}
          onBlur={() => saveAwayMessage(awayMsg)}
          rows={3}
          placeholder="Сейчас занят, отвечу позже..."
          className="w-full rounded-2xl bg-tg-secondary text-tg-text text-sm p-3 resize-none outline-none border border-tg-hint/10 focus:border-tg-accent/40 placeholder:text-tg-hint"
        />
      </div>

      <div className="mt-6">
        <h2 className="text-xs font-semibold text-tg-hint uppercase tracking-wider mb-3">
          {t("ghost_inquiries_section")} ({inquiries.length})
        </h2>
        <InquiryList inquiries={inquiries} />
      </div>
    </div>
  );
}
