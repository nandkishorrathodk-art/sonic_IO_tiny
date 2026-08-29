import React from "react";
import {
  MessageSquare,
  HelpCircle,
  BookOpen,
  Settings,
  Download,
  PanelLeftClose,
  Plus,
  GitBranch,
  Search,
  Compass,
  Monitor,
  Share2,
  FileCheck2,
  Dna,
} from "lucide-react";
import Link from "next/link";

interface WorkstationSidebarProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  sessionName: string;
  gitBranch: string;
  onNewSession?: () => void;
}

export function WorkstationSidebar({
  sidebarOpen,
  setSidebarOpen,
  sessionName,
  gitBranch,
  onNewSession,
}: WorkstationSidebarProps) {
  return (
    <aside
      className={`${
        sidebarOpen ? "w-[240px]" : "w-0"
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
      <div className="p-2 space-y-0.5 text-xs font-medium">
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

      {/* Sessions Section */}
      <div className="px-3 pt-3 pb-1 flex items-center justify-between text-xs text-[#8B949E]">
        <span className="font-semibold text-[11px]">Active Session</span>
        {onNewSession && (
          <button
            onClick={onNewSession}
            className="p-0.5 text-[#8B949E] hover:text-white hover:bg-[#21262D] rounded transition"
            title="Create New Mission Session"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Active Session Card */}
      <div className="px-2 flex-1 overflow-y-auto space-y-1.5 font-sans text-xs">
        <div className="p-2.5 rounded-md bg-[#181C23] border border-[#30363D] cursor-pointer hover:bg-[#1E232B] transition">
          <div className="font-semibold text-white truncate text-[12px]">
            {sessionName}
          </div>
          <div className="flex items-center gap-2 text-[11px] text-[#8B949E] font-mono mt-1">
            <span className="text-[#3FB950] flex items-center gap-0.5">
              <GitBranch className="w-3 h-3" /> {gitBranch}
            </span>
          </div>
        </div>
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
