import { cn } from "@/lib/utils";

interface SectionProps {
  eyebrow?: string;
  title: string;
  description?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function Section({
  eyebrow,
  title,
  description,
  right,
  children,
  className,
}: SectionProps) {
  return (
    <section className={cn("rule-top mt-12", className)}>
      <header className="flex items-end justify-between gap-6 mb-6">
        <div className="max-w-2xl">
          {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
          <h2 className="display text-h2">{title}</h2>
          {description && (
            <p className="text-body text-slate mt-2">{description}</p>
          )}
        </div>
        {right && <div className="shrink-0">{right}</div>}
      </header>
      {children}
    </section>
  );
}
