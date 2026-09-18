// SONIC-REDA — Workstation TypeScript Definitions

export type SystemStatus = "CONNECTING" | "LIVE" | "DISCONNECTED" | "OFFLINE" | "ERROR";

export type WorkstationTab = "desktop" | "code" | "changes";

export interface WorklogItem {
  id: string;
  type: "action" | "command" | "read" | "write" | "event" | "evidence" | "thought" | "response" | "approval" | "plan" | "observation" | "replan" | "completed" | "info" | string;
  title: string;
  content?: string;
  command?: string;
  output?: string;
  file?: string;
  lines?: string;
  timestamp?: string;
  duration_seconds?: number;
  exit_code?: number;
  role?: "user" | "assistant" | "system" | string;
  proposed_actions?: any[];
  sub_agent_number?: number;
  sub_mission_id?: string;
  goal?: string;
  success?: boolean;
  findings_summary?: string;
  key_discoveries?: string[];
}

export interface DesktopApp {
  name: string;
  icon: string;
  status: "active" | "running" | "idle" | "background";
}

export interface DesktopState {
  os_name: string;
  display: string;
  status: string;
  active_window?: string;
  running_apps: DesktopApp[];
  vnc_url?: string;
  novnc_url?: string;
  running_processes?: string[];
}

export interface WorkstationState {
  session_id: string;
  tenant_id: string;
  mission_name: string;
  status: "IDLE" | "RUNNING" | "PAUSED" | "COMPLETED" | "ERROR";
  target_repo: string;
  git_branch: string;
  latest_commit?: string;
  active_file: string;
  elapsed_seconds: number;
  thought_summary?: string;
  current_action?: string;
  worklog: WorklogItem[];
  desktop: DesktopState;
  mission?: MissionSummary;
}

export interface MissionSummary {
  status?: string;
  objective?: string;
  events?: Array<{
    id: string;
    type: string;
    title: string;
    content?: string;
  }>;
}

export interface FileTreeResponse {
  files: string[];
}

export interface FileContentResponse {
  path: string;
  filename: string;
  total_lines: number;
  content: string;
  lines: string[];
}

export interface GitDiffResponse {
  diff: string;
  success: boolean;
}

export interface CommandResult {
  command: string;
  exit_code: number;
  output: string;
  execution_environment?: string;
}

export interface SessionItem {
  session_id: string;
  mission_name: string;
  status: string;
  workspace_id?: string;
  git_branch: string;
  log_count?: number;
  last_action?: string;
}

/**
 * Normalizes raw responses from /workstation/sessions.
 * Handles arrays, wrapped objects ({ sessions: [...] }, { data: [...] }),
 * empty values, and malformed items without throwing.
 */
export function normalizeSessionList(raw: unknown): SessionItem[] {
  if (!raw) return [];
  let list: unknown[] = [];

  if (Array.isArray(raw)) {
    list = raw;
  } else if (typeof raw === "object" && raw !== null) {
    const obj = raw as Record<string, unknown>;
    if (Array.isArray(obj.sessions)) {
      list = obj.sessions;
    } else if (Array.isArray(obj.data)) {
      list = obj.data;
    } else {
      return [];
    }
  } else {
    return [];
  }

  return list
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((item, idx) => ({
      session_id: typeof item.session_id === "string" && item.session_id.trim()
        ? item.session_id.trim()
        : `session-${idx}`,
      mission_name: typeof item.mission_name === "string" && item.mission_name.trim()
        ? item.mission_name.trim()
        : "Unprovisioned Workstation",
      status: typeof item.status === "string" && item.status.trim()
        ? item.status.trim()
        : "IDLE",
      workspace_id: typeof item.workspace_id === "string" ? item.workspace_id : "",
      git_branch: typeof item.git_branch === "string" ? item.git_branch : "",
      log_count: typeof item.log_count === "number" ? item.log_count : 0,
      last_action: typeof item.last_action === "string" ? item.last_action : "Ready when you are.",
    }));
}

/**
 * Sanitizes current_action to eliminate puppet strings ("Reasoning queued", "queued"),
 * ensures that if status is IDLE, PAUSED, BLOCKED, or COMPLETED, no spinner text is returned,
 * and preserves real in-progress actions.
 */
export function sanitizeCurrentAction(
  action?: string | null,
  status?: string | null,
  loading?: boolean
): string | undefined {
  // If state is not RUNNING and not loading, or if explicitly idle/finished:
  const normalizedStatus = (status || "").toUpperCase();
  if (
    normalizedStatus === "IDLE" ||
    normalizedStatus === "PAUSED" ||
    normalizedStatus === "BLOCKED" ||
    normalizedStatus === "COMPLETED" ||
    normalizedStatus === "ERROR"
  ) {
    return undefined;
  }

  if (normalizedStatus !== "RUNNING" && !loading) {
    return undefined;
  }

  const raw = (action || "").trim();
  if (!raw) {
    return loading || normalizedStatus === "RUNNING" ? "Thinking..." : undefined;
  }

  const lower = raw.toLowerCase();
  // Strip puppet strings / queued text / idle text / reasoning placeholders
  if (
    lower.includes("queued") ||
    lower.includes("reasoning queued") ||
    lower.includes("autonomous reasoning") ||
    lower.startsWith("idle") ||
    lower.startsWith("ready") ||
    lower === "thinking" ||
    lower.startsWith("thinking:")
  ) {
    return normalizedStatus === "RUNNING" || loading ? "Thinking..." : undefined;
  }

  return raw;
}
