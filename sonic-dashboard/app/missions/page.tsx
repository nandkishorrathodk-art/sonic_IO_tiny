"use client";

import React, { useState, useEffect } from "react";
import { Compass, RefreshCw } from "lucide-react";
import { api } from "../../lib/api";
import { PageShell, PageHeader, StateBlock } from "../../components/common/PageShell";

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
    <PageShell>
      <PageHeader
        accent="primary"
        icon={<Compass className="w-6 h-6 text-primary-400" />}
        title="AUTONOMOUS MISSION DIRECTOR"
        badge="LIFECYCLE CONTROLLER"
        subtitle="Mission planning, execution coordination, dynamic replanning, and deliverable verification."
        actions={
          <button onClick={fetchMission} className="btn-ghost text-primary-400">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        }
      />

      <StateBlock
        error={error}
        loading={loading}
        loadingText="Loading Mission Lifecycle State…"
        empty={!missionState}
        emptyIcon={<Compass className="w-8 h-8" />}
        emptyTitle="No Mission Loaded"
        emptyText="Enter a goal on the main Workstation page to launch execution."
        spinnerColor="border-t-primary-400"
      >
        <div className="space-y-4 font-mono text-xs">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="glass-card p-4 rounded-xl space-y-1">
              <span className="text-muted-dim">Active Objective</span>
              <div className="text-sm font-bold text-white truncate">{missionState?.mission_name || "Awaiting Objective"}</div>
              <p className="text-[10px] text-secondary-400">Target: {missionState?.target_repo || "Not connected"}</p>
            </div>
            <div className="glass-card p-4 rounded-xl space-y-1">
              <span className="text-muted-dim">Execution Status</span>
              <div className="text-sm font-bold text-success">{missionState?.status || "IDLE"}</div>
              <p className="text-[10px] text-muted">Branch: {missionState?.git_branch || "—"}</p>
            </div>
            <div className="glass-card p-4 rounded-xl space-y-1">
              <span className="text-muted-dim">Security Gate</span>
              <div className="text-sm font-bold text-success">FAIL-CLOSED</div>
              <p className="text-[10px] text-muted">Zero Host Shell Fallback</p>
            </div>
          </div>

          <div className="glass-card p-5 rounded-2xl space-y-2">
            <span className="text-xs font-bold text-white">Current Action</span>
            <p className="text-xs text-muted leading-relaxed">
              {missionState?.thought_summary || "Workstation is initialized. Enter a goal on the main Workstation page to launch execution."}
            </p>
          </div>
        </div>
      </StateBlock>
    </PageShell>
  );
}
