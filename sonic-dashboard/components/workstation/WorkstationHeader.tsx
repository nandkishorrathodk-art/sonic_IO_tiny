import React from "react";
import { GitBranch, PanelLeft, PanelLeftClose, ShieldCheck, MoreHorizontal } from "lucide-react";
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
    <header className="h-11 border-b border-ink-800 bg-ink-900/80 backdrop-blur-sm px-3 flex items-center justify-between text-xs z-10">
      <div className="flex items-center gap-2.5 min-w-0">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="text-muted hover:text-white p-1 rounded hover:bg-ink-800 transition mr-1"
          title={sidebarOpen ? "Collapse sidebar" : "Open sidebar"}
          aria-label={sidebarOpen ? "Collapse sidebar" : "Open sidebar"}
        >
          {sidebarOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeft className="w-4 h-4" />}
        </button>
        <span className="font-semibold text-white truncate max-w-xs">{sessionName}</span>

        {(gitBranch || latestCommit) && (
          <span className="chip border border-ink-700 bg-ink-850 text-success">
            <GitBranch className="w-3 h-3 text-success" />
            <span>{gitBranch || "detached"}</span>
            {latestCommit && <span className="text-muted-dim ml-1">({latestCommit.slice(0, 7)})</span>}
          </span>
        )}

        <StatusBadge status={connectionStatus} />
      </div>

      <div className="flex items-center gap-3">
        <div className="chip border border-ink-700 bg-ink-850 text-success">
          <ShieldCheck className="w-3 h-3 text-success" />
          <span>FAIL-CLOSED</span>
        </div>
        <MoreHorizontal className="w-4 h-4 text-muted hover:text-white cursor-pointer" />
      </div>
    </header>
  );
}
