import React from "react";
import { Compass, Play, Pause, CheckCircle2, Workflow, ShieldCheck } from "lucide-react";
import { WorkstationState } from "../../types/workstation";

interface MissionViewProps {
  workstationState: WorkstationState | null;
}

export function MissionView({ workstationState }: MissionViewProps) {
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
    </div>
  );
}
