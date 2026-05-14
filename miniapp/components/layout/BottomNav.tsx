"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLang } from "@/contexts/LanguageContext";

export function BottomNav() {
  const pathname = usePathname();
  const { t } = useLang();

  const NAV_ITEMS = [
    { href: "/today", icon: "📅", label: t("nav_today") },
    { href: "/tasks", icon: "📌", label: t("nav_tasks") },
    { href: "/ghost", icon: "👻", label: t("nav_ghost") },
    { href: "/settings", icon: "⚙️", label: t("nav_settings") },
  ];

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 flex bg-tg-secondary border-t border-tg-hint/20"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      {NAV_ITEMS.map((item) => {
        const active = pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex flex-1 flex-col items-center py-2 gap-0.5 text-xs transition-colors ${
              active ? "text-tg-accent" : "text-tg-hint"
            }`}
          >
            <span className="text-xl leading-none">{item.icon}</span>
            <span className="font-medium">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
