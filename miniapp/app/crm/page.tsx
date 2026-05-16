"use client";

import { useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import useSWR from "swr";
import { PageHeader } from "@/components/layout/PageHeader";
import { SegmentedControl } from "@/components/tasks/SegmentedControl";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { TimePickerSheet } from "@/components/ui/TimePickerSheet";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import type { ContactCrm, ContactHistory, CrmStatus } from "@/lib/types";

// ─── helpers ────────────────────────────────────────────────────────────────

const STATUS_ORDER: (CrmStatus | "all")[] = ["all", "lead", "negotiation", "client", "partner"];

const STATUS_COLORS: Record<CrmStatus, { bg: string; text: string }> = {
  lead: { bg: "#8e8e9322", text: "#8e8e93" },
  negotiation: { bg: "#007aff22", text: "#007aff" },
  client: { bg: "#34c75922", text: "#34c759" },
  partner: { bg: "#af52de22", text: "#af52de" },
  archived: { bg: "#c7c7cc22", text: "#c7c7cc" },
};

function avatarColor(name: string): string {
  const colors = ["#007aff", "#34c759", "#ff9500", "#af52de", "#ff3b30", "#5ac8fa", "#ff2d55"];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
  return colors[Math.abs(h) % colors.length];
}

function initials(contact: ContactCrm): string {
  const n = contact.name || contact.username || "?";
  const parts = n.trim().split(/\s+/);
  return parts.length >= 2
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : n.slice(0, 2).toUpperCase();
}

function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
}

// ─── contact detail sheet ────────────────────────────────────────────────────

interface DetailSheetProps {
  contact: ContactCrm;
  history: ContactHistory | undefined;
  gmailConnected: boolean;
  onClose: () => void;
  onUpdate: (patch: Partial<ContactCrm>) => Promise<void>;
}

const CRM_STATUSES: CrmStatus[] = ["lead", "negotiation", "client", "partner", "archived"];

function DetailSheet({ contact, history, gmailConnected, onClose, onUpdate }: DetailSheetProps) {
  const { t } = useLang();
  const [notes, setNotes] = useState(contact.notes || "");
  const [nextAction, setNextAction] = useState(contact.next_action || "");
  const [reminderOpen, setReminderOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function debouncedUpdate(patch: Partial<ContactCrm>) {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => onUpdate(patch), 500);
  }

  const statusLabel: Record<CrmStatus, string> = {
    lead: t("crm_status_lead"),
    negotiation: t("crm_status_negotiation"),
    client: t("crm_status_client"),
    partner: t("crm_status_partner"),
    archived: t("crm_status_archived"),
  };

  function openTg() {
    if (contact.username) {
      window.open(`https://t.me/${contact.username}`, "_blank");
    }
  }

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-40 flex flex-col justify-end"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        {/* Backdrop */}
        <motion.div
          className="absolute inset-0 bg-black/40"
          onClick={onClose}
        />

        {/* Sheet */}
        <motion.div
          className="relative z-50 rounded-t-2xl overflow-hidden"
          style={{ background: "var(--tg-theme-bg-color, #fff)", maxHeight: "90vh", overflowY: "auto" }}
          initial={{ y: "100%" }}
          animate={{ y: 0 }}
          exit={{ y: "100%" }}
          transition={{ type: "spring", stiffness: 380, damping: 32 }}
        >
          {/* Drag handle */}
          <div className="flex justify-center pt-3 pb-1">
            <div className="w-10 h-1 rounded-full" style={{ background: "var(--tg-theme-hint-color, #ccc)" }} />
          </div>

          <div className="px-4 pb-8">
            {/* Header */}
            <div className="flex items-center gap-3 mb-4 mt-2">
              <div
                className="w-12 h-12 rounded-full flex items-center justify-center text-white text-base font-bold shrink-0"
                style={{ background: avatarColor(contact.name || contact.username || "?") }}
              >
                {initials(contact)}
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-tg-text leading-tight truncate">
                  {contact.name || contact.username || "—"}
                </p>
                <p className="text-xs text-tg-hint truncate">
                  {[contact.username && `@${contact.username}`, contact.email].filter(Boolean).join(" · ")}
                </p>
              </div>
            </div>

            {/* Status chips */}
            <div className="flex gap-2 flex-wrap mb-4">
              {CRM_STATUSES.map((s) => {
                const active = contact.crm_status === s;
                const col = STATUS_COLORS[s];
                return (
                  <motion.button
                    key={s}
                    whileTap={{ scale: 0.94 }}
                    onClick={() => onUpdate({ crm_status: s })}
                    className="px-3 py-1 rounded-full text-xs font-semibold transition-all"
                    style={{
                      background: active ? col.bg : "var(--tg-theme-secondary-bg-color, #f2f2f7)",
                      color: active ? col.text : "var(--tg-theme-hint-color, #8e8e93)",
                      border: active ? `1px solid ${col.text}44` : "1px solid transparent",
                    }}
                  >
                    {statusLabel[s]}
                  </motion.button>
                );
              })}
            </div>

            {/* Next step */}
            <div
              className="rounded-xl p-3 mb-3"
              style={{ background: "var(--tg-theme-secondary-bg-color, #f2f2f7)" }}
            >
              <p className="text-[10px] font-semibold uppercase tracking-wide text-tg-hint mb-1.5">
                {t("crm_next_action")}
              </p>
              <input
                className="w-full bg-transparent text-sm text-tg-text outline-none placeholder:text-tg-hint"
                placeholder="Что сделать следующим…"
                value={nextAction}
                onChange={(e) => {
                  setNextAction(e.target.value);
                  debouncedUpdate({ next_action: e.target.value });
                }}
              />
              {contact.next_action_date && (
                <p className="text-xs text-tg-hint mt-1">
                  📅 {new Date(contact.next_action_date).toLocaleDateString("ru-RU")}
                </p>
              )}
              <button
                className="text-xs mt-2"
                style={{ color: "var(--tg-theme-link-color, #007aff)" }}
                onClick={() => setReminderOpen(true)}
              >
                {t("crm_add_date")}
              </button>
            </div>

            {/* Notes */}
            <div
              className="rounded-xl p-3 mb-3"
              style={{ background: "var(--tg-theme-secondary-bg-color, #f2f2f7)" }}
            >
              <p className="text-[10px] font-semibold uppercase tracking-wide text-tg-hint mb-1.5">
                {t("crm_notes")}
              </p>
              <textarea
                className="w-full bg-transparent text-sm text-tg-text outline-none resize-none placeholder:text-tg-hint"
                placeholder="Заметка о контакте…"
                rows={3}
                value={notes}
                onChange={(e) => {
                  setNotes(e.target.value);
                  debouncedUpdate({ notes: e.target.value });
                }}
              />
            </div>

            {/* Tasks history */}
            {history && (
              <div
                className="rounded-xl p-3 mb-4"
                style={{ background: "var(--tg-theme-secondary-bg-color, #f2f2f7)" }}
              >
                <p className="text-[10px] font-semibold uppercase tracking-wide text-tg-hint mb-1">
                  {t("crm_tasks_section")}
                </p>
                <p className="text-sm text-tg-text">
                  {history.open_tasks} {t("crm_open_tasks")}
                  {history.done_tasks > 0 && ` · ${history.done_tasks} завершено`}
                </p>
              </div>
            )}

            {/* Actions */}
            <div className="grid grid-cols-4 gap-2">
              {[
                { icon: "💬", label: t("crm_action_write"), onClick: openTg, show: !!contact.username },
                { icon: "📋", label: t("crm_action_task"), onClick: () => {}, show: true },
                { icon: "⏰", label: t("crm_action_remind"), onClick: () => setReminderOpen(true), show: true },
                { icon: "✉️", label: t("crm_action_email"), onClick: () => {}, show: gmailConnected && !!contact.email },
              ]
                .filter((a) => a.show)
                .map((a) => (
                  <motion.button
                    key={a.label}
                    whileTap={{ scale: 0.92 }}
                    onClick={a.onClick}
                    className="flex flex-col items-center gap-1 rounded-xl py-2.5 text-xs font-medium"
                    style={{ background: "var(--tg-theme-secondary-bg-color, #f2f2f7)", color: "var(--tg-theme-text-color)" }}
                  >
                    <span className="text-xl">{a.icon}</span>
                    {a.label}
                  </motion.button>
                ))}
            </div>
          </div>
        </motion.div>
      </motion.div>

      <TimePickerSheet
        open={reminderOpen}
        title={t("crm_add_date")}
        onConfirm={(iso) => {
          setReminderOpen(false);
          onUpdate({ next_action_date: iso });
        }}
        onCancel={() => setReminderOpen(false)}
      />
    </AnimatePresence>
  );
}

// ─── contact row ──────────────────────────────────────────────────────────────

const listVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.05 } },
};
const itemVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 400, damping: 28 } },
};

interface ContactRowProps {
  contact: ContactCrm;
  onTap: () => void;
}

function ContactRow({ contact, onTap }: ContactRowProps) {
  const { t } = useLang();
  const col = contact.crm_status ? STATUS_COLORS[contact.crm_status] : null;
  const days = daysSince(contact.last_seen);

  const statusLabel: Record<CrmStatus, string> = {
    lead: t("crm_status_lead"),
    negotiation: t("crm_status_negotiation"),
    client: t("crm_status_client"),
    partner: t("crm_status_partner"),
    archived: t("crm_status_archived"),
  };

  const subtitle = contact.next_action
    ? contact.next_action + (contact.next_action_date ? ` · ${new Date(contact.next_action_date).toLocaleDateString("ru-RU")}` : "")
    : days !== null
    ? `${t("crm_last_seen")} ${days} ${t("crm_days_ago")}`
    : null;

  return (
    <motion.button
      variants={itemVariants}
      onClick={onTap}
      className="w-full flex items-center gap-3 p-3 rounded-2xl text-left active:opacity-70 transition-opacity"
      style={{ background: "var(--tg-theme-secondary-bg-color, #f2f2f7)" }}
    >
      <div
        className="w-10 h-10 rounded-full flex items-center justify-center text-white text-sm font-bold shrink-0"
        style={{ background: avatarColor(contact.name || contact.username || "?") }}
      >
        {initials(contact)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-tg-text truncate">
            {contact.name || contact.username || "—"}
          </p>
          {contact.is_vip && (
            <span className="text-[10px] text-amber-500 font-semibold">VIP</span>
          )}
        </div>
        {subtitle && (
          <p className="text-xs text-tg-hint truncate mt-0.5">{subtitle}</p>
        )}
      </div>
      {col && contact.crm_status && (
        <span
          className="shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded-full"
          style={{ background: col.bg, color: col.text }}
        >
          {statusLabel[contact.crm_status]}
        </span>
      )}
    </motion.button>
  );
}

// ─── main page ────────────────────────────────────────────────────────────────

export default function CrmPage() {
  const { t } = useLang();
  const [tabIndex, setTabIndex] = useState(0);
  const [selected, setSelected] = useState<ContactCrm | null>(null);

  const statusFilter = STATUS_ORDER[tabIndex];
  const swrKey = `/api/contacts?crm_status=${statusFilter === "all" ? "" : statusFilter}`;

  const { data: contacts, mutate } = useSWR<ContactCrm[]>(swrKey, () =>
    api.crm.list(statusFilter === "all" ? undefined : statusFilter)
  );

  const { data: history } = useSWR<ContactHistory>(
    selected ? `/api/contacts/${selected.id}/history` : null,
    () => api.crm.history(selected!.id)
  );

  const { data: integrations } = useSWR("/api/integrations/status", api.integrations.status);
  const gmailConnected = !!integrations?.gmail?.connected;

  const handleUpdate = useCallback(
    async (patch: Partial<ContactCrm>) => {
      if (!selected) return;
      const updated = { ...selected, ...patch };
      setSelected(updated);
      await api.crm.update(selected.id, patch);
      mutate();
    },
    [selected, mutate]
  );

  const tabs = [
    t("crm_tab_all"),
    t("crm_tab_leads"),
    t("crm_status_negotiation"),
    t("crm_tab_clients"),
    t("crm_tab_partners"),
  ];

  return (
    <div className="max-w-lg mx-auto px-4 pt-5 pb-24">
      <PageHeader title={`📇 ${t("crm_title")}`} />

      <div className="mb-4 overflow-x-auto">
        <SegmentedControl
          segments={tabs}
          activeIndex={tabIndex}
          onChange={setTabIndex}
        />
      </div>

      {!contacts ? (
        <Spinner />
      ) : contacts.length === 0 ? (
        <EmptyState icon="📇" message={t("crm_no_contacts")} />
      ) : (
        <motion.div
          className="flex flex-col gap-2"
          variants={listVariants}
          initial="hidden"
          animate="visible"
          key={tabIndex}
        >
          {contacts.map((c) => (
            <ContactRow key={c.id} contact={c} onTap={() => setSelected(c)} />
          ))}
        </motion.div>
      )}

      {selected && (
        <DetailSheet
          contact={selected}
          history={history}
          gmailConnected={gmailConnected}
          onClose={() => setSelected(null)}
          onUpdate={handleUpdate}
        />
      )}
    </div>
  );
}
