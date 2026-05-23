"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Task } from "@/lib/types";

interface NudgePreviewSheetProps {
  task: { task: Task; text: string } | null;
  onClose: () => void;
  onSend: (text: string) => Promise<void>;
}

export function NudgePreviewSheet({ task, onClose, onSend }: NudgePreviewSheetProps) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (task) setText(task.text);
  }, [task]);

  const handleSend = async () => {
    if (!text.trim() || sending) return;
    setSending(true);
    try {
      await onSend(text.trim());
    } finally {
      setSending(false);
    }
  };

  return (
    <AnimatePresence>
      {task && (
        <>
          <motion.div
            className="fixed inset-0 bg-black/40 z-40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            className="fixed bottom-0 left-0 right-0 z-50 bg-tg-bg rounded-t-3xl shadow-2xl"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", stiffness: 400, damping: 35 }}
          >
            <div className="p-6 pb-10">
              <div className="w-10 h-1 bg-tg-hint/30 rounded-full mx-auto mb-5" />

              <div className="flex items-center gap-2 mb-1">
                <span className="text-base">🔔</span>
                <h3 className="text-base font-semibold text-tg-text">Напоминание</h3>
              </div>

              {task.task.assignee_name && (
                <p className="text-xs text-tg-hint mb-4">
                  Кому: <span className="text-tg-text font-medium">{task.task.assignee_name}</span>
                </p>
              )}

              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={4}
                className="w-full text-sm bg-tg-secondary text-tg-text rounded-2xl px-4 py-3 outline-none border border-tg-hint/10 focus:border-tg-accent/40 resize-none mb-6"
                placeholder="Текст напоминания..."
              />

              <div className="flex gap-3">
                <button
                  onClick={onClose}
                  disabled={sending}
                  className="flex-1 py-3 rounded-2xl bg-tg-secondary text-tg-text text-sm font-medium disabled:opacity-40"
                >
                  Отмена
                </button>
                <button
                  onClick={handleSend}
                  disabled={!text.trim() || sending}
                  className="flex-1 py-3 rounded-2xl bg-tg-btn text-tg-btn-text text-sm font-semibold disabled:opacity-40"
                >
                  {sending ? "Отправка…" : "Отправить"}
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
