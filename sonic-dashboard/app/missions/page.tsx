"use client";

import React, { useState, useEffect } from "react";
import {
  Compass,
  Play,
  Pause,
  RefreshCw,
  Loader2,
  AlertCircle,
  Workflow,
} from "lucide-react";
import { api } from "../../lib/api";

export default function LongHorizonMissionsPage() {
  const [missionState, setMissionState] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMission = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getWorkstationState();
      setMissionState(data);
    } catch (err: any) {
      setError(err.message || "Failed to load mission status.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMission();
  }, []);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto font-sans">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#0F131F]/90 border border-slate-800/80 p-5 rounded-2xl">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-cyan-600 via-blue-600 to-indigo-600 p-0.5 shadow-lg shadow-cyan-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-[#0C0E16] rounded-[10px] flex items-center justify-center">
              <Compass className="w-6 h-6 text-cyan-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-wide">AUTONOMOUS MISSION DIRECTOR</h2>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-cyan-950 text-cyan-300 border border-cyan-800/60 rounded-full font-semibold">
                LIFECYCLE CONTROLLER
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              Mission planning, execution coordination, dynamic replanning, and deliverable verification.
            </p>
          </div>
        </div>

        <button
          onClick={fetchMission}
          className="px-3.5 py-1.5 bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-300 border border-cyan-500/40 rounded-xl font-semibold flex items-center gap-2 transition text-xs font-mono"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Main Content */}
      {error ? (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/60 text-red-300 text-xs font-mono">
          <strong>Backend Error:</strong> {error}
        </div>
      ) : loading ? (
        <div className="py-20 text-center space-y-2">
          <Loader2 className="w-8 h-8 animate-spin text-cyan-400 mx-auto" />
          <span className="text-xs text-slate-400 font-mono">Loading Mission Lifecycle State...</span>
        </div>
      ) : (
        <div className="space-y-4 font-mono text-xs">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="glass-card p-4 rounded-xl border border-slate-800 space-y-1">
              <span className="text-slate-500">Active Objective</span>
              <div className="text-sm font-bold text-white truncate">{missionState?.mission_name || "Awaiting Objective"}</div>
              <p className="text-[10px] text-cyan-400">Target: {missionState?.target_repo || "sonic"}</p>
            </div>
            <div className="glass-card p-4 rounded-xl border border-slate-800 space-y-1">
              <span className="text-slate-500">Execution Status</span>
              <div className="text-sm font-bold text-[#3FB950]">{missionState?.status || "IDLE"}</div>
              <p className="text-[10px] text-slate-400">Branch: {missionState?.git_branch || "main"}</p>
            </div>
            <div className="glass-card p-4 rounded-xl border border-slate-800 space-y-1">
              <span className="text-slate-500">Security Gate</span>
              <div className="text-sm font-bold text-emerald-400">FAIL-CLOSED</div>
              <p className="text-[10px] text-slate-400">Zero Host Shell Fallback</p>
            </div>
          </div>

          <div className="glass-card p-5 rounded-2xl border border-slate-800 space-y-2">
            <span className="text-xs font-bold text-white">Current Action</span>
            <p className="text-xs text-slate-400 leading-relaxed">
              {missionState?.thought_summary || "Workstation is initialized. Enter a goal on the main Workstation page to launch execution."}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
