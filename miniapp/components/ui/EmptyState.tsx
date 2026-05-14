interface EmptyStateProps {
  icon?: string;
  message: string;
}

export function EmptyState({ icon = "📭", message }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-2 text-tg-hint">
      <span className="text-4xl">{icon}</span>
      <p className="text-sm text-center">{message}</p>
    </div>
  );
}
