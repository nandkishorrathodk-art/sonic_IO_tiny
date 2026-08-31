import React, { useState, useEffect } from "react";
import {
  Cloud,
  Maximize2,
  Minimize2,
  RefreshCw,
  Monitor,
  ExternalLink,
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
  const [vncUrl, setVncUrl] = useState<string | null>(null);
  // Daytona's proxy auth callback uses redirect+cookie which Chrome blocks
  // inside cross-origin iframes.  When this happens the iframe renders a JSON
  // 400 error instead of the noVNC desktop.  We detect this and fall back to
  // screenshot-based live preview while keeping "Open Tab" for the real thing.
  const [iframeAuthFailed, setIframeAuthFailed] = useState(false);

  // Resolve VNC URL from desktopState or fetch it from stream endpoint
  useEffect(() => {
    const stateUrl = desktopState?.vnc_url;
    if (stateUrl) {
      setVncUrl(stateUrl);
      setIframeAuthFailed(false);
    } else {
      setVncUrl(null);
      setIframeAuthFailed(false);
      api
        .getDesktopStream(sessionId)
        .then((data) => {
          if (data?.vnc_url) {
            setVncUrl(data.vnc_url);
          }
        })
        .catch(() => {
          // Stream endpoint unavailable
        });
    }
  }, [desktopState?.vnc_url, sessionId]);

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

  const refreshStream = async () => {
    try {
      setLoadingScreen(true);
      const data = await api.getDesktopStream(sessionId);
      if (data?.vnc_url) {
        setVncUrl(data.vnc_url);
        setIframeAuthFailed(false);
      }
    } catch {
      // Keep the current live URL if the preview refresh is temporarily unavailable.
    } finally {
      setLoadingScreen(false);
    }
  };

  // Screenshot polling: run when there is no working iframe stream
  const useScreenshots = !vncUrl || iframeAuthFailed;
  useEffect(() => {
    if (useScreenshots) {
      fetchScreenshot();
      const interval = setInterval(fetchScreenshot, 3000);
      return () => clearInterval(interval);
    }
  }, [useScreenshots, sessionId]);

  // When iframe loads, probe for auth failure after a short delay.
  // We can't read cross-origin content, but the Daytona proxy error page is
  // very small; a successful noVNC page is interactive. We use a simple
  // timer: if the iframe loaded, assume it might have failed and start
  // fetching screenshots as a background fallback regardless.
  useEffect(() => {
    if (vncUrl && !iframeAuthFailed) {
      // Give the iframe a few seconds to complete Daytona's auth callback.
      // If it fails the user will at least have live screenshots available.
      const timer = setTimeout(() => {
        setIframeAuthFailed(true);
      }, 4000);
      return () => clearTimeout(timer);
    }
  }, [vncUrl]);

  const handleDesktopClick = async (e: React.MouseEvent<HTMLDivElement>) => {
    // Only dispatch click coordinates in screenshot mode (not iframe)
    if (vncUrl && !iframeAuthFailed) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.round((e.clientX - rect.left) * (1280 / rect.width));
    const y = Math.round((e.clientY - rect.top) * (800 / rect.height));

    try {
        await api.executeDesktopAction({
          action: "click",
          coordinates: [x, y],
          sessionId,
      });
      await fetchScreenshot();
    } catch {
      // ignore
    }
  };

  const hasScreenshot = Boolean(screenshotBase64 && screenshotBase64.length > 100);
  const isLive = Boolean(vncUrl || desktopState?.vnc_url || hasScreenshot);
  const resolution = desktopState?.resolution;
  const displayLabel = [
    desktopState?.display,
    resolution?.width && resolution?.height ? `${resolution.width}x${resolution.height}` : "",
  ]
    .filter(Boolean)
    .join(" ");

  // Show screenshot-based live preview instead of broken iframe
  const showScreenshots = iframeAuthFailed || !vncUrl;

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
            <span className="flex items-center gap-1 text-[10px] text-[#3FB950] font-semibold bg-[#238636]/15 border border-[#238636]/30 px-1.5 py-0.5 rounded">
              <span className="w-1.5 h-1.5 rounded-full bg-[#3FB950] animate-pulse"></span>
              <span>LIVE DESKTOP {hasScreenshot ? "(screenshot)" : "(noVNC)"}</span>
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] text-[#8B949E] font-semibold bg-[#21262D]/60 border border-[#30363D] px-1.5 py-0.5 rounded">
              <span className="w-1.5 h-1.5 rounded-full bg-[#8B949E]"></span>
              <span>DISCONNECTED</span>
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {vncUrl && (
            <a
              href={vncUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1 hover:bg-[#21262D] rounded text-[#8B949E] hover:text-white transition flex items-center gap-1 text-[11px]"
              title="Open full interactive Daytona noVNC Desktop in new tab (recommended)"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Open noVNC Tab</span>
            </a>
          )}
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

      {/* Main Surface Body: Live Screenshot Desktop / noVNC new-tab fallback */}
      <div
        onClick={handleDesktopClick}
        className="flex-1 bg-[#06080D] relative flex items-center justify-center overflow-hidden cursor-crosshair"
        style={{ minHeight: 0 }}
      >
        {hasScreenshot ? (
          /* Live interactive X11 desktop canvas with coordinate click dispatch */
          <div className="w-full h-full max-w-[1280px] max-h-[800px] aspect-[16/10] rounded border border-[#21262D] bg-[#000000] relative shadow-2xl overflow-hidden flex items-center justify-center m-2">
            <img
              src={`data:image/png;base64,${screenshotBase64}`}
              alt="Daytona Graphical Desktop"
              className="w-full h-full object-contain pointer-events-none"
            />
            {vncUrl && (
              <div className="absolute bottom-2 right-2 z-10">
                <a
                  href={vncUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#238636]/80 hover:bg-[#238636] border border-[#3FB950]/40 text-[10px] font-mono text-white transition shadow-lg backdrop-blur-sm"
                  onClick={(e) => e.stopPropagation()}
                >
                  <ExternalLink className="w-3 h-3" />
                  <span>Open Interactive noVNC</span>
                </a>
              </div>
            )}
          </div>
        ) : isLive ? (
          /* Loading state while first screenshot is captured */
          <div className="w-full h-full max-w-[1280px] max-h-[800px] aspect-[16/10] rounded border border-[#21262D] bg-[#0A0D14] flex flex-col items-center justify-center p-6 text-center space-y-3 m-3">
            <div className="w-12 h-12 rounded-full bg-[#161B22] border border-[#238636]/30 flex items-center justify-center text-[#3FB950]">
              <RefreshCw className="w-6 h-6 animate-spin" />
            </div>
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-white font-mono">
                Connecting to live desktop…
              </h3>
              <p className="text-xs text-[#8B949E] font-mono max-w-md">
                Capturing real-time screenshot from your Daytona workstation. The display will appear momentarily.
              </p>
            </div>
            {vncUrl && (
              <a
                href={vncUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#238636]/25 hover:bg-[#238636]/40 border border-[#3FB950]/40 text-xs font-mono text-[#3FB950] transition"
                onClick={(e) => e.stopPropagation()}
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Open Interactive noVNC in New Tab</span>
              </a>
            )}
          </div>
        ) : (
          /* Explicit disconnected state — zero fake data */
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
                remote desktop; display streaming will remain unavailable until the provider returns a live URL.
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
