"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import type {
  SlackChannel,
  SourceState,
  TeamConfig,
  TeamSummary,
} from "@/lib/types";
import { cn, formatRelative, parseBackendDate, teamColor } from "@/lib/utils";

export function TeamEditor({
  name,
  team,
  sources,
  summary,
  slackChannels,
  onUpdate,
  onRemove,
}: {
  name: string;
  team: TeamConfig;
  sources: Record<string, SourceState>;
  summary?: TeamSummary;
  /** When non-null, replace the slack ListEditor with a channel picker
   *  populated from the workspace's connected Slack workspace. */
  slackChannels?: SlackChannel[] | null;
  onUpdate: (f: Partial<TeamConfig>) => void;
  onRemove: () => void;
}) {
  const params = useParams<{ wsId: string }>();
  const wsId = params?.wsId || "";
  const color = team.color || teamColor(name);
  const stateFor = (kind: "repo" | "slack" | "ticket", id: string) =>
    sources[`${kind}::${name}::${id}`];

  return (
    <div className="panel p-6">
      <header className="flex items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <input
            type="color"
            value={color}
            onChange={(e) => onUpdate({ color: e.target.value })}
            className="w-7 h-7 rounded border border-rule cursor-pointer shrink-0"
            title="Team color"
          />
          <Link
            href={`/w/${wsId}/teams/${encodeURIComponent(name)}`}
            className="font-serif text-h3 hover:underline truncate"
            title="Open team detail"
          >
            {name}
          </Link>
        </div>
        <button onClick={onRemove} className="btn btn-danger shrink-0">
          Remove
        </button>
      </header>

      {summary && (
        <div className="grid grid-cols-3 gap-6 pb-5 mb-5 border-b border-rule">
          <Stat label="Entities" value={summary.entities} />
          <Stat
            label="Active work"
            value={summary.active_work}
            hint={summary.concerns ? `${summary.concerns} concerns` : undefined}
          />
          <Stat
            label="Conflicts"
            value={summary.conflicts}
            hint={
              summary.critical_conflicts
                ? `${summary.critical_conflicts} critical`
                : undefined
            }
            emphasis={
              summary.critical_conflicts > 0
                ? "critical"
                : summary.conflicts > 0
                ? "warning"
                : "default"
            }
          />
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        <ListEditor
          label="GitHub repositories"
          placeholder="owner/repo or github.com URL"
          items={team.repos}
          stateFor={(id) => stateFor("repo", id)}
          onChange={(repos) => onUpdate({ repos })}
        />
        {slackChannels && slackChannels.length > 0 ? (
          <SlackChannelPicker
            label="Slack channels"
            items={team.slack_channels}
            channels={slackChannels}
            stateFor={(id) => stateFor("slack", id)}
            onChange={(slack_channels) => onUpdate({ slack_channels })}
          />
        ) : (
          <ListEditor
            label="Slack channels"
            placeholder="C0123456 or path/to/snapshot.json"
            items={team.slack_channels}
            stateFor={(id) => stateFor("slack", id)}
            onChange={(slack_channels) => onUpdate({ slack_channels })}
          />
        )}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  emphasis = "default",
}: {
  label: string;
  value: number;
  hint?: string;
  emphasis?: "default" | "critical" | "warning";
}) {
  const cls =
    emphasis === "critical"
      ? "text-critical"
      : emphasis === "warning"
      ? "text-warning"
      : "text-ink";
  return (
    <div>
      <div className="eyebrow mb-1.5">{label}</div>
      <div className={`figure-num font-medium text-h2 leading-none ${cls}`}>
        {value}
      </div>
      {hint && <div className="text-meta text-muted mt-1 font-mono">{hint}</div>}
    </div>
  );
}

function SlackChannelPicker({
  label,
  items,
  channels,
  stateFor,
  onChange,
}: {
  label: string;
  items: string[];
  channels: SlackChannel[];
  stateFor?: (id: string) => SourceState | undefined;
  onChange: (next: string[]) => void;
}) {
  const byId = new Map(channels.map((c) => [c.id, c]));
  const remaining = channels.filter((c) => !items.includes(c.id));

  const add = (id: string) => {
    if (!id || items.includes(id)) return;
    onChange([...items, id]);
  };

  return (
    <div>
      <div className="eyebrow mb-2">{label}</div>
      {items.length === 0 ? (
        <p className="text-meta text-muted mb-3">None.</p>
      ) : (
        <ul className="space-y-1.5 mb-3">
          {items.map((it) => {
            const st = stateFor?.(it);
            const channel = byId.get(it);
            const synced = !!st?.last_synced_at;
            const errored = !!st?.last_error;
            const syncing = !synced && !errored;
            const dotClass = errored
              ? "bg-critical animate-pulse"
              : synced
              ? "bg-success"
              : "bg-rule";
            const statusLabel = errored
              ? "failed"
              : synced
              ? formatRelative(st!.last_activity_at || st!.last_synced_at!)
              : "syncing…";
            const statusTitle = errored
              ? `Last error: ${st!.last_error}`
              : st?.last_synced_at
              ? `Synced: ${parseBackendDate(st.last_synced_at).toLocaleString()}`
              : "Background sync running";
            return (
              <li
                key={it}
                className={cn(
                  "flex items-center gap-2 text-meta font-mono panel-soft px-3 py-1.5",
                  errored && "border-critical/40"
                )}
                title={statusTitle}
              >
                <span
                  className={cn("w-1.5 h-1.5 rounded-full shrink-0", dotClass)}
                />
                <span className="truncate flex-1" title={it}>
                  {channel ? `#${channel.name}` : it}
                </span>
                {channel?.is_private && (
                  <span className="text-eyebrow text-muted shrink-0">
                    private
                  </span>
                )}
                <span
                  className={cn(
                    "shrink-0",
                    errored
                      ? "text-critical"
                      : syncing
                      ? "text-warning"
                      : "text-muted"
                  )}
                >
                  {statusLabel}
                </span>
                <button
                  onClick={() => onChange(items.filter((x) => x !== it))}
                  className="text-muted hover:text-critical shrink-0"
                  title="Remove"
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <select
        value=""
        onChange={(e) => {
          if (e.target.value) {
            add(e.target.value);
            // Reset so the same channel can be picked again later if removed.
            e.currentTarget.value = "";
          }
        }}
        className="input text-meta font-mono"
      >
        <option value="">
          {remaining.length === 0
            ? "All channels added"
            : "Pick a Slack channel…"}
        </option>
        {remaining.map((c) => (
          <option key={c.id} value={c.id}>
            #{c.name}
            {c.is_private ? " (private)" : ""}
            {c.is_member ? "" : " · invite bot first"}
          </option>
        ))}
      </select>
      <p className="text-eyebrow font-mono text-muted mt-1.5">
        Tip: <span className="text-ink">/invite @SyncLayer</span> in the
        channel before syncing.
      </p>
    </div>
  );
}

function ListEditor({
  label,
  placeholder,
  items,
  stateFor,
  onChange,
}: {
  label: string;
  placeholder: string;
  items: string[];
  stateFor?: (id: string) => SourceState | undefined;
  onChange: (next: string[]) => void;
}) {
  const [v, setV] = useState("");

  const commit = () => {
    const value = v.trim();
    if (!value || items.includes(value)) {
      setV("");
      return;
    }
    onChange([...items, value]);
    setV("");
  };

  return (
    <div>
      <div className="eyebrow mb-2">{label}</div>
      {items.length === 0 ? (
        <p className="text-meta text-muted mb-3">None.</p>
      ) : (
        <ul className="space-y-1.5 mb-3">
          {items.map((it) => {
            const st = stateFor?.(it);
            const synced = !!st?.last_synced_at;
            const errored = !!st?.last_error;
            // "Syncing" state: source exists in config but the background
            // task hasn't returned yet (no last_synced_at, no last_error).
            const syncing = !synced && !errored;
            const dotClass = errored
              ? "bg-critical animate-pulse"
              : synced
              ? "bg-success"
              : "bg-rule";
            // Prefer the source's own "last activity" timestamp (most recent
            // commit / PR for a repo) over our internal sync time — that's
            // what the user actually wants to see at a glance.
            const displayTs = st?.last_activity_at || st?.last_synced_at;
            const statusLabel = errored
              ? "failed"
              : synced
              ? formatRelative(displayTs)
              : "syncing…";
            const statusTitle = errored
              ? `Last error: ${st!.last_error}`
              : st?.last_synced_at
              ? `${
                  st.last_activity_at
                    ? `Last activity: ${parseBackendDate(st.last_activity_at).toLocaleString()} · `
                    : ""
                }Synced: ${parseBackendDate(st.last_synced_at).toLocaleString()}`
              : "Background sync running — this can take 5–30s on first add";
            return (
              <li
                key={it}
                className={cn(
                  "flex items-center gap-2 text-meta font-mono panel-soft px-3 py-1.5",
                  errored && "border-critical/40"
                )}
                title={statusTitle}
              >
                <span
                  className={cn("w-1.5 h-1.5 rounded-full shrink-0", dotClass)}
                />
                <span className="truncate flex-1" title={it}>
                  {it}
                </span>
                <span
                  className={cn(
                    "shrink-0",
                    errored
                      ? "text-critical"
                      : syncing
                      ? "text-warning"
                      : "text-muted"
                  )}
                >
                  {statusLabel}
                </span>
                <button
                  onClick={() => onChange(items.filter((x) => x !== it))}
                  className="text-muted hover:text-critical shrink-0"
                  title="Remove"
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <div className="flex gap-2">
        <input
          value={v}
          onChange={(e) => setV(e.target.value)}
          placeholder={placeholder}
          className="input text-meta font-mono"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commit();
            }
          }}
        />
        <button
          type="button"
          onClick={commit}
          disabled={!v.trim()}
          className={cn(
            "btn shrink-0",
            v.trim() && "btn-primary"
          )}
        >
          Add
        </button>
      </div>
    </div>
  );
}
