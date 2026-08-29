// SONIC-REDA — Workstation TypeScript Definitions

export type SystemStatus = "CONNECTING" | "LIVE" | "DISCONNECTED" | "OFFLINE" | "ERROR";

export type WorkstationTab = "desktop" | "code" | "changes" | "research" | "evidence" | "evolution" | "mission";

export interface WorklogItem {
  id: string;
  type: "action" | "command" | "read" | "write" | "event" | "evidence" | "thought";
  title: string;
  content?: string;
  command?: string;
  output?: string;
  file?: string;
  lines?: string;
  timestamp?: string;
  duration_seconds?: number;
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
