"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Send,
  ExternalLink,
  X,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
} from "lucide-react";
import { api as apiFactory } from "@/lib/api";
import type { BotStatus, MeetingBot } from "@/lib/types";
import { cn, formatRelative, parseBackendDate } from "@/lib/utils";

const STATUS_LABEL: Record<BotStatus, string> = {
  joining: "joining",
  in_call: "recording",
  processing: "processing",
  done: "done",
  failed: "failed",
};

const STATUS_TONE: Record<BotStatus, string> = {
  joining: "text-warning",
  in_call: "text-critical",
  processing: "text-accent",
  done: "text-success",
  failed: "text-critical",
};

const STATUS_DOT: Record<BotStatus, string> = {
  joining: "bg-warning animate-pulse",
  in_call: "bg-critical animate-pulse",
  processing: "bg-accent animate-pulse",
  done: "bg-success",
  failed: "bg-critical",
};

const URL_PATTERNS: { pattern: RegExp; label: string }[] = [
  { pattern: /meet\.google\.com/i, label: "google_meet" },
  { pattern: /zoom\.us/i, label: "zoom" },
  { pattern: /teams\.microsoft\.com|teams\.live\.com/i, label: "teams" },
  { pattern: /webex\./i, label: "webex" },
];

function detectPlatform(url: string): string | null {
  for (const { pattern, label } of URL_PATTERNS) {
    if (pattern.test(url)) return label;
  }
  return null;
}

function shortenUrl(url: string): string {
  try {
    const u = new URL(url);
    return `${u.host}${u.pathname}`.replace(/\/$/, "");
  } catch {
    return url;
  }
}

export function MeetingBotPanel({
  wsId,
  teams,
  selectedTeam,
  onSelectTeam,
  onBotCompleted,
}: {
  wsId: string;
  teams: string[];
  selectedTeam: string;
  onSelectTeam: (t: string) => void;
  onBotCompleted?: (bot: MeetingBot) => void;
}) {
  const api = useMemo(() => apiFactory(wsId), [wsId]);

  const [bots, setBots] = useState<MeetingBot[]>([]);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [botName, setBotName] = useState("SyncLayer");

  const completedRef = useRef<Set<string>>(new Set());

  const refresh = () => {
    api
      .listBots()
      .then((list) => {
        setBots(list);
        if (onBotCompleted) {
          for (const b of list) {
            if (b.status === "done" && !completedRef.current.has(b.bot_id)) {
              completedRef.current.add(b.bot_id);
              onBotCompleted(b);
            }
          }
        }
      })
      .catch(() => {});
  };

  const hasActive = bots.some(
    (b) => b.status !== "done" && b.status !== "failed"
  );

  useEffect(() => {
    refresh();
    const interval = hasActive ? 4000 : 20000;
    const id = setInterval(refresh, interval);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasActive]);

  const send = async () => {
    if (!url.trim() || !selectedTeam) return;
    setBusy(true);
    setError(null);
    try {
      await api.sendBot({
        meeting_url: url.trim(),
        team: selectedTeam,
        title: title.trim() || undefined,
        bot_name: (botName.trim() || "SyncLayer").slice(0, 64),
      });
      setUrl("");
      setTitle("");
      refresh();
    } catch (e: any) {
      setError(e.message || "Failed to dispatch bot");
    } finally {
      setBusy(false);
    }
  };

  const kick = async (id: string) => {
    if (!confirm("Make the bot leave the meeting?")) return;
    try {
      await api.kickBot(id);
      refresh();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const platform = detectPlatform(url);
  const active = bots.filter(
    (b) => b.status !== "done" && b.status !== "failed"
  );
  const recent = bots.filter(
    (b) => b.status === "done" || b.status === "failed"
  );
  const canSend = !busy && url.trim().length > 5 && !!selectedTeam;

  return (
    <section className="panel overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-rule">
        <div className="flex items-center gap-2.5">
          <h3 className="text-h3 font-semibold leading-tight">Live meetings</h3>
          <span className="font-mono text-eyebrow text-muted">
            {active.length} active
          </span>
        </div>
        <button
          type="button"
          onClick={() => setAdvancedOpen((v) => !v)}
          className={cn(
            "text-eyebrow font-mono text-muted hover:text-ink inline-flex items-center gap-1 transition-colors",
            advancedOpen && "text-ink"
          )}
        >
          Advanced
          <ChevronDown
            size={11}
            className={cn(
              "transition-transform",
              advancedOpen && "rotate-180"
            )}
          />
        </button>
      </div>

      {/* Compact dispatch form */}
      <div className="p-3 border-b border-rule">
        <div className="flex items-stretch gap-2">
          <div className="relative flex-1">
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="meet.google.com/… · zoom.us/… · teams.microsoft.com/…"
              className="input font-mono text-meta pl-8"
              disabled={busy}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canSend) send();
              }}
            />
            <span
              className={cn(
                "absolute left-2.5 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full",
                platform ? "bg-accent" : "bg-rule2"
              )}
              title={platform || "no platform detected"}
            />
          </div>
          <select
            value={selectedTeam}
            onChange={(e) => onSelectTeam(e.target.value)}
            disabled={busy || teams.length === 0}
            className="input text-meta w-40 shrink-0"
            title="Team that owns this meeting"
          >
            {teams.length === 0 ? (
              <option value="">no teams</option>
            ) : (
              teams.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))
            )}
          </select>
          <button
            onClick={send}
            disabled={!canSend}
            className="btn btn-primary inline-flex items-center gap-1.5 shrink-0"
          >
            <Send size={12} strokeWidth={2} />
            {busy ? "Sending" : "Dispatch"}
          </button>
        </div>

        {advancedOpen && (
          <div className="grid sm:grid-cols-2 gap-2 mt-2">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Meeting title (optional)"
              className="input text-meta"
              disabled={busy}
            />
            <input
              value={botName}
              onChange={(e) => setBotName(e.target.value)}
              placeholder="Bot display name"
              className="input text-meta font-mono"
              disabled={busy}
            />
          </div>
        )}

        {error && (
          <div className="text-meta font-mono text-critical mt-2">{error}</div>
        )}
      </div>

      {/* Active calls */}
      {active.length > 0 && (
        <ul className="divide-y divide-rule">
          {active.map((b) => (
            <BotRow key={b.bot_id} bot={b} onKick={kick} />
          ))}
        </ul>
      )}

      {/* Recent completions */}
      {recent.length > 0 && (
        <>
          {active.length > 0 && <div className="border-t border-rule" />}
          <div className="px-5 pt-3 pb-1 eyebrow border-t border-rule">
            Recent
          </div>
          <ul className="divide-y divide-rule">
            {recent.slice(0, 5).map((b) => (
              <BotRow key={b.bot_id} bot={b} onKick={kick} />
            ))}
          </ul>
        </>
      )}

      {/* Empty state */}
      {active.length === 0 && recent.length === 0 && (
        <div className="px-5 py-6 text-meta text-muted font-mono">
          No bots dispatched yet.
        </div>
      )}
    </section>
  );
}

function BotRow({
  bot,
  onKick,
}: {
  bot: MeetingBot;
  onKick: (id: string) => void;
}) {
  const active = bot.status !== "done" && bot.status !== "failed";
  return (
    <li className="px-5 py-3 flex items-center gap-3">
      <span
        className={cn("w-1.5 h-1.5 rounded-full shrink-0", STATUS_DOT[bot.status])}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="text-meta text-ink truncate font-medium">
            {bot.title || shortenUrl(bot.meeting_url)}
          </span>
          <a
            href={bot.meeting_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted hover:text-ink shrink-0"
            title="Open meeting URL"
          >
            <ExternalLink size={11} strokeWidth={1.75} />
          </a>
        </div>
        <div className="flex items-center gap-3 mt-0.5 text-eyebrow font-mono text-muted">
          <span className="lowercase">{bot.team}</span>
          <span className="text-dim">·</span>
          <span className={cn("uppercase tracking-wider", STATUS_TONE[bot.status])}>
            {STATUS_LABEL[bot.status]}
          </span>
          {bot.recall_status && active && (
            <>
              <span className="text-dim">·</span>
              <span className="lowercase">
                {bot.recall_status.replace(/_/g, " ")}
              </span>
            </>
          )}
          <span className="ml-auto" title={parseBackendDate(bot.created_at).toLocaleString()}>
            {formatRelative(bot.created_at)}
          </span>
        </div>
        {bot.status === "done" && (
          <div className="text-meta text-slate mt-1 inline-flex items-center gap-2">
            <CheckCircle2 size={12} className="text-success" strokeWidth={2} />
            <span className="font-mono">
              +{bot.entities_extracted} entities
              <span className="text-dim mx-1.5">·</span>
              <span
                className={cn(
                  bot.new_conflicts > 0 ? "text-critical font-medium" : "text-muted"
                )}
              >
                {bot.new_conflicts} new conflict{bot.new_conflicts === 1 ? "" : "s"}
              </span>
            </span>
          </div>
        )}
        {bot.error && (
          <div className="text-meta text-critical mt-1 inline-flex items-center gap-2">
            <AlertTriangle size={12} strokeWidth={2} />
            <span className="font-mono">{bot.error}</span>
          </div>
        )}
      </div>
      {active && (
        <button
          onClick={() => onKick(bot.bot_id)}
          className="text-muted hover:text-critical shrink-0"
          title="Kick bot from the meeting"
        >
          <X size={14} strokeWidth={1.75} />
        </button>
      )}
    </li>
  );
}
