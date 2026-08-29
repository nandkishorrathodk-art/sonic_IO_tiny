// SONIC-REDA — Frontend Authentication Helper

const TOKEN_KEY = "sonic_auth_token";
const USER_KEY = "sonic_auth_user";

export interface UserSession {
  email: string;
  name: string;
  role: string;
  tenant_id: string;
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string, user?: UserSession): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
}

export function clearAuth(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getUserSession(): UserSession {
  if (typeof window === "undefined") {
    return { email: "engineer@company.com", name: "Lead Engineer", role: "operator", tenant_id: "default" };
  }
  const raw = localStorage.getItem(USER_KEY);
  if (raw) {
    try {
      return JSON.parse(raw);
    } catch {
      // ignore
    }
  }
  return {
    email: "engineer@company.com",
    name: "Lead Engineer",
    role: "operator",
    tenant_id: "default",
  };
}

/**
 * Ensures a valid JWT token is stored in localStorage.
 * If absent, fetches a signed JWT from /auth/dev-token.
 */
export async function ensureAuthToken(apiBase: string): Promise<string> {
  const existing = getAuthToken();
  if (existing) return existing;

  try {
    const res = await fetch(`${apiBase}/auth/dev-token`, { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      if (data?.access_token) {
        setAuthToken(data.access_token, data.token?.user);
        return data.access_token;
      }
    }
  } catch (err) {
    console.error("Failed to auto-provision session token:", err);
  }
  return "";
}
