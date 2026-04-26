import clsx, { type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

/**
 * Parse a timestamp emitted by the backend.
 *
 * The backend writes naive UTC ISO strings (`datetime.utcnow().isoformat()`,
 * no `Z`/offset). JavaScript's `new Date()` interprets such strings as
 * **local time**, which produces a time-zone-sized offset on every relative
 * timestamp. This helper appends `Z` when no offset is present so the parse
 * is unambiguously UTC. Use it instead of `new Date(value)` everywhere a
 * backend timestamp is consumed.
 */
export function parseBackendDate(value: string): Date {
  const hasTz = /Z$|[+-]\d{2}:?\d{2}$/.test(value);
  return new Date(hasTz ? value : value + "Z");
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  try {
    return parseBackendDate(value).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

export function formatRelative(value?: string | null): string {
  if (!value) return "—";
  const ms = Date.now() - parseBackendDate(value).getTime();
  const sec = Math.floor(ms / 1000);
  if (sec < 0) return "just now";
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

export function teamColor(team: string, palette = TEAM_PALETTE): string {
  let hash = 0;
  for (let i = 0; i < team.length; i++)
    hash = (hash * 31 + team.charCodeAt(i)) >>> 0;
  return palette[hash % palette.length];
}

export const TEAM_PALETTE = [
  "#1E3A8A", // cobalt
  "#15803D", // emerald-700
  "#B45309", // amber-700
  "#7E22CE", // purple-700
  "#BE185D", // pink-700
  "#0E7490", // cyan-700
  "#B91C1C", // red-700
  "#3F6212", // lime-700
];

export const SEVERITY_LABEL: Record<string, string> = {
  critical: "Critical",
  warning: "Warning",
  info: "Info",
};

export const CONFLICT_LABEL: Record<string, string> = {
  duplication: "Duplication",
  contradiction: "Contradiction",
  dependency: "Hidden dependency",
  say_vs_do: "Say vs do",
};
