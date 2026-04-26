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
  meeting: "meeting",
  github: "repo",
  slack: "slack",
  ticket: "ticket",
};

export function ConflictCard({
  conflict,
  compact = false,
}: {
  conflict: Conflict;
  compact?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const sev = conflict.severity;
  const a = conflict.entity_a;
  const b = conflict.entity_b;
  const typeLabel = (
    CONFLICT_LABEL[conflict.conflict_type] || conflict.conflict_type
  ).toLowerCase();

  if (compact) {
    return (
      <article className="relative panel pl-4 pr-4 py-3 mb-2 overflow-hidden">
        <div className={cn("severity-bar", SEVERITY_BAR[sev])} />

        <div className="flex items-center gap-2.5 min-w-0 mb-2">
          <span
            className={cn("w-1.5 h-1.5 rounded-full shrink-0", SEVERITY_DOT[sev])}
          />
          <span className="font-mono text-meta uppercase tracking-wider text-ink shrink-0">
            {typeLabel}
          </span>
          <span className="text-dim text-meta shrink-0">/</span>
          <span
            className={cn(
              "font-mono text-eyebrow font-medium uppercase tracking-wider shrink-0",
              SEVERITY_TEXT[sev]
            )}
          >
            {SEVERITY_LABEL[sev]}
          </span>
          <span className="ml-auto font-mono text-meta text-muted truncate lowercase">
            {a.team}
            <span className="text-dim mx-1.5">↔</span>
            {b.team}
          </span>
        </div>

        <div className="space-y-1">
          <CompactEntity source={a.source_type} name={a.name} />
          <CompactEntity source={b.source_type} name={b.name} />
        </div>
      </article>
    );
  }

  return (
    <article className="relative panel mb-3 overflow-hidden">
      <div className={cn("severity-bar", SEVERITY_BAR[sev])} />

      {/* Header — click anywhere here to expand/collapse. */}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full text-left px-5 py-3.5 flex items-start justify-between gap-4 hover:bg-surface/50 transition-colors"
        aria-expanded={expanded}
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2.5 mb-1">
            <span
              className={cn(
                "w-1.5 h-1.5 rounded-full shrink-0",
                SEVERITY_DOT[sev]
              )}
            />
            <span className="font-mono text-meta uppercase tracking-wider text-ink">
              {typeLabel}
            </span>
            <span className="text-dim text-meta">/</span>
            <span
              className={cn(
                "font-mono text-eyebrow font-medium uppercase tracking-wider",
                SEVERITY_TEXT[sev]
              )}
            >
              {SEVERITY_LABEL[sev]}
            </span>
          </div>
          <div className="font-mono text-meta text-muted lowercase">
            {a.team}
            <span className="text-dim mx-1.5">↔</span>
            {b.team}
          </div>
        </div>
        <ChevronDown
          size={16}
          strokeWidth={2}
          className={cn(
            "text-muted shrink-0 mt-1 transition-transform duration-150",
            expanded && "rotate-180"
          )}
        />
      </button>

      {/* The two entities side by side. */}
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

      {/* Context — Claude's explanation. Truncated by default; full when expanded. */}
      {conflict.explanation && (
        <div className="border-t border-rule bg-surface px-5 py-3.5">
          <p
            className={cn(
              "text-meta text-slate leading-relaxed",
              !expanded && "line-clamp-3"
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
    <div className="px-5 py-3.5">
      <div className="font-mono text-eyebrow font-medium uppercase tracking-wider text-muted mb-1.5">
        {SOURCE_LABEL[source] || source}
        <span className="text-dim mx-1.5">·</span>
        <span className="lowercase">{team}</span>
      </div>
      <div
        className={cn("text-body text-ink leading-snug", !expanded && "truncate")}
        title={name}
      >
        {name}
      </div>
      {description && (
        <p
          className={cn(
            "text-meta text-muted mt-1.5 leading-relaxed",
            !expanded && "line-clamp-2"
          )}
        >
          {description}
        </p>
      )}
    </div>
  );
}

function CompactEntity({ source, name }: { source: string; name: string }) {
  return (
    <div className="flex items-baseline gap-2.5 min-w-0">
      <span className="font-mono text-eyebrow font-medium uppercase tracking-wider text-muted w-14 shrink-0">
        {SOURCE_LABEL[source] || source}
      </span>
      <span className="text-meta text-ink truncate" title={name}>
        {name}
      </span>
    </div>
  );
}
