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

function ContactEditSheet({
  contact,
  onClose,
  onSaved,
}: {
  contact: Contact;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useLang();
  const [savedName, setSavedName] = useState(contact.saved_name ?? "");
  const [email, setEmail] = useState(contact.email ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const originalName = contact.name || contact.username || String(contact.user_id);

  async function handleSave() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await api.contacts.update(contact.user_id, {
        saved_name: savedName.trim() || null,
        email: email.trim() || null,
      });
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
        className="bg-tg-bg rounded-t-2xl p-5 space-y-4 max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3">
          <ContactAvatar user_id={contact.user_id} name={displayName(contact)} />
          <div>
            <p className="font-semibold text-tg-text">{originalName}</p>
            {contact.username && (
              <p className="text-xs text-tg-hint">@{contact.username}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="ml-auto text-tg-hint text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-tg-hint block mb-1">
              {t("contacts_bot_name")}
            </label>
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
            <label className="text-xs font-medium text-tg-hint block mb-1">
              {t("contacts_email")}
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email@example.com"
              className="w-full px-3 py-2.5 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors"
            />
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
  const [editing, setEditing] = useState<Contact | null>(null);

  const { data: contacts, mutate } = useSWR<Contact[]>(
    "/api/contacts",
    api.contacts.list,
    { refreshInterval: 30_000 }
  );

  const filtered = (contacts ?? []).filter((c) => {
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
        <button
          onClick={() => router.back()}
          className="text-tg-hint text-xl leading-none px-1"
        >
          ‹
        </button>
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

        {!contacts && (
          <p className="text-sm text-tg-hint text-center mt-8">Загрузка…</p>
        )}

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
          onClose={() => setEditing(null)}
          onSaved={() => mutate()}
        />
      )}
    </div>
  );
}
