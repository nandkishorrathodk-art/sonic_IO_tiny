import React from "react";
import {
  MessageSquare,
  Settings,
  PanelLeftClose,
  Plus,
  GitBranch,
  Compass,
  Share2,
  FileCheck2,
  Dna,
  Trash2,
  ShieldCheck,
  Monitor,
  BrainCircuit,
  FlaskConical,
  Cpu,
} from "lucide-react";
import Link from "next/link";
import { BrandMark } from "../common/BrandMark";
import { SessionItem } from "../../types/workstation";

export type { SessionItem };

interface WorkstationSidebarProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  sessions: SessionItem[];
  currentSessionId: string;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  onDeleteSession?: (sessionId: string) => void;
}

const NAV = [
  { href: "/", label: "Workstation", icon: <MessageSquare className="w-4 h-4 text-secondary-400" /> },
  { href: "/missions", label: "Missions", icon: <Compass className="w-4 h-4 text-primary-400" /> },
  { href: "/computer", label: "Computer", icon: <Monitor className="w-4 h-4 text-secondary-400" /> },
  { href: "/research", label: "Research", icon: <BrainCircuit className="w-4 h-4 text-accent-400" /> },
  { href: "/experiments", label: "Experiments", icon: <FlaskConical className="w-4 h-4 text-primary-400" /> },
  { href: "/graph", label: "Graph Memory", icon: <Share2 className="w-4 h-4 text-accent-400" /> },
  { href: "/evidence", label: "Evidence Board", icon: <FileCheck2 className="w-4 h-4 text-success" /> },
  { href: "/agents", label: "Agents", icon: <Cpu className="w-4 h-4 text-secondary-400" /> },
  { href: "/security-lab", label: "Security Lab", icon: <ShieldCheck className="w-4 h-4 text-danger" /> },
];

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
      } transition-all duration-200 ease-in-out border-r border-ink-800 bg-ink-900 flex flex-col flex-shrink-0 z-30 overflow-hidden`}
    >
      {/* Workspace Header */}
      <div className="p-3 border-b border-ink-800 flex items-center justify-between">
        <BrandMark size={24} withWordmark />
        <button
          onClick={() => setSidebarOpen(false)}
          className="text-muted hover:text-white p-1 rounded hover:bg-ink-800 transition"
          title="Collapse sidebar"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* Primary Nav */}
      <nav className="p-2 space-y-0.5 text-xs font-medium border-b border-ink-800/60">
        <Link href="/" className="nav-link nav-link-active">
          <MessageSquare className="w-4 h-4 text-secondary-400" />
          <span>Workstation</span>
        </Link>
        {NAV.slice(1).map((n) => (
          <Link key={n.href} href={n.href} className="nav-link">
            {n.icon}
            <span>{n.label}</span>
          </Link>
        ))}
      </nav>

      {/* Sessions header */}
      {(() => {
        const safeSessions = Array.isArray(sessions)
          ? sessions.filter((s): s is SessionItem => Boolean(s && typeof s === "object"))
          : [];

        return (
          <>
            <div className="px-3 pt-3 pb-1 flex items-center justify-between text-xs text-muted">
              <span className="font-semibold text-[11px] uppercase tracking-wider text-muted-dim font-mono">
                Missions ({safeSessions.length})
              </span>
              <button
                onClick={onNewSession}
                className="px-2 py-0.5 text-secondary-400 hover:text-white hover:bg-ink-800 rounded border border-secondary-700/40 bg-secondary-600/10 transition flex items-center gap-1 text-[11px] font-mono font-bold"
                title="Create New Mission Session"
              >
                <Plus className="w-3 h-3" />
                <span>New</span>
              </button>
            </div>

            {/* Session list */}
            <div className="px-2 flex-1 overflow-y-auto space-y-1.5 font-sans text-xs pt-1">
              {safeSessions.length === 0 ? (
                <div className="p-3 text-center text-muted-dim font-mono text-[11px]">
                  No active sessions.
                </div>
              ) : (
                safeSessions.map((sess, idx) => {
                  const sessId = typeof sess.session_id === "string" && sess.session_id.trim()
                    ? sess.session_id.trim()
                    : `session-${idx}`;
                  const isActive = sessId === currentSessionId;
                  return (
                    <div
                      key={sessId}
                      onClick={() => onSelectSession(sessId)}
                      className={`group p-2.5 rounded-lg border cursor-pointer transition relative flex flex-col gap-1 ${
                        isActive
                          ? "bg-ink-800 border-primary-500/50 shadow-glow text-white"
                          : "bg-ink-850 border-ink-700 hover:bg-ink-800 hover:border-ink-600 text-slate-300"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-1">
                        <div className="font-semibold truncate text-[12px] flex-1 leading-snug">
                          {sess.mission_name || "Unprovisioned Workstation"}
                        </div>
                        {onDeleteSession && sessId !== "default" && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeleteSession(sessId);
                            }}
                            className="opacity-0 group-hover:opacity-100 text-muted-dim hover:text-danger p-0.5 rounded transition"
                            title="Delete Session"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        )}
                      </div>

                      <div className="flex items-center justify-between text-[10px] text-muted font-mono mt-0.5">
                        <span className="text-success flex items-center gap-0.5">
                          <GitBranch className="w-2.5 h-2.5" /> {sess.git_branch || "—"}
                        </span>
                        {typeof sess.log_count === "number" && sess.log_count > 0 && (
                          <span className="text-muted-dim">
                            {sess.log_count} event{sess.log_count > 1 ? "s" : ""}
                          </span>
                        )}
                        {isActive && (
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-primary-600/30 text-primary-400 font-bold border border-primary-500/40">
                            ACTIVE
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </>
        );
      })()}


      {/* Bottom */}
      <div className="p-3 border-t border-ink-800 flex items-center justify-between text-xs text-muted">
        <Link href="/settings" className="flex items-center gap-2 hover:text-white transition">
          <Settings className="w-4 h-4" />
          <span>Settings</span>
        </Link>
      </div>
    </aside>
  );
}
