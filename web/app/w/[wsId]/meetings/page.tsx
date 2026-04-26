"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api as apiFactory } from "@/lib/api";
import type { CompanyConfig, MeetingSummary } from "@/lib/types";
import { Empty } from "@/components/empty";
import {
  NewConflictsBanner,
  type NewConflictsResult,
} from "@/components/new-conflicts-banner";
import { MeetingBotPanel } from "@/components/meeting-bot-panel";
import type { MeetingBot } from "@/lib/types";
import { formatRelative, parseBackendDate, teamColor } from "@/lib/utils";

export default function MeetingsPage() {
  const params = useParams<{ wsId: string }>();
  const wsId = params?.wsId || "";
  const api = useMemo(() => apiFactory(wsId), [wsId]);

  const [cfg, setCfg] = useState<CompanyConfig | null>(null);
  const [meetings, setMeetings] = useState<MeetingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [meetingTeam, setMeetingTeam] = useState<string>("");
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

  useEffect(refresh, [api]);

  if (loading) return <p className="text-meta text-muted">Loading…</p>;

  const teams = Object.keys(cfg?.teams || {});

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-6">
        <div>
          <div className="eyebrow mb-2">Workspace</div>
          <h1 className="display text-h2">Meetings</h1>
          <p className="text-body text-slate mt-2 max-w-2xl">
            Every meeting is a checkpoint. Record live, upload an audio file or
            paste a transcript — Claude extracts the decisions and re-runs
            cross-team conflict detection.
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

      {teams.length === 0 ? (
        <section className="panel p-6">
          <Empty
            title="No teams configured"
            description="Add at least one team before logging a meeting."
            action={
              <Link href={`/w/${wsId}/teams`} className="btn btn-primary">
                Configure teams
              </Link>
            }
          />
        </section>
      ) : (
        <MeetingBotPanel
          wsId={wsId}
          teams={teams}
          selectedTeam={meetingTeam}
          onSelectTeam={setMeetingTeam}
          onBotCompleted={(bot: MeetingBot) => {
            refresh();
            if (bot.new_conflicts > 0) {
              setResult({
                team: bot.team,
                new_conflicts: [],
                extracted: bot.entities_extracted,
                triggered: true,
              });
              setError(null);
            }
          }}
        />
      )}

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
            description="Record or paste your first meeting above. The conflicts it surfaces will populate Conflicts and the team detail pages."
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
                      href={`/w/${wsId}/teams/${encodeURIComponent(m.team)}`}
                      className="text-body hover:underline shrink-0 lowercase font-mono"
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
