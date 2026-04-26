"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Activity, Plus, Trash2 } from "lucide-react";
import { workspaceApi } from "@/lib/api";
import type { WorkspaceSummary } from "@/lib/types";
import { TEAM_PALETTE, cn, formatRelative } from "@/lib/utils";

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
      <header className="border-b border-rule">
        <div className="max-w-6xl mx-auto px-6 lg:px-8 h-14 flex items-center">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="inline-flex items-center justify-center w-7 h-7 rounded-md bg-ink text-paper">
              <Activity size={14} strokeWidth={2.5} />
            </span>
            <span className="text-lead font-semibold tracking-tight">
              SyncLayer
            </span>
          </Link>
        </div>
      </header>

      <main className="flex-1 max-w-6xl mx-auto w-full px-6 lg:px-8 py-12">
        <div className="mb-10 max-w-2xl">
          <div className="eyebrow mb-3">Workspaces</div>
          <h1 className="display text-h1">Choose a workspace</h1>
          <p className="text-body text-slate mt-3">
            Each workspace is an isolated tenant — its own teams, repos,
            meetings and cross-team intelligence. Pick one to enter or create a
            new one.
          </p>
        </div>

        {error && (
          <div className="panel border-critical/30 bg-critical/5 px-4 py-3 mb-6 text-meta text-critical">
            {error}
          </div>
        )}

        {loading ? (
          <p className="text-meta text-muted">Loading…</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
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
                className="panel border-dashed border-rule2 hover:border-ink hover:bg-paper transition-colors flex flex-col items-center justify-center gap-2 aspect-square text-muted hover:text-ink"
              >
                <Plus size={20} strokeWidth={1.75} />
                <span className="text-meta font-medium">New workspace</span>
              </button>
            )}
          </div>
        )}
      </main>

      <footer className="border-t border-rule mt-12">
        <div className="max-w-6xl mx-auto px-6 lg:px-8 py-4 text-eyebrow text-muted flex items-baseline justify-between">
          <span>SyncLayer · cross-team intelligence</span>
          <span className="data-mono text-dim">v0.4</span>
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
  const tone =
    ws.critical_conflicts > 0
      ? "critical"
      : ws.conflicts > 0
      ? "warning"
      : "default";

  return (
    <div className="group relative aspect-square">
      <Link
        href={`/w/${ws.id}`}
        className="panel h-full p-5 hover:border-ink transition-colors flex flex-col justify-between"
      >
        {/* Top — name + initial */}
        <div className="flex items-start gap-3 min-w-0">
          <div
            className="w-12 h-12 rounded-md flex items-center justify-center font-semibold text-paper shrink-0"
            style={{ backgroundColor: ws.color, fontSize: "20px" }}
          >
            {ws.name.charAt(0).toUpperCase() || "?"}
          </div>
          <div className="min-w-0 pt-0.5">
            <div className="text-h3 font-semibold truncate leading-tight">
              {ws.name}
            </div>
            <div className="data-mono text-eyebrow text-muted lowercase truncate mt-0.5">
              {ws.id}
            </div>
          </div>
        </div>

        {/* Middle — hero number */}
        <div>
          <div className="eyebrow mb-2">Open conflicts</div>
          <div className="flex items-baseline gap-3">
            <span
              className={cn(
                "figure-num text-figure leading-none",
                tone === "critical" && "text-critical",
                tone === "warning" && "text-warning",
                tone === "default" && "text-ink"
              )}
            >
              {ws.conflicts}
            </span>
            {ws.critical_conflicts > 0 && (
              <span className="text-meta text-critical font-medium">
                {ws.critical_conflicts} critical
              </span>
            )}
          </div>
        </div>

        {/* Bottom — secondary stats */}
        <div className="flex items-baseline justify-between text-meta">
          <span className="text-muted">
            <span className="data-mono text-ink font-medium">{ws.entities}</span>{" "}
            entities
          </span>
          <span className="text-muted">
            <span className="data-mono text-ink font-medium">{ws.teams}</span>{" "}
            teams
          </span>
          <span className="text-eyebrow text-muted">
            {formatRelative(ws.created_at)}
          </span>
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
        <Trash2 size={13} strokeWidth={1.75} />
      </button>
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
    <div className="panel border-ink/40 p-5 aspect-square flex flex-col gap-3">
      <div className="eyebrow">New workspace</div>
      <div className="flex items-center gap-2.5">
        <input
          type="color"
          value={color}
          onChange={(e) => onColor(e.target.value)}
          className="w-9 h-9 rounded-md border border-rule2 cursor-pointer shrink-0"
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
      <div className="text-meta text-muted">
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
