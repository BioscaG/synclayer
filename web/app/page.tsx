"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Activity, Plus, Trash2 } from "lucide-react";
import { workspaceApi } from "@/lib/api";
import type { WorkspaceSummary } from "@/lib/types";
import { TEAM_PALETTE, cn, formatRelative, parseBackendDate } from "@/lib/utils";

export default function WorkspacesLanding() {
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [color, setColor] = useState(TEAM_PALETTE[0]);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    workspaceApi
      .list()
      .then(setWorkspaces)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const create = async () => {
    if (!name.trim()) return;
    setBusy("create");
    setError(null);
    try {
      await workspaceApi.create(name.trim(), color);
      setName("");
      setCreating(false);
      refresh();
    } catch (e: any) {
      setError(e.message || "Failed to create workspace");
    } finally {
      setBusy(null);
    }
  };

  const remove = async (ws: WorkspaceSummary) => {
    if (
      !confirm(
        `Delete workspace "${ws.name}"? This wipes its teams, entities and conflicts permanently.`
      )
    )
      return;
    setBusy(`del:${ws.id}`);
    try {
      await workspaceApi.remove(ws.id);
      refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top brand bar — slim, no sidebar */}
      <header className="border-b border-rule">
        <div className="max-w-6xl mx-auto px-6 lg:px-8 h-16 flex items-center">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="inline-flex items-center justify-center w-7 h-7 rounded-md bg-ink text-paper">
              <Activity size={15} strokeWidth={2.5} />
            </span>
            <span className="text-lead font-semibold tracking-tight">
              SyncLayer
            </span>
          </Link>
        </div>
      </header>

      <main className="flex-1 max-w-6xl mx-auto w-full px-6 lg:px-8 py-12">
        <div className="mb-10">
          <div className="eyebrow mb-2">Workspaces</div>
          <h1 className="display text-h1 mb-2">Choose a workspace</h1>
          <p className="text-body text-slate max-w-xl">
            Each workspace is an isolated tenant — its own teams, repos,
            meetings and cross-team intelligence. Pick one to enter or create a
            new one.
          </p>
        </div>

        {error && (
          <div className="panel border-critical/30 bg-critical/5 px-4 py-3 mb-6 text-meta font-mono text-critical">
            {error}
          </div>
        )}

        {loading ? (
          <p className="text-meta text-muted font-mono">Loading…</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {workspaces.map((w) => (
              <WorkspaceTile
                key={w.id}
                ws={w}
                busy={busy === `del:${w.id}`}
                onDelete={() => remove(w)}
              />
            ))}

            {creating ? (
              <CreateTile
                name={name}
                color={color}
                busy={busy === "create"}
                onName={setName}
                onColor={setColor}
                onSubmit={create}
                onCancel={() => {
                  setCreating(false);
                  setName("");
                  setError(null);
                }}
              />
            ) : (
              <button
                type="button"
                onClick={() => setCreating(true)}
                className="panel border-dashed border-rule2 hover:border-accent hover:bg-accentSoft/40 transition-colors p-6 flex flex-col items-center justify-center gap-2 aspect-square text-muted hover:text-accent"
              >
                <Plus size={20} strokeWidth={1.75} />
                <span className="text-meta font-medium">New workspace</span>
              </button>
            )}
          </div>
        )}
      </main>

      <footer className="border-t border-rule mt-12">
        <div className="max-w-6xl mx-auto px-6 lg:px-8 py-4 text-eyebrow font-mono text-muted tracking-wide">
          SyncLayer · v0.4
        </div>
      </footer>
    </div>
  );
}

function WorkspaceTile({
  ws,
  busy,
  onDelete,
}: {
  ws: WorkspaceSummary;
  busy: boolean;
  onDelete: () => void;
}) {
  return (
    <div className="group relative aspect-square">
      <Link
        href={`/w/${ws.id}`}
        className="panel h-full p-5 hover:border-ink/40 transition-colors flex flex-col justify-between"
      >
        {/* Header — icon block with initial + name + id */}
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="w-11 h-11 rounded-md flex items-center justify-center font-semibold text-paper text-h3 shrink-0"
            style={{ backgroundColor: ws.color }}
          >
            {ws.name.charAt(0).toUpperCase() || "?"}
          </div>
          <div className="min-w-0">
            <div className="text-h3 font-semibold truncate leading-tight">
              {ws.name}
            </div>
            <div className="text-eyebrow font-mono text-muted lowercase truncate">
              {ws.id}
            </div>
          </div>
        </div>

        {/* Stats — three big numbers */}
        <div className="grid grid-cols-3 gap-2">
          <Stat label="Entities" value={ws.entities} />
          <Stat label="Teams" value={ws.teams} />
          <Stat
            label="Conflicts"
            value={ws.conflicts}
            tone={
              ws.critical_conflicts > 0
                ? "critical"
                : ws.conflicts > 0
                ? "warning"
                : "default"
            }
            badge={
              ws.critical_conflicts > 0
                ? `${ws.critical_conflicts} critical`
                : undefined
            }
          />
        </div>

        {/* Footer — created at */}
        <div className="text-eyebrow font-mono text-muted">
          created {formatRelative(ws.created_at)}
        </div>
      </Link>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onDelete();
        }}
        disabled={busy}
        className={cn(
          "absolute top-3 right-3 p-1.5 rounded text-muted hover:text-critical hover:bg-critical/5 transition-all",
          "opacity-0 group-hover:opacity-100 focus:opacity-100"
        )}
        title={`Delete ${ws.name}`}
      >
        <Trash2 size={14} strokeWidth={1.75} />
      </button>
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "default",
  badge,
}: {
  label: string;
  value: number;
  tone?: "default" | "critical" | "warning";
  badge?: string;
}) {
  const cls =
    tone === "critical"
      ? "text-critical"
      : tone === "warning"
      ? "text-warning"
      : "text-ink";
  return (
    <div>
      <div className="text-eyebrow font-mono uppercase tracking-wider text-muted mb-1.5">
        {label}
      </div>
      <div className={cn("figure-num text-figure leading-none", cls)}>
        {value}
      </div>
      {badge && (
        <div className="text-eyebrow font-mono text-critical mt-1.5">
          {badge}
        </div>
      )}
    </div>
  );
}

function CreateTile({
  name,
  color,
  busy,
  onName,
  onColor,
  onSubmit,
  onCancel,
}: {
  name: string;
  color: string;
  busy: boolean;
  onName: (n: string) => void;
  onColor: (c: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="panel border-accent/40 p-5 aspect-square flex flex-col gap-3">
      <div className="flex items-center gap-2.5">
        <input
          type="color"
          value={color}
          onChange={(e) => onColor(e.target.value)}
          className="w-7 h-7 rounded border border-rule2 cursor-pointer shrink-0"
          title="Workspace color"
        />
        <input
          autoFocus
          value={name}
          onChange={(e) => onName(e.target.value)}
          placeholder="Workspace name…"
          className="input flex-1"
          onKeyDown={(e) => {
            if (e.key === "Enter") onSubmit();
            if (e.key === "Escape") onCancel();
          }}
        />
      </div>
      <div className="text-meta text-muted font-mono">
        Each workspace is fully isolated — its own teams and data.
      </div>
      <div className="mt-auto flex gap-2">
        <button
          type="button"
          onClick={onSubmit}
          disabled={!name.trim() || busy}
          className="btn btn-primary flex-1"
        >
          {busy ? "Creating…" : "Create"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="btn"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
