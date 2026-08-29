import React from "react";
import {
  MessageSquare,
  Settings,
  PanelLeftClose,
  Plus,
  GitBranch,
  Monitor,
  Share2,
  FileCheck2,
  Dna,
  Trash2,
  Clock,
  Sparkles,
} from "lucide-react";
import Link from "next/link";

export interface SessionItem {
  session_id: string;
  mission_name: string;
  status: string;
  git_branch: string;
  log_count?: number;
  last_action?: string;
}

interface WorkstationSidebarProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  sessions: SessionItem[];
  currentSessionId: string;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  onDeleteSession?: (sessionId: string) => void;
}

export function WorkstationSidebar({
  sidebarOpen,
  setSidebarOpen,
  sessions,
  currentSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
}: WorkstationSidebarProps) {
  return (
    <aside
      className={`${
        sidebarOpen ? "w-[260px]" : "w-0"
      } transition-all duration-200 ease-in-out border-r border-[#21262D] bg-[#12151A] flex flex-col flex-shrink-0 z-30 overflow-hidden select-none`}
    >
      {/* Workspace Header */}
      <div className="p-3 border-b border-[#21262D] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded bg-[#238636] text-white text-[11px] font-bold flex items-center justify-center">
            S
          </div>
          <span className="text-xs font-semibold text-white tracking-wide truncate">sonic-workspace</span>
        </div>
        <button
          onClick={() => setSidebarOpen(false)}
          className="text-[#8B949E] hover:text-white p-1 rounded hover:bg-[#21262D] transition"
          title="Collapse sidebar"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* Primary Nav Links */}
      <div className="p-2 space-y-0.5 text-xs font-medium border-b border-[#21262D]/60">
        <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-md bg-[#1F242C] text-white cursor-pointer font-semibold">
          <MessageSquare className="w-4 h-4 text-[#58A6FF]" />
          <span>Workstation</span>
        </div>
        <Link
          href="/graph"
          className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[#8B949E] hover:text-white hover:bg-[#1A1F26] transition"
        >
          <Share2 className="w-4 h-4 text-purple-400" />
          <span>Graph Memory</span>
        </Link>
        <Link
          href="/evidence"
          className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[#8B949E] hover:text-white hover:bg-[#1A1F26] transition"
        >
          <FileCheck2 className="w-4 h-4 text-emerald-400" />
          <span>Evidence Board</span>
        </Link>
        <Link
          href="/evolution"
          className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[#8B949E] hover:text-white hover:bg-[#1A1F26] transition"
        >
          <Dna className="w-4 h-4 text-pink-400" />
          <span>Self-Evolution</span>
        </Link>
      </div>

      {/* Sessions Header & New Session CTA */}
      <div className="px-3 pt-3 pb-1 flex items-center justify-between text-xs text-[#8B949E]">
        <span className="font-semibold text-[11px] uppercase tracking-wider text-slate-400 font-mono">
          Missions & Sessions ({sessions.length})
        </span>
        <button
          onClick={onNewSession}
          className="px-2 py-0.5 text-[#58A6FF] hover:text-white hover:bg-[#21262D] rounded border border-blue-900/50 bg-blue-950/40 transition flex items-center gap-1 text-[11px] font-mono font-bold"
          title="Create New Mission Session"
        >
          <Plus className="w-3 h-3" />
          <span>New</span>
        </button>
      </div>

      {/* Scrollable Session History List */}
      <div className="px-2 flex-1 overflow-y-auto space-y-1.5 font-sans text-xs pt-1">
        {sessions.length === 0 ? (
          <div className="p-3 text-center text-slate-500 font-mono text-[11px]">
            No active sessions.
          </div>
        ) : (
          sessions.map((sess) => {
            const isActive = sess.session_id === currentSessionId;
            return (
              <div
                key={sess.session_id}
                onClick={() => onSelectSession(sess.session_id)}
                className={`group p-2.5 rounded-lg border cursor-pointer transition relative flex flex-col gap-1 ${
                  isActive
                    ? "bg-[#1C2129] border-[#58A6FF]/60 shadow-md shadow-blue-500/10 text-white"
                    : "bg-[#141820] border-[#262C36] hover:bg-[#181D26] hover:border-slate-600 text-slate-300"
                }`}
              >
                <div className="flex items-start justify-between gap-1">
                  <div className="font-semibold truncate text-[12px] flex-1 leading-snug">
                    {sess.mission_name || "Autonomous Mission"}
                  </div>
                  {onDeleteSession && sess.session_id !== "default" && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteSession(sess.session_id);
                      }}
                      className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 p-0.5 rounded transition"
                      title="Delete Session"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  )}
                </div>

                <div className="flex items-center justify-between text-[10px] text-[#8B949E] font-mono mt-0.5">
                  <span className="text-[#3FB950] flex items-center gap-0.5">
                    <GitBranch className="w-2.5 h-2.5" /> {sess.git_branch || "main"}
                  </span>
                  {sess.log_count !== undefined && sess.log_count > 0 && (
                    <span className="text-slate-400">
                      {sess.log_count} event{sess.log_count > 1 ? "s" : ""}
                    </span>
                  )}
                  {isActive && (
                    <span className="text-[9px] px-1.5 py-0.2 rounded bg-blue-900/60 text-blue-300 font-bold border border-blue-700/50">
                      ACTIVE
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Bottom Settings */}
      <div className="p-3 border-t border-[#21262D] flex items-center justify-between text-xs text-[#8B949E]">
        <Link href="/settings" className="flex items-center gap-2 hover:text-white transition">
          <Settings className="w-4 h-4" />
          <span>Settings</span>
        </Link>
        <Link href="/terminal" className="flex items-center gap-1.5 hover:text-white transition">
          <Monitor className="w-4 h-4" />
          <span>PTY Shell</span>
        </Link>
      </div>
    </aside>
  );
}
