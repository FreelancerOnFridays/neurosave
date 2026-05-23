"use client";

import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/Card";
import { useLang } from "@/contexts/LanguageContext";
import { useContacts } from "@/hooks/useContacts";

export function ContactsSection() {
  const { t } = useLang();
  const { status } = useContacts();
  const router = useRouter();

  const contactCount = status?.contact_count ?? 0;

  return (
    <Card className="mt-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-semibold text-tg-text">{t("settings_contacts_title")}</p>
        {contactCount > 0 && (
          <span className="text-xs text-tg-hint">
            {contactCount} {t("contacts_count")}
          </span>
        )}
      </div>

      {contactCount === 0 ? (
        <p className="text-xs text-tg-hint leading-relaxed">
          {t("contacts_no_contacts_hint")}
        </p>
      ) : (
        <button
          onClick={() => router.push("/contacts")}
          className="mt-2 w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm font-medium transition-colors"
          style={{ background: "var(--tg-theme-secondary-bg-color, #f2f2f7)" }}
        >
          <span className="text-tg-text">👥 {t("contacts_all")}</span>
          <span className="text-tg-hint">›</span>
        </button>
      )}
    </Card>
  );
}
