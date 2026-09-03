import React, { useEffect, useState } from "react";
import { Compass, FlaskConical, Trash2 } from "lucide-react";
import { WorkstationState, MissionSummary } from "../../types/workstation";
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
  const [mission, setMission] = useState<MissionSummary | null>(null);

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

  const stats = [
    { label: "Mission Name", value: workstationState?.mission_name || "Awaiting Objective", accent: "text-white" },
    { label: "Lifecycle Status", value: workstationState?.status || "IDLE", accent: "text-success" },
    { label: "Target Repository", value: workstationState?.target_repo || "Local Workspace", accent: "text-secondary-400" },
    { label: "Security Guard", value: "FAIL-CLOSED", accent: "text-success" },
  ];

  return (
    <div className="flex-1 panel flex flex-col overflow-hidden p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-ink-700 pb-3">
        <div className="flex items-center gap-2">
          <Compass className="w-4 h-4 text-primary-400" />
          <span className="text-sm font-bold text-white">Autonomous Mission Owner & Controller</span>
          <span className="chip border border-ink-700 bg-ink-850 text-primary-400">
            {workstationState?.session_id || "Session Active"}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {stats.map((s) => (
          <div key={s.label} className="panel p-3">
            <span className="text-[10px] font-mono text-muted-dim block">{s.label}</span>
            <span className={`text-xs font-bold ${s.accent} block mt-0.5 truncate`}>{s.value}</span>
          </div>
        ))}
      </div>

      <div className="panel p-4 space-y-2">
        <span className="text-xs font-bold text-white">Current Autonomous State</span>
        <p className="text-xs text-muted font-mono leading-relaxed">
          {workstationState?.thought_summary || "Workstation is initialized. Enter a high-level engineering or research goal in the execution prompt below."}
        </p>
      </div>

      <div className="panel p-4 space-y-3 border-warning/40">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-warning" />
            <span className="text-xs font-bold text-white">Authorized Target Testing Sandbox</span>
          </div>
          <span className="text-[10px] font-mono text-warning">{targetSandbox?.status || "NO_ACTIVE_TARGET_SANDBOX"}</span>
        </div>
        <p className="text-[11px] text-muted">Separate disposable environment for an explicitly scoped target. It is not the agent desktop.</p>
        {targetSandbox?.workspace_id ? (
          <div className="flex items-center justify-between text-[11px] font-mono">
            <span className="text-warning truncate">{targetSandbox.target}</span>
            <button onClick={destroyTarget} disabled={busy} className="btn-ghost text-danger border-danger/40 hover:bg-danger/10 disabled:opacity-50">
              <Trash2 className="w-3 h-3" /> Destroy
            </button>
          </div>
        ) : (
          <div className="flex gap-2">
            <input
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder="authorized.example.com"
              className="input-field !py-1.5 !text-xs font-mono"
            />
            <button
              onClick={provisionTarget}
              disabled={busy || !target.trim()}
              className="btn-secondary !px-3 !py-1.5 text-xs font-mono disabled:opacity-50"
            >
              Provision
            </button>
          </div>
        )}
      </div>

      <div className="panel p-4 space-y-3 border-secondary-600/40">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-white">Mission Execution Plane</span>
          <span className="text-[10px] font-mono text-secondary-400">{mission?.status || "IDLE"}</span>
        </div>
        <p className="text-[11px] text-muted">Starts a real read-only preflight in the scoped target sandbox. Active testing remains approval-gated.</p>
        <div className="flex gap-2">
          <input
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            placeholder="Assess the authorized target"
            className="input-field !py-1.5 !text-xs font-mono"
          />
          <button
            onClick={startMission}
            disabled={busy || !targetSandbox?.workspace_id || !objective.trim()}
            className="btn-secondary !px-3 !py-1.5 text-xs font-mono disabled:opacity-50"
          >
            Start Mission
          </button>
        </div>
        {mission?.events?.length ? (
          <div className="max-h-40 overflow-y-auto space-y-1.5 text-[10px] font-mono text-muted border-t border-ink-700 pt-2">
            {mission.events.slice(-8).map((event) => (
              <div key={event.id} className="flex gap-2 items-start">
                <span className="text-secondary-400 shrink-0">[{event.type}]</span>
                <span className="text-muted-bright">{event.title}</span>
                {event.content && <span className="text-muted-dim truncate">— {event.content}</span>}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
