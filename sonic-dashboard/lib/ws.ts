// SONIC-REDA — Authenticated WebSocket Client

import { getAuthToken } from "./auth";
import { API_BASE } from "./api";

export function createTerminalWebSocket(options: {
  onOpen?: () => void;
  onClose?: (e: CloseEvent) => void;
  onError?: (err: Event) => void;
  onMessage?: (data: any) => void;
  container?: string;
}): WebSocket {
  const token = getAuthToken();
  const wsUrl = API_BASE.replace(/^http/, "ws");
  const containerParam = encodeURIComponent(options.container || "sonic-sandbox");
  const tokenParam = token ? `&token=${encodeURIComponent(token)}` : "";
  
  const fullUrl = `${wsUrl}/terminal/ws/terminal?container=${containerParam}${tokenParam}`;
  const ws = new WebSocket(fullUrl);

  if (options.onOpen) ws.onopen = options.onOpen;
  if (options.onClose) ws.onclose = options.onClose;
  if (options.onError) ws.onerror = options.onError;
  if (options.onMessage) {
    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        options.onMessage!(parsed);
      } catch {
        options.onMessage!({ type: "raw", data: event.data });
      }
    };
  }

  return ws;
}
