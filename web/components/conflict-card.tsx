"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Conflict } from "@/lib/types";
import { CONFLICT_LABEL, SEVERITY_LABEL } from "@/lib/utils";

const SEVERITY_DOT: Record<string, string> = {
  critical: "bg-critical",
  warning: "bg-warning",
  info: "bg-accent",
};

const SEVERITY_BAR: Record<string, string> = {
  critical: "bg-critical",
  warning: "bg-warning",
  info: "bg-accent",
};

const SEVERITY_TEXT: Record<string, string> = {
  critical: "text-critical",
  warning: "text-warning",
  info: "text-accent",
};

const SOURCE_LABEL: Record<string, string> = {
  meeting: "Meeting",
  github: "Repo",
  slack: "Slack",
  ticket: "Ticket",
};

export function ConflictCard({
  conflict,
  compact: _compact,
}: {
  conflict: Conflict;
  compact?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const sev = conflict.severity;
  const a = conflict.entity_a;
  const b = conflict.entity_b;
  const typeLabel = CONFLICT_LABEL[conflict.conflict_type] || conflict.conflict_type;

  return (
    <article className="relative panel mb-3 overflow-hidden">
      <div className={cn("severity-bar", SEVERITY_BAR[sev])} />

      {/* Header — type + severity dot + teams + chevron */}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full text-left px-5 py-4 flex items-start justify-between gap-4 hover:bg-surface/40 transition-colors"
        aria-expanded={expanded}
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2.5 mb-1.5">
            <span
              className={cn(
                "w-1.5 h-1.5 rounded-full shrink-0",
                SEVERITY_DOT[sev]
              )}
            />
            <span className="text-meta font-medium text-ink">
              {typeLabel}
            </span>
            <span
              className={cn(
                "text-eyebrow font-medium",
                SEVERITY_TEXT[sev]
              )}
            >
              {SEVERITY_LABEL[sev]}
            </span>
          </div>
          <div className="text-meta text-muted">
            <span className="text-ink font-medium">{a.team}</span>
            <span className="mx-2 text-dim">↔</span>
            <span className="text-ink font-medium">{b.team}</span>
          </div>
        </div>
        <ChevronDown
          size={15}
          strokeWidth={1.75}
          className={cn(
            "text-muted shrink-0 mt-1 transition-transform duration-150",
            expanded && "rotate-180"
          )}
        />
      </button>

      {/* Side-by-side entity blocks */}
      <div className="border-t border-rule grid grid-cols-1 sm:grid-cols-2 sm:divide-x sm:divide-rule">
        <EntityBlock
          source={a.source_type}
          team={a.team}
          name={a.name}
          description={a.description}
          expanded={expanded}
        />
        <div className="border-t border-rule sm:border-t-0">
          <EntityBlock
            source={b.source_type}
            team={b.team}
            name={b.name}
            description={b.description}
            expanded={expanded}
          />
        </div>
      </div>

      {/* Context — explanation. Truncated by default. */}
      {conflict.explanation && (
        <div className="border-t border-rule bg-surface/60 px-5 py-3">
          <p
            className={cn(
              "text-meta text-slate leading-relaxed",
              !expanded && "line-clamp-2"
            )}
          >
            {conflict.explanation}
          </p>
        </div>
      )}
    </article>
  );
}

function EntityBlock({
  source,
  team,
  name,
  description,
  expanded,
}: {
  source: string;
  team: string;
  name: string;
  description?: string;
  expanded?: boolean;
}) {
  return (
    <div className="px-5 py-4">
      <div className="flex items-baseline gap-2 mb-1.5">
        <span className="eyebrow">
          {SOURCE_LABEL[source] || source}
        </span>
        <span className="text-eyebrow text-dim">·</span>
        <span className="text-eyebrow text-muted">{team}</span>
      </div>
      <div
        className={cn(
          "text-body text-ink font-medium leading-snug",
          !expanded && "truncate"
        )}
        title={name}
      >
        {name}
      </div>
      {description && (
        <p
          className={cn(
            "text-meta text-slate mt-1.5 leading-relaxed",
            !expanded && "line-clamp-2"
          )}
        >
          {description}
        </p>
      )}
    </div>
  );
}
