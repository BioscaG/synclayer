// Mirrors backend/models/schemas.py for type-safe consumption.

export type SourceType = "meeting" | "github" | "slack" | "ticket";
export type DecisionType =
  | "decision"
  | "plan"
  | "commitment"
  | "concern"
  | "dependency";
export type ConflictType =
  | "duplication"
  | "contradiction"
  | "dependency"
  | "say_vs_do";
export type Severity = "critical" | "warning" | "info";

export interface Entity {
  id: string;
  name: string;
  description: string;
  source_type: SourceType;
  source_id: string;
  team: string;
  decision_type: DecisionType;
  timestamp: string;
  speaker?: string | null;
  confidence: number;
  raw_text?: string;
}

export interface Conflict {
  id: string;
  conflict_type: ConflictType;
  severity: Severity;
  entity_a: Entity;
  entity_b: Entity;
  similarity_score: number;
  explanation: string;
  recommendation: string;
}

export interface IngestEvent {
  id: string;
  source_type: SourceType;
  team: string;
  description: string;
  entities_extracted: number;
  timestamp: string;
}

export interface TeamConfig {
  color?: string;
  repos: string[];
  slack_channels: string[];
  ticket_paths: string[];
}

export interface CompanyConfig {
  name: string;
  teams: Record<string, TeamConfig>;
}

export interface SourceState {
  initialized: boolean;
  last_synced_at: string | null;
  /** Most recent commit / PR timestamp seen in the source itself (repos only). */
  last_activity_at?: string | null;
  seen_pr_numbers: number[];
  seen_commit_shas: string[];
  seen_message_ts: string[];
  entity_count: number;
  last_error?: string | null;
  last_attempt_at?: string | null;
}

export interface TeamSummary {
  team: string;
  entities: number;
  by_source: Record<string, number>;
  by_type: Record<string, number>;
  concerns: number;
  active_work: number;
  conflicts: number;
  critical_conflicts: number;
}

export interface TeamDetail {
  team: string;
  summary: TeamSummary;
  config: TeamConfig;
  active_work: Entity[];
  concerns: Entity[];
  dependencies: Entity[];
  entities: Entity[];
  conflicts: Conflict[];
  internal_duplications: Array<{
    entity_a: Entity;
    entity_b: Entity;
    similarity: number;
  }>;
  source_states: Record<string, SourceState>;
}

export interface Workspace {
  id: string;
  name: string;
  color: string;
  created_at: string;
}

export interface WorkspaceSummary extends Workspace {
  entities: number;
  teams: number;
  conflicts: number;
  critical_conflicts: number;
}

export interface OverviewStats {
  entities: number;
  by_source: Record<string, number>;
  by_team: Record<string, number>;
  pair_cache: number;
  conflicts: number;
  last_meeting_analysis_at: string | null;
  pending_non_meeting_entities: number;
}

export interface PollerStatus {
  enabled: boolean;
  interval_seconds: number;
  last_poll_at: string | null;
  last_poll_duration_ms: number | null;
  last_poll_error: string | null;
  last_new_entities: number;
  ticks: number;
  is_running: boolean;
}

export interface SyncStatus {
  polling: PollerStatus;
  sources: Record<string, SourceState>;
}

export interface ConflictSnapshot {
  at: string;
  total: number;
  critical: number;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  entities: number;
}

export interface DailyEntities {
  date: string;
  meeting: number;
  github: number;
  slack: number;
  ticket: number;
}

export interface DailyEvents {
  date: string;
  events: number;
}

export interface History {
  conflict_snapshots: ConflictSnapshot[];
  daily_entities: DailyEntities[];
  daily_events: DailyEvents[];
  window_days: number;
}

export interface MeetingSummary {
  meeting_id: string;
  team: string;
  ingested_at: string;
  entity_count: number;
}

export type BotStatus =
  | "joining"
  | "in_call"
  | "processing"
  | "done"
  | "failed";

export interface MeetingBot {
  bot_id: string;
  ws_id: string;
  team: string;
  meeting_url: string;
  title: string;
  bot_name: string;
  status: BotStatus;
  recall_status: string;
  error: string | null;
  transcript_chars: number;
  entities_extracted: number;
  new_conflicts: number;
  created_at: string;
  completed_at: string | null;
}

export interface SlackStatus {
  connected: boolean;
  configured: boolean;
  team_id?: string | null;
  team_name?: string | null;
  connected_at?: string | null;
}

export interface SlackChannel {
  id: string;
  name: string;
  is_private: boolean;
  is_member: boolean;
  num_members?: number;
  topic?: string;
}

export interface SendBotRequest {
  meeting_url: string;
  team: string;
  title?: string;
  bot_name?: string;
  transcription_provider?: string;
}

export interface IngestMeetingResponse {
  entities_extracted: number;
  new_in_memory: number;
  triggered_analysis: boolean;
  analysis: {
    entities: number;
    matches: number;
    conflicts: number;
    critical: number;
    by_type: Record<string, number>;
    new_conflicts: number;
  } | null;
  new_conflicts: Conflict[];
}
