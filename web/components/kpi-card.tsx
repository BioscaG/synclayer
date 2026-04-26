import { cn } from "@/lib/utils";
import { Sparkline } from "@/components/charts/sparkline";

type Tone = "default" | "critical" | "warning" | "success" | "accent";

interface KpiCardProps {
  label: string;
  value: string | number;
  hint?: string;
  delta?: { value: number; tone?: Tone };
  trend?: number[];
  tone?: Tone;
}

const TONE_TEXT: Record<Tone, string> = {
  default: "text-ink",
  critical: "text-critical",
  warning: "text-warning",
  success: "text-success",
  accent: "text-accent",
};

export function KpiCard({
  label,
  value,
  hint,
  delta,
  trend,
  tone = "default",
}: KpiCardProps) {
  return (
    <div className="panel p-5 flex flex-col gap-3.5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="eyebrow mb-2.5">{label}</div>
          <div
            className={cn(
              "figure-num text-figure leading-none",
              TONE_TEXT[tone]
            )}
          >
            {value}
          </div>
        </div>
        {delta && (
          <span
            className={cn(
              "tag",
              delta.value > 0 && "tag-critical",
              delta.value < 0 && "tag-success",
              delta.value === 0 && ""
            )}
            title="vs previous period"
          >
            {delta.value > 0 ? "+" : ""}
            {delta.value}
          </span>
        )}
      </div>

      {trend && trend.length > 1 && (
        <div className="-mx-1">
          <Sparkline
            data={trend}
            tone={tone === "default" ? "accent" : tone}
            height={32}
          />
        </div>
      )}

      {hint && (
        <div className="text-meta text-muted font-mono leading-tight">{hint}</div>
      )}
    </div>
  );
}
