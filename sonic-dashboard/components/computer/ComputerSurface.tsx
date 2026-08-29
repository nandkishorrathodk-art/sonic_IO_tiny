import React, { useState, useEffect, useRef } from "react";
import {
  Monitor,
  Terminal as TerminalIcon,
  ShieldCheck,
  Cpu,
  Copy,
  Check,
  Server,
  Cloud,
  ExternalLink,
  Maximize2,
  Minimize2,
  RefreshCw,
  Play,
  Layers,
  Sparkles,
  Wifi,
  WifiOff,
} from "lucide-react";
import { DesktopState, CommandResult } from "../../types/workstation";
import { api } from "../../lib/api";

interface ComputerSurfaceProps {
  desktopState?: DesktopState & {
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
}

export function ComputerSurface({
  desktopState,
  onRunCommand,
  commandLogs,
}: ComputerSurfaceProps) {
  const [viewMode, setViewMode] = useState<"desktop" | "terminal">("desktop");
  const [terminalInput, setTerminalInput] = useState("");
  const [running, setRunning] = useState(false);
  const [copiedSsh, setCopiedSsh] = useState(false);
  const [screenshotBase64, setScreenshotBase64] = useState<string | null>(null);
  const [activeWindow, setActiveWindow] = useState("XFCE Desktop");
  const [fullscreen, setFullscreen] = useState(false);
  const [loadingScreen, setLoadingScreen] = useState(false);
  const [vncUrl, setVncUrl] = useState<string | null>(null);

  const sshCmd =
    desktopState?.ssh_command ||
    process.env.NEXT_PUBLIC_DAYTONA_SSH ||
    "";

  const sandboxId =
    desktopState?.sandbox_id ||
    process.env.NEXT_PUBLIC_DAYTONA_SANDBOX_ID ||
    "";

  const image =
    desktopState?.image ||
    process.env.NEXT_PUBLIC_DAYTONA_IMAGE ||
    "";

  // Resolve VNC URL from desktopState or fetch it from stream endpoint
  useEffect(() => {
    const stateUrl = desktopState?.vnc_url;
    if (stateUrl) {
      setVncUrl(stateUrl);
    } else {
      // Try fetching from the stream endpoint
      api.getDesktopStream().then((data) => {
        if (data?.vnc_url) {
          setVncUrl(data.vnc_url);
        }
      }).catch(() => {
        // Stream endpoint unavailable — keep null
      });
    }
  }, [desktopState?.vnc_url]);

  const fetchScreenshot = async () => {
    try {
      setLoadingScreen(true);
      const data = await api.getDesktopScreenshot();
      if (data?.image_base64) {
        setScreenshotBase64(data.image_base64);
      } else if (data?.screenshot_base64) {
        setScreenshotBase64(data.screenshot_base64);
      }
      if (data?.active_window) {
        setActiveWindow(data.active_window);
      }
    } catch {
      // ignore
    } finally {
      setLoadingScreen(false);
    }
  };

  useEffect(() => {
    if (!vncUrl) {
      fetchScreenshot();
      const interval = setInterval(fetchScreenshot, 10000);
      return () => clearInterval(interval);
    }
  }, [vncUrl]);

  const handleLaunchApp = async (appName: string) => {
    try {
      setActiveWindow(appName);
      await api.executeDesktopAction({
        action: "open_app",
        target: appName,
      });
      if (!vncUrl) {
        await fetchScreenshot();
      }
    } catch (err: any) {
      alert(`Launch error: ${err.message}`);
    }
  };

  const handleDesktopClick = async (e: React.MouseEvent<HTMLDivElement>) => {
    // Only dispatch click coordinates in screenshot-fallback mode (not iframe)
    if (vncUrl) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.round((e.clientX - rect.left) * (1280 / rect.width));
    const y = Math.round((e.clientY - rect.top) * (800 / rect.height));

    try {
      await api.executeDesktopAction({
        action: "click",
        coordinates: [x, y],
      });
      await fetchScreenshot();
    } catch {
      // ignore
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!terminalInput.trim() || running) return;
    const cmd = terminalInput;
    setTerminalInput("");
    setRunning(true);
    await onRunCommand(cmd);
    setRunning(false);
    if (!vncUrl) {
      await fetchScreenshot();
    }
  };

  const handleCopySsh = () => {
    if (!sshCmd) return;
    navigator.clipboard.writeText(sshCmd);
    setCopiedSsh(true);
    setTimeout(() => setCopiedSsh(false), 2000);
  };

  return (
    <div
      className={`flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden shadow-2xl ${
        fullscreen ? "fixed inset-2 z-50 bg-[#0D0F12]" : ""
      }`}
    >
      {/* Top Bar: Controls & Mode Switcher */}
      <div className="h-10 border-b border-[#21262D] bg-[#1C2128] px-3 flex items-center justify-between text-xs font-mono text-[#8B949E]">
        <div className="flex items-center gap-2">
          <Cloud className="w-4 h-4 text-[#58A6FF]" />
          <span className="text-white font-semibold flex items-center gap-1.5 truncate">
            <span>Daytona Linux Workstation</span>
            {image && (
              <span className="text-[10px] text-[#3FB950] font-normal font-mono hidden sm:inline">
                ({image})
              </span>
            )}
          </span>
          {/* Live/Disconnected status badge */}
          {vncUrl ? (
            <span className="flex items-center gap-1 text-[10px] text-[#3FB950] font-semibold">
              <Wifi className="w-3 h-3" />
              <span>LIVE</span>
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] text-[#8B949E]">
              <WifiOff className="w-3 h-3" />
              <span>OFFLINE</span>
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Mode Switcher */}
          <div className="flex items-center bg-[#0D1117] p-0.5 rounded-lg border border-[#30363D] text-[11px]">
            <button
              onClick={() => setViewMode("desktop")}
              className={`px-2.5 py-0.5 rounded-md transition flex items-center gap-1 ${
                viewMode === "desktop" ? "bg-[#21262D] text-white font-semibold" : "text-[#8B949E] hover:text-white"
              }`}
            >
              <Monitor className="w-3 h-3 text-[#3FB950]" />
              <span>{vncUrl ? "noVNC Stream" : "Desktop"}</span>
            </button>
            <button
              onClick={() => setViewMode("terminal")}
              className={`px-2.5 py-0.5 rounded-md transition flex items-center gap-1 ${
                viewMode === "terminal" ? "bg-[#21262D] text-white font-semibold" : "text-[#8B949E] hover:text-white"
              }`}
            >
              <TerminalIcon className="w-3 h-3 text-[#58A6FF]" />
              <span>PTY Shell</span>
            </button>
          </div>

          <button
            onClick={() => setFullscreen(!fullscreen)}
            className="p-1 hover:bg-[#21262D] rounded text-[#8B949E] hover:text-white transition"
            title="Toggle fullscreen"
          >
            {fullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Daytona Metadata Bar */}
      <div className="bg-[#12151A] border-b border-[#21262D] px-3 py-2 flex flex-wrap items-center justify-between gap-2 text-xs font-mono">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-[#8B949E] text-[10px]">DISPLAY:</span>
            <span className="text-white text-[11px] font-bold">:99 (1280x800)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[#8B949E] text-[10px]">ACTIVE:</span>
            <span className="text-[#58A6FF] text-[11px] font-bold">{activeWindow}</span>
          </div>
        </div>

        {/* SSH Connection Chip */}
        {sshCmd ? (
          <div className="flex items-center gap-2 bg-[#0D1117] border border-[#30363D] px-2 py-0.5 rounded-md">
            <span className="text-[#8B949E] text-[10px]">SSH:</span>
            <code className="text-[#79C0FF] text-[11px] truncate max-w-xs">{sshCmd}</code>
            <button
              onClick={handleCopySsh}
              className="text-[#8B949E] hover:text-white p-0.5 rounded hover:bg-[#21262D] transition ml-1"
              title="Copy SSH command"
            >
              {copiedSsh ? <Check className="w-3 h-3 text-[#3FB950]" /> : <Copy className="w-3 h-3" />}
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 bg-[#0D1117] border border-[#30363D] px-2 py-0.5 rounded-md text-[10px] text-[#8B949E]">
            <Server className="w-3 h-3 text-slate-500" />
            <span>SSH: Not connected</span>
          </div>
        )}
      </div>

      {/* App Quick Launcher Bar (hidden in noVNC mode — noVNC handles interaction) */}
      {!vncUrl && (
        <div className="bg-[#0A0D14] border-b border-[#21262D] px-3 py-1.5 flex items-center justify-between gap-2 text-xs font-mono overflow-x-auto">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-[#8B949E] uppercase font-bold mr-1">Launch:</span>
            <button
              onClick={() => handleLaunchApp("xfce4-terminal")}
              className="px-2 py-0.5 rounded bg-[#1F242C] hover:bg-[#2D333B] text-[#C9D1D9] hover:text-white border border-[#30363D] transition text-[10px] flex items-center gap-1"
            >
              <TerminalIcon className="w-2.5 h-2.5 text-[#58A6FF]" />
              <span>Terminal</span>
            </button>
            <button
              onClick={() => handleLaunchApp("code-server")}
              className="px-2 py-0.5 rounded bg-[#1F242C] hover:bg-[#2D333B] text-[#C9D1D9] hover:text-white border border-[#30363D] transition text-[10px] flex items-center gap-1"
            >
              <Cpu className="w-2.5 h-2.5 text-[#3FB950]" />
              <span>VS Code</span>
            </button>
            <button
              onClick={() => handleLaunchApp("chromium")}
              className="px-2 py-0.5 rounded bg-[#1F242C] hover:bg-[#2D333B] text-[#C9D1D9] hover:text-white border border-[#30363D] transition text-[10px] flex items-center gap-1"
            >
              <ExternalLink className="w-2.5 h-2.5 text-purple-400" />
              <span>Browser</span>
            </button>
          </div>

          <button
            onClick={fetchScreenshot}
            className="text-[#8B949E] hover:text-white text-[10px] flex items-center gap-1 transition"
          >
            <RefreshCw className={`w-3 h-3 ${loadingScreen ? "animate-spin text-[#58A6FF]" : ""}`} />
            <span>Sync Screen</span>
          </button>
        </div>
      )}

      {/* Main Surface Body: noVNC Stream / Screenshot Fallback / Disconnected / PTY Shell */}
      {viewMode === "desktop" ? (
        <div
          onClick={handleDesktopClick}
          className="flex-1 bg-[#06080D] relative flex items-center justify-center overflow-hidden cursor-crosshair select-none"
          style={{ minHeight: 0 }}
        >
          {/* Priority 1: Real interactive noVNC desktop via iframe */}
          {vncUrl ? (
            <iframe
              src={vncUrl}
              title="Daytona noVNC Desktop"
              className="w-full h-full border-0"
              style={{ minHeight: "400px" }}
              allow="clipboard-read; clipboard-write; fullscreen"
              sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
            />
          ) : screenshotBase64 && screenshotBase64.length > 100 ? (
            /* Priority 2: Non-interactive screenshot fallback with click dispatch */
            <div className="w-full h-full max-w-[1280px] max-h-[800px] aspect-[16/10] rounded border border-[#21262D] bg-[#000000] relative shadow-2xl overflow-hidden flex items-center justify-center m-3">
              <img
                src={`data:image/png;base64,${screenshotBase64}`}
                alt="Daytona Graphical Desktop"
                className="w-full h-full object-contain pointer-events-none"
              />
            </div>
          ) : (
            /* Priority 3: Explicit disconnected state — zero fake data */
            <div className="w-full h-full max-w-[1280px] max-h-[800px] aspect-[16/10] rounded border border-[#21262D] bg-[#0A0D14] flex flex-col items-center justify-center p-6 text-center space-y-3 m-3">
              <div className="w-12 h-12 rounded-full bg-[#161B22] border border-[#30363D] flex items-center justify-center text-[#8B949E]">
                <Monitor className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <h3 className="text-sm font-semibold text-white font-mono">
                  No live display — sandbox disconnected
                </h3>
                <p className="text-xs text-[#8B949E] font-mono max-w-md">
                  The graphical desktop session is not currently streaming. Provision a Daytona sandbox
                  with DAYTONA_API_KEY to enable the live noVNC desktop. Click Sync Screen to retry screenshot capture.
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  fetchScreenshot();
                }}
                className="px-3 py-1.5 rounded-lg bg-[#21262D] hover:bg-[#30363D] text-xs font-mono text-white transition flex items-center gap-1.5"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingScreen ? "animate-spin text-[#58A6FF]" : ""}`} />
                <span>Sync Screen</span>
              </button>
            </div>
          )}
        </div>
      ) : (
        /* PTY Shell Mode */
        <div className="flex-1 bg-[#06080D] p-3 flex flex-col font-mono text-xs overflow-hidden">
          <div className="flex-1 overflow-y-auto space-y-1 text-[#C9D1D9] leading-tight select-text">
            <div className="text-[#8B949E] pb-2 border-b border-[#21262D] space-y-0.5">
              <div># Attached to Daytona Cloud Linux Container: {sandboxId || "not connected"}</div>
              <div># Snapshot: {image || "none"} | Direct host command execution is permanently prohibited.</div>
            </div>
            {commandLogs.map((log, idx) => (
              <div key={idx} className="whitespace-pre-wrap">
                {log.startsWith("sonic@") ? (
                  <span className="text-[#79C0FF] font-bold">{log}</span>
                ) : log.includes("PASSED") ? (
                  <span className="text-[#3FB950]">{log}</span>
                ) : log.includes("FAILED") || log.includes("Error") || log.includes("prohibited") ? (
                  <span className="text-[#FF7B72]">{log}</span>
                ) : (
                  <span className="text-[#8B949E]">{log}</span>
                )}
              </div>
            ))}
          </div>

          {/* Terminal Input Box */}
          <form onSubmit={handleSubmit} className="mt-2 flex items-center gap-2 border-t border-[#21262D] pt-2">
            <span className="text-[#3FB950] font-bold">sonic@daytona:~$</span>
            <input
              type="text"
              value={terminalInput}
              onChange={(e) => setTerminalInput(e.target.value)}
              placeholder="Execute command inside Daytona sandbox (e.g. 'pytest tests/' or 'uname -a')..."
              className="flex-1 bg-transparent text-xs text-white outline-none font-mono placeholder-[#484F58]"
              disabled={running}
            />
            {running && (
              <span className="text-[10px] text-[#58A6FF] animate-pulse font-bold">
                EXECUTING IN SANDBOX...
              </span>
            )}
          </form>
        </div>
      )}
    </div>
  );
}
