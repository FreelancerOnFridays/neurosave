"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import type { NotionPage } from "@/lib/types";

const SECTIONS = [
  { value: "capture", label: "📝", key: "notion_section_capture" as const },
  { value: "task", label: "✅", key: "notion_section_task" as const },
  { value: "meeting_notes", label: "🤝", key: "notion_section_meetings" as const },
];

function sectionIcon(section: string) {
  return SECTIONS.find((s) => s.value === section)?.label ?? "📄";
}

function formatDate(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return "сегодня " + d.toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
  if (days === 1) return "вчера";
  return d.toLocaleDateString("ru", { day: "numeric", month: "short" });
}

export function NotionWorkspace() {
  const { t } = useLang();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [section, setSection] = useState("capture");
  const [loading, setLoading] = useState(false);
  const [savedUrl, setSavedUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: pages, mutate } = useSWR<NotionPage[]>(
    "/api/integrations/notion/pages",
    api.integrations.notionPages,
    { refreshInterval: 30_000 }
  );

  async function handleSave() {
    if (!title.trim() || loading) return;
    setLoading(true);
    setError(null);
    setSavedUrl(null);
    try {
      const res = await api.integrations.notionCapture(title.trim(), content.trim(), section);
      setSavedUrl(res.url || null);
      setTitle("");
      setContent("");
      mutate();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <input
          type="text"
          placeholder="Заголовок заметки..."
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full px-3 py-2.5 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors"
        />
        <textarea
          placeholder="Текст (поддерживает # заголовки, - списки, [] чекбоксы)..."
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={4}
          className="w-full px-3 py-2.5 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors resize-none"
        />
        <div className="flex items-center gap-2">
          <select
            value={section}
            onChange={(e) => setSection(e.target.value)}
            className="flex-1 px-3 py-2 text-sm rounded-xl border border-tg-hint/20 bg-tg-secondary text-tg-text outline-none"
          >
            {SECTIONS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label} {t(s.key)}
              </option>
            ))}
          </select>
          <button
            onClick={handleSave}
            disabled={loading || !title.trim()}
            className="shrink-0 px-4 py-2 rounded-xl text-sm font-medium transition-opacity disabled:opacity-40"
            style={{
              background: "var(--tg-theme-button-color, #007aff)",
              color: "var(--tg-theme-button-text-color, #fff)",
            }}
          >
            {loading ? "…" : t("notion_save")}
          </button>
        </div>
        {savedUrl && (
          <a
            href={savedUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-xs text-center py-1.5 rounded-xl font-medium"
            style={{ color: "var(--tg-theme-accent-text-color, #007aff)" }}
          >
            ✅ {t("notion_saved")} — {t("notion_open")}
          </a>
        )}
        {error && (
          <p className="text-xs text-center text-red-500">❌ {error}</p>
        )}
      </div>

      {pages && pages.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-tg-hint uppercase tracking-wide mb-2">
            {t("notion_recent")}
          </p>
          <div className="space-y-1">
            {pages.map((page) => (
              <a
                key={page.id}
                href={page.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-tg-secondary transition-colors group"
              >
                <span className="text-base leading-none">{sectionIcon(page.section)}</span>
                <span className="flex-1 text-sm text-tg-text truncate">{page.title}</span>
                <span className="text-xs text-tg-hint shrink-0">{formatDate(page.created_time)}</span>
                <span className="text-tg-hint opacity-0 group-hover:opacity-100 transition-opacity text-sm">→</span>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
