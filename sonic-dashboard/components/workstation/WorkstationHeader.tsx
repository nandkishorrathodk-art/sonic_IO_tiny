import React from "react";
import { GitBranch, Maximize2, MoreHorizontal, PanelLeft, PanelLeftClose, Zap, ShieldCheck } from "lucide-react";
import { StatusBadge } from "../common/StatusBadge";
import { SystemStatus } from "../../types/workstation";

interface WorkstationHeaderProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  sessionName: string;
  gitBranch: string;
  latestCommit?: string;
  connectionStatus: SystemStatus;
}

export function WorkstationHeader({
  sidebarOpen,
  setSidebarOpen,
  sessionName,
  gitBranch,
  latestCommit,
  connectionStatus,
}: WorkstationHeaderProps) {
  return (
    <header className="h-10 border-b border-[#21262D] bg-[#12151A] px-3 flex items-center justify-between text-xs z-10">
      <div className="flex items-center gap-2.5 min-w-0">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="text-[#8B949E] hover:text-white p-1 rounded hover:bg-[#21262D] transition mr-1"
          title={sidebarOpen ? "Collapse sidebar" : "Open sidebar"}
          aria-label={sidebarOpen ? "Collapse sidebar" : "Open sidebar"}
        >
          {sidebarOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeft className="w-4 h-4" />}
        </button>
        <span className="font-semibold text-white truncate max-w-xs">{sessionName}</span>
        
        {/* Real Git metadata only appears after the backend returns it. */}
        {(gitBranch || latestCommit) && (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1F242C] text-[#3FB950] border border-[#30363D] flex items-center gap-1">
            <GitBranch className="w-3 h-3 text-[#3FB950]" />
            <span>{gitBranch || "detached"}</span>
            {latestCommit && <span className="text-[#8B949E] ml-1">({latestCommit.slice(0, 7)})</span>}
          </span>
        )}

        {/* Real Connection Status */}
        <StatusBadge status={connectionStatus} />
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-[#1F242C] border border-[#30363D] text-[10px] font-mono text-[#3FB950]">
          <ShieldCheck className="w-3 h-3 text-[#3FB950]" />
          <span>FAIL-CLOSED CONTAINER</span>
        </div>
        <MoreHorizontal className="w-4 h-4 text-[#8B949E] hover:text-white cursor-pointer" />
      </div>
    </header>
  );
}
