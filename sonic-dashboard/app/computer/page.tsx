"use client";

import React, { useState, useEffect } from "react";
import {
  Monitor,
  Terminal,
  FolderTree,
  ShieldCheck,
  RefreshCw,
  Activity,
  Server,
  Loader2,
  AlertCircle,
  Cloud,
  Maximize2,
  ExternalLink,
} from "lucide-react";
import { api } from "../../lib/api";
import { ComputerSurface } from "../../components/computer/ComputerSurface";
import { CommandResult } from "../../types/workstation";
import Link from "next/link";

export default function ComputerWorkspacePage() {
  const [desktopState, setDesktopState] = useState<any>(null);
  const [commandLogs, setCommandLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getDesktopStatus();
      setDesktopState(data);
    } catch (err: any) {
      setError(err.message || "Failed to query computer status.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleRunCommand = async (cmd: string): Promise<CommandResult | null> => {
    setCommandLogs((prev) => [...prev, `sonic@daytona:~$ ${cmd}`]);
    try {
      const res = await api.executeCommand(cmd);
      if (res?.output) {
        setCommandLogs((prev) => [...prev, res.output.trim()]);
      }
      await fetchStatus();
      return res;
    } catch (err: any) {
      setCommandLogs((prev) => [...prev, `[FAIL-CLOSED REJECTED]: ${err.message}`]);
      return null;
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto font-sans h-[calc(100vh-80px)] flex flex-col">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#0F131F]/90 border border-slate-800/80 p-4 rounded-2xl flex-shrink-0">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-500 p-0.5 shadow-lg shadow-blue-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-[#0C0E16] rounded-[10px] flex items-center justify-center">
              <Cloud className="w-5 h-5 text-blue-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-wide">
                DAYTONA GRAPHICAL WORKSTATION
              </h2>
              {desktopState?.vnc_url || desktopState?.status === "LIVE" || desktopState?.status === "ACTIVE" || desktopState?.status === "READY / ACTIVE" ? (
                <span className="px-2 py-0.5 text-[10px] font-mono bg-emerald-950 text-emerald-300 border border-emerald-800/60 rounded-full font-semibold flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  LIVE (:99)
                </span>
              ) : (
                <span className="px-2 py-0.5 text-[10px] font-mono bg-slate-900 text-slate-400 border border-slate-800 rounded-full font-semibold flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-500"></span>
                  OFFLINE / DISCONNECTED
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              Real Cloud Sandbox Execution: X11 GUI Desktop, PTY Shell, Filesystem, and Native Computer Use.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 font-mono text-xs">
          <button
            onClick={fetchStatus}
            className="px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/40 rounded-xl font-semibold flex items-center gap-1.5 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh Desktop</span>
          </button>
        </div>
      </div>

      {/* Main Graphical Desktop Surface */}
      {error ? (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/60 text-red-300 text-xs font-mono flex-shrink-0">
          <strong>Backend Error:</strong> {error}
        </div>
      ) : (
        <div className="flex-1 flex min-h-0 overflow-hidden">
          <ComputerSurface
            desktopState={desktopState}
            onRunCommand={handleRunCommand}
            commandLogs={commandLogs}
          />
        </div>
      )}
    </div>
  );
}
