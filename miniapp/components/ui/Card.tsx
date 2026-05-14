import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}

export function Card({ children, className = "", onClick }: CardProps) {
  return (
    <div
      className={`bg-tg-secondary rounded-2xl p-4 shadow-sm ${className}`}
      onClick={onClick}
    >
      {children}
    </div>
  );
}
