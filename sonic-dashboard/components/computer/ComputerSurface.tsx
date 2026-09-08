import React, { useState, useEffect, useRef } from "react";
import {
  Cloud,
  Maximize2,
  Minimize2,
  RefreshCw,
  Monitor,
  Bot,
  Shield,
  MousePointer,
  Keyboard,
  Send,
  TerminalSquare,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { DesktopState, CommandResult } from "../../types/workstation";
import { api } from "../../lib/api";

interface ComputerSurfaceProps {
  desktopState?: DesktopState & {
    workspace_id?: string;
    sandbox_id?: string;
    image?: string;
    ssh_command?: string;
    display?: string;
    resolution?: { width: number; height: number };
    active_services?: Array<{ name: string; status: string; port: number }>;
    vnc_url?: string;
  };
  onRunCommand: (cmd: string) => Promise<CommandResult | null>;
  commandLogs: string[];
  onProvision?: () => Promise<void>;
  onInterrupt?: () => Promise<void> | void;
  sessionId?: string;
}

export function ComputerSurface({
  desktopState,
  onRunCommand,
  commandLogs,
  onProvision,
  onInterrupt,
  sessionId = "default",
}: ComputerSurfaceProps) {
  const [screenshotBase64, setScreenshotBase64] = useState<string | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [loadingScreen, setLoadingScreen] = useState(false);
  const [isInteractive, setIsInteractive] = useState(false);
  const [inputText, setInputText] = useState("");
  const [sendingInput, setSendingInput] = useState(false);
  const [clickRipples, setClickRipples] = useState<Array<{ id: number; x: number; y: number }>>([]);
  const [showCmdPanel, setShowCmdPanel] = useState(false);
  const [cmdInput, setCmdInput] = useState("");
  const [cmdRunning, setCmdRunning] = useState(false);
  const [useStream, setUseStream] = useState(true);
  const canvasRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const cmdLogRef = useRef<HTMLDivElement>(null);
  const isFetchingScreenshot = useRef(false);

  const streamUrl = desktopState?.novnc_url || (desktopState as any)?.vnc_url || "http://localhost:6080/vnc.html?autoconnect=true&resize=scale";

  const fetchScreenshot = async () => {
    if (isFetchingScreenshot.current) return;
    isFetchingScreenshot.current = true;
    try {
      setLoadingScreen(true);
      const data = await api.getDesktopScreenshot(sessionId);
      if (data?.image_base64) {
        setScreenshotBase64(data.image_base64);
      } else if (data?.screenshot_base64) {
        setScreenshotBase64(data.screenshot_base64);
      }
    } catch {
      // ignore
    } finally {
      setLoadingScreen(false);
      isFetchingScreenshot.current = false;
    }
  };

  useEffect(() => {
    fetchScreenshot();
    const interval = setInterval(fetchScreenshot, 3000);
    return () => clearInterval(interval);
  }, [sessionId]);

  // Auto-scroll the command log to the newest line.
  useEffect(() => {
    if (cmdLogRef.current) {
      cmdLogRef.current.scrollTop = cmdLogRef.current.scrollHeight;
    }
  }, [commandLogs, showCmdPanel]);

  const runCommand = async (e: React.FormEvent) => {
    e.preventDefault();
    const cmd = cmdInput.trim();
    if (!cmd || cmdRunning || !onRunCommand) return;
    setCmdRunning(true);
    setCmdInput("");
    try {
      await onRunCommand(cmd);
    } finally {
      setCmdRunning(false);
    }
  };
  const handleCanvasClick = async (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isInteractive || !canvasRef.current) return;
    const containerRect = canvasRef.current.getBoundingClientRect();

    const img = imgRef.current;
    const naturalWidth = img?.naturalWidth || desktopState?.resolution?.width || 1280;
    const naturalHeight = img?.naturalHeight || desktopState?.resolution?.height || 800;

    const containerRatio = containerRect.width / containerRect.height;
    const imageRatio = naturalWidth / naturalHeight;

    let renderedWidth = containerRect.width;
    let renderedHeight = containerRect.height;
    let offsetX = 0;
    let offsetY = 0;

    if (containerRatio > imageRatio) {
      // Pillarbox (bars on left/right)
      renderedWidth = containerRect.height * imageRatio;
      offsetX = (containerRect.width - renderedWidth) / 2;
    } else {
      // Letterbox (bars on top/bottom)
      renderedHeight = containerRect.width / imageRatio;
      offsetY = (containerRect.height - renderedHeight) / 2;
    }

    const clickRelX = e.clientX - containerRect.left - offsetX;
    const clickRelY = e.clientY - containerRect.top - offsetY;

    if (clickRelX < 0 || clickRelX > renderedWidth || clickRelY < 0 || clickRelY > renderedHeight) {
      return;
    }

    const x = Math.round((clickRelX / renderedWidth) * naturalWidth);
    const y = Math.round((clickRelY / renderedHeight) * naturalHeight);

    const rippleId = Date.now();
    setClickRipples((prev) => [...prev, { id: rippleId, x: e.clientX - containerRect.left, y: e.clientY - containerRect.top }]);
    setTimeout(() => setClickRipples((prev) => prev.filter((r) => r.id !== rippleId)), 800);

    try {
      await api.postGUIAction(sessionId, { action: "CLICK", x, y });
      setTimeout(fetchScreenshot, 300);
    } catch (err) {
      console.error("Failed to dispatch GUI click:", err);
    }
  };

  const handleSendText = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim()) return;
    setSendingInput(true);
    try {
      await api.postGUIAction(sessionId, { action: "TYPE", text: inputText });
      await api.postGUIAction(sessionId, { action: "KEYPRESS", key: "Return" });
      setInputText("");
      setTimeout(fetchScreenshot, 400);
    } catch (err) {
      console.error("Failed to type text:", err);
    } finally {
      setSendingInput(false);
    }
  };

  const handleSendKey = async (key: string) => {
    try {
      await api.postGUIAction(sessionId, { action: "KEYPRESS", key });
      setTimeout(fetchScreenshot, 300);
    } catch (err) {
      console.error("Failed to press key:", err);
    }
  };

  const handleToggleTakeover = async () => {
    const nextState = !isInteractive;
    setIsInteractive(nextState);
    if (nextState && onInterrupt) {
      try {
        await onInterrupt();
      } catch (err) {
        console.error("Failed to trigger onInterrupt during human takeover:", err);
      }
    }
  };

  const hasScreenshot = Boolean(screenshotBase64 && screenshotBase64.length > 100);
  const isLive = Boolean(hasScreenshot || desktopState?.status === "RUNNING" || desktopState?.status === "LIVE");
  const resolution = desktopState?.resolution;
  const displayLabel = [
    desktopState?.display,
    resolution?.width && resolution?.height ? `${resolution.width}x${resolution.height}` : "1280x800",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={`flex-1 panel flex flex-col overflow-hidden shadow-2xl ${
        fullscreen ? "fixed inset-2 z-50 bg-ink-950" : ""
      }`}
    >
      {/* Top bar */}
      <div className="h-9 border-b border-ink-700 bg-ink-850 px-3 flex items-center justify-between text-xs font-mono text-muted">
        <div className="flex items-center gap-2">
          <Cloud className="w-3.5 h-3.5 text-secondary-400" />
          <span className="text-white font-semibold flex items-center gap-1.5 truncate text-[12px]">
            <span>SONIC Cyber Workstation</span>
            {displayLabel && <span className="text-[10px] text-muted-dim font-normal">({displayLabel})</span>}
          </span>
          {isLive ? (
            <span className="chip border border-success/40 bg-success/10 text-success">
              <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
              <span>AGENT CONTROLLED</span>
            </span>
          ) : (
            <span className="chip border border-ink-700 bg-ink-800 text-muted">
              <span className="w-1.5 h-1.5 rounded-full bg-muted-dim" />
              <span>DISCONNECTED</span>
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center rounded bg-ink-950 border border-ink-700 p-0.5 text-[10px] font-mono">
            <button
              type="button"
              onClick={() => setUseStream(true)}
              className={`px-2 py-0.5 rounded transition ${
                useStream ? "bg-secondary-600 text-white font-bold shadow-glow" : "text-muted hover:text-white"
              }`}
              title="Live 60fps interactive noVNC stream"
            >
              VNC Stream
            </button>
            <button
              type="button"
              onClick={() => setUseStream(false)}
              className={`px-2 py-0.5 rounded transition ${
                !useStream ? "bg-secondary-600 text-white font-bold shadow-glow" : "text-muted hover:text-white"
              }`}
              title="Static screenshot snapshots"
            >
              Snapshot
            </button>
          </div>

          <button
            onClick={handleToggleTakeover}
            className={`px-2.5 py-0.5 rounded text-[10px] font-mono font-semibold flex items-center gap-1.5 transition border ${
              isInteractive
                ? "bg-warning/20 text-warning border-warning/60 shadow-glow"
                : "bg-ink-950 text-muted border-ink-700 hover:text-white"
            }`}
            title="Toggle direct mouse & keyboard control"
          >
            <MousePointer className={`w-3 h-3 ${isInteractive ? "text-warning animate-bounce" : ""}`} />
            <span>{isInteractive ? "HUMAN TAKEOVER (ACTIVE)" : "TAKE OVER"}</span>
          </button>

          <button
            onClick={async (e) => { e.stopPropagation(); await fetchScreenshot(); }}
            className="p-1 hover:bg-ink-800 rounded text-muted hover:text-white transition"
            title="Capture live screenshot from sandbox"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingScreen ? "animate-spin text-secondary-400" : ""}`} />
          </button>
          <button
            onClick={() => setFullscreen(!fullscreen)}
            className="p-1 hover:bg-ink-800 rounded text-muted hover:text-white transition"
            title="Toggle fullscreen"
          >
            {fullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Surface body */}
      <div
        className="flex-1 bg-ink-950 relative flex flex-col items-center justify-center overflow-hidden select-none"
        style={{ minHeight: 0 }}
      >
        {useStream && (isLive || streamUrl) ? (
          <div className="w-full h-full flex flex-col items-center justify-center p-2 relative">
            <div
              className="w-full h-full max-w-[1280px] max-h-[800px] aspect-[16/10] rounded border border-ink-700 bg-black relative shadow-2xl overflow-hidden flex items-center justify-center"
            >
              <iframe
                src={streamUrl}
                title="SONIC Cyber Workstation VNC Stream"
                className="w-full h-full border-0"
                allow="clipboard-read; clipboard-write; fullscreen"
              />
              <div className="absolute top-2.5 left-2.5 z-20 flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-black/80 border border-success/40 text-[11px] font-mono text-success shadow-lg backdrop-blur-sm pointer-events-none">
                <Bot className="w-3.5 h-3.5 text-success" />
                <span>SONIC Autonomous Desktop</span>
                <span className="text-[9px] text-muted-dim uppercase tracking-wider ml-1 bg-ink-800 px-1 py-0.2 rounded">60 FPS Live VNC</span>
              </div>
            </div>
          </div>
        ) : hasScreenshot ? (
          <div className="w-full h-full flex flex-col items-center justify-center p-2 relative">
            <div
              ref={canvasRef}
              onClick={handleCanvasClick}
              className={`w-full h-full max-w-[1280px] max-h-[800px] aspect-[16/10] rounded border border-ink-700 bg-black relative shadow-2xl overflow-hidden flex items-center justify-center ${
                isInteractive ? "cursor-crosshair ring-2 ring-warning/50" : ""
              }`}
            >
              <img
                ref={imgRef}
                src={`data:image/png;base64,${screenshotBase64}`}
                alt="SONIC Cyber Workstation"
                className="w-full h-full object-contain pointer-events-none select-none"
              />

              {clickRipples.map((r) => (
                <span
                  key={r.id}
                  style={{ left: r.x, top: r.y }}
                  className="absolute -translate-x-1/2 -translate-y-1/2 w-6 h-6 rounded-full border-2 border-warning bg-warning/30 animate-ping pointer-events-none z-30"
                />
              ))}

              <div className="absolute top-2.5 left-2.5 z-20 flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-black/80 border border-success/40 text-[11px] font-mono text-success shadow-lg backdrop-blur-sm pointer-events-none">
                <Bot className="w-3.5 h-3.5 text-success" />
                <span>SONIC Autonomous Desktop</span>
                <span className="text-[9px] text-muted-dim uppercase tracking-wider ml-1 bg-ink-800 px-1 py-0.2 rounded">Live Feed</span>
              </div>

              {isInteractive && (
                <div className="absolute top-2.5 right-2.5 z-20 flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-warning/20 border border-warning/50 text-[11px] font-mono text-warning shadow-lg backdrop-blur-sm pointer-events-none">
                  <MousePointer className="w-3.5 h-3.5 text-warning" />
                  <span>Click anywhere to control</span>
                </div>
              )}

              <div className="absolute bottom-2.5 right-2.5 z-20 flex items-center gap-1.5 px-2 py-0.5 rounded bg-black/70 border border-ink-700 text-[10px] font-mono text-muted backdrop-blur-sm pointer-events-none">
                <Shield className="w-3 h-3 text-secondary-400" />
                <span>Agent Sandboxed (Fail-Closed)</span>
              </div>
            </div>

            {isInteractive && (
              <div className="w-full max-w-[1280px] mt-2 flex items-center gap-2 bg-ink-850 border border-warning/40 p-2 rounded-lg z-20">
                <Keyboard className="w-4 h-4 text-warning shrink-0 ml-1" />
                <form onSubmit={handleSendText} className="flex-1 flex items-center gap-2">
                  <input
                    type="text"
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    placeholder="Type here to send keystrokes directly into active window…"
                    className="flex-1 bg-ink-950 border border-ink-700 focus:border-warning px-3 py-1 text-xs font-mono text-white rounded outline-none"
                  />
                  <button
                    type="submit"
                    disabled={sendingInput || !inputText.trim()}
                    className="px-3 py-1 bg-warning/20 hover:bg-warning/30 border border-warning/50 text-warning font-mono font-bold text-xs rounded flex items-center gap-1 disabled:opacity-40"
                  >
                    <Send className="w-3 h-3" />
                    <span>Send</span>
                  </button>
                </form>
                <div className="flex items-center gap-1 border-l border-ink-700 pl-2">
                  <button onClick={() => handleSendKey("Return")} className="px-2 py-1 bg-ink-800 hover:bg-ink-700 text-muted-bright text-[10px] font-mono rounded">Enter</button>
                  <button onClick={() => handleSendKey("Escape")} className="px-2 py-1 bg-ink-800 hover:bg-ink-700 text-muted-bright text-[10px] font-mono rounded">Esc</button>
                  <button onClick={() => handleSendKey("Tab")} className="px-2 py-1 bg-ink-800 hover:bg-ink-700 text-muted-bright text-[10px] font-mono rounded">Tab</button>
                </div>
              </div>
            )}
          </div>
        ) : isLive ? (
          <div className="w-full h-full max-w-[1280px] max-h-[800px] aspect-[16/10] rounded border border-ink-700 bg-ink-900 flex flex-col items-center justify-center p-6 text-center space-y-3 m-3">
            <div className="w-12 h-12 rounded-full bg-ink-850 border border-success/40 flex items-center justify-center text-success">
              <RefreshCw className="w-6 h-6 animate-spin" />
            </div>
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-white font-mono">Connecting to live agent desktop…</h3>
              <p className="text-xs text-muted font-mono max-w-md">
                Streaming real-time view from SONIC Cyber Workstation. The display will appear momentarily.
              </p>
            </div>
          </div>
        ) : (
          <div className="w-full h-full max-w-[1280px] max-h-[800px] aspect-[16/10] rounded border border-ink-700 bg-ink-900 flex flex-col items-center justify-center p-6 text-center space-y-3 m-3">
            <div className="w-12 h-12 rounded-full bg-ink-850 border border-ink-700 flex items-center justify-center text-muted">
              <Monitor className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-white font-mono">No live display — sandbox disconnected</h3>
              <p className="text-xs text-muted font-mono max-w-md">
                No cyber workstation is attached to this session. Connect or launch sonic-desktop-workstation to stream the desktop.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {onProvision && !desktopState?.workspace_id && (
                <button
                  onClick={async (e) => { e.stopPropagation(); await onProvision(); }}
                  className="btn-secondary !px-3 !py-1.5 text-xs font-mono"
                >
                  Connect Workstation
                </button>
              )}
              <button
                onClick={(e) => { e.stopPropagation(); fetchScreenshot(); }}
                className="btn-ghost !px-3 !py-1.5 text-xs font-mono"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingScreen ? "animate-spin text-secondary-400" : ""}`} />
                <span>Sync Display</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Command terminal panel — executes inside the sandbox via onRunCommand */}
      <div className="border-t border-ink-700 bg-ink-900 flex-shrink-0">
        <button
          onClick={() => setShowCmdPanel((v) => !v)}
          className="w-full px-3 py-2 flex items-center justify-between text-xs font-mono text-muted hover:text-white transition"
        >
          <span className="flex items-center gap-1.5">
            <TerminalSquare className="w-3.5 h-3.5 text-secondary-400" />
            <span className="font-semibold">Sandbox Command Terminal</span>
            <span className="text-[10px] text-muted-dim">({commandLogs.length} lines)</span>
          </span>
          {showCmdPanel ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
        </button>
        {showCmdPanel && (
          <div className="px-3 pb-3 space-y-2">
            <div
              ref={cmdLogRef}
              className="h-32 overflow-auto rounded border border-ink-700 bg-ink-950 p-2 text-[11px] font-mono leading-relaxed"
            >
              {commandLogs.length === 0 ? (
                <div className="text-muted-dim">No commands run yet. Execute a command below.</div>
              ) : (
                commandLogs.map((line, i) => {
                  const isPrompt = line.startsWith("sonic@workstation") || line.startsWith("sonic@sonic-desktop-workstation") || line.startsWith("sonic@daytona");
                  const isFail = line.startsWith("[FAIL-CLOSED REJECTED]");
                  return (
                    <div
                      key={i}
                      className={`whitespace-pre-wrap break-all ${
                        isPrompt ? "text-secondary-400" : isFail ? "text-danger" : "text-muted-bright"
                      }`}
                    >
                      {line}
                    </div>
                  );
                })
              )}
            </div>
            <form onSubmit={runCommand} className="flex items-center gap-2">
              <span className="text-[11px] font-mono text-secondary-400 shrink-0">sonic@workstation:~$</span>
              <input
                type="text"
                value={cmdInput}
                onChange={(e) => setCmdInput(e.target.value)}
                placeholder="Run a command inside the sandbox (fail-closed enforced)…"
                className="flex-1 bg-ink-950 border border-ink-700 focus:border-secondary-500 px-2 py-1 text-[11px] font-mono text-white rounded outline-none"
              />
              <button
                type="submit"
                disabled={cmdRunning || !cmdInput.trim()}
                className="px-3 py-1 bg-secondary-600/20 hover:bg-secondary-600/30 border border-secondary-500/50 text-secondary-300 font-mono font-bold text-[11px] rounded flex items-center gap-1 disabled:opacity-40"
              >
                {cmdRunning ? <span className="w-3 h-3 border-2 border-secondary-500/40 border-t-secondary-300 rounded-full animate-spin" /> : <Send className="w-3 h-3" />}
                <span>Run</span>
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
