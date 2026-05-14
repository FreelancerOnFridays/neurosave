interface PageHeaderProps {
  title: string;
  subtitle?: string;
}

export function PageHeader({ title, subtitle }: PageHeaderProps) {
  return (
    <div className="mb-4">
      <h1 className="text-xl font-bold text-tg-text">{title}</h1>
      {subtitle && <p className="text-sm text-tg-hint mt-0.5">{subtitle}</p>}
    </div>
  );
}
