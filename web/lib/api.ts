// Thin HTTP wrapper. All requests go through /api/* which Next rewrites to FastAPI.

import type {
  ChatResponse,
  ChatTurn,
  CompanyConfig,
  Conflict,
  Entity,
  History,
  IngestEvent,
  IngestMeetingResponse,
  MeetingSummary,
  OverviewStats,
  SyncStatus,
  TeamDetail,
  TeamSummary,
} from "./types";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} · ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // Health
  ping: () => http<{ service: string; status: string } & OverviewStats>("/"),

  // Stats
  stats: () => http<OverviewStats>("/stats"),

  // Read
  entities: () => http<Entity[]>("/entities"),
  conflicts: () => http<Conflict[]>("/conflicts"),
  events: () => http<IngestEvent[]>("/events"),

  // Config
  getConfig: () => http<CompanyConfig>("/config"),
  setConfig: (cfg: CompanyConfig) =>
    http<CompanyConfig>("/config", { method: "POST", body: JSON.stringify(cfg) }),
  upsertTeam: (team: {
    name: string;
    color?: string;
    repos?: string[];
    slack_channels?: string[];
    ticket_paths?: string[];
  }) =>
    http<CompanyConfig>("/config/team", {
      method: "POST",
      body: JSON.stringify(team),
    }),
  deleteTeam: (name: string) =>
    http<CompanyConfig>(`/config/team/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  // Teams
  teams: () => http<(TeamSummary & { config: TeamDetail["config"] })[]>("/teams"),
  team: (name: string) =>
    http<TeamDetail>(`/teams/${encodeURIComponent(name)}`),
  orphanTeams: () =>
    http<{ team: string; entity_count: number }[]>("/teams/orphans"),
  forgetTeamEntities: (name: string) =>
    http<{ removed_entities: number }>(
      `/entities/by-team/${encodeURIComponent(name)}`,
      { method: "DELETE" }
    ),

  // Ingest meeting (form-data)
  ingestMeetingText: async (
    team: string,
    transcript: string,
    meetingId?: string
  ): Promise<IngestMeetingResponse> => {
    const fd = new FormData();
    fd.append("team", team);
    fd.append("transcript_text", transcript);
    if (meetingId) fd.append("meeting_id", meetingId);
    const res = await fetch("/api/ingest/meeting", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  ingestMeetingAudio: async (
    team: string,
    file: File,
    meetingId?: string
  ): Promise<IngestMeetingResponse> => {
    const fd = new FormData();
    fd.append("team", team);
    fd.append("audio", file);
    if (meetingId) fd.append("meeting_id", meetingId);
    const res = await fetch("/api/ingest/meeting", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // Bulk
  analyze: () => http<any>("/analyze", { method: "POST" }),

  // Feature chatbot
  chat: (message: string, history: ChatTurn[] = []) =>
    http<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, history }),
    }),

  // Live sync state (per-source last_synced / last_error / last_activity)
  syncStatus: () => http<SyncStatus>("/sync/status"),

  // Time-series for the dashboard
  history: (days: number = 14) => http<History>(`/history?days=${days}`),

  // Meetings
  meetings: () => http<MeetingSummary[]>("/meetings"),
};
