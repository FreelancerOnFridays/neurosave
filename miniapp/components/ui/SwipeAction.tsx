"use client";

import { type ReactNode, useRef, useState } from "react";

interface SwipeActionProps {
  children: ReactNode;
  onDelete: () => void;
  label?: string;
}

const THRESHOLD = 80;

export function SwipeAction({
  children,
  onDelete,
  label = "Удалить",
}: SwipeActionProps) {
  const [offset, setOffset] = useState(0);
  const [swiped, setSwiped] = useState(false);
  const startX = useRef<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const onPointerDown = (e: React.PointerEvent) => {
    startX.current = e.clientX;
    containerRef.current?.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (startX.current === null) return;
    const dx = e.clientX - startX.current;
    if (dx < 0) setOffset(Math.max(dx, -THRESHOLD - 20));
  };

  const onPointerUp = () => {
    if (offset < -THRESHOLD) {
      setSwiped(true);
      setOffset(-THRESHOLD);
    } else {
      setSwiped(false);
      setOffset(0);
    }
    startX.current = null;
  };

  const handleDelete = () => {
    setOffset(0);
    setSwiped(false);
    onDelete();
  };

  return (
    <div className="relative overflow-hidden rounded-2xl">
      <div
        className="absolute inset-y-0 right-0 flex items-center justify-end px-4 bg-tg-destructive rounded-2xl"
        style={{ minWidth: THRESHOLD }}
      >
        <button
          onClick={handleDelete}
          className="text-white text-sm font-medium"
        >
          {label}
        </button>
      </div>
      <div
        ref={containerRef}
        style={{
          transform: `translateX(${offset}px)`,
          transition: startX.current === null ? "transform 0.2s ease" : "none",
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        className="relative z-10 touch-pan-y"
      >
        {children}
      </div>
    </div>
  );
}
