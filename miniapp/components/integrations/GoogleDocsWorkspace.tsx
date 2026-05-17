"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import type { DriveFile } from "@/lib/types";

function FileIcon({ type }: { type: string }) {
  return <span className="text-base leading-none">{type === "sheet" ? "📊" : "📄"}</span>;
}

function formatDate(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return "сегодня";
  if (days === 1) return "вчера";
  return d.toLocaleDateString("ru", { day: "numeric", month: "short" });
}

type CreateMode = "doc" | "sheet" | null;

export function GoogleDocsWorkspace() {
  const { t } = useLang();
  const [createMode, setCreateMode] = useState<CreateMode>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createdUrl, setCreatedUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: files, mutate } = useSWR<DriveFile[]>(
    "/api/integrations/google-docs/files",
    api.integrations.googleDocsFiles,
    { refreshInterval: 30_000 }
  );

  async function handleCreate() {
    if (!name.trim() || !createMode || creating) return;
    setCreating(true);
    setError(null);
    setCreatedUrl(null);
    try {
      const res = await api.integrations.googleDocsCreate(name.trim(), createMode);
      setCreatedUrl(res.url);
      setName("");
      setCreateMode(null);
      mutate();
    } catch (e) {
      setError(String(e));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <button
          onClick={() => { setCreateMode("doc"); setCreatedUrl(null); setError(null); }}
          className="flex-1 py-2.5 rounded-xl text-sm font-medium border transition-colors"
          style={
            createMode === "doc"
              ? { background: "var(--tg-theme-button-color, #007aff)", color: "var(--tg-theme-button-text-color, #fff)", borderColor: "transparent" }
              : { borderColor: "rgba(var(--tg-hint-rgb, 128,128,128), 0.3)", color: "var(--tg-theme-text-color)" }
          }
        >
          📄 {t("gdocs_new_doc")}
        </button>
        <button
          onClick={() => { setCreateMode("sheet"); setCreatedUrl(null); setError(null); }}
          className="flex-1 py-2.5 rounded-xl text-sm font-medium border transition-colors"
          style={
            createMode === "sheet"
              ? { background: "var(--tg-theme-button-color, #007aff)", color: "var(--tg-theme-button-text-color, #fff)", borderColor: "transparent" }
              : { borderColor: "rgba(var(--tg-hint-rgb, 128,128,128), 0.3)", color: "var(--tg-theme-text-color)" }
          }
        >
          📊 {t("gdocs_new_sheet")}
        </button>
      </div>

      {createMode && (
        <div className="flex gap-2">
          <input
            type="text"
            placeholder={t("gdocs_name_placeholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            autoFocus
            className="flex-1 px-3 py-2.5 text-sm rounded-xl border border-tg-hint/20 bg-transparent text-tg-text outline-none focus:border-tg-accent/50 transition-colors"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !name.trim()}
            className="shrink-0 px-4 py-2 rounded-xl text-sm font-medium transition-opacity disabled:opacity-40"
            style={{
              background: "var(--tg-theme-button-color, #007aff)",
              color: "var(--tg-theme-button-text-color, #fff)",
            }}
          >
            {creating ? "…" : t("gdocs_create")}
          </button>
        </div>
      )}

      {createdUrl && (
        <a
          href={createdUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-xs text-center py-1.5 rounded-xl font-medium"
          style={{ color: "var(--tg-theme-accent-text-color, #007aff)" }}
        >
          ✅ Создано — Открыть →
        </a>
      )}
      {error && <p className="text-xs text-center text-red-500">❌ {error}</p>}

      {files && files.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-tg-hint uppercase tracking-wide mb-2">
            {t("gdocs_recent")}
          </p>
          <div className="space-y-1">
            {files.map((file) => (
              <a
                key={file.id}
                href={file.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-tg-secondary transition-colors group"
              >
                <FileIcon type={file.type} />
                <span className="flex-1 text-sm text-tg-text truncate">{file.name}</span>
                <span className="text-xs text-tg-hint shrink-0">{formatDate(file.modified_time)}</span>
                <span className="text-tg-hint opacity-0 group-hover:opacity-100 transition-opacity text-sm">→</span>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
