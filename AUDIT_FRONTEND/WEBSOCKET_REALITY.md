# WEBSOCKET REALITY AUDIT

**Date:** 2026-08-28  
**Audit Target:** Realtime streaming, event subscriptions, and WebSocket connections in `sonic-dashboard/`

---

## 1. WebSocket Channel Scan

A recursive search across `sonic-dashboard/` for `WebSocket`, `EventSource`, `SSE`, and streaming connections yielded exactly **one** WebSocket connection in the entire frontend:

- **File:** `app/terminal/page.tsx:26`
- **URI:** `ws://localhost:8000/terminal/ws/terminal`

### Analysis of the Terminal WebSocket Connection:

```typescript
// app/terminal/page.tsx:25-33
const connectWs = () => {
  const ws = new WebSocket("ws://localhost:8000/terminal/ws/terminal");
  wsRef.current = ws;

  ws.onopen = () => setConnected(true);
  ws.onclose = () => setConnected(false);
  ws.onerror = () => setConnected(false);
```

#### Why it is BROKEN in practice:
1. **Missing Token Parameter:** The backend in `sonic-core/sonic/api/routes/terminal.py:125` enforces:
   ```python
   user = verify_ws_token(token)
   if not user:
       await websocket.send_json({
           "type": "error",
           "data": "\x1b[1;31m[AUTH ERROR] Authentication required. Please provide a valid JWT token.\x1b[0m\r\n"
       })
       await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
       return
   ```
   The frontend never passes `?token=...`, causing immediate connection termination.

2. **Simulated Local Echo:**
   When the connection fails, the user typing in the terminal does not see an error; instead, `app/terminal/page.tsx:50-54` echoes the input locally:
   ```typescript
   // Local echo for offline/simulation
   setBuffer(prev => [
     ...prev,
     `\x1b[32m[sonic@sandbox]\x1b[0m $ ${cmd}\n`,
   ]);
   ```
   This gives the user the illusion of a working terminal prompt even though no command is actually sent or executed.

---

## 2. Worklog, Telemetry, & Agent Reasoning Streams

### A. Main Workstation Worklog (`app/page.tsx`)
- **WebSocket?** **NONE.**
- **Implementation:** `app/page.tsx:137-141` uses `setInterval` polling every **4000ms**:
  ```typescript
  const interval = setInterval(() => {
    fetchState();
    fetchDesktop();
  }, 4000);
  ```
- **Real-Time Assessment:** Polling an in-memory dictionary every 4 seconds. There is no live event stream, no SSE, and no pub/sub channel.

### B. Animated Spinner & "Devin Typing" Badges
- **Source:** Pure CSS micro-animations:
  - `app/page.tsx:565-567`: CSS `animate-bounce` on 3 colored dots.
  - `app/page.tsx:791`: CSS `animate-ping` on a white dot inside a blue box labeled `"Devin typing at ..."`
- **Backend Connection:** ZERO backend trigger. It is a permanent CSS animation rendered whenever the component mounts.

---

## 3. Summary of Realtime Reality

| Telemetry / Event Domain | Claimed UI State | Actual Mechanism | Backend Channel | Classification |
|---|---|---|---|---|
| Worklog Event Stream | Live autonomous execution feed | `setInterval(fetch, 4000)` polling | `GET /workstation/state` | `SIMULATED REALTIME` |
| Virtual PTY Terminal | Live Daytona sandbox shell | WebSocket without auth token + local echo fallback | `ws://localhost:8000/terminal/ws/terminal` | `BROKEN` / `SIMULATED` |
| Agent Thinking State | Live cognitive reasoning | Static text strings in fallback array | None | `MOCK` |
| AI Code Editor Cursor | Live agent typing indicator | Static absolute positioned div + CSS `animate-ping` | None | `MOCK` |
| Waveform Timeline | Realtime agent thought waveform | Static array `[4, 8, 12, 6, 14, 9, ...]` rendered with height styles | None | `MOCK` |
| Mission Milestones | Live step progression | Static array + local state index | None | `MOCK` |
| Security Test Stream | Live adversarial test execution | Static list with hardcoded durations | None | `MOCK` |
