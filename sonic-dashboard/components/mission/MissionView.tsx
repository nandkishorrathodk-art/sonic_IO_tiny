import React, { useEffect, useState } from "react";
import { Compass, FlaskConical, Trash2 } from "lucide-react";
import { WorkstationState } from "../../types/workstation";
import { api } from "../../lib/api";

interface MissionViewProps {
  workstationState: WorkstationState | null;
  sessionId?: string;
}

export function MissionView({ workstationState, sessionId = "default" }: MissionViewProps) {
  const [target, setTarget] = useState("");
  const [targetSandbox, setTargetSandbox] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const [objective, setObjective] = useState("");
  const [mission, setMission] = useState<any | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const [targetState, workstation] = await Promise.all([
          api.getTargetSandboxStatus(sessionId),
          api.getWorkstationState(sessionId),
        ]);
        if (!cancelled) {
          setTargetSandbox(targetState);
          setMission(workstation?.mission || null);
        }
      } catch {
        if (!cancelled) {
          setTargetSandbox(null);
          setMission(null);
        }
      }
    };
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [sessionId]);

  const provisionTarget = async () => {
    if (!target.trim()) return;
    setBusy(true);
    try {
      const targetValue = target.trim();
      let targetHost = targetValue;
      try {
        targetHost = new URL(targetValue.includes("://") ? targetValue : `https://${targetValue}`).hostname;
      } catch {
        // The API will return a clear validation error for malformed targets.
      }
      const data = await api.provisionTargetSandbox(
        targetValue,
        { targets: { domains: [targetHost], ips: [] }, exclusions: { domains: [], ips: [] } },
        sessionId,
      );
      setTargetSandbox(data.target_sandbox);
    } catch (err: any) {
      alert(err.message || "Target sandbox provisioning failed.");
    } finally {
      setBusy(false);
    }
  };

  const destroyTarget = async () => {
    setBusy(true);
    try {
      const data = await api.destroyTargetSandbox(sessionId);
      setTargetSandbox(data.target_sandbox);
    } catch (err: any) {
      alert(err.message || "Target sandbox cleanup failed.");
    } finally {
      setBusy(false);
    }
  };

  const startMission = async () => {
    if (!objective.trim()) return;
    setBusy(true);
    try {
      const data = await api.startMission(objective.trim(), sessionId);
      setMission(data.mission);
    } catch (err: any) {
      alert(err.message || "Mission could not start.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-[#30363D] pb-3">
        <div className="flex items-center gap-2">
          <Compass className="w-4 h-4 text-cyan-400" />
          <span className="text-sm font-bold text-white">Autonomous Mission Owner & Controller</span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800">
            {workstationState?.session_id || "Session Active"}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 bg-[#0D1117] border border-[#30363D] rounded-lg">
          <span className="text-[10px] font-mono text-[#8B949E] block">Mission Name</span>
          <span className="text-xs font-bold text-white block mt-0.5 truncate">
            {workstationState?.mission_name || "Awaiting Objective"}
          </span>
        </div>
        <div className="p-3 bg-[#0D1117] border border-[#30363D] rounded-lg">
          <span className="text-[10px] font-mono text-[#8B949E] block">Lifecycle Status</span>
          <span className="text-xs font-bold text-[#3FB950] block mt-0.5">
            {workstationState?.status || "IDLE"}
          </span>
        </div>
        <div className="p-3 bg-[#0D1117] border border-[#30363D] rounded-lg">
          <span className="text-[10px] font-mono text-[#8B949E] block">Target Repository</span>
          <span className="text-xs font-bold text-cyan-400 block mt-0.5 truncate">
            {workstationState?.target_repo || "Local Workspace"}
          </span>
        </div>
        <div className="p-3 bg-[#0D1117] border border-[#30363D] rounded-lg">
          <span className="text-[10px] font-mono text-[#8B949E] block">Security Guard</span>
          <span className="text-xs font-bold text-emerald-400 block mt-0.5">
            FAIL-CLOSED
          </span>
        </div>
      </div>

      <div className="p-4 rounded-lg bg-[#0D1117] border border-[#30363D] space-y-2">
        <span className="text-xs font-bold text-white">Current Autonomous State</span>
        <p className="text-xs text-[#8B949E] font-mono leading-relaxed">
          {workstationState?.thought_summary || "Workstation is initialized. Enter a high-level engineering or research goal in the execution prompt below."}
        </p>
      </div>

      <div className="p-4 rounded-lg bg-[#0D1117] border border-amber-800/50 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-amber-400" />
            <span className="text-xs font-bold text-white">Authorized Target Testing Sandbox</span>
          </div>
          <span className="text-[10px] font-mono text-amber-300">{targetSandbox?.status || "NO_ACTIVE_TARGET_SANDBOX"}</span>
        </div>
        <p className="text-[11px] text-[#8B949E]">Separate disposable environment for an explicitly scoped target. It is not the agent desktop.</p>
        {targetSandbox?.workspace_id ? (
          <div className="flex items-center justify-between text-[11px] font-mono">
            <span className="text-amber-200 truncate">{targetSandbox.target}</span>
            <button onClick={destroyTarget} disabled={busy} className="px-2 py-1 rounded border border-red-800/60 text-red-300 hover:bg-red-950/30 disabled:opacity-50 flex items-center gap-1"><Trash2 className="w-3 h-3" /> Destroy</button>
          </div>
        ) : (
          <div className="flex gap-2">
            <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="authorized.example.com" className="flex-1 bg-[#161B22] border border-[#30363D] rounded px-2 py-1.5 text-xs font-mono text-white outline-none focus:border-amber-500" />
            <button onClick={provisionTarget} disabled={busy || !target.trim()} className="px-3 py-1.5 rounded bg-amber-600/20 border border-amber-600/50 text-amber-200 text-xs font-mono disabled:opacity-50">Provision</button>
          </div>
        )}
      </div>

      <div className="p-4 rounded-lg bg-[#0D1117] border border-cyan-800/50 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-white">Mission Execution Plane</span>
          <span className="text-[10px] font-mono text-cyan-300">{mission?.status || "IDLE"}</span>
        </div>
        <p className="text-[11px] text-[#8B949E]">Starts a real read-only preflight in the scoped target sandbox. Active testing remains approval-gated.</p>
        <div className="flex gap-2">
          <input value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="Assess the authorized target" className="flex-1 bg-[#161B22] border border-[#30363D] rounded px-2 py-1.5 text-xs font-mono text-white outline-none focus:border-cyan-500" />
          <button onClick={startMission} disabled={busy || !targetSandbox?.workspace_id || !objective.trim()} className="px-3 py-1.5 rounded bg-cyan-600/20 border border-cyan-600/50 text-cyan-200 text-xs font-mono disabled:opacity-50">Start Mission</button>
        </div>
        {mission?.events?.length ? (
          <div className="max-h-40 overflow-y-auto space-y-1.5 text-[10px] font-mono text-[#8B949E] border-t border-[#1F2B38] pt-2">
            {mission.events.slice(-8).map((event: any) => (
              <div key={event.id} className="flex gap-2 items-start">
                <span className="text-cyan-400 shrink-0">[{event.type}]</span>
                <span className="text-[#C4CFDB]">{event.title}</span>
                {event.content && <span className="text-[#718096] truncate">— {event.content}</span>}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
