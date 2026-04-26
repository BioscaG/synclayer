import { cn } from "@/lib/utils";
import type { Conflict } from "@/lib/types";
import { CONFLICT_LABEL, SEVERITY_LABEL } from "@/lib/utils";

const severityBar: Record<string, string> = {
  critical: "bg-critical",
  warning: "bg-warning",
  info: "bg-accent",
};

const severityTag: Record<string, string> = {
  critical: "tag-critical",
  warning: "tag-warning",
  info: "tag-accent",
};

const sourceLabel: Record<string, string> = {
  meeting: "Meeting",
  github: "Repository",
  slack: "Slack",
  ticket: "Ticket",
};

export function ConflictCard({
  conflict,
  compact = false,
}: {
  conflict: Conflict;
  compact?: boolean;
}) {
  const sev = conflict.severity;
  const cls = severityTag[sev] || "tag";
  const a = conflict.entity_a;
  const b = conflict.entity_b;

  return (
    <article
      className={cn(
        "relative panel pl-6 pr-6 py-5 mb-3",
        "border-rule"
      )}
    >
      <div className={cn("severity-bar", severityBar[sev])} />
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className={cls}>{CONFLICT_LABEL[conflict.conflict_type] || conflict.conflict_type}</span>
        <span className="tag">{SEVERITY_LABEL[sev]}</span>
        <span className="tag">{a.team} ↔ {b.team}</span>
        <span className="ml-auto text-meta font-mono text-muted">
          similarity · {conflict.similarity_score.toFixed(2)}
        </span>
      </div>

      <div className={cn("grid gap-4", compact ? "grid-cols-1" : "md:grid-cols-[1fr_auto_1fr] md:items-center")}>
        <EntityBlock label={`${a.team} · ${sourceLabel[a.source_type] || a.source_type}`} name={a.name} description={a.description} compact={compact} />
        {!compact && (
          <div className="hidden md:flex justify-center text-muted text-meta font-mono">vs</div>
        )}
        <EntityBlock label={`${b.team} · ${sourceLabel[b.source_type] || b.source_type}`} name={b.name} description={b.description} compact={compact} />
      </div>

      <p className="mt-4 text-body text-slate">{conflict.explanation}</p>

      <div className="mt-4 border-t border-rule pt-4">
        <div className="eyebrow mb-1.5 text-accent">Recommendation</div>
        <p className="text-body text-ink">{conflict.recommendation}</p>
      </div>
    </article>
  );
}

function EntityBlock({
  label,
  name,
  description,
  compact,
}: {
  label: string;
  name: string;
  description: string;
  compact: boolean;
}) {
  return (
    <div className="bg-surface border border-rule rounded p-4">
      <div className="eyebrow mb-2">{label}</div>
      <div className="font-serif text-lead leading-snug text-ink">{name}</div>
      <p className="text-meta text-slate mt-1.5 line-clamp-3">
        {compact ? description.slice(0, 140) : description.slice(0, 280)}
      </p>
    </div>
  );
}
