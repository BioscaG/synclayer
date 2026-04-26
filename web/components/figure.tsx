import { cn } from "@/lib/utils";

interface FigureProps {
  label: string;
  value: string | number;
  hint?: string;
  trend?: "up" | "down" | "flat";
  emphasis?: "default" | "critical" | "warning" | "success";
  size?: "default" | "lg";
}

export function Figure({
  label,
  value,
  hint,
  emphasis = "default",
  size = "default",
}: FigureProps) {
  const valueClass = cn(
    "figure-num font-medium tracking-tight",
    size === "lg" ? "text-hero" : "text-figure",
    emphasis === "critical" && "text-critical",
    emphasis === "warning"  && "text-warning",
    emphasis === "success"  && "text-success"
  );
  return (
    <div>
      <div className="eyebrow mb-3">{label}</div>
      <div className={valueClass}>{value}</div>
      {hint && <div className="text-meta text-muted mt-2 font-mono">{hint}</div>}
    </div>
  );
}
