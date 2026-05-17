"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import type { NotionPage } from "@/lib/types";

const SECTION_KEYS = ["capture", "task", "meeting_notes"] as const;
const SECTION_EMOJIS: Record<string, string> = {
  capture: "📝",
  task: "✅",
  meeting_notes: "🤝",
};

function sectionIcon(section: string) {
  return SECTION_EMOJIS[section] ?? "📄";
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

function insertAtCursor(
  ref: React.RefObject<HTMLTextAreaElement | null>,
  before: string,
  after: string,
  setValue: (v: string) => void,
  currentValue: string
) {
  const el = ref.current;
  if (!el) return;
  const start = el.selectionStart;
  const end = el.selectionEnd;
  const selected = currentValue.slice(start, end);
  const newValue =
    currentValue.slice(0, start) + before + selected + after + currentValue.slice(end);
  setValue(newValue);
  requestAnimationFrame(() => {
    el.focus();
    el.setSelectionRange(start + before.length, start + before.length + selected.length);
  });
}

const FORMAT_BUTTONS = [
  { label: "B", before: "**", after: "**", title: "Жирный" },
  { label: "I", before: "_", after: "_", title: "Курсив" },
  { label: "H1", before: "# ", after: "", title: "Заголовок 1" },
  { label: "H2", before: "## ", after: "", title: "Заголовок 2" },
  { label: "•", before: "- ", after: "", title: "Список" },
  { label: "☐", before: "[ ] ", after: "", title: "Чекбокс" },
  { label: "</>", before: "`", after: "`", title: "Код" },
];

export function NotionWorkspace() {
  const { t } = useLang();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [section, setSection] = useState("capture");
  const [loading, setLoading] = useState(false);
  const [savedUrl, setSavedUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [showFolderSettings, setShowFolderSettings] = useState(false);
  const [folderNames, setFolderNames] = useState<Record<string, string>>({});
  const [savingFolders, setSavingFolders] = useState(false);
  const [foldersSaved, setFoldersSaved] = useState(false);

  const { data: pages, mutate } = useSWR<NotionPage[]>(
    "/api/integrations/notion/pages",
    api.integrations.notionPages,
    { refreshInterval: 30_000 }
  );

  const { data: sectionLabels, mutate: mutateLabels } = useSWR<Record<string, string>>(
    "/api/integrations/notion/sections",
    api.integrations.notionSections
  );

  const getLabel = (key: string) =>
    (showFolderSettings ? folderNames[key] : sectionLabels?.[key]) ??
    { capture: "Заметки", task: "Задачи", meeting_notes: "Встречи" }[key] ??
    key;

  function openFolderSettings() {
    setFolderNames({ ...sectionLabels });
    setShowFolderSettings(true);
    setFoldersSaved(false);
  }

  async function saveFolderNames() {
    if (savingFolders) return;
    setSavingFolders(true);
    try {
      await api.integrations.notionSectionsUpdate({
        capture: folderNames["capture"] || "Заметки",
        task: folderNames["task"] || "Задачи",
        meeting_notes: folderNames["meeting_notes"] || "Встречи",
      });
      await mutateLabels();
      setFoldersSaved(true);
      setTimeout(() => setShowFolderSettings(false), 1000);
    } catch {
      // ignore
    } finally {
      setSavingFolders(false);
    }
  }

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

        {/* Formatting toolbar */}
        <div className="flex gap-1 flex-wrap">
          {FORMAT_BUTTONS.map((btn) => (
            <button
              key={btn.label}
              type="button"
              title={btn.title}
              onClick={() =>
                insertAtCursor(textareaRef, btn.before, btn.after, setContent, content)
              }
              className="px-2 py-1 text-xs font-mono rounded-lg border border-tg-hint/20 text-tg-hint hover:text-tg-text hover:border-tg-hint/40 transition-colors"
            >
              {btn.label}
            </button>
          ))}
        </div>

        <textarea
          ref={textareaRef}
          placeholder="Текст (поддерживает # заголовки, - списки, [ ] чекбоксы, **жирный**)..."
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={4}
          className="w-full px-3 py-2.5 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors resize-none font-mono"
        />

        <div className="flex items-center gap-2">
          <select
            value={section}
            onChange={(e) => setSection(e.target.value)}
            className="flex-1 px-3 py-2 text-sm rounded-xl border border-tg-hint/20 bg-tg-secondary text-tg-text outline-none"
          >
            {SECTION_KEYS.map((key) => (
              <option key={key} value={key}>
                {sectionIcon(key)} {sectionLabels?.[key] ?? getLabel(key)}
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
        {error && <p className="text-xs text-center text-red-500">❌ {error}</p>}
      </div>

      {/* Folder settings */}
      <div>
        <button
          onClick={() => (showFolderSettings ? setShowFolderSettings(false) : openFolderSettings())}
          className="flex items-center gap-1.5 text-xs text-tg-hint hover:text-tg-text transition-colors"
        >
          <span>{showFolderSettings ? "▲" : "▼"}</span>
          <span>{t("notion_folders_settings")}</span>
        </button>

        {showFolderSettings && (
          <div className="mt-2 space-y-2">
            {SECTION_KEYS.map((key) => (
              <div key={key} className="flex items-center gap-2">
                <span className="text-base w-6 shrink-0">{sectionIcon(key)}</span>
                <input
                  type="text"
                  value={folderNames[key] ?? ""}
                  onChange={(e) => setFolderNames((prev) => ({ ...prev, [key]: e.target.value }))}
                  className="flex-1 px-3 py-2 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none"
                />
              </div>
            ))}
            <button
              onClick={saveFolderNames}
              disabled={savingFolders}
              className="w-full py-2 rounded-xl text-sm font-medium transition-opacity disabled:opacity-40"
              style={{
                background: "var(--tg-theme-button-color, #007aff)",
                color: "var(--tg-theme-button-text-color, #fff)",
              }}
            >
              {foldersSaved ? `✅ ${t("notion_folders_saved")}` : savingFolders ? "…" : t("notion_folders_save")}
            </button>
          </div>
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
