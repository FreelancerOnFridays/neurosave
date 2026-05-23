"use client";

import { useState } from "react";
import useSWR from "swr";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import type { Contact } from "@/lib/types";

interface Props {
  excludedContactIds: number[];
  excludedLabels: string[];
  onUpdate: (ids: number[], labels: string[]) => Promise<void>;
}

type Tab = "labels" | "contacts";

export function GhostExclusions({ excludedContactIds, excludedLabels, onUpdate }: Props) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("labels");
  const [search, setSearch] = useState("");

  const { data: contacts } = useSWR<Contact[]>(open ? "/api/contacts" : null, api.contacts.list);
  const { data: allLabels } = useSWR<string[]>(open ? "/api/contacts/labels" : null, api.contacts.getLabels);

  const toggleLabel = async (label: string) => {
    const next = excludedLabels.includes(label)
      ? excludedLabels.filter((l) => l !== label)
      : [...excludedLabels, label];
    await onUpdate(excludedContactIds, next);
  };

  const toggleContact = async (userId: number) => {
    const next = excludedContactIds.includes(userId)
      ? excludedContactIds.filter((id) => id !== userId)
      : [...excludedContactIds, userId];
    await onUpdate(next, excludedLabels);
  };

  const totalExcluded = excludedContactIds.length + excludedLabels.length;

  const filteredContacts = (contacts ?? []).filter((c) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (c.saved_name ?? c.name ?? "").toLowerCase().includes(q) ||
      (c.username ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="mt-4 rounded-2xl overflow-hidden" style={{ background: "var(--tg-theme-secondary-bg-color)" }}>
      {/* Header row */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-base">🚫</span>
          <span className="text-sm font-medium text-tg-text">{t("ghost_exclusions_title")}</span>
          {totalExcluded > 0 && (
            <span
              className="text-xs font-semibold px-2 py-0.5 rounded-full"
              style={{ background: "var(--tg-theme-button-color, #007aff)", color: "var(--tg-theme-button-text-color, #fff)" }}
            >
              {totalExcluded}
            </span>
          )}
        </div>
        <span
          className="text-tg-hint text-sm transition-transform duration-200"
          style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}
        >
          ▾
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 380, damping: 30 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-1">
              <p className="text-xs text-tg-hint mb-3 leading-relaxed">{t("ghost_exclusions_hint")}</p>

              {/* Tab switcher */}
              <div
                className="flex rounded-xl p-0.5 mb-3 gap-0.5"
                style={{ background: "var(--tg-theme-bg-color, #fff)" }}
              >
                {(["labels", "contacts"] as Tab[]).map((id) => (
                  <button
                    key={id}
                    onClick={() => setTab(id)}
                    className="flex-1 py-1.5 rounded-[10px] text-sm font-medium transition-colors"
                    style={
                      tab === id
                        ? { background: "var(--tg-theme-button-color, #007aff)", color: "var(--tg-theme-button-text-color, #fff)" }
                        : { color: "var(--tg-theme-hint-color)" }
                    }
                  >
                    {id === "labels" ? t("ghost_exclusions_by_label") : t("ghost_exclusions_by_contact")}
                  </button>
                ))}
              </div>

              {/* Labels tab */}
              {tab === "labels" && (
                <div className="pb-3">
                  {!allLabels || allLabels.length === 0 ? (
                    <p className="text-xs text-tg-hint text-center py-3">{t("ghost_exclusions_empty_labels")}</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {allLabels.map((label) => {
                        const active = excludedLabels.includes(label);
                        return (
                          <button
                            key={label}
                            onClick={() => toggleLabel(label)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-all"
                            style={
                              active
                                ? { background: "var(--tg-theme-destructive-text-color, #ff3b30)", color: "#fff" }
                                : { background: "var(--tg-theme-bg-color, #fff)", color: "var(--tg-theme-text-color)" }
                            }
                          >
                            {active && <span className="text-xs">✕</span>}
                            {label}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Contacts tab */}
              {tab === "contacts" && (
                <div className="pb-3">
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={t("ghost_exclusions_search")}
                    className="w-full mb-2 px-3 py-2 rounded-xl text-sm bg-tg-bg text-tg-text outline-none border border-tg-hint/10"
                    style={{ background: "var(--tg-theme-bg-color, #fff)" }}
                  />
                  {!contacts || filteredContacts.length === 0 ? (
                    <p className="text-xs text-tg-hint text-center py-3">{t("ghost_exclusions_empty_contacts")}</p>
                  ) : (
                    <div className="flex flex-col gap-1 max-h-56 overflow-y-auto">
                      {filteredContacts.map((c) => {
                        const active = excludedContactIds.includes(c.user_id);
                        const name = c.saved_name ?? c.name ?? c.username ?? `ID ${c.user_id}`;
                        return (
                          <button
                            key={c.user_id}
                            onClick={() => toggleContact(c.user_id)}
                            className="flex items-center justify-between gap-3 px-3 py-2 rounded-xl transition-colors"
                            style={{ background: active ? "rgba(255,59,48,0.08)" : "transparent" }}
                          >
                            <span className="text-sm text-tg-text truncate">{name}</span>
                            <span
                              className="shrink-0 w-5 h-5 rounded-full border-2 flex items-center justify-center text-xs font-bold"
                              style={
                                active
                                  ? { borderColor: "var(--tg-theme-destructive-text-color, #ff3b30)", background: "var(--tg-theme-destructive-text-color, #ff3b30)", color: "#fff" }
                                  : { borderColor: "var(--tg-theme-hint-color)", color: "transparent" }
                              }
                            >
                              {active ? "✕" : ""}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
