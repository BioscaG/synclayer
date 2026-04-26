"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowUpRight } from "lucide-react";
import { api as apiFactory } from "@/lib/api";
import type {
  Conflict,
  History,
  IngestEvent,
  OverviewStats,
} from "@/lib/types";
import { ConflictCard } from "@/components/conflict-card";
import { Empty } from "@/components/empty";
import { Sparkline } from "@/components/charts/sparkline";
import { StackedAreaChart } from "@/components/charts/area-chart";
import { CONFLICT_LABEL, cn, formatRelative } from "@/lib/utils";

const TYPE_COLORS: Record<string, string> = {
  duplication: "#B91C1C",
  contradiction: "#B45309",
  dependency: "#1E3A8A",
  say_vs_do: "#0F1419",
};

const SOURCE_LABEL: Record<string, string> = {
  meeting: "meeting",
  github: "repo",
  slack: "slack",
  ticket: "ticket",
};

export default function OverviewPage() {
  const params = useParams<{ wsId: string }>();
  const wsId = params?.wsId || "";
  const api = useMemo(() => apiFactory(wsId), [wsId]);

  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [events, setEvents] = useState<IngestEvent[]>([]);
  const [history, setHistory] = useState<History | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.stats(), api.conflicts(), api.events(), api.history(14)])
      .then(([s, c, e, h]) => {
        setStats(s);
        setConflicts(c);
        setEvents(e);
        setHistory(h);
      })
      .finally(() => setLoading(false));

    const id = setInterval(() => {
      api.stats().then(setStats).catch(() => {});
      api.events().then(setEvents).catch(() => {});
    }, 10_000);
    return () => clearInterval(id);
  }, [api]);

  if (loading) return <SkeletonOverview />;
  if (!stats)
    return (
      <Empty
        title="Backend unreachable"
        description="Start the FastAPI server: uvicorn backend.main:app --reload --port 8000"
      />
    );

  const empty = stats.entities === 0;
  const critical = conflicts.filter((c) => c.severity === "critical").length;
  const warning = conflicts.filter((c) => c.severity === "warning").length;
  const teamCount = Object.keys(stats.by_team).length;

  // Trends from history
  const dailyEntities = (history?.daily_entities || []).map(
    (d) => d.meeting + d.github + d.slack + d.ticket
  );
  const conflictTrend = (history?.conflict_snapshots || []).map((s) => s.total);
  const criticalTrend = (history?.conflict_snapshots || []).map(
    (s) => s.critical
  );

  // Conflicts by type
  const byType: Record<string, number> = {};
  for (const c of conflicts) byType[c.conflict_type] = (byType[c.conflict_type] || 0) + 1;
  const totalConflicts = conflicts.length || 1;
  const breakdown = Object.entries(byType)
    .map(([t, v]) => ({
      type: t,
      label: CONFLICT_LABEL[t] || t,
      count: v,
      pct: v / totalConflicts,
      color: TYPE_COLORS[t] || "#5A6068",
    }))
    .sort((a, b) => b.count - a.count);

  // Activity: ONE line chart, total daily entities (monochrome)
  const activitySeries = (history?.daily_entities || []).map((d) => ({
    date: d.date,
    total: d.meeting + d.github + d.slack + d.ticket,
  }));

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <header className="flex items-end justify-between gap-6 pt-2">
        <div>
          <div className="eyebrow mb-2">Operations</div>
          <h1 className="display text-h1">Overview</h1>
        </div>
        <div className="text-meta text-muted text-right">
          {stats.last_meeting_analysis_at ? (
            <>
              <div>Last analysis</div>
              <div className="text-ink data-mono">
                {formatRelative(stats.last_meeting_analysis_at)}
              </div>
            </>
          ) : (
            <div>No meeting analysed yet</div>
          )}
        </div>
      </header>

      {empty ? (
        <Empty
          title="Nothing in memory yet"
          description="Add your first team and connect its sources to start mapping work across the company."
          action={
            <Link href={`/w/${wsId}/teams`} className="btn btn-primary">
              Configure teams
            </Link>
          }
        />
      ) : (
        <>
          {/* HERO row — open conflicts on the left, stat strip on the right */}
          <div className="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-4">
            <HeroConflicts
              total={conflicts.length}
              critical={critical}
              warning={warning}
              trend={conflictTrend}
              criticalTrend={criticalTrend}
              wsId={wsId}
            />

            <div className="grid grid-rows-4 gap-3">
              <StatRow
                label="Entities in memory"
                value={stats.entities}
                hint={Object.entries(stats.by_source)
                  .map(([k, v]) => `${v} ${SOURCE_LABEL[k] || k}`)
                  .join(" · ")}
                trend={dailyEntities}
              />
              <StatRow
                label="Pending since meeting"
                value={stats.pending_non_meeting_entities}
                hint={
                  stats.pending_non_meeting_entities > 0
                    ? "considered next analysis"
                    : "all caught up"
                }
                tone={
                  stats.pending_non_meeting_entities > 0
                    ? "warning"
                    : "success"
                }
              />
              <StatRow
                label="Teams active"
                value={teamCount}
                hint={
                  Object.keys(stats.by_team).slice(0, 3).join(" · ") || undefined
                }
              />
              <StatRow
                label="Cached judgments"
                value={stats.pair_cache}
                hint="Claude calls saved"
              />
            </div>
          </div>

          {/* Activity timeline + type breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-4">
            <Panel title="Activity" hint="last 14 days · entities ingested">
              {activitySeries.length > 1 ? (
                <StackedAreaChart
                  data={activitySeries}
                  series={[
                    {
                      key: "total",
                      label: "Entities",
                      color: "#1E3A8A",
                    },
                  ]}
                  height={220}
                />
              ) : (
                <p className="text-meta text-muted py-12 text-center">
                  Not enough history yet.
                </p>
              )}
            </Panel>

            <Panel
              title="By type"
              hint={`${conflicts.length} conflict${conflicts.length === 1 ? "" : "s"}`}
            >
              {breakdown.length === 0 ? (
                <p className="text-meta text-muted py-8 text-center">
                  No conflicts surfaced yet.
                </p>
              ) : (
                <div className="space-y-2.5 mt-1">
                  {breakdown.map((b) => (
                    <BreakdownBar key={b.type} {...b} />
                  ))}
                </div>
              )}
            </Panel>
          </div>

          {/* Top conflicts + activity feed */}
          <div className="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-4">
            <Panel
              title="Top open conflicts"
              hint={`${conflicts.length} total`}
              right={
                conflicts.length > 0 ? (
                  <Link
                    href={`/w/${wsId}/conflicts`}
                    className="text-meta text-accent inline-flex items-center gap-1 hover:underline"
                  >
                    View all
                    <ArrowUpRight size={12} strokeWidth={1.75} />
                  </Link>
                ) : undefined
              }
            >
              {conflicts.length === 0 ? (
                <p className="text-meta text-muted">
                  No conflicts surfaced yet — ingest a meeting to trigger
                  analysis.
                </p>
              ) : (
                <div className="-mb-2 mt-1">
                  {conflicts.slice(0, 3).map((c) => (
                    <ConflictCard key={c.id} conflict={c} compact />
                  ))}
                </div>
              )}
            </Panel>

            <Panel title="Live" hint={`last ${Math.min(events.length, 8)} events`}>
              <ul className="-mx-5 mt-1 divide-y divide-rule">
                {events.slice(0, 8).map((ev) => (
                  <li
                    key={ev.id}
                    className="flex items-center justify-between gap-3 px-5 py-2"
                  >
                    <div className="flex items-baseline gap-2.5 min-w-0">
                      <span className="text-eyebrow text-muted shrink-0 w-12 truncate">
                        {SOURCE_LABEL[ev.source_type] || ev.source_type}
                      </span>
                      <span className="text-meta truncate">{ev.team}</span>
                    </div>
                    <div className="data-mono text-eyebrow text-muted shrink-0">
                      {formatRelative(ev.timestamp)}
                    </div>
                  </li>
                ))}
                {events.length === 0 && (
                  <li className="px-5 py-4 text-meta text-muted">
                    No activity yet.
                  </li>
                )}
              </ul>
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}

function HeroConflicts({
  total,
  critical,
  warning,
  trend,
  criticalTrend,
  wsId,
}: {
  total: number;
  critical: number;
  warning: number;
  trend: number[];
  criticalTrend: number[];
  wsId: string;
}) {
  const tone =
    critical > 0 ? "critical" : total > 0 ? "warning" : "success";
  return (
    <article className="panel-hero relative overflow-hidden">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="eyebrow">Open conflicts</div>
        {total > 0 && (
          <Link
            href={`/w/${wsId}/conflicts`}
            className="text-eyebrow text-accent hover:underline inline-flex items-center gap-1"
          >
            Drill down
            <ArrowUpRight size={11} strokeWidth={1.75} />
          </Link>
        )}
      </div>

      <div className="flex items-end gap-6 flex-wrap">
        <div
          className={cn(
            "figure-num text-hero leading-none",
            tone === "critical" && "text-critical",
            tone === "warning" && "text-warning",
            tone === "success" && "text-success"
          )}
        >
          {total}
        </div>
        <div className="flex flex-col gap-1 text-meta pb-2 min-w-0">
          <div className="text-ink">
            <span
              className={cn(
                "data-mono font-semibold",
                critical > 0 ? "text-critical" : "text-muted"
              )}
            >
              {critical}
            </span>{" "}
            <span className="text-muted">critical</span>
          </div>
          <div className="text-ink">
            <span
              className={cn(
                "data-mono font-semibold",
                warning > 0 ? "text-warning" : "text-muted"
              )}
            >
              {warning}
            </span>{" "}
            <span className="text-muted">warning</span>
          </div>
        </div>

        {trend.length > 1 && (
          <div className="flex-1 min-w-[180px] -mb-1">
            <Sparkline data={trend} tone="accent" height={48} />
            <div className="text-eyebrow text-muted mt-1">
              total · last {trend.length} runs
            </div>
          </div>
        )}
      </div>
    </article>
  );
}

function StatRow({
  label,
  value,
  hint,
  trend,
  tone = "default",
}: {
  label: string;
  value: number | string;
  hint?: string;
  trend?: number[];
  tone?: "default" | "warning" | "success" | "critical";
}) {
  const valueClass = cn(
    "figure-num text-h2 leading-none",
    tone === "critical" && "text-critical",
    tone === "warning" && "text-warning",
    tone === "success" && "text-success",
    tone === "default" && "text-ink"
  );
  return (
    <div className="panel px-5 py-3.5 flex items-center justify-between gap-4">
      <div className="min-w-0">
        <div className="eyebrow mb-1.5">{label}</div>
        <div className="flex items-baseline gap-3">
          <span className={valueClass}>{value}</span>
          {hint && (
            <span className="text-meta text-muted truncate">{hint}</span>
          )}
        </div>
      </div>
      {trend && trend.length > 1 && (
        <div className="w-24 shrink-0">
          <Sparkline data={trend} tone="default" height={28} />
        </div>
      )}
    </div>
  );
}

function Panel({
  title,
  hint,
  right,
  children,
}: {
  title: string;
  hint?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="panel p-5 flex flex-col">
      <header className="flex items-baseline justify-between gap-3 mb-3">
        <div>
          <h3 className="display text-h3 leading-tight">{title}</h3>
          {hint && (
            <div className="text-meta text-muted mt-0.5">{hint}</div>
          )}
        </div>
        {right}
      </header>
      <div className="flex-1">{children}</div>
    </section>
  );
}

function BreakdownBar({
  label,
  count,
  pct,
  color,
}: {
  label: string;
  count: number;
  pct: number;
  color: string;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-meta">{label}</span>
        <span className="data-mono text-meta text-ink font-semibold">
          {count}
        </span>
      </div>
      <div className="h-1.5 bg-surface rounded-sm overflow-hidden">
        <div
          className="h-full rounded-sm transition-[width] duration-300"
          style={{
            width: `${Math.max(2, pct * 100)}%`,
            backgroundColor: color,
          }}
        />
      </div>
    </div>
  );
}

function SkeletonOverview() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-9 w-44 bg-rule rounded" />
      <div className="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-4">
        <div className="panel-hero h-44" />
        <div className="grid grid-rows-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="panel h-16" />
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-4">
        <div className="panel h-72" />
        <div className="panel h-72" />
      </div>
    </div>
  );
}
