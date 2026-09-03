// SONIC-REDA — Unified API Client

import { getAuthToken, ensureAuthToken } from "./auth";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface RequestOptions extends RequestInit {
  timeout?: number;
}

export async function apiClient<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { timeout = 15000, headers = {}, ...rest } = options;

  // Ensure an authenticated token exists
  let token = getAuthToken();
  if (!token && typeof window !== "undefined" && !endpoint.includes("/auth/")) {
    token = await ensureAuthToken(API_BASE);
  }

  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);

  const requestHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(headers as Record<string, string>),
  };

  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  try {
    const res = await fetch(url, {
      ...rest,
      headers: requestHeaders,
      signal: controller.signal,
    });

    clearTimeout(id);

    if (res.status === 401) {
      // Re-provision token if expired and retry once
      const newToken = await ensureAuthToken(API_BASE);
      if (newToken && newToken !== token) {
        requestHeaders.Authorization = `Bearer ${newToken}`;
        const retryRes = await fetch(url, { ...rest, headers: requestHeaders });
        if (retryRes.ok) return (await retryRes.json()) as T;
      }
      throw new Error("Authentication required (401 Unauthorized)");
    }

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errorData.detail || `API error ${res.status}: ${res.statusText}`);
    }

    return (await res.json()) as T;
  } catch (err: any) {
    clearTimeout(id);
    if (err.name === "AbortError") {
      throw new Error(`Request timeout (${timeout}ms) on ${endpoint}`);
    }
    throw err;
  }
}

// Workstation Specific API Endpoints
export const api = {
  getWorkstationState: (sessionId = "default") =>
    apiClient<any>(`/workstation/state?session_id=${encodeURIComponent(sessionId)}`),

  listSessions: () =>
    apiClient<Array<{
      session_id: string;
      mission_name: string;
      status: string;
      git_branch: string;
      log_count: number;
      last_action: string;
    }>>("/workstation/sessions"),

  deleteSession: (sessionId: string) =>
    apiClient<any>(`/workstation/session?session_id=${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    }),

  getDesktopStatus: (sessionId = "default") =>
    apiClient<any>(`/workstation/desktop/status?session_id=${encodeURIComponent(sessionId)}`),

  provisionDesktop: (sessionId = "default") =>
    apiClient<any>(`/workstation/desktop/provision?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      timeout: 120000,
    }),

  provisionResearchLab: (sessionId = "default") =>
    apiClient<any>(`/workstation/research-lab/provision?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      timeout: 120000,
    }),

  getResearchLabStatus: (sessionId = "default") =>
    apiClient<any>(`/workstation/research-lab/status?session_id=${encodeURIComponent(sessionId)}`),

  destroyResearchLab: (sessionId = "default") =>
    apiClient<any>(`/workstation/research-lab?session_id=${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    }),

  provisionTargetSandbox: (target: string, scopeConfig: Record<string, unknown>, sessionId = "default") =>
    apiClient<any>(`/workstation/target-sandbox/provision?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      body: JSON.stringify({ target, scope_config: scopeConfig }),
      timeout: 120000,
    }),

  getTargetSandboxStatus: (sessionId = "default") =>
    apiClient<any>(`/workstation/target-sandbox/status?session_id=${encodeURIComponent(sessionId)}`),

  destroyTargetSandbox: (sessionId = "default") =>
    apiClient<any>(`/workstation/target-sandbox?session_id=${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    }),

  executeTargetSandboxCommand: (command: string, sessionId = "default", approved = false) =>
    apiClient<any>(`/workstation/target-sandbox/command?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      body: JSON.stringify({ command, approved }),
    }),

  startMission: (objective: string, sessionId = "default") =>
    apiClient<any>(`/workstation/mission/start?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      body: JSON.stringify({ objective }),
    }),

  getMissionEvents: (sessionId = "default", after = 0) =>
    apiClient<any>(`/workstation/mission/events?session_id=${encodeURIComponent(sessionId)}&after=${after}`),

  getMissionEvidence: (sessionId = "default") =>
    apiClient<any>(`/workstation/mission/evidence?session_id=${encodeURIComponent(sessionId)}`),

  openMissionBrowser: (url: string, sessionId = "default", approved = false) =>
    apiClient<any>(`/workstation/mission/browser-open?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      body: JSON.stringify({ url, approved }),
    }),

  getDesktopScreenshot: (sessionId = "default") =>
    apiClient<any>(`/workstation/desktop/screenshot?session_id=${encodeURIComponent(sessionId)}`),

  getDesktopStream: (sessionId = "default") =>
    apiClient<{ status: string; vnc_url: string | null; tenant_id: string }>(
      `/workstation/desktop/stream?session_id=${encodeURIComponent(sessionId)}`
    ),

  postGUIAction: (
    sessionId: string = "default",
    actionData: {
      action: string;
      x?: number;
      y?: number;
      text?: string;
      key?: string;
      app_name?: string;
      scroll_delta?: number;
    }
  ) =>
    apiClient<any>(`/workstation/desktop/gui-action?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      body: JSON.stringify(actionData),
    }),

  executeDesktopAction: (actionData: {
    action: string;
    target?: string;
    coordinates?: [number, number];
    text?: string;
    key?: string;
    sessionId?: string;
  }) =>
    apiClient<any>("/workstation/desktop/action", {
      method: "POST",
      body: JSON.stringify({
        action: actionData.action,
        target: actionData.target,
        coordinates: actionData.coordinates,
        text: actionData.text,
        key: actionData.key,
      session_id: actionData.sessionId || "default",
      }),
    }),

  getFileTree: (sessionId = "default") =>
    apiClient<{ files: string[] }>(`/workstation/tree?session_id=${encodeURIComponent(sessionId)}`),

  getFileContent: (path: string, sessionId = "default") =>
    apiClient<any>(`/workstation/file?path=${encodeURIComponent(path)}&session_id=${encodeURIComponent(sessionId)}`),

  saveFileContent: (path: string, content: string, sessionId = "default") =>
    apiClient<any>(`/workstation/file?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      body: JSON.stringify({ path, content }),
    }),

  getGitDiff: (sessionId = "default") =>
    apiClient<{ diff: string; success: boolean }>(`/workstation/git-diff?session_id=${encodeURIComponent(sessionId)}`),

  sendPrompt: (prompt: string, sessionId = "default", mode = "normal") =>
    apiClient<any>("/workstation/prompt", {
      method: "POST",
      body: JSON.stringify({ prompt, session_id: sessionId, mode }),
    }),

  executeCommand: (command: string, sessionId = "default") =>
    apiClient<any>("/workstation/command", {
      method: "POST",
      body: JSON.stringify({ command, session_id: sessionId }),
    }),

  // Graph Memory
  getGraph: () =>
    apiClient<any>("/live/graph"),

  // Evidence
  getEvidence: () =>
    apiClient<any>("/live/evidence"),

  // Experiments / Self-Evolution
  getExperiments: () =>
    apiClient<any>("/live/experiments"),

  runBenchmark: () =>
    apiClient<any>("/live/experiments/benchmark", { method: "POST" }),

  // Settings
  getSettings: () =>
    apiClient<any>("/live/settings"),

  updateSettings: (config: any) =>
    apiClient<any>("/live/settings", {
      method: "POST",
      body: JSON.stringify(config),
    }),

  // Self-Security Lab
  runSecurityAudit: () =>
    apiClient<any>("/security/audit", { method: "POST", timeout: 60000 }),

  getSecurityTests: () =>
    apiClient<any>("/security/tests"),

  getSecurityFindings: () =>
    apiClient<any>("/security/findings"),

  getReleaseGate: () =>
    apiClient<any>("/security/release-gate"),

  getAttackSurface: () =>
    apiClient<any>("/security/attack-surface"),

  reproduceSecurityTest: (testId: string) =>
    apiClient<any>(`/security/reproduce/${encodeURIComponent(testId)}`, { method: "POST", timeout: 60000 }),

  // Experiment lifecycle
  approveExperiment: (id: string) =>
    apiClient<any>(`/experiments/${encodeURIComponent(id)}/approve`, { method: "POST" }),

  rejectExperiment: (id: string, reason: string) =>
    apiClient<any>(`/experiments/${encodeURIComponent(id)}/reject?reason=${encodeURIComponent(reason)}`, { method: "POST" }),

  promoteExperiment: (id: string) =>
    apiClient<any>(`/experiments/${encodeURIComponent(id)}/promote`, { method: "POST" }),

  getExperimentWeaknesses: () =>
    apiClient<any>("/experiments/weaknesses/summary"),

  getExperimentHistory: () =>
    apiClient<any>("/experiments/history/timeline"),
};
