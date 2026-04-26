"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type {
  CompanyConfig,
  Conflict,
  MeetingSummary,
} from "@/lib/types";
import { Empty } from "@/components/empty";
import {
  NewConflictsBanner,
  type NewConflictsResult,
} from "@/components/new-conflicts-banner";
import { formatRelative, parseBackendDate, teamColor } from "@/lib/utils";

export default function MeetingsPage() {
  const [cfg, setCfg] = useState<CompanyConfig | null>(null);
  const [meetings, setMeetings] = useState<MeetingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [meetingTeam, setMeetingTeam] = useState<string>("");
  const [meetingText, setMeetingText] = useState<string>("");
  const [result, setResult] = useState<NewConflictsResult | null>(null);

  const refresh = () => {
    Promise.all([api.getConfig(), api.meetings()])
      .then(([c, m]) => {
        setCfg(c);
        setMeetings(m);
        if (!meetingTeam) setMeetingTeam(Object.keys(c.teams || {})[0] || "");
      })
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const ingest = async () => {
    if (!meetingTeam || !meetingText.trim()) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.ingestMeetingText(
        meetingTeam,
        meetingText,
        `meeting-${Date.now()}`
      );
      setResult({
        team: meetingTeam,
        new_conflicts: res.new_conflicts || [],
        extracted: res.entities_extracted,
        triggered: res.triggered_analysis,
      });
      setMeetingText("");
      refresh();
    } catch (e: any) {
      setError(e.message || "Failed to ingest meeting");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className="text-meta text-muted">Loading…</p>;

  const teams = Object.keys(cfg?.teams || {});

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between gap-6">
        <div>
          <div className="eyebrow mb-2">Workspace</div>
          <h1 className="display text-h2">Meetings</h1>
          <p className="text-body text-slate mt-2 max-w-2xl">
            Every meeting is a checkpoint. Logging one extracts decisions and
            re-runs cross-team conflict detection against current memory.
          </p>
        </div>
      </div>

      {result && result.new_conflicts.length > 0 && (
        <NewConflictsBanner result={result} onDismiss={() => setResult(null)} />
      )}

      {result && result.new_conflicts.length === 0 && (
        <div className="panel-soft p-4 text-meta font-mono">
          Meeting ingested · +{result.extracted} entities ·{" "}
          {result.triggered
            ? "analysis re-ran, no new conflicts surfaced"
            : "analysis skipped"}
        </div>
      )}

      {error && (
        <div className="panel border-critical/40 bg-critical/5 p-4 text-meta font-mono text-critical">
          {error}
        </div>
      )}

      {/* Ingest form */}
      <section className="panel p-6">
        <header className="mb-4">
          <div className="eyebrow mb-1">Log a meeting</div>
          <h3 className="display text-h3">Ingest a transcript</h3>
          <p className="text-meta text-muted font-mono mt-1">
            Paste a transcript (any format) — Claude extracts the decisions and
            re-runs the cross-team analysis.
          </p>
        </header>

        {teams.length === 0 ? (
          <Empty
            title="No teams configured"
            description="Add at least one team before logging a meeting."
            action={
              <Link href="/teams" className="btn btn-primary">
                Configure teams
              </Link>
            }
          />
        ) : (
          <div className="grid lg:grid-cols-[2fr_1fr] gap-6">
            <textarea
              value={meetingText}
              onChange={(e) => setMeetingText(e.target.value)}
              placeholder={`Speaker A: I think we should…\nSpeaker B: …`}
              className="input min-h-[200px] font-mono"
            />
            <div className="space-y-3">
              <label>
                <div className="eyebrow mb-2">Team</div>
                <select
                  value={meetingTeam}
                  onChange={(e) => setMeetingTeam(e.target.value)}
                  className="input"
                >
                  {teams.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <button
                onClick={ingest}
                disabled={!meetingTeam || !meetingText.trim() || busy}
                className="btn btn-primary w-full"
              >
                {busy ? "Analysing…" : "Ingest & analyse"}
              </button>
              <p className="text-meta text-muted font-mono">
                Pair judgments are cached, so re-runs are cheap.
              </p>
            </div>
          </div>
        )}
      </section>

      {/* History */}
      <section>
        <header className="flex items-baseline justify-between mb-3">
          <div>
            <div className="eyebrow mb-1">History</div>
            <h3 className="display text-h3">Past meetings</h3>
          </div>
          <span className="text-meta text-muted font-mono">
            {meetings.length} total
          </span>
        </header>

        {meetings.length === 0 ? (
          <Empty
            title="No meetings ingested yet"
            description="Log your first meeting above. The conflicts it surfaces will populate Conflicts and the team detail pages."
          />
        ) : (
          <ul className="panel divide-y divide-rule">
            {meetings.map((m) => {
              const cfgTeam = cfg?.teams?.[m.team];
              const color = cfgTeam?.color || teamColor(m.team);
              return (
                <li
                  key={m.meeting_id}
                  className="flex items-center justify-between gap-4 px-5 py-3.5"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span
                      className="inline-block w-2 h-2 rounded-sm shrink-0"
                      style={{ backgroundColor: color }}
                    />
                    <Link
                      href={`/teams/${encodeURIComponent(m.team)}`}
                      className="font-serif text-body hover:underline shrink-0"
                    >
                      {m.team}
                    </Link>
                    <span className="text-meta text-muted font-mono truncate">
                      {m.meeting_id}
                    </span>
                  </div>
                  <div className="flex items-center gap-6 text-meta font-mono shrink-0">
                    <span className="text-muted">
                      +{m.entity_count} entit
                      {m.entity_count === 1 ? "y" : "ies"}
                    </span>
                    <span
                      className="text-muted"
                      title={parseBackendDate(m.ingested_at).toLocaleString()}
                    >
                      {formatRelative(m.ingested_at)}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
