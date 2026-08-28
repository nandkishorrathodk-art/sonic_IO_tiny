import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import { 
  ShieldAlert, 
  Terminal, 
  Share2, 
  FileCheck2, 
  FlaskConical, 
  Box, 
  Settings, 
  Power,
  Activity,
  Cpu,
  Brain,
  BrainCircuit,
  ShieldCheck,
  Monitor,
  Bot,
  Compass
} from "lucide-react";

export const metadata: Metadata = {
  title: "SONIC-REDA — Mission Control",
  description: "Next-Generation Autonomous AI Bug Hunting System Dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#08090E] text-slate-100 min-h-screen flex antialiased font-sans selection:bg-red-500 selection:text-white">
        {/* Operator Sidebar */}
        <aside className="w-64 border-r border-slate-800/80 bg-[#0C0E16]/95 flex flex-col justify-between p-4 flex-shrink-0">
          <div>
            {/* System Logo */}
            <div className="flex items-center gap-3 px-2 py-3 mb-6 border-b border-slate-800/60">
              <div className="w-8 h-8 rounded-lg bg-red-600/20 border border-red-500 flex items-center justify-center glow-red">
                <ShieldAlert className="w-5 h-5 text-red-500" />
              </div>
              <div>
                <h1 className="font-bold tracking-wider text-sm text-white">SONIC-REDA</h1>
                <p className="text-[10px] text-red-400 font-mono tracking-widest uppercase">Red Team Swarm</p>
              </div>
            </div>

            {/* Navigation links */}
            <nav className="space-y-1 text-xs font-medium">
              <Link href="/" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition group">
                <Terminal className="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
                <span>Mission Control</span>
              </Link>
              <Link href="/missions" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition group">
                <Compass className="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
                <span>Autonomous Missions</span>
              </Link>
              <Link href="/mission" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition group">
                <Brain className="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
                <span>Cognitive Mission</span>
              </Link>
              <Link href="/research" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition group">
                <BrainCircuit className="w-4 h-4 text-indigo-400 group-hover:scale-110 transition-transform" />
                <span>Autonomous Researcher</span>
              </Link>
              <Link href="/graph" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition group">
                <Share2 className="w-4 h-4 text-purple-400 group-hover:scale-110 transition-transform" />
                <span>Graph Explorer</span>
              </Link>
              <Link href="/evidence" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition group">
                <FileCheck2 className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
                <span>Evidence Board</span>
              </Link>
              <Link href="/evolution" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition group">
                <FlaskConical className="w-4 h-4 text-pink-400 group-hover:scale-110 transition-transform" />
                <span>Evolution Lab</span>
              </Link>
              <Link href="/security-lab" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition group">
                <ShieldCheck className="w-4 h-4 text-red-400 group-hover:scale-110 transition-transform" />
                <span>Self-Security Lab</span>
              </Link>
              <Link href="/experiments" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/60 transition group">
                <Activity className="w-4 h-4 text-amber-400 group-hover:scale-110 transition-transform" />
                <span>Experiment Lab</span>
              </Link>
              <Link href="/computer" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition group">
                <Monitor className="w-4 h-4 text-blue-400 group-hover:scale-110 transition-transform" />
                <span>SONIC Computer</span>
              </Link>
              <Link href="/engineer" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition group">
                <Bot className="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
                <span>Autonomous Engineer</span>
              </Link>
              <Link href="/terminal" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/60 transition group">
                <Terminal className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
                <span>Live Terminal</span>
              </Link>
              <Link href="/sandbox" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/60 transition group">
                <Box className="w-4 h-4 text-blue-400 group-hover:scale-110 transition-transform" />
                <span>Sandbox Fleet</span>
              </Link>
              <Link href="/settings" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/60 transition group">
                <Settings className="w-4 h-4 text-slate-400 group-hover:scale-110 transition-transform" />
                <span>Scope & Settings</span>
              </Link>
            </nav>
          </div>

          {/* Bottom Info & Kill Switch */}
          <div className="space-y-3 pt-4 border-t border-slate-800/60 text-xs">
            <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800/80 flex items-center justify-between font-mono">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span className="text-[11px] text-slate-300">CORE STATUS</span>
              </div>
              <span className="text-[10px] text-emerald-400 font-bold">ONLINE</span>
            </div>

            <button className="w-full py-2.5 px-3 bg-red-600/10 hover:bg-red-600/20 border border-red-500/50 hover:border-red-500 rounded-lg text-red-400 hover:text-red-300 font-bold flex items-center justify-center gap-2 transition duration-200 glow-red">
              <Power className="w-4 h-4" />
              <span>KILL ALL AGENTS</span>
            </button>
          </div>
        </aside>

        {/* Main Content Viewport */}
        <main className="flex-1 flex flex-col min-w-0 h-screen overflow-y-auto">
          {/* Top Bar */}
          <header className="h-14 border-b border-slate-800/80 bg-[#0C0E16]/80 backdrop-blur px-6 flex items-center justify-between sticky top-0 z-20">
            <div className="flex items-center gap-3 text-xs font-mono">
              <span className="text-slate-500">ENGAGEMENT:</span>
              <span className="px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 font-semibold">Active Swarm #01</span>
            </div>
            <div className="flex items-center gap-4 text-xs">
              <div className="flex items-center gap-2 text-slate-400">
                <Cpu className="w-3.5 h-3.5 text-purple-400" />
                <span>Provider: <strong className="text-slate-200">Claude / Grok Hybrid</strong></span>
              </div>
              <div className="h-4 w-px bg-slate-800"></div>
              <div className="flex items-center gap-2">
                <span className="text-slate-400 font-mono text-[11px]">operator@society</span>
                <div className="w-6 h-6 rounded-full bg-red-600/30 border border-red-500/50 flex items-center justify-center text-[10px] font-bold text-red-300">OP</div>
              </div>
            </div>
          </header>

          {/* Page Child Component */}
          <div className="p-6 flex-1">
            {children}
          </div>
        </main>
      </body>
    </html>
  );
}
