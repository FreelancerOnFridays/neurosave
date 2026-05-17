"use client";

import { useState } from "react";
import { api } from "@/lib/api";

const SECTIONS = [
  { value: "capture", label: "📝 Заметки" },
  { value: "task", label: "✅ Задачи" },
  { value: "meeting_notes", label: "🤝 Встречи" },
];

export function NotionQuickCapture() {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [section, setSection] = useState("capture");
  const [loading, setLoading] = useState(false);
  const [savedUrl, setSavedUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-3 pt-3 border-t border-tg-hint/10 space-y-2">
      <input
        type="text"
        placeholder="Заголовок..."
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="w-full px-3 py-2 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors"
      />
      <textarea
        placeholder="Текст заметки..."
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={3}
        className="w-full px-3 py-2 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors resize-none"
      />
      <div className="flex items-center gap-2">
        <select
          value={section}
          onChange={(e) => setSection(e.target.value)}
          className="flex-1 px-3 py-2 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none"
        >
          {SECTIONS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
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
          {loading ? "…" : "Сохранить"}
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
          ✅ Сохранено — Открыть в Notion →
        </a>
      )}
      {error && (
        <p className="text-xs text-center" style={{ color: "var(--tg-theme-destructive-text-color, #ff3b30)" }}>
          ❌ {error}
        </p>
      )}
    </div>
  );
}
