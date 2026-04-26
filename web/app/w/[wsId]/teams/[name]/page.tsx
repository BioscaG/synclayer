"use client";

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api as apiFactory } from "@/lib/api";
import type { Entity, TeamDetail } from "@/lib/types";
import { ConflictCard } from "@/components/conflict-card";
import { Section } from "@/components/section";
import { formatRelative, teamColor } from "@/lib/utils";

const SOURCE_LABEL: Record<string, string> = {
  meeting: "Meeting",
  github: "Repository",
  slack: "Slack",
  ticket: "Ticket",
};

export default function TeamDetailPage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  const { name } = use(params);
  const routeParams = useParams<{ wsId: string }>();
  const wsId = routeParams?.wsId || "";
  const api = useMemo(() => apiFactory(wsId), [wsId]);

  const [data, setData] = useState<TeamDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    api
      .team(decodeURIComponent(name))
      .then(setData)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // The poller refreshes sources every minute on the backend; mirror that
    // cadence on the detail page so stats stay current passively.
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [name, api]);

  if (loading || !data) return <p className="text-meta text-muted">Loading…</p>;

  const team = data.team;
  const color = data.config?.color || teamColor(team);
  const summary = data.summary;
  const t_cfg = data.config || { repos: [], slack_channels: [], ticket_paths: [] };

  return (
    <div>
      <Link href={`/w/${wsId}/teams`} className="text-meta text-muted hover:text-ink">
        ← All teams
      </Link>

      <header className="mt-4 pb-6 border-b border-rule">
        <div className="flex items-center gap-3 mb-3">
          <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: color }} />
          <span className="eyebrow">Team</span>
        </div>
        <h1 className="display text-h1 capitalize">{team}</h1>
        <p className="text-body text-slate mt-2">
          {summary.entities} entities tracked · {summary.active_work} active work items ·{" "}
          {summary.conflicts} cross-team conflicts
          {summary.critical_conflicts > 0 && (
            <span className="text-critical font-medium"> · {summary.critical_conflicts} critical</span>
          )}
        </p>
      </header>

      {/* Active work / Concerns / Sources */}
      <div className="grid lg:grid-cols-[1.4fr_1fr_1fr] gap-12 mt-12">
        <div>
          <SubHeader eyebrow="Active work" title="What the team is shipping" hint={`${data.active_work.length}`} />
          {data.active_work.length === 0 ? (
            <p className="text-body text-slate mt-4">No active work captured yet.</p>
          ) : (
            <ul className="mt-2 divide-y divide-rule">
              {data.active_work.map((e) => (
                <EntityRow key={e.id} entity={e} />
              ))}
            </ul>
          )}
        </div>

        <div>
          <SubHeader eyebrow="Concerns & dependencies" title="Risks on record" />
          <ul className="mt-2 divide-y divide-rule">
            {[...data.concerns, ...data.dependencies].map((e) => (
              <EntityRow key={e.id} entity={e} compact />
            ))}
            {data.concerns.length + data.dependencies.length === 0 && (
              <li className="py-3 text-meta text-muted">None on record.</li>
            )}
          </ul>
        </div>

        <div>
          <SubHeader eyebrow="Sources" title="Connected channels" />
          <SourceList
            label="Repositories"
            kind="repo"
            items={t_cfg.repos || []}
            states={data.source_states}
          />
          <SourceList
            label="Slack channels"
            kind="slack"
            items={t_cfg.slack_channels || []}
            states={data.source_states}
          />
          <SourceList
            label="Ticket files"
            kind="ticket"
            items={t_cfg.ticket_paths || []}
            states={data.source_states}
          />
          {(t_cfg.repos.length + t_cfg.slack_channels.length + t_cfg.ticket_paths.length) === 0 && (
            <p className="text-meta text-muted mt-2">
              No sources connected.{" "}
              <Link href={`/w/${wsId}/teams`} className="text-accent hover:underline">
                Connect repositories, Slack channels and ticket files →
              </Link>
            </p>
          )}
        </div>
      </div>

      {/* Conflicts */}
      <Section
        eyebrow="Cross-team friction"
        title={`Conflicts involving ${team}`}
        right={<span className="text-meta text-muted font-mono">{data.conflicts.length}</span>}
      >
        {data.conflicts.length === 0 ? (
          <p className="text-body text-slate">
            No cross-team conflicts on record. They&rsquo;ll surface on the next meeting analysis.
          </p>
        ) : (
          <div>
            {data.conflicts.map((c) => (
              <ConflictCard key={c.id} conflict={c} />
            ))}
          </div>
        )}
      </Section>

      {/* Internal duplications */}
      <Section
        eyebrow="Inside the team"
        title="Internal duplication warnings"
        description="Two work items from this team that look essentially the same. Merge them or pick a single owner."
      >
        {data.internal_duplications.length === 0 ? (
          <p className="text-body text-slate">No internal redundancy detected.</p>
        ) : (
          <div className="grid lg:grid-cols-2 gap-4">
            {data.internal_duplications.map((p, i) => (
              <article key={i} className="panel p-5">
                <div className="flex items-center gap-2 mb-3">
                  <span className="tag tag-warning">Efficiency</span>
                  <span className="text-meta text-muted font-mono ml-auto">
                    {p.similarity.toFixed(2)}
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr] sm:items-center gap-3">
                  <DupBlock e={p.entity_a} />
                  <span className="text-muted font-mono text-meta hidden sm:block">≈</span>
                  <DupBlock e={p.entity_b} />
                </div>
              </article>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

function SubHeader({
  eyebrow,
  title,
  hint,
}: {
  eyebrow: string;
  title: string;
  hint?: string;
}) {
  return (
    <div>
      <div className="eyebrow mb-2">{eyebrow}</div>
      <div className="flex items-baseline justify-between">
        <h3 className="display text-h3">{title}</h3>
        {hint && <span className="text-meta text-muted font-mono">{hint}</span>}
      </div>
    </div>
  );
}

function EntityRow({ entity, compact }: { entity: Entity; compact?: boolean }) {
  return (
    <li className="py-4">
      <div className="flex items-center gap-2 mb-1">
        <span className="tag">{entity.decision_type}</span>
        <span className="text-meta text-muted font-mono">
          {SOURCE_LABEL[entity.source_type]}
        </span>
        <span className="text-meta text-muted font-mono ml-auto">
          conf · {entity.confidence.toFixed(2)}
        </span>
      </div>
      <div className="font-serif text-lead leading-snug">{entity.name}</div>
      {!compact && entity.description && (
        <p className="text-body text-slate mt-1.5 line-clamp-2">
          {entity.description}
        </p>
      )}
    </li>
  );
}

function SourceList({
  label,
  kind,
  items,
  states,
}: {
  label: string;
  kind: "repo" | "slack" | "ticket";
  items: string[];
  states: Record<string, any>;
}) {
  if (items.length === 0) return null;
  return (
    <div className="mt-4">
      <div className="eyebrow mb-2">{label}</div>
      <ul className="space-y-2">
        {items.map((it) => {
          const state = states[`${kind}::${it}`];
          return (
            <li
              key={it}
              className="text-meta font-mono flex items-center justify-between gap-3 panel-soft px-3 py-2"
            >
              <span className="truncate">{it}</span>
              <span className="text-muted shrink-0 text-eyebrow">
                {state?.initialized ? `synced ${formatRelative(state.last_synced_at)}` : "not synced"}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function DupBlock({ e }: { e: Entity }) {
  return (
    <div className="bg-surface rounded p-3">
      <div className="eyebrow mb-1.5">{e.source_type}</div>
      <div className="font-serif text-body leading-snug">{e.name}</div>
      <p className="text-meta text-slate mt-1 line-clamp-2">{e.description}</p>
    </div>
  );
}
