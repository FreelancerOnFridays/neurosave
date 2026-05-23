"use client";

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";

interface InfoTooltipProps {
  text: string;
}

export function InfoTooltip({ text }: InfoTooltipProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const btnRef = useRef<HTMLButtonElement>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  const handleToggle = () => {
    if (!open && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      const tooltipWidth = 256;
      const margin = 8;
      // Prefer aligning right edge of tooltip with right edge of button,
      // but clamp so tooltip stays within the viewport.
      const idealLeft = rect.right - tooltipWidth;
      const left = Math.max(margin, Math.min(idealLeft, window.innerWidth - tooltipWidth - margin));
      setPos({ top: rect.bottom + 8, left });
    }
    setOpen((v) => !v);
  };

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | TouchEvent) => {
      if (btnRef.current && !btnRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const closeOnScroll = () => setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    window.addEventListener("scroll", closeOnScroll, true);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
      window.removeEventListener("scroll", closeOnScroll, true);
    };
  }, [open]);

  return (
    <>
      <button
        ref={btnRef}
        onClick={handleToggle}
        className="w-5 h-5 rounded-full bg-tg-hint/20 text-tg-hint text-xs font-bold flex items-center justify-center hover:bg-tg-hint/30 transition-colors"
        aria-label="Info"
      >
        i
      </button>
      {mounted && createPortal(
        <AnimatePresence>
          {open && (
            <motion.div
              style={{ top: pos.top, left: pos.left, position: "fixed" }}
              className="w-64 bg-tg-secondary border border-tg-hint/10 rounded-2xl shadow-xl p-3 z-[9999]"
              initial={{ opacity: 0, scale: 0.85, transformOrigin: "top right" }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.85 }}
              transition={{ type: "spring", stiffness: 500, damping: 30 }}
            >
              <p className="text-xs text-tg-text leading-relaxed">{text}</p>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body
      )}
    </>
  );
}
