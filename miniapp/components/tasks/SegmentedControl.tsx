"use client";

import { motion } from "framer-motion";

interface SegmentedControlProps {
  segments: string[];
  activeIndex: number;
  onChange: (index: number) => void;
}

export function SegmentedControl({ segments, activeIndex, onChange }: SegmentedControlProps) {
  return (
    <div className="relative flex bg-tg-secondary rounded-2xl p-1 mb-4">
      <motion.div
        className="absolute top-1 bottom-1 rounded-xl bg-tg-bg shadow-sm"
        layoutId="seg-pill"
        style={{ width: `${100 / segments.length}%`, left: `${(activeIndex * 100) / segments.length}%` }}
        transition={{ type: "spring", stiffness: 400, damping: 30 }}
      />
      {segments.map((label, i) => (
        <button
          key={i}
          onClick={() => onChange(i)}
          className="relative z-10 flex-1 py-2 text-sm font-medium transition-colors rounded-xl"
          style={{ color: i === activeIndex ? "var(--tg-theme-text-color)" : "var(--tg-theme-hint-color)" }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
