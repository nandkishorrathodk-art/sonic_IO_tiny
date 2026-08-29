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
} from "lucide-react";
import { api } from "../../lib/api";
import Link from "next/link";

export default function ComputerWorkspacePage() {
  const [desktopState, setDesktopState] = useState<any>(null);
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

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto font-sans">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#0F131F]/90 border border-slate-800/80 p-5 rounded-2xl">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-500 p-0.5 shadow-lg shadow-blue-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-[#0C0E16] rounded-[10px] flex items-center justify-center">
              <Monitor className="w-6 h-6 text-blue-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-wide">AUTONOMOUS COMPUTER & WORKSPACE</h2>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-blue-950 text-blue-300 border border-blue-800/60 rounded-full font-semibold">
                CONTAINERIZED
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              Docker / Daytona sandbox computer: Headless PTY shell, sandboxed workspace filesystem, and execution lock.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 font-mono text-xs">
          <button
            onClick={fetchStatus}
            className="px-3.5 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/40 rounded-xl font-semibold flex items-center gap-2 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Main Computer Status */}
      {error ? (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/60 text-red-300 text-xs font-mono">
          <strong>Backend Error:</strong> {error}
        </div>
      ) : loading ? (
        <div className="py-20 text-center space-y-2">
          <Loader2 className="w-8 h-8 animate-spin text-blue-400 mx-auto" />
          <span className="text-xs text-slate-400 font-mono">Querying Compute Provider...</span>
        </div>
      ) : (
        <div className="space-y-4 font-mono text-xs">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="glass-card p-4 rounded-xl border border-slate-800 space-y-1">
              <span className="text-slate-500">Operating System</span>
              <div className="text-sm font-bold text-white">{desktopState?.os_name || "Linux Container"}</div>
              <p className="text-[10px] text-emerald-400">ISOLATED SANDBOX</p>
            </div>
            <div className="glass-card p-4 rounded-xl border border-slate-800 space-y-1">
              <span className="text-slate-500">Display / Shell Mode</span>
              <div className="text-sm font-bold text-white">{desktopState?.display || "Headless PTY"}</div>
              <p className="text-[10px] text-slate-400">Zero Host Execution</p>
            </div>
            <div className="glass-card p-4 rounded-xl border border-slate-800 space-y-1">
              <span className="text-slate-500">Execution Safety</span>
              <div className="text-sm font-bold text-emerald-400">FAIL-CLOSED</div>
              <p className="text-[10px] text-slate-400">Direct host fallback prohibited</p>
            </div>
          </div>

          {/* Quick Access to Real Terminal */}
          <div className="glass-card p-6 rounded-2xl border border-slate-800 text-center space-y-3">
            <Terminal className="w-8 h-8 text-emerald-400 mx-auto" />
            <h4 className="text-sm font-bold text-white">Interactive Sandbox Shell</h4>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              Execute shell commands inside the authenticated Docker/Daytona container session.
            </p>
            <Link
              href="/terminal"
              className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-950 hover:bg-emerald-900 border border-emerald-800 text-emerald-400 rounded-lg text-xs font-bold transition"
            >
              Open Container Terminal
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
