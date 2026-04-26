// Workspace-scoped HTTP client. Pages bind to a workspace via `api(wsId)`
// and use the returned object exactly like the old global client. Workspace
// registry endpoints (list/create/delete workspaces) live on `workspaceApi`.

import type {
  CompanyConfig,
  Conflict,
  Entity,
  History,
  IngestEvent,
  IngestMeetingResponse,
  MeetingBot,
  MeetingSummary,
  OverviewStats,
  SendBotRequest,
  SlackChannel,
  SlackStatus,
  SyncStatus,
  TeamDetail,
  TeamSummary,
  Workspace,
  WorkspaceSummary,
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

// --- Workspace registry (no /w prefix) -------------------------------------
export const workspaceApi = {
  list: () => http<WorkspaceSummary[]>("/workspaces"),
  get: (id: string) =>
    http<Workspace>(`/workspaces/${encodeURIComponent(id)}`),
  create: (name: string, color: string) =>
    http<Workspace>("/workspaces", {
      method: "POST",
      body: JSON.stringify({ name, color }),
    }),
  update: (id: string, fields: { name?: string; color?: string }) =>
    http<Workspace>(`/workspaces/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(fields),
    }),
  remove: (id: string) =>
    http<{ ok: boolean }>(
      `/workspaces/${encodeURIComponent(id)}`,
      { method: "DELETE" }
    ),
};

// --- Workspace-bound client ------------------------------------------------
export function api(wsId: string) {
  const p = `/w/${encodeURIComponent(wsId)}`;
  return {
    // Stats / health
    stats: () => http<OverviewStats>(`${p}/stats`),

    // Reads
    entities: () => http<Entity[]>(`${p}/entities`),
    conflicts: () => http<Conflict[]>(`${p}/conflicts`),
    events: () => http<IngestEvent[]>(`${p}/events`),
    meetings: () => http<MeetingSummary[]>(`${p}/meetings`),
    history: (days: number = 14) =>
      http<History>(`${p}/history?days=${days}`),

    // Recall.ai bots — dispatch one to a Google Meet / Zoom / Teams URL.
    sendBot: (req: SendBotRequest) =>
      http<MeetingBot>(`${p}/meetings/from-url`, {
        method: "POST",
        body: JSON.stringify(req),
      }),
    listBots: () => http<MeetingBot[]>(`${p}/meetings/bots`),
    kickBot: (botId: string) =>
      http<{ ok: boolean }>(
        `${p}/meetings/bots/${encodeURIComponent(botId)}`,
        { method: "DELETE" }
      ),

    // Slack OAuth integration (per-workspace bot token)
    slackStatus: () => http<SlackStatus>(`${p}/slack/status`),
    slackChannels: () => http<SlackChannel[]>(`${p}/slack/channels`),
    slackDisconnect: () =>
      http<{ ok: boolean }>(`${p}/slack/disconnect`, { method: "POST" }),
    /** URL to send the user to so they install the Slack app for this workspace. */
    slackConnectUrl: () =>
      `/api/slack/oauth/start?ws_id=${encodeURIComponent(wsId)}`,

    // Config
    getConfig: () => http<CompanyConfig>(`${p}/config`),
    setConfig: (cfg: CompanyConfig) =>
      http<CompanyConfig>(`${p}/config`, {
        method: "POST",
        body: JSON.stringify(cfg),
      }),
    upsertTeam: (team: {
      name: string;
      color?: string;
      repos?: string[];
      slack_channels?: string[];
      ticket_paths?: string[];
    }) =>
      http<CompanyConfig>(`${p}/config/team`, {
        method: "POST",
        body: JSON.stringify(team),
      }),
    deleteTeam: (name: string) =>
      http<CompanyConfig>(
        `${p}/config/team/${encodeURIComponent(name)}`,
        { method: "DELETE" }
      ),

    // Teams
    teams: () =>
      http<(TeamSummary & { config: TeamDetail["config"] })[]>(`${p}/teams`),
    team: (name: string) =>
      http<TeamDetail>(`${p}/teams/${encodeURIComponent(name)}`),
    orphanTeams: () =>
      http<{ team: string; entity_count: number }[]>(`${p}/teams/orphans`),
    forgetTeamEntities: (name: string) =>
      http<{ removed_entities: number }>(
        `${p}/entities/by-team/${encodeURIComponent(name)}`,
        { method: "DELETE" }
      ),

    // Live sync state
    syncStatus: () => http<SyncStatus>(`${p}/sync/status`),

    // Meeting ingestion (form-data)
    ingestMeetingText: async (
      team: string,
      transcript: string,
      meetingId?: string
    ): Promise<IngestMeetingResponse> => {
      const fd = new FormData();
      fd.append("team", team);
      fd.append("transcript_text", transcript);
      if (meetingId) fd.append("meeting_id", meetingId);
      const res = await fetch(`/api${p}/ingest/meeting`, {
        method: "POST",
        body: fd,
      });
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
      const res = await fetch(`/api${p}/ingest/meeting`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },

    // Manual analyze (escape hatch)
    analyze: () => http<any>(`${p}/analyze`, { method: "POST" }),
  };
}

export type WorkspaceApi = ReturnType<typeof api>;
