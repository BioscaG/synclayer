"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Slack, CheckCircle2, AlertTriangle } from "lucide-react";
import { api as apiFactory, workspaceApi } from "@/lib/api";
import type { SlackStatus, Workspace } from "@/lib/types";
import { cn, formatRelative, parseBackendDate } from "@/lib/utils";

export default function SettingsPage() {
  const params = useParams<{ wsId: string }>();
  const search = useSearchParams();
  const wsId = params?.wsId || "";
  const api = useMemo(() => apiFactory(wsId), [wsId]);

  const [ws, setWs] = useState<Workspace | null>(null);
  const [slack, setSlack] = useState<SlackStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [slackError, setSlackError] = useState<string | null>(null);

  const justConnected = search?.get("slack") === "connected";

  const refresh = () => {
    if (!wsId) return;
    setLoading(true);
    Promise.all([workspaceApi.get(wsId), api.slackStatus()])
      .then(([w, s]) => {
        setWs(w);
        setSlack(s);
      })
      .finally(() => setLoading(false));
  };

  useEffect(refresh, [wsId]);

  const update = async (fields: { name?: string; color?: string }) => {
    if (!ws) return;
    setBusy("ws");
    try {
      const updated = await workspaceApi.update(wsId, fields);
      setWs(updated);
      window.dispatchEvent(new CustomEvent("synclayer:config-changed"));
    } finally {
      setBusy(null);
    }
  };

  const connectSlack = () => {
    setSlackError(null);
    window.location.href = api.slackConnectUrl();
  };

  const disconnectSlack = async () => {
    if (
      !confirm(
        `Disconnect Slack from this workspace? Channels you've added to teams will stop syncing.`
      )
    )
      return;
    setBusy("slack");
    setSlackError(null);
    try {
      await api.slackDisconnect();
      refresh();
    } catch (e: any) {
      setSlackError(e.message || "Failed to disconnect");
    } finally {
      setBusy(null);
    }
  };

  if (loading || !ws)
    return <p className="text-meta text-muted">Loading…</p>;

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <div className="eyebrow mb-2">Workspace</div>
        <h1 className="display text-h2">Settings</h1>
        <p className="text-body text-slate mt-2">
          Workspace-level configuration. Team management lives in{" "}
          <span className="font-mono">Teams</span> and meeting ingest in{" "}
          <span className="font-mono">Meetings</span>.
        </p>
      </div>

      <section className="panel p-6">
        <header className="mb-4">
          <div className="eyebrow mb-1">Identity</div>
          <h3 className="display text-h3">How this workspace appears</h3>
        </header>
        <div className="grid sm:grid-cols-[auto_1fr] gap-4 max-w-lg">
          <label>
            <div className="eyebrow mb-2">Color</div>
            <input
              type="color"
              defaultValue={ws.color}
              onBlur={(e) => {
                if (e.target.value !== ws.color) update({ color: e.target.value });
              }}
              disabled={busy === "ws"}
              className="w-11 h-11 rounded border border-rule2 cursor-pointer"
              title="Workspace color"
            />
          </label>
          <label>
            <div className="eyebrow mb-2">Workspace name</div>
            <input
              defaultValue={ws.name}
              onBlur={(e) => {
                const v = e.target.value.trim();
                if (v && v !== ws.name) update({ name: v });
              }}
              disabled={busy === "ws"}
              className="input"
              placeholder="Workspace name"
            />
            <p className="text-meta text-muted font-mono mt-2">
              Shown in the topbar and on the workspace landing. The workspace
              ID (<span className="lowercase">{ws.id}</span>) doesn&rsquo;t
              change.
            </p>
          </label>
        </div>
      </section>

      <section className="panel p-6">
        <header className="mb-4 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="inline-flex items-center justify-center w-9 h-9 rounded bg-ink/5 shrink-0">
              <Slack size={16} strokeWidth={1.75} />
            </span>
            <div>
              <div className="eyebrow mb-0.5">Integrations</div>
              <h3 className="display text-h3 leading-tight">Slack</h3>
              <p className="text-meta text-muted mt-1">
                Install the SyncLayer app in a Slack workspace. Channels you
                add to teams will be polled in the background and feed
                cross-team conflict detection.
              </p>
            </div>
          </div>
          {slack?.connected ? (
            <span className="tag tag-success shrink-0 inline-flex items-center gap-1">
              <CheckCircle2 size={11} strokeWidth={2} />
              Connected
            </span>
          ) : null}
        </header>

        {justConnected && slack?.connected && (
          <div className="panel-soft border-success/30 bg-success/5 px-3 py-2 mb-3 text-meta font-mono text-success">
            ✓ Slack workspace connected
          </div>
        )}

        {slackError && (
          <div className="panel-soft border-critical/30 bg-critical/5 px-3 py-2 mb-3 text-meta font-mono text-critical">
            {slackError}
          </div>
        )}

        {!slack?.configured && !slack?.connected && (
          <div className="panel-soft border-warning/30 bg-warning/5 px-3 py-2 mb-3 text-meta font-mono text-warning inline-flex items-start gap-2">
            <AlertTriangle size={14} strokeWidth={2} className="shrink-0 mt-0.5" />
            <span>
              Slack OAuth is not configured on this server. Set{" "}
              <code className="text-ink">SLACK_CLIENT_ID</code> and{" "}
              <code className="text-ink">SLACK_CLIENT_SECRET</code> in{" "}
              <code className="text-ink">.env</code> and restart the backend.
              See <code className="text-ink">backend/slack_oauth.py</code> for
              required scopes.
            </span>
          </div>
        )}

        {slack?.connected ? (
          <div className="space-y-3">
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-2 text-meta">
              <Field label="Slack workspace" value={slack.team_name || "—"} />
              <Field
                label="Workspace ID"
                value={slack.team_id || "—"}
                mono
              />
              <Field
                label="Connected"
                value={
                  slack.connected_at
                    ? `${formatRelative(slack.connected_at)} (${parseBackendDate(slack.connected_at).toLocaleString()})`
                    : "—"
                }
              />
            </div>
            <div className="text-meta text-muted">
              Tip: invite the bot to each channel you want to track —{" "}
              <code className="font-mono text-ink">/invite @SyncLayer</code>{" "}
              from inside the channel. Then add the channel ID to a team in{" "}
              <span className="font-mono">Teams</span>.
            </div>
            <div className="flex gap-2">
              <button
                onClick={disconnectSlack}
                disabled={busy === "slack"}
                className="btn btn-danger"
              >
                {busy === "slack" ? "Disconnecting…" : "Disconnect Slack"}
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={connectSlack}
            disabled={!slack?.configured || busy === "slack"}
            className="btn btn-primary inline-flex items-center gap-2"
          >
            <Slack size={13} strokeWidth={2} />
            Connect Slack workspace
          </button>
        )}
      </section>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="eyebrow mb-0.5">{label}</div>
      <div className={cn("text-ink", mono && "font-mono")}>{value}</div>
    </div>
  );
}
