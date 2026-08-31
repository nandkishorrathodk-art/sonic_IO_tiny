"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Monitor,
  Terminal as TerminalIcon,
  ShieldCheck,
  Cpu,
  Server,
  Cloud,
  Sparkles,
  ArrowRight,
  Layers,
  Activity,
  Zap,
  Lock,
  GitBranch,
  Dna,
  FileCheck2,
  Share2,
  CheckCircle,
  Play,
} from "lucide-react";
import { API_BASE } from "../../lib/api";

export default function LandingPage() {
  const [systemHealth, setSystemHealth] = useState<any>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE}/health`, { signal: controller.signal })
      .then((res) => res.json())
      .then((data) => setSystemHealth(data))
      .catch(() => {});
    return () => controller.abort();
  }, []);

  const isHealthy = systemHealth?.overall_status === "healthy";

  return (
    <div className="min-h-screen bg-[#07090E] text-slate-100 flex flex-col font-sans relative overflow-x-hidden selection:bg-blue-600 selection:text-white">
      {/* Background Ambient Glowing Lights */}
      <div className="absolute top-[-15%] left-[20%] w-[600px] h-[600px] bg-blue-600/15 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute top-[30%] right-[-10%] w-[500px] h-[500px] bg-indigo-600/15 rounded-full blur-[130px] pointer-events-none" />
      <div className="absolute bottom-[-10%] left-[-5%] w-[700px] h-[700px] bg-cyan-600/10 rounded-full blur-[160px] pointer-events-none" />

      {/* Top Navbar */}
      <header className="h-16 border-b border-[#1E2436]/60 backdrop-blur-xl px-6 md:px-12 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-400 p-0.5 shadow-lg shadow-blue-500/25">
            <div className="w-full h-full bg-[#0C0E16] rounded-[10px] flex items-center justify-center font-mono font-black text-xs text-blue-400">
              S
            </div>
          </div>
          <div>
            <span className="font-extrabold tracking-wider text-sm text-white">SONIC-REDA</span>
            <span className="text-[10px] font-mono ml-2 text-cyan-400 font-semibold uppercase hidden sm:inline">
              Autonomous Workstation
            </span>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono">
          <Link
            href="/graph"
            className="text-slate-400 hover:text-white transition px-3 py-1.5 rounded-lg hover:bg-slate-800/40 hidden md:block"
          >
            Graph Memory
          </Link>
          <Link
            href="/evidence"
            className="text-slate-400 hover:text-white transition px-3 py-1.5 rounded-lg hover:bg-slate-800/40 hidden md:block"
          >
            Evidence Board
          </Link>
          <Link
            href="/login"
            className="text-slate-300 hover:text-white transition px-3 py-1.5 rounded-lg border border-slate-700/80 hover:border-slate-500 bg-[#0E131F]"
          >
            Sign In / Tenant
          </Link>
          <Link
            href="/"
            className="px-4 py-2 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 text-white font-bold tracking-wide shadow-lg shadow-blue-500/25 transition flex items-center gap-1.5"
          >
            <span>Launch Workstation</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </header>

      {/* Hero Section */}
      <section className="px-6 md:px-12 pt-20 pb-16 max-w-7xl mx-auto flex flex-col items-center text-center space-y-8 z-10">
        {/* Status Chip */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-950/80 border border-blue-800/60 text-blue-300 text-xs font-mono shadow-inner">
          <span className={`w-2 h-2 rounded-full ${isHealthy ? "bg-emerald-400 animate-pulse" : "bg-slate-500"}`} />
          <span>{isHealthy ? "CONTROL PLANE ONLINE" : "CONTROL PLANE STATUS UNKNOWN"}</span>
        </div>

        {/* Hero Title */}
        <h1 className="text-4xl sm:text-6xl md:text-7xl font-extrabold tracking-tight text-white max-w-5xl leading-[1.1]">
          The Autonomous AI Engineer &{" "}
          <span className="bg-gradient-to-r from-blue-400 via-indigo-300 to-cyan-400 bg-clip-text text-transparent">
            Graphical Workstation
          </span>
        </h1>

        {/* Hero Subtitle */}
        <p className="text-base sm:text-lg text-slate-400 max-w-3xl font-mono leading-relaxed">
          Full Linux GUI Desktop streaming with real XFCE + noVNC, NVIDIA NIM multi-model reasoning,
          isolated container sandboxes, and fail-closed host security.
        </p>

        {/* CTA Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
          <Link
            href="/"
            className="px-8 py-4 rounded-2xl bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 text-white font-bold text-sm tracking-wide shadow-2xl shadow-blue-500/40 transition flex items-center gap-2 hover:scale-[1.02]"
          >
            <span>Open Workstation Surface</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            href="/login"
            className="px-6 py-4 rounded-2xl bg-[#111624] hover:bg-[#182033] border border-slate-700/80 text-slate-200 font-bold text-sm tracking-wide transition flex items-center gap-2"
          >
            <Lock className="w-4 h-4 text-purple-400" />
            <span>Tenant Authentication</span>
          </Link>
          <Link
            href="/terminal"
            className="px-6 py-4 rounded-2xl bg-[#111624] hover:bg-[#182033] border border-slate-700/80 text-slate-200 font-bold text-sm tracking-wide transition flex items-center gap-2 font-mono text-xs"
          >
            <TerminalIcon className="w-4 h-4 text-emerald-400" />
            <span>Interactive PTY Shell</span>
          </Link>
        </div>

        {/* System Capability Badges */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 w-full max-w-4xl pt-8 font-mono text-xs text-left">
          <div className="p-3.5 rounded-xl bg-[#0D111A]/90 border border-slate-800 flex items-center gap-3">
            <Cloud className="w-5 h-5 text-blue-400 flex-shrink-0" />
            <div>
              <div className="text-white font-bold">Daytona Cloud</div>
              <div className="text-slate-500 text-[10px]">noVNC XFCE Desktop</div>
            </div>
          </div>
          <div className="p-3.5 rounded-xl bg-[#0D111A]/90 border border-slate-800 flex items-center gap-3">
            <Cpu className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <div>
              <div className="text-white font-bold">NVIDIA NIM LLM</div>
              <div className="text-slate-500 text-[10px]">Meta Llama 3.2 Vision</div>
            </div>
          </div>
          <div className="p-3.5 rounded-xl bg-[#0D111A]/90 border border-slate-800 flex items-center gap-3">
            <ShieldCheck className="w-5 h-5 text-purple-400 flex-shrink-0" />
            <div>
              <div className="text-white font-bold">Fail-Closed</div>
              <div className="text-slate-500 text-[10px]">Zero Host OS Execution</div>
            </div>
          </div>
          <div className="p-3.5 rounded-xl bg-[#0D111A]/90 border border-slate-800 flex items-center gap-3">
            <Share2 className="w-5 h-5 text-pink-400 flex-shrink-0" />
            <div>
              <div className="text-white font-bold">Graph Memory</div>
              <div className="text-slate-500 text-[10px]">Persistent Threat Matrix</div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Grid Section */}
      <section className="px-6 md:px-12 py-16 max-w-7xl mx-auto z-10 w-full">
        <div className="text-center space-y-2 mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Architecture & Engineering Capabilities
          </h2>
          <p className="text-xs text-slate-400 font-mono">
            Engineered for high-assurance autonomous mission execution and live verification.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Card 1: Daytona Computer */}
          <div className="p-6 rounded-2xl bg-[#0F131F]/80 border border-slate-800/80 backdrop-blur-lg space-y-4 hover:border-blue-500/50 transition">
            <div className="w-10 h-10 rounded-xl bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-blue-400">
              <Monitor className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-white">Daytona Graphical Workstation</h3>
            <p className="text-xs text-slate-400 font-mono leading-relaxed">
              Real interactive Linux GUI powered by Xvfb :99, XFCE desktop environment, and x11vnc streamed
              via noVNC directly into the dashboard.
            </p>
            <div className="text-[11px] font-mono text-blue-400 flex items-center gap-1">
              <span>Port 6080 WebSocket Stream</span>
              <ArrowRight className="w-3 h-3" />
            </div>
          </div>

          {/* Card 2: NVIDIA NIM LLM */}
          <div className="p-6 rounded-2xl bg-[#0F131F]/80 border border-slate-800/80 backdrop-blur-lg space-y-4 hover:border-emerald-500/50 transition">
            <div className="w-10 h-10 rounded-xl bg-emerald-600/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-white">NVIDIA NIM Multi-Model AI</h3>
            <p className="text-xs text-slate-400 font-mono leading-relaxed">
              Direct integration with NVIDIA NIM endpoints executing Meta Llama 3.2 Vision, 90B Reasoning,
              and CodeLlama for autonomous plan formulation.
            </p>
            <div className="text-[11px] font-mono text-emerald-400 flex items-center gap-1">
              <span>Universal OpenAI-Compatible Router</span>
              <ArrowRight className="w-3 h-3" />
            </div>
          </div>

          {/* Card 3: Security & Multi-Tenant */}
          <div className="p-6 rounded-2xl bg-[#0F131F]/80 border border-slate-800/80 backdrop-blur-lg space-y-4 hover:border-purple-500/50 transition">
            <div className="w-10 h-10 rounded-xl bg-purple-600/20 border border-purple-500/40 flex items-center justify-center text-purple-400">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-white">Fail-Closed Tenant Isolation</h3>
            <p className="text-xs text-slate-400 font-mono leading-relaxed">
              Path-traversal proof, cryptographically signed JWT auth, and zero host command execution
              guarantee absolute workload isolation.
            </p>
            <div className="text-[11px] font-mono text-purple-400 flex items-center gap-1">
              <span>Security Invariant 503 Enforced</span>
              <ArrowRight className="w-3 h-3" />
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-auto border-t border-[#1E2436]/60 px-6 md:px-12 py-6 flex flex-col sm:flex-row items-center justify-between text-xs font-mono text-slate-500 gap-3 z-10">
        <div>SONIC-REDA Autonomous Workstation Core v1.3.0</div>
        <div className="flex items-center gap-4">
          <Link href="/login" className="hover:text-slate-300">Login</Link>
          <Link href="/" className="hover:text-slate-300">Workstation</Link>
          <Link href="/settings" className="hover:text-slate-300">Settings</Link>
        </div>
      </footer>
    </div>
  );
}
