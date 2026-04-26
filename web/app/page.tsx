"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type {
  Conflict,
  History,
  IngestEvent,
  OverviewStats,
} from "@/lib/types";
import { ConflictCard } from "@/components/conflict-card";
import { Empty } from "@/components/empty";
import { KpiCard } from "@/components/kpi-card";
import { StackedAreaChart } from "@/components/charts/area-chart";
import { DonutChart } from "@/components/charts/donut-chart";
import { CONFLICT_LABEL, formatRelative } from "@/lib/utils";

const SOURCE_COLORS = {
  meeting: "#4F46E5",  // indigo-600 — accent
  github: "#18181B",   // zinc-900
  slack: "#7C3AED",    // violet-600
  ticket: "#D97706",   // amber-600
} as const;

const TYPE_COLORS: Record<string, string> = {
  duplication: "#DC2626",   // red-600
  contradiction: "#D97706", // amber-600
  dependency: "#7C3AED",    // violet-600
  say_vs_do: "#0891B2",     // cyan-600
};

export default function OverviewPage() {
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
  }, []);

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
  const teamCount = Object.keys(stats.by_team).length;

  // Sparkline trends derived from /history.
  const entitiesTrend = (history?.daily_entities || []).map(
    (d) => d.meeting + d.github + d.slack + d.ticket
  );
  const conflictTrend = (history?.conflict_snapshots || []).map((s) => s.total);
  const criticalTrend = (history?.conflict_snapshots || []).map(
    (s) => s.critical
  );

  // Conflicts by type — derived from current list.
  const byType: Record<string, number> = {};
  for (const c of conflicts) byType[c.conflict_type] = (byType[c.conflict_type] || 0) + 1;
  const donutData = Object.entries(byType).map(([t, v]) => ({
    name: CONFLICT_LABEL[t] || t,
    value: v,
    color: TYPE_COLORS[t] || "#71717A",
  }));

  const areaData = (history?.daily_entities || []).map((d) => ({ ...d }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between gap-6">
        <div>
          <div className="eyebrow mb-2">Operations</div>
          <h1 className="display text-h2">Overview</h1>
        </div>
        <div className="text-meta text-muted font-mono">
          {stats.last_meeting_analysis_at
            ? `Last analysis · ${formatRelative(stats.last_meeting_analysis_at)}`
            : "No meeting analysed yet"}
        </div>
      </div>

      {empty ? (
        <Empty
          title="Nothing in memory yet"
          description="Add your first team and connect its sources to start mapping work across the company."
          action={
            <Link href="/teams" className="btn btn-primary">
              Configure teams
            </Link>
          }
        />
      ) : (
        <>
          {/* KPI strip */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <KpiCard
              label="Entities in memory"
              value={stats.entities.toLocaleString()}
              hint={Object.entries(stats.by_source)
                .map(([k, v]) => `${v} ${k}`)
                .join(" · ")}
              trend={entitiesTrend}
              tone="default"
            />
            <KpiCard
              label="Open conflicts"
              value={stats.conflicts}
              hint={`${conflicts.length - critical} non-critical`}
              trend={conflictTrend.length > 1 ? conflictTrend : undefined}
              tone={stats.conflicts > 0 ? "warning" : "success"}
            />
            <KpiCard
              label="Critical"
              value={critical}
              hint={
                critical > 0 ? "needs attention" : "no critical conflicts"
              }
              trend={criticalTrend.length > 1 ? criticalTrend : undefined}
              tone={critical > 0 ? "critical" : "success"}
            />
            <KpiCard
              label="Teams active"
              value={teamCount}
              hint={Object.keys(stats.by_team).slice(0, 3).join(" · ") || "—"}
              tone="accent"
            />
            <KpiCard
              label="Pending since meeting"
              value={stats.pending_non_meeting_entities}
              hint={
                stats.pending_non_meeting_entities > 0
                  ? "considered on next meeting"
                  : "all caught up"
              }
              tone={
                stats.pending_non_meeting_entities > 0 ? "warning" : "success"
              }
            />
          </div>

          {/* Two-up: activity over time + conflicts by type */}
          <div className="grid lg:grid-cols-[1.7fr_1fr] gap-4">
            <ChartPanel
              eyebrow="Last 14 days"
              title="Activity by source"
              hint="New entities per day, stacked by where they came from"
            >
              <StackedAreaChart
                data={areaData}
                series={[
                  { key: "meeting", label: "Meetings", color: SOURCE_COLORS.meeting },
                  { key: "github", label: "GitHub", color: SOURCE_COLORS.github },
                  { key: "slack", label: "Slack", color: SOURCE_COLORS.slack },
                  { key: "ticket", label: "Tickets", color: SOURCE_COLORS.ticket },
                ]}
                height={260}
              />
              <Legend
                items={[
                  { label: "Meetings", color: SOURCE_COLORS.meeting },
                  { label: "GitHub", color: SOURCE_COLORS.github },
                  { label: "Slack", color: SOURCE_COLORS.slack },
                  { label: "Tickets", color: SOURCE_COLORS.ticket },
                ]}
              />
            </ChartPanel>

            <ChartPanel
              eyebrow="Distribution"
              title="Conflicts by type"
              hint={`${conflicts.length} total · ${critical} critical`}
            >
              <DonutChart
                data={donutData}
                height={220}
                centerValue={conflicts.length}
                centerLabel="Conflicts"
              />
              <Legend
                items={donutData.map((d) => ({
                  label: `${d.name} · ${d.value}`,
                  color: d.color,
                }))}
              />
            </ChartPanel>
          </div>

          {/* Top conflicts + activity */}
          <div className="grid lg:grid-cols-[1.6fr_1fr] gap-4">
            <ChartPanel
              eyebrow="Most pressing"
              title="Top open conflicts"
              right={
                conflicts.length > 0 ? (
                  <Link
                    href="/conflicts"
                    className="text-meta text-accent font-mono hover:underline"
                  >
                    View all {conflicts.length} →
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
                <div className="-mb-3">
                  {conflicts.slice(0, 3).map((c) => (
                    <ConflictCard key={c.id} conflict={c} compact />
                  ))}
                </div>
              )}
            </ChartPanel>

            <ChartPanel
              eyebrow="Activity"
              title="Live ingestion feed"
              hint="Last 8 events"
            >
              <ul className="divide-y divide-rule -mx-5">
                {events.slice(0, 8).map((ev) => (
                  <li
                    key={ev.id}
                    className="flex items-center justify-between gap-3 px-5 py-2.5"
                  >
                    <div className="flex items-baseline gap-3 min-w-0">
                      <span
                        className="tag font-mono shrink-0"
                        style={{
                          color: SOURCE_COLORS[ev.source_type],
                          borderColor: SOURCE_COLORS[ev.source_type] + "55",
                        }}
                      >
                        {ev.source_type}
                      </span>
                      <span className="text-body truncate">{ev.team}</span>
                      <span className="text-meta text-muted truncate hidden sm:inline">
                        {ev.description}
                      </span>
                    </div>
                    <div className="text-meta text-muted font-mono shrink-0">
                      +{ev.entities_extracted} ·{" "}
                      {formatRelative(ev.timestamp)}
                    </div>
                  </li>
                ))}
                {events.length === 0 && (
                  <li className="px-5 py-6 text-meta text-muted">
                    No activity yet.
                  </li>
                )}
              </ul>
            </ChartPanel>
          </div>
        </>
      )}
    </div>
  );
}

function ChartPanel({
  eyebrow,
  title,
  hint,
  right,
  children,
}: {
  eyebrow?: string;
  title: string;
  hint?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="panel p-5 flex flex-col gap-3">
      <header className="flex items-start justify-between gap-3">
        <div>
          {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
          <h3 className="display text-h3 leading-tight">{title}</h3>
          {hint && (
            <div className="text-meta text-muted font-mono mt-1">{hint}</div>
          )}
        </div>
        {right}
      </header>
      <div className="flex-1">{children}</div>
    </section>
  );
}

function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3">
      {items.map((it) => (
        <span
          key={it.label}
          className="inline-flex items-center gap-1.5 text-meta font-mono text-muted"
        >
          <span
            className="w-2 h-2 rounded-sm"
            style={{ backgroundColor: it.color }}
          />
          {it.label}
        </span>
      ))}
    </div>
  );
}

function SkeletonOverview() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-9 w-48 bg-rule rounded" />
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="panel p-5 h-32" />
        ))}
      </div>
      <div className="grid lg:grid-cols-[1.7fr_1fr] gap-4">
        <div className="panel h-80" />
        <div className="panel h-80" />
      </div>
    </div>
  );
}
