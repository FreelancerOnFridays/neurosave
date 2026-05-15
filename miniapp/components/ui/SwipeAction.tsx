"use client";

import { type ReactNode, useRef, useState } from "react";
import { motion, useMotionValue, useTransform, animate } from "framer-motion";

export interface SwipeActionItem {
  label: string;
  color: string;
  textColor?: string;
  onClick: () => void;
}

interface SwipeActionProps {
  children: ReactNode;
  actions: SwipeActionItem[];
}

const ACTION_WIDTH = 72;

export function SwipeAction({ children, actions }: SwipeActionProps) {
  const totalWidth = actions.length * ACTION_WIDTH;
  const x = useMotionValue(0);
  const [revealed, setRevealed] = useState(false);
  const startX = useRef<number | null>(null);
  const isDragging = useRef(false);

  const handlePointerDown = (e: React.PointerEvent) => {
    startX.current = e.clientX;
    isDragging.current = false;
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (startX.current === null) return;
    const dx = e.clientX - startX.current;
    if (Math.abs(dx) > 4) isDragging.current = true;
    if (dx < 0) {
      x.set(Math.max(dx, -totalWidth - 20));
    } else if (revealed) {
      x.set(Math.min(dx - totalWidth, 0));
    }
  };

  const handlePointerUp = () => {
    if (!isDragging.current) {
      startX.current = null;
      return;
    }
    const current = x.get();
    if (current < -totalWidth / 2) {
      animate(x, -totalWidth, { type: "spring", stiffness: 400, damping: 30 });
      setRevealed(true);
    } else {
      animate(x, 0, { type: "spring", stiffness: 400, damping: 30 });
      setRevealed(false);
    }
    startX.current = null;
  };

  const close = () => {
    animate(x, 0, { type: "spring", stiffness: 400, damping: 30 });
    setRevealed(false);
  };

  return (
    <div className="relative overflow-hidden rounded-2xl">
      {/* Action buttons revealed on swipe-left */}
      <div
        className="absolute inset-y-0 right-0 flex"
        style={{ width: totalWidth }}
      >
        {actions.map((action, i) => (
          <button
            key={i}
            onClick={() => { close(); action.onClick(); }}
            className="flex-1 flex flex-col items-center justify-center text-xs font-semibold gap-1"
            style={{ backgroundColor: action.color, color: action.textColor ?? "#fff" }}
          >
            {action.label}
          </button>
        ))}
      </div>

      {/* Draggable content */}
      <motion.div
        style={{ x }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        className="relative z-10 touch-pan-y cursor-grab active:cursor-grabbing"
      >
        {children}
      </motion.div>
    </div>
  );
}
