"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useLang } from "@/contexts/LanguageContext";

interface TimePickerSheetProps {
  open: boolean;
  title: string;
  initialValue?: string;
  onConfirm: (isoTime: string) => void;
  onCancel: () => void;
}

export function TimePickerSheet({
  open,
  title,
  initialValue,
  onConfirm,
  onCancel,
}: TimePickerSheetProps) {
  const { t } = useLang();
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      if (initialValue) {
        const dt = new Date(initialValue);
        const pad = (n: number) => String(n).padStart(2, "0");
        const local = new Date(dt.getTime() - dt.getTimezoneOffset() * 60000);
        setValue(local.toISOString().slice(0, 16));
      } else {
        const now = new Date();
        now.setMinutes(now.getMinutes() + 30);
        const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
        setValue(local.toISOString().slice(0, 16));
      }
      setTimeout(() => inputRef.current?.focus(), 200);
    }
  }, [open, initialValue]);

  const handleConfirm = () => {
    if (!value) return;
    const dt = new Date(value);
    onConfirm(dt.toISOString());
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 bg-black/40 z-40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onCancel}
          />
          <motion.div
            className="fixed bottom-0 left-0 right-0 z-50 bg-tg-bg rounded-t-3xl p-6 pb-10 shadow-2xl"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", stiffness: 400, damping: 35 }}
          >
            <div className="w-10 h-1 bg-tg-hint/30 rounded-full mx-auto mb-5" />
            <h3 className="text-base font-semibold text-tg-text mb-5">{title}</h3>
            <input
              ref={inputRef}
              type="datetime-local"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="w-full text-sm bg-tg-secondary text-tg-text rounded-2xl px-4 py-3 outline-none border border-tg-hint/10 focus:border-tg-accent/40 mb-6"
            />
            <div className="flex gap-3">
              <button
                onClick={onCancel}
                className="flex-1 py-3 rounded-2xl bg-tg-secondary text-tg-text text-sm font-medium"
              >
                {t("reminder_cancel")}
              </button>
              <button
                onClick={handleConfirm}
                disabled={!value}
                className="flex-1 py-3 rounded-2xl bg-tg-btn text-tg-btn-text text-sm font-semibold disabled:opacity-40"
              >
                {t("reminder_confirm")}
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
