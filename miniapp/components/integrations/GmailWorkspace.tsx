"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import type { GmailMessage, GmailThread } from "@/lib/types";

function parseDate(raw: string): string {
  if (!raw) return "";
  try {
    const d = new Date(raw);
    if (isNaN(d.getTime())) return raw;
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const days = Math.floor(diff / 86400000);
    if (days === 0) return d.toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
    if (days === 1) return "вчера";
    return d.toLocaleDateString("ru", { day: "numeric", month: "short" });
  } catch {
    return raw;
  }
}

function senderName(from_: string): string {
  const match = from_.match(/^"?([^"<]+)"?\s*</);
  return match ? match[1].trim() : from_.replace(/<.*>/, "").trim() || from_;
}

function senderEmail(from_: string): string {
  const match = from_.match(/<([^>]+)>/);
  return match ? match[1] : from_;
}

// ── Compose / Reply sheet ─────────────────────────────────────────────────────

interface ComposeProps {
  initialTo?: string;
  initialSubject?: string;
  threadId?: string;
  inReplyTo?: string;
  onClose: () => void;
  onSent: () => void;
}

function ComposeSheet({ initialTo = "", initialSubject = "", threadId, inReplyTo, onClose, onSent }: ComposeProps) {
  const { t } = useLang();
  const [to, setTo] = useState(initialTo);
  const [subject, setSubject] = useState(initialSubject);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function handleSend() {
    if (!to.trim() || !subject.trim() || !body.trim() || sending) return;
    setSending(true);
    setError(null);
    try {
      await api.integrations.gmailSend({
        to: to.trim(),
        subject: subject.trim(),
        body: body.trim(),
        thread_id: threadId ?? null,
        in_reply_to: inReplyTo ?? null,
      });
      setSent(true);
      setTimeout(onSent, 1200);
    } catch (e) {
      setError(String(e));
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end" onClick={onClose}>
      <div
        className="bg-tg-bg rounded-t-2xl p-5 space-y-3 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <p className="font-semibold text-tg-text">
            {threadId ? `↩ ${t("gmail_reply")}` : `✉️ ${t("gmail_compose")}`}
          </p>
          <button onClick={onClose} className="text-tg-hint text-xl">×</button>
        </div>

        <input
          type="email"
          placeholder={t("gmail_compose_to")}
          value={to}
          onChange={(e) => setTo(e.target.value)}
          disabled={!!initialTo}
          className="w-full px-3 py-2.5 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors disabled:opacity-60"
        />
        <input
          type="text"
          placeholder={t("gmail_compose_subject")}
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          className="w-full px-3 py-2.5 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors"
        />
        <textarea
          placeholder={t("gmail_compose_body")}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={5}
          className="w-full px-3 py-2.5 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors resize-none"
        />

        {error && <p className="text-xs text-red-500">❌ {error}</p>}
        {sent && <p className="text-xs text-center font-medium" style={{ color: "var(--tg-theme-accent-text-color, #34c759)" }}>{t("gmail_sent")}</p>}

        <div className="flex gap-2">
          <button
            onClick={handleSend}
            disabled={sending || sent || !to.trim() || !subject.trim() || !body.trim()}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold transition-opacity disabled:opacity-40"
            style={{ background: "var(--tg-theme-button-color, #007aff)", color: "var(--tg-theme-button-text-color, #fff)" }}
          >
            {sending ? t("gmail_sending") : t("gmail_compose_send")}
          </button>
          <button
            onClick={onClose}
            className="py-2.5 px-4 rounded-xl text-sm text-tg-hint"
            style={{ background: "var(--tg-theme-secondary-bg-color, #f2f2f7)" }}
          >
            {t("gmail_compose_cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Message detail sheet ──────────────────────────────────────────────────────

interface DetailSheetProps {
  thread: GmailThread;
  onClose: () => void;
}

function DetailSheet({ thread, onClose }: DetailSheetProps) {
  const { t } = useLang();
  const [composing, setComposing] = useState(false);

  const { data: msg, isLoading } = useSWR<GmailMessage>(
    `/api/integrations/gmail/messages/${thread.id}`,
    () => api.integrations.gmailMessage(thread.id),
    { revalidateOnFocus: false }
  );

  if (composing && msg) {
    return (
      <ComposeSheet
        initialTo={senderEmail(msg.from_)}
        initialSubject={msg.subject.startsWith("Re:") ? msg.subject : `Re: ${msg.subject}`}
        threadId={msg.thread_id}
        inReplyTo={msg.message_id_header}
        onClose={() => setComposing(false)}
        onSent={() => { setComposing(false); onClose(); }}
      />
    );
  }

  return (
    <div className="fixed inset-0 z-40 flex flex-col" style={{ background: "var(--tg-theme-bg-color, #fff)" }}>
      {/* Header */}
      <div className="flex items-center gap-2 px-4 pt-4 pb-3 border-b border-tg-hint/10 shrink-0">
        <button onClick={onClose} className="text-tg-hint text-xl leading-none px-1">‹</button>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-tg-text truncate text-sm">{thread.subject}</p>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {isLoading && <p className="text-sm text-tg-hint text-center py-8">Загрузка…</p>}

        {msg && (
          <>
            <div className="space-y-0.5">
              <p className="text-xs text-tg-hint">
                <span className="font-medium text-tg-text">{senderName(msg.from_)}</span>
                {" "}{"<"}{senderEmail(msg.from_)}{">"}
              </p>
              <p className="text-xs text-tg-hint">Кому: {msg.to}</p>
              <p className="text-xs text-tg-hint">{parseDate(msg.date)}</p>
            </div>

            {msg.attachments.length > 0 && (
              <div>
                <p className="text-xs font-medium text-tg-hint mb-1.5">📎 {t("gmail_attachments")}</p>
                <div className="flex flex-wrap gap-1.5">
                  {msg.attachments.map((att) => (
                    <span
                      key={att.attachment_id}
                      className="text-xs px-2 py-1 rounded-lg"
                      style={{ background: "var(--tg-theme-secondary-bg-color, #f2f2f7)", color: "var(--tg-theme-text-color)" }}
                    >
                      {att.filename}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div
              className="text-sm text-tg-text whitespace-pre-wrap leading-relaxed"
              style={{ wordBreak: "break-word" }}
            >
              {msg.body || <span className="text-tg-hint italic">{thread.snippet}</span>}
            </div>
          </>
        )}
      </div>

      {/* Reply button */}
      {msg && (
        <div className="px-4 pb-6 pt-3 border-t border-tg-hint/10 shrink-0">
          <button
            onClick={() => setComposing(true)}
            className="w-full py-2.5 rounded-xl text-sm font-semibold"
            style={{ background: "var(--tg-theme-button-color, #007aff)", color: "var(--tg-theme-button-text-color, #fff)" }}
          >
            ↩ {t("gmail_reply")}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Main workspace ────────────────────────────────────────────────────────────

export function GmailWorkspace() {
  const { t } = useLang();
  const [selected, setSelected] = useState<GmailThread | null>(null);
  const [composing, setComposing] = useState(false);

  const { data: threads, isLoading, mutate } = useSWR<GmailThread[]>(
    "/api/integrations/gmail/threads",
    () => api.integrations.gmailThreads(30),
    { refreshInterval: 60_000 }
  );

  if (selected) {
    return <DetailSheet thread={selected} onClose={() => setSelected(null)} />;
  }

  if (composing) {
    return (
      <ComposeSheet
        onClose={() => setComposing(false)}
        onSent={() => { setComposing(false); mutate(); }}
      />
    );
  }

  return (
    <div className="space-y-4">
      <button
        onClick={() => setComposing(true)}
        className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-medium"
        style={{ background: "var(--tg-theme-button-color, #007aff)", color: "var(--tg-theme-button-text-color, #fff)" }}
      >
        ✉️ {t("gmail_compose")}
      </button>

      <p className="text-xs font-semibold text-tg-hint uppercase tracking-wide">
        {t("gmail_recent_threads")}
      </p>

      {isLoading && (
        <p className="text-sm text-tg-hint text-center py-4">Загрузка…</p>
      )}

      {!isLoading && (!threads || threads.length === 0) && (
        <p className="text-sm text-tg-hint text-center py-6">{t("gmail_no_threads")}</p>
      )}

      {threads && threads.length > 0 && (
        <div className="space-y-1">
          {threads.map((thread) => (
            <button
              key={thread.id}
              onClick={() => setSelected(thread)}
              className="w-full flex items-start gap-3 px-3 py-2.5 rounded-xl text-left transition-colors hover:bg-tg-secondary"
              style={{ background: "var(--tg-theme-secondary-bg-color, #f2f2f7)" }}
            >
              <span className="text-base leading-none mt-0.5 shrink-0">
                {thread.is_reply ? "📨" : "📤"}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-xs font-semibold text-tg-text truncate flex-1">
                    {senderName(thread.from_)}
                  </span>
                  {thread.is_reply && (
                    <span
                      className="shrink-0 text-xs px-1.5 py-0.5 rounded-full font-medium"
                      style={{ background: "rgba(52, 199, 89, 0.15)", color: "#34c759" }}
                    >
                      {t("gmail_inbox_reply")}
                    </span>
                  )}
                  <span className="text-xs text-tg-hint shrink-0">{parseDate(thread.date)}</span>
                </div>
                <p className="text-xs font-medium text-tg-text truncate">{thread.subject}</p>
                {thread.snippet && (
                  <p className="text-xs text-tg-hint truncate mt-0.5">{thread.snippet}</p>
                )}
              </div>
              <span className="text-tg-hint text-sm shrink-0 mt-1">›</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
