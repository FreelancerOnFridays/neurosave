"use client";

import { EmptyState } from "@/components/ui/EmptyState";
import { InquiryCard } from "./InquiryCard";
import { useLang } from "@/contexts/LanguageContext";
import type { Inquiry, InquiryCategory } from "@/lib/types";

const ORDER: InquiryCategory[] = ["Urgent", "Team", "Sales", "Spam"];

interface InquiryListProps {
  inquiries: Inquiry[];
}

export function InquiryList({ inquiries }: InquiryListProps) {
  const { t } = useLang();

  const LABELS: Record<InquiryCategory, string> = {
    Urgent: t("cat_urgent"),
    Team: t("cat_team"),
    Sales: t("cat_sales"),
    Spam: t("cat_spam"),
  };

  if (inquiries.length === 0) {
    return <EmptyState icon="📬" message={t("empty_inquiries")} />;
  }

  const grouped = ORDER.map((cat) => ({
    category: cat,
    items: inquiries.filter((i) => i.category === cat),
  })).filter((g) => g.items.length > 0);

  return (
    <div className="flex flex-col gap-4">
      {grouped.map(({ category, items }) => (
        <div key={category}>
          <h3 className="text-xs font-semibold text-tg-hint uppercase tracking-wider mb-2">
            {LABELS[category]} ({items.length})
          </h3>
          <div className="flex flex-col gap-2">
            {items.map((i) => (
              <InquiryCard key={i.id} inquiry={i} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
