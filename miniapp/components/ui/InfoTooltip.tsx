"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface InfoTooltipProps {
  text: string;
}

export function InfoTooltip({ text }: InfoTooltipProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative inline-flex">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-5 h-5 rounded-full bg-tg-hint/20 text-tg-hint text-xs font-bold flex items-center justify-center hover:bg-tg-hint/30 transition-colors"
        aria-label="Info"
      >
        i
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            className="absolute top-7 right-0 w-64 bg-tg-secondary border border-tg-hint/10 rounded-2xl shadow-xl p-3 z-50"
            initial={{ opacity: 0, scale: 0.85, transformOrigin: "top right" }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.85 }}
            transition={{ type: "spring", stiffness: 500, damping: 30 }}
          >
            <p className="text-xs text-tg-text leading-relaxed">{text}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
