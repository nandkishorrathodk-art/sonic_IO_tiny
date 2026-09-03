import React, { useState, useEffect, useRef } from "react";
import {
  Cloud,
  Maximize2,
  Minimize2,
  RefreshCw,
  Monitor,
  Bot,
  Shield,
  Eye,
  MousePointer,
  Keyboard,
  Send,
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
  sessionId?: string;
}

export function ComputerSurface({
  desktopState,
  onRunCommand,
  commandLogs,
  onProvision,
  sessionId = "default",
}: ComputerSurfaceProps) {
  const [screenshotBase64, setScreenshotBase64] = useState<string | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [loadingScreen, setLoadingScreen] = useState(false);
  const [isInteractive, setIsInteractive] = useState(false);
  const [inputText, setInputText] = useState("");
  const [sendingInput, setSendingInput] = useState(false);
  const [clickRipples, setClickRipples] = useState<Array<{ id: number; x: number; y: number }>>([]);
  const canvasRef = useRef<HTMLDivElement>(null);

  const fetchScreenshot = async () => {
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
    }
  };

  // Poll live screenshot from Daytona sandbox every 3 seconds for read-only agent monitoring
  useEffect(() => {
    fetchScreenshot();
    const interval = setInterval(fetchScreenshot, 3000);
    return () => clearInterval(interval);
  }, [sessionId]);

  const handleCanvasClick = async (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isInteractive || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const scaleX = 1280 / rect.width;
    const scaleY = 800 / rect.height;
    const x = Math.round((e.clientX - rect.left) * scaleX);
    const y = Math.round((e.clientY - rect.top) * scaleY);

    // Visual ripple effect
    const rippleId = Date.now();
    setClickRipples((prev) => [...prev, { id: rippleId, x: e.clientX - rect.left, y: e.clientY - rect.top }]);
    setTimeout(() => {
      setClickRipples((prev) => prev.filter((r) => r.id !== rippleId));
    }, 800);

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

  const hasScreenshot = Boolean(screenshotBase64 && screenshotBase64.length > 100);
  const isLive = Boolean(desktopState?.workspace_id || desktopState?.sandbox_id || hasScreenshot);
  const resolution = desktopState?.resolution;
  const displayLabel = [
    desktopState?.display,
    resolution?.width && resolution?.height ? `${resolution.width}x${resolution.height}` : "1280x800",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={`flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden shadow-2xl ${
        fullscreen ? "fixed inset-2 z-50 bg-[#0D0F12]" : ""
      }`}
    >
      {/* Sleek Minimal Top Bar */}
      <div className="h-9 border-b border-[#21262D] bg-[#161B22] px-3 flex items-center justify-between text-xs font-mono text-[#8B949E]">
        <div className="flex items-center gap-2">
          <Cloud className="w-3.5 h-3.5 text-[#58A6FF]" />
          <span className="text-white font-semibold flex items-center gap-1.5 truncate text-[12px]">
            <span>Daytona Linux Workstation</span>
            {displayLabel && (
              <span className="text-[10px] text-slate-400 font-normal font-mono">({displayLabel})</span>
            )}
          </span>
          {isLive ? (
            <span className="flex items-center gap-1.5 text-[10px] text-emerald-400 font-semibold bg-emerald-950/50 border border-emerald-500/30 px-2 py-0.5 rounded">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>AGENT CONTROLLED</span>
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] text-[#8B949E] font-semibold bg-[#21262D]/60 border border-[#30363D] px-1.5 py-0.5 rounded">
              <span className="w-1.5 h-1.5 rounded-full bg-[#8B949E]"></span>
              <span>DISCONNECTED</span>
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Interactive Takeover Toggle */}
          <button
            onClick={() => setIsInteractive(!isInteractive)}
            className={`px-2.5 py-0.5 rounded text-[10px] font-mono font-semibold flex items-center gap-1.5 transition border ${
              isInteractive
                ? "bg-amber-950/80 text-amber-300 border-amber-500/60 shadow-lg shadow-amber-500/20"
                : "bg-[#0D1117] text-slate-400 border-[#30363D] hover:text-white"
            }`}
            title="Toggle direct mouse & keyboard control"
          >
            <MousePointer className={`w-3 h-3 ${isInteractive ? "text-amber-400 animate-bounce" : ""}`} />
            <span>{isInteractive ? "HUMAN TAKEOVER (ACTIVE)" : "TAKE OVER"}</span>
          </button>

          <button
            onClick={async (e) => { e.stopPropagation(); await fetchScreenshot(); }}
            className="p-1 hover:bg-[#21262D] rounded text-[#8B949E] hover:text-white transition"
            title="Capture live screenshot from sandbox"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingScreen ? "animate-spin text-[#58A6FF]" : ""}`} />
          </button>
          <button
            onClick={() => setFullscreen(!fullscreen)}
            className="p-1 hover:bg-[#21262D] rounded text-[#8B949E] hover:text-white transition"
            title="Toggle fullscreen"
          >
            {fullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Main Surface Body: Live Screen + Optional Takeover Overlay */}
      <div
        className="flex-1 bg-[#06080D] relative flex flex-col items-center justify-center overflow-hidden select-none"
        style={{ minHeight: 0 }}
      >
        {hasScreenshot ? (
          <div className="w-full h-full flex flex-col items-center justify-center p-2 relative">
            <div
              ref={canvasRef}
              onClick={handleCanvasClick}
              className={`w-full h-full max-w-[1280px] max-h-[800px] aspect-[16/10] rounded border border-[#21262D] bg-[#000000] relative shadow-2xl overflow-hidden flex items-center justify-center ${
                isInteractive ? "cursor-crosshair ring-2 ring-amber-500/50" : ""
              }`}
            >
              <img
                src={`data:image/png;base64,${screenshotBase64}`}
                alt="Daytona Graphical Desktop"
                className="w-full h-full object-contain pointer-events-none select-none"
              />

              {/* Click Ripple Indicators */}
              {clickRipples.map((r) => (
                <span
                  key={r.id}
                  style={{ left: r.x, top: r.y }}
                  className="absolute -translate-x-1/2 -translate-y-1/2 w-6 h-6 rounded-full border-2 border-amber-400 bg-amber-400/30 animate-ping pointer-events-none z-30"
                />
              ))}

              {/* Exclusive Autonomous Control Badge */}
              <div className="absolute top-2.5 left-2.5 z-20 flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-black/80 border border-emerald-500/30 text-[11px] font-mono text-emerald-400 shadow-lg backdrop-blur-sm pointer-events-none">
                <Bot className="w-3.5 h-3.5 text-emerald-400" />
                <span>SONIC Autonomous Desktop</span>
                <span className="text-[9px] text-slate-400 uppercase tracking-wider ml-1 bg-slate-800 px-1 py-0.2 rounded">Live Feed</span>
              </div>

              {/* Interactive Takeover Indicator */}
              {isInteractive && (
                <div className="absolute top-2.5 right-2.5 z-20 flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-950/90 border border-amber-500/50 text-[11px] font-mono text-amber-300 shadow-lg backdrop-blur-sm pointer-events-none">
                  <MousePointer className="w-3.5 h-3.5 text-amber-400" />
                  <span>Click anywhere to control</span>
                </div>
              )}

              {/* Security Guarantee Pill */}
              <div className="absolute bottom-2.5 right-2.5 z-20 flex items-center gap-1.5 px-2 py-0.5 rounded bg-black/70 border border-[#30363D] text-[10px] font-mono text-slate-400 backdrop-blur-sm pointer-events-none">
                <Shield className="w-3 h-3 text-blue-400" />
                <span>Agent Sandboxed (Fail-Closed)</span>
              </div>
            </div>

            {/* Quick Keyboard Bar in Interactive Mode */}
            {isInteractive && (
              <div className="w-full max-w-[1280px] mt-2 flex items-center gap-2 bg-[#161B22] border border-amber-500/30 p-2 rounded-lg z-20">
                <Keyboard className="w-4 h-4 text-amber-400 shrink-0 ml-1" />
                <form onSubmit={handleSendText} className="flex-1 flex items-center gap-2">
                  <input
                    type="text"
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    placeholder="Type here to send keystrokes directly into active window..."
                    className="flex-1 bg-[#0D1117] border border-[#30363D] focus:border-amber-500 px-3 py-1 text-xs font-mono text-white rounded outline-none"
                  />
                  <button
                    type="submit"
                    disabled={sendingInput || !inputText.trim()}
                    className="px-3 py-1 bg-amber-600 hover:bg-amber-500 text-black font-mono font-bold text-xs rounded flex items-center gap-1 disabled:opacity-40"
                  >
                    <Send className="w-3 h-3" />
                    <span>Send</span>
                  </button>
                </form>
                <div className="flex items-center gap-1 border-l border-[#30363D] pl-2">
                  <button
                    onClick={() => handleSendKey("Return")}
                    className="px-2 py-1 bg-[#21262D] hover:bg-[#30363D] text-slate-300 text-[10px] font-mono rounded"
                  >
                    Enter
                  </button>
                  <button
                    onClick={() => handleSendKey("Escape")}
                    className="px-2 py-1 bg-[#21262D] hover:bg-[#30363D] text-slate-300 text-[10px] font-mono rounded"
                  >
                    Esc
                  </button>
                  <button
                    onClick={() => handleSendKey("Tab")}
                    className="px-2 py-1 bg-[#21262D] hover:bg-[#30363D] text-slate-300 text-[10px] font-mono rounded"
                  >
                    Tab
                  </button>
                </div>
          </div>
        ) : isLive ? (
          /* Loading state while first screenshot is captured */
          <div className="w-full h-full max-w-[1280px] max-h-[800px] aspect-[16/10] rounded border border-[#21262D] bg-[#0A0D14] flex flex-col items-center justify-center p-6 text-center space-y-3 m-3">
            <div className="w-12 h-12 rounded-full bg-[#161B22] border border-emerald-500/30 flex items-center justify-center text-emerald-400">
              <RefreshCw className="w-6 h-6 animate-spin" />
            </div>
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-white font-mono">
                Connecting to live agent desktop…
              </h3>
              <p className="text-xs text-[#8B949E] font-mono max-w-md">
                Streaming real-time view from SONIC's Daytona workstation. The display will appear momentarily.
              </p>
            </div>
          </div>
        ) : (
          /* Explicit disconnected state */
          <div className="w-full h-full max-w-[1280px] max-h-[800px] aspect-[16/10] rounded border border-[#21262D] bg-[#0A0D14] flex flex-col items-center justify-center p-6 text-center space-y-3 m-3">
            <div className="w-12 h-12 rounded-full bg-[#161B22] border border-[#30363D] flex items-center justify-center text-[#8B949E]">
              <Monitor className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-white font-mono">
                No live display — sandbox disconnected
              </h3>
              <p className="text-xs text-[#8B949E] font-mono max-w-md">
                No tenant-owned Daytona workstation is attached to this session. Provision one to create a real
                remote desktop for SONIC to control.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {onProvision && !desktopState?.workspace_id && (
                <button
                  onClick={async (e) => {
                    e.stopPropagation();
                    await onProvision();
                  }}
                  className="px-3 py-1.5 rounded-lg bg-blue-600/25 hover:bg-blue-600/40 border border-blue-500/40 text-xs font-mono text-blue-200 transition"
                >
                  Provision Daytona Desktop
                </button>
              )}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  fetchScreenshot();
                }}
                className="px-3 py-1.5 rounded-lg bg-[#21262D] hover:bg-[#30363D] text-xs font-mono text-white transition flex items-center gap-1.5"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingScreen ? "animate-spin text-[#58A6FF]" : ""}`} />
                <span>Sync Display</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
