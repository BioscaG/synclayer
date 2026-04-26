"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type {
  CompanyConfig,
  SyncStatus,
  TeamConfig,
  TeamSummary,
} from "@/lib/types";
import { Empty } from "@/components/empty";
import { TeamEditor } from "@/components/team-editor";
import { TEAM_PALETTE } from "@/lib/utils";

type TeamRow = TeamSummary & { config: TeamConfig };

export default function TeamsPage() {
  const [cfg, setCfg] = useState<CompanyConfig | null>(null);
  const [rows, setRows] = useState<TeamRow[]>([]);
  const [orphans, setOrphans] = useState<{ team: string; entity_count: number }[]>(
    []
  );
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // New-team form
  const [newTeam, setNewTeam] = useState("");
  const [newColor, setNewColor] = useState(TEAM_PALETTE[0]);

  const refresh = () => {
    setLoading(true);
    Promise.all([
      api.getConfig(),
      api.teams(),
      api.orphanTeams(),
      api.syncStatus(),
    ])
      .then(([c, t, o, s]) => {
        setCfg(c);
        setRows(t as TeamRow[]);
        setOrphans(o);
        setSyncStatus(s);
        // Notify topbar in case team count or company changed indirectly.
        window.dispatchEvent(new CustomEvent("synclayer:config-changed"));
      })
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  // Light polling so background-sync results show up without a manual reload:
  // pulls fresh team stats AND per-source last_synced_at / last_error.
  useEffect(() => {
    const id = setInterval(() => {
      api.syncStatus().then(setSyncStatus).catch(() => {});
      api
        .teams()
        .then((t) => setRows(t as TeamRow[]))
        .catch(() => {});
    }, 8000);
    return () => clearInterval(id);
  }, []);

  const updateTeam = async (
    team: string,
    fields: Partial<TeamConfig> & { name?: string }
  ) => {
    setBusy(`team:${team}`);
    try {
      await api.upsertTeam({ name: team, ...fields });
      refresh();
    } finally {
      setBusy(null);
    }
  };

  const removeTeam = async (name: string) => {
    if (!confirm(`Remove team "${name}"?`)) return;
    setBusy(`rm:${name}`);
    try {
      await api.deleteTeam(name);
      refresh();
    } finally {
      setBusy(null);
    }
  };

  const addTeam = async () => {
    if (!newTeam.trim()) return;
    await updateTeam(newTeam.trim(), {
      color: newColor,
      repos: [],
      slack_channels: [],
      ticket_paths: [],
    });
    setNewTeam("");
  };

  const registerOrphan = async (name: string, idx: number) => {
    setBusy(`reg:${name}`);
    try {
      await api.upsertTeam({
        name,
        color: TEAM_PALETTE[idx % TEAM_PALETTE.length],
        repos: [],
        slack_channels: [],
        ticket_paths: [],
      });
      refresh();
    } finally {
      setBusy(null);
    }
  };

  const forgetOrphan = async (name: string) => {
    if (!confirm(`Forget all entities tagged with team "${name}"?`)) return;
    setBusy(`forget:${name}`);
    try {
      const r = await api.forgetTeamEntities(name);
      setMsg(`Removed ${r.removed_entities} entities from "${name}".`);
      refresh();
    } finally {
      setBusy(null);
    }
  };

  if (loading || !cfg)
    return <p className="text-meta text-muted">Loading…</p>;

  const teamMap = new Map(rows.map((r) => [r.team, r]));
  const configured = Object.entries(cfg.teams || {});

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-6">
        <div>
          <div className="eyebrow mb-2">Workspace</div>
          <h1 className="display text-h2">Teams</h1>
          <p className="text-body text-slate mt-2 max-w-2xl">
            Every team and the sources that feed its memory. Add a team, link
            its repositories and channels, and SyncLayer keeps the cross-team
            map current.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <input
            type="color"
            value={newColor}
            onChange={(e) => setNewColor(e.target.value)}
            className="w-9 h-9 rounded border border-rule cursor-pointer shrink-0"
            title="Team color"
          />
          <input
            value={newTeam}
            onChange={(e) => setNewTeam(e.target.value)}
            placeholder="New team name…"
            className="input w-56"
            onKeyDown={(e) => {
              if (e.key === "Enter") addTeam();
            }}
          />
          <button
            onClick={addTeam}
            disabled={!newTeam.trim()}
            className="btn btn-primary"
          >
            Add team
          </button>
        </div>
      </div>

      {msg && (
        <div className="panel-soft px-4 py-3 text-meta font-mono">{msg}</div>
      )}

      {configured.length === 0 ? (
        <Empty
          title="No teams configured yet"
          description="Add your first team using the form above. You can connect repositories, Slack channels and ticket files once it's created."
        />
      ) : (
        <div className="space-y-4">
          {configured.map(([name, t]) => (
            <TeamEditor
              key={name}
              name={name}
              team={t}
              sources={syncStatus?.sources || {}}
              summary={teamMap.get(name)}
              onUpdate={(f) => updateTeam(name, f)}
              onRemove={() => removeTeam(name)}
            />
          ))}
        </div>
      )}

      {orphans.length > 0 && (
        <section className="mt-12 pt-8 border-t border-rule">
          <header className="mb-4">
            <div className="eyebrow mb-1">Auto-detected from memory</div>
            <h3 className="display text-h3">Unregistered teams</h3>
            <p className="text-body text-slate mt-2 max-w-2xl">
              These team names appear in already-ingested entities but
              aren&rsquo;t in your configuration. Register them to manage their
              sources, or forget their entities to clean up.
            </p>
          </header>
          <ul className="space-y-2">
            {orphans.map((o, i) => (
              <li
                key={o.team}
                className="panel-soft px-4 py-3 flex items-center justify-between gap-4"
              >
                <div className="flex items-baseline gap-3 min-w-0">
                  <span className="font-serif text-lead truncate">
                    {o.team}
                  </span>
                  <span className="text-meta text-muted font-mono shrink-0">
                    {o.entity_count} entit
                    {o.entity_count === 1 ? "y" : "ies"} in memory
                  </span>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => registerOrphan(o.team, i)}
                    disabled={busy === `reg:${o.team}`}
                    className="btn btn-primary"
                  >
                    {busy === `reg:${o.team}` ? "…" : "Register"}
                  </button>
                  <button
                    onClick={() => forgetOrphan(o.team)}
                    disabled={busy === `forget:${o.team}`}
                    className="btn btn-danger"
                  >
                    {busy === `forget:${o.team}` ? "…" : "Forget entities"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
