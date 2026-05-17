"use client";

import { useState } from "react";
import useSWR from "swr";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import type { Contact } from "@/lib/types";

function displayName(c: Contact): string {
  return c.saved_name || c.name || c.username || String(c.user_id);
}

function ContactAvatar({ user_id, name }: { user_id: number; name: string }) {
  const [error, setError] = useState(false);
  const initials = name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  if (error) {
    return (
      <div
        className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold shrink-0"
        style={{ background: "var(--tg-theme-button-color, #007aff)", color: "#fff" }}
      >
        {initials || "?"}
      </div>
    );
  }

  return (
    <img
      src={api.contacts.avatarUrl(user_id)}
      alt={name}
      onError={() => setError(true)}
      className="w-10 h-10 rounded-full object-cover shrink-0"
    />
  );
}

function LabelChip({ label, removable, onRemove }: { label: string; removable?: boolean; onRemove?: () => void }) {
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-medium"
      style={{
        background: "var(--tg-theme-button-color, #007aff)",
        color: "var(--tg-theme-button-text-color, #fff)",
        opacity: 0.85,
      }}
    >
      {label}
      {removable && onRemove && (
        <button onClick={onRemove} className="opacity-80 hover:opacity-100 leading-none">
          ×
        </button>
      )}
    </span>
  );
}

function ContactEditSheet({
  contact,
  allLabels,
  onClose,
  onSaved,
}: {
  contact: Contact;
  allLabels: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useLang();
  const [savedName, setSavedName] = useState(contact.saved_name ?? "");
  const [email, setEmail] = useState(contact.email ?? "");
  const [labels, setLabels] = useState<string[]>(contact.labels ?? []);
  const [newLabel, setNewLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const originalName = contact.name || contact.username || String(contact.user_id);

  function addLabel(label: string) {
    const l = label.trim();
    if (l && !labels.includes(l)) setLabels([...labels, l]);
    setNewLabel("");
  }

  function removeLabel(label: string) {
    setLabels(labels.filter((l) => l !== label));
  }

  async function handleSave() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await api.contacts.update(contact.user_id, {
        saved_name: savedName.trim() || null,
        email: email.trim() || null,
      });
      await api.contacts.setLabels(contact.user_id, labels);
      onSaved();
      onClose();
    } catch (e) {
      setError(String(e));
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end" onClick={onClose}>
      <div
        className="bg-tg-bg rounded-t-2xl p-5 space-y-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3">
          <ContactAvatar user_id={contact.user_id} name={displayName(contact)} />
          <div>
            <p className="font-semibold text-tg-text">{originalName}</p>
            {contact.username && <p className="text-xs text-tg-hint">@{contact.username}</p>}
          </div>
          <button onClick={onClose} className="ml-auto text-tg-hint text-xl leading-none">×</button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-tg-hint block mb-1">{t("contacts_bot_name")}</label>
            <input
              type="text"
              value={savedName}
              onChange={(e) => setSavedName(e.target.value)}
              placeholder={originalName}
              className="w-full px-3 py-2.5 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors"
            />
            <p className="text-xs text-tg-hint mt-1">{t("contacts_bot_name_hint")}</p>
          </div>

          <div>
            <label className="text-xs font-medium text-tg-hint block mb-1">{t("contacts_email")}</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email@example.com"
              className="w-full px-3 py-2.5 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-tg-hint block mb-2">{t("labels_section")}</label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {labels.length === 0 ? (
                <p className="text-xs text-tg-hint">{t("labels_empty")}</p>
              ) : (
                labels.map((l) => (
                  <LabelChip key={l} label={l} removable onRemove={() => removeLabel(l)} />
                ))
              )}
            </div>
            {/* Existing labels to quickly add */}
            {allLabels.filter((l) => !labels.includes(l)).length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {allLabels
                  .filter((l) => !labels.includes(l))
                  .map((l) => (
                    <button
                      key={l}
                      onClick={() => addLabel(l)}
                      className="text-[10px] px-2 py-0.5 rounded-full border border-tg-hint/30 text-tg-hint hover:border-tg-accent/50 hover:text-tg-accent transition-colors"
                    >
                      + {l}
                    </button>
                  ))}
              </div>
            )}
            <div className="flex gap-2">
              <input
                type="text"
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addLabel(newLabel)}
                placeholder={t("labels_add")}
                className="flex-1 px-3 py-2 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors"
              />
              <button
                onClick={() => addLabel(newLabel)}
                disabled={!newLabel.trim()}
                className="px-3 py-2 text-sm rounded-xl transition-opacity disabled:opacity-30"
                style={{ background: "var(--tg-theme-button-color, #007aff)", color: "var(--tg-theme-button-text-color, #fff)" }}
              >
                +
              </button>
            </div>
          </div>
        </div>

        {error && <p className="text-xs text-red-500 text-center">❌ {error}</p>}

        <button
          onClick={handleSave}
          disabled={saving}
          className="w-full py-3 rounded-xl text-sm font-semibold transition-opacity disabled:opacity-40"
          style={{
            background: "var(--tg-theme-button-color, #007aff)",
            color: "var(--tg-theme-button-text-color, #fff)",
          }}
        >
          {saving ? "…" : t("contacts_save")}
        </button>
      </div>
    </div>
  );
}

export default function ContactsPage() {
  const { t } = useLang();
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [activeLabel, setActiveLabel] = useState<string | null>(null);
  const [editing, setEditing] = useState<Contact | null>(null);

  const { data: contacts, mutate } = useSWR<Contact[]>("/api/contacts", api.contacts.list, { refreshInterval: 30_000 });
  const { data: allLabels = [] } = useSWR<string[]>("/api/contacts/labels", api.contacts.getLabels, { refreshInterval: 60_000 });

  const filtered = (contacts ?? []).filter((c) => {
    if (activeLabel && !(c.labels ?? []).includes(activeLabel)) return false;
    const q = search.toLowerCase();
    return (
      !q ||
      (c.name ?? "").toLowerCase().includes(q) ||
      (c.saved_name ?? "").toLowerCase().includes(q) ||
      (c.username ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="flex flex-col min-h-screen pb-20">
      <div className="flex items-center gap-2 px-4 pt-4 pb-2">
        <button onClick={() => router.back()} className="text-tg-hint text-xl leading-none px-1">‹</button>
        <h1 className="text-xl font-bold text-tg-text">{t("contacts_all")}</h1>
      </div>

      <div className="px-4 pt-2 pb-20">
        <input
          type="text"
          placeholder={t("contacts_search")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full mb-3 px-3 py-2.5 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors"
        />

        {/* Label filter bar */}
        {allLabels.length > 0 && (
          <div className="flex gap-2 mb-3 overflow-x-auto pb-1">
            <button
              onClick={() => setActiveLabel(null)}
              className="text-xs px-3 py-1 rounded-full whitespace-nowrap shrink-0 transition-colors"
              style={
                !activeLabel
                  ? { background: "var(--tg-theme-button-color, #007aff)", color: "var(--tg-theme-button-text-color, #fff)" }
                  : { background: "var(--tg-theme-secondary-bg-color, #f2f2f7)", color: "var(--tg-theme-hint-color, #8e8e93)" }
              }
            >
              {t("labels_filter")}
            </button>
            {allLabels.map((label) => (
              <button
                key={label}
                onClick={() => setActiveLabel(activeLabel === label ? null : label)}
                className="text-xs px-3 py-1 rounded-full whitespace-nowrap shrink-0 transition-colors"
                style={
                  activeLabel === label
                    ? { background: "var(--tg-theme-button-color, #007aff)", color: "var(--tg-theme-button-text-color, #fff)" }
                    : { background: "var(--tg-theme-secondary-bg-color, #f2f2f7)", color: "var(--tg-theme-hint-color, #8e8e93)" }
                }
              >
                {label}
              </button>
            ))}
          </div>
        )}

        {!contacts && <p className="text-sm text-tg-hint text-center mt-8">Загрузка…</p>}

        <div className="space-y-1">
          {filtered.map((c) => {
            const name = displayName(c);
            return (
              <button
                key={c.id}
                onClick={() => setEditing(c)}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-tg-secondary transition-colors text-left"
              >
                <ContactAvatar user_id={c.user_id} name={name} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-tg-text truncate">{name}</p>
                  {c.saved_name && c.name && c.saved_name !== c.name && (
                    <p className="text-xs text-tg-hint truncate">{c.name}</p>
                  )}
                  {(c.labels ?? []).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {(c.labels ?? []).map((l) => <LabelChip key={l} label={l} />)}
                    </div>
                  )}
                </div>
                {c.email ? (
                  <span className="text-xs text-tg-hint shrink-0 truncate max-w-28">{c.email}</span>
                ) : (
                  <span className="text-xs text-tg-hint/50 shrink-0">{t("contacts_no_email")}</span>
                )}
                <span className="text-tg-hint text-sm shrink-0">›</span>
              </button>
            );
          })}
        </div>
      </div>

      {editing && (
        <ContactEditSheet
          contact={editing}
          allLabels={allLabels}
          onClose={() => setEditing(null)}
          onSaved={() => { mutate(); }}
        />
      )}
    </div>
  );
}
