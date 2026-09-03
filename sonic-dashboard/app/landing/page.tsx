"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Monitor,
  Terminal as TerminalIcon,
  ShieldCheck,
  Cpu,
  Cloud,
  ArrowRight,
  Lock,
  Dna,
  FileCheck2,
  Share2,
  Crosshair,
  ChevronRight,
} from "lucide-react";
import { API_BASE } from "../../lib/api";
import { BrandMark } from "../../components/common/BrandMark";

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

  const capabilities = [
    { icon: <Cloud className="w-5 h-5 text-secondary-400" />, title: "Daytona Cloud", sub: "noVNC XFCE Desktop" },
    { icon: <Cpu className="w-5 h-5 text-success" />, title: "Multi-Model AI", sub: "Llama 3.2 Vision" },
    { icon: <ShieldCheck className="w-5 h-5 text-accent-400" />, title: "Fail-Closed", sub: "Zero Host Execution" },
    { icon: <Share2 className="w-5 h-5 text-primary-400" />, title: "Graph Memory", sub: "Persistent Threat Matrix" },
  ];

  const features = [
    {
      icon: <Monitor className="w-5 h-5" />,
      accent: "secondary",
      title: "Daytona Graphical Workstation",
      desc: "A real interactive Linux GUI powered by Xvfb, XFCE, and x11vnc — streamed live via noVNC directly into the dashboard, with full mouse & keyboard takeover.",
      tag: "Port 6080 WebSocket Stream",
    },
    {
      icon: <Cpu className="w-5 h-5" />,
      accent: "success",
      title: "Multi-Model Reasoning Core",
      desc: "Direct integration with NVIDIA NIM and OpenAI-compatible endpoints, executing Meta Llama 3.2 Vision, 90B reasoning, and CodeLlama for autonomous plan formulation.",
      tag: "Universal OpenAI-Compatible Router",
    },
    {
      icon: <ShieldCheck className="w-5 h-5" />,
      accent: "accent",
      title: "Fail-Closed Tenant Isolation",
      desc: "Path-traversal proof filesystem, cryptographically signed JWT auth, and zero host command execution guarantee absolute workload isolation per tenant.",
      tag: "Security Invariant 503 Enforced",
    },
  ];

  return (
    <div className="min-h-screen bg-ink-950 text-slate-200 flex flex-col font-sans relative overflow-x-hidden">
      {/* Ambient background */}
      <div className="fixed inset-0 bg-grid-glow pointer-events-none" />
      <div className="absolute top-[-15%] left-[20%] w-[600px] h-[600px] bg-primary-600/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute top-[30%] right-[-10%] w-[500px] h-[500px] bg-secondary-600/10 rounded-full blur-[130px] pointer-events-none" />

      {/* Top Navbar */}
      <header className="h-16 border-b border-ink-800/80 backdrop-blur-xl bg-ink-950/70 px-6 md:px-12 flex items-center justify-between sticky top-0 z-50">
        <BrandMark withWordmark href="/landing" />
        <div className="flex items-center gap-3 text-xs font-mono">
          <Link href="/graph" className="btn-ghost hidden md:inline-flex">Graph Memory</Link>
          <Link href="/evidence" className="btn-ghost hidden md:inline-flex">Evidence Board</Link>
          <Link href="/login" className="btn-secondary !px-4 !py-2 text-xs">
            <Lock className="w-3.5 h-3.5" />
            <span>Sign In</span>
          </Link>
          <Link href="/" className="btn-primary !px-4 !py-2 text-xs">
            <span>Launch</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="relative px-6 md:px-12 pt-24 pb-16 max-w-7xl mx-auto flex flex-col items-center text-center space-y-8 z-10">
        <div className="chip border bg-ink-850/80 border-ink-700 text-muted-bright animate-fade-in-up">
          <span className={`w-2 h-2 rounded-full ${isHealthy ? "bg-success animate-pulse" : "bg-muted-dim"}`} />
          <span>{isHealthy ? "CONTROL PLANE ONLINE" : "CONTROL PLANE STATUS UNKNOWN"}</span>
        </div>

        <h1 className="text-4xl sm:text-6xl md:text-7xl font-extrabold tracking-tight text-white max-w-5xl leading-[1.08] animate-fade-in-up">
          The Autonomous AI
          <br />
          <span className="text-gradient">Red Team Workstation</span>
        </h1>

        <p className="text-base sm:text-lg text-muted max-w-3xl font-mono leading-relaxed animate-fade-in-up">
          A self-evolving multi-agent swarm that observes, reasons, and proves real kill-chains —
          backed by full Linux GUI streaming, isolated sandboxes, and cryptographic evidence.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-4 pt-2 animate-fade-in-up">
          <Link href="/" className="btn-primary !px-8 !py-4 text-sm hover:scale-[1.02]">
            <span>Open Workstation Surface</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
          <Link href="/terminal" className="btn-ghost !px-5 !py-4 text-sm border border-ink-700 hover:border-ink-600 font-mono">
            <TerminalIcon className="w-4 h-4 text-secondary-400" />
            <span>Interactive PTY Shell</span>
          </Link>
        </div>

        {/* Capability badges */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 w-full max-w-4xl pt-10 font-mono text-xs text-left animate-fade-in-up">
          {capabilities.map((c) => (
            <div key={c.title} className="panel p-3.5 flex items-center gap-3 hover:border-ink-600 transition">
              <div className="grid place-items-center w-9 h-9 rounded-lg bg-ink-900 border border-ink-700 shrink-0">
                {c.icon}
              </div>
              <div className="min-w-0">
                <div className="text-white font-bold truncate">{c.title}</div>
                <div className="text-muted-dim text-[10px] truncate">{c.sub}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Feature grid */}
      <section className="relative px-6 md:px-12 py-16 max-w-7xl mx-auto z-10 w-full">
        <div className="text-center space-y-2 mb-12 animate-fade-in-up">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Architecture & Engineering Capabilities
          </h2>
          <p className="text-xs text-muted font-mono">
            Engineered for high-assurance autonomous mission execution and live verification.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {features.map((f) => (
            <div
              key={f.title}
              className="glass-card rounded-2xl p-6 space-y-4 hover:-translate-y-1 transition group animate-fade-in-up"
            >
              <div
                className={`grid place-items-center w-11 h-11 rounded-xl border ${
                  f.accent === "secondary"
                    ? "bg-secondary-600/15 border-secondary-500/40 text-secondary-400"
                    : f.accent === "success"
                    ? "bg-success/15 border-success/40 text-success"
                    : "bg-accent-600/15 border-accent-500/40 text-accent-400"
                }`}
              >
                {f.icon}
              </div>
              <h3 className="text-base font-bold text-white">{f.title}</h3>
              <p className="text-xs text-muted font-mono leading-relaxed">{f.desc}</p>
              <div
                className={`text-[11px] font-mono flex items-center gap-1 ${
                  f.accent === "secondary"
                    ? "text-secondary-400"
                    : f.accent === "success"
                    ? "text-success"
                    : "text-accent-400"
                }`}
              >
                <span>{f.tag}</span>
                <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition" />
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Principle strip */}
      <section className="relative px-6 md:px-12 pb-16 max-w-7xl mx-auto z-10 w-full">
        <div className="glass-card rounded-2xl p-8 grid grid-cols-1 md:grid-cols-3 gap-6 text-center">
          {[
            { icon: <FileCheck2 className="w-5 h-5 text-success" />, t: "Evidence > Claims", d: "No finding ships without real request + response proof." },
            { icon: <Crosshair className="w-5 h-5 text-primary-400" />, t: "Sonic, never reckless", d: "Speed under an immutable, default-deny safety layer." },
            { icon: <Dna className="w-5 h-5 text-accent-400" />, t: "Measured self-evolution", d: "Agents improve only through verified canary experiments." },
          ].map((p) => (
            <div key={p.t} className="space-y-2">
              <div className="grid place-items-center w-10 h-10 mx-auto rounded-xl bg-ink-900 border border-ink-700">
                {p.icon}
              </div>
              <h4 className="text-sm font-bold text-white">{p.t}</h4>
              <p className="text-xs text-muted font-mono">{p.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="relative mt-auto border-t border-ink-800/80 px-6 md:px-12 py-6 flex flex-col sm:flex-row items-center justify-between text-xs font-mono text-muted-dim gap-3 z-10">
        <div>SONIC-REDA Autonomous Workstation Core v1.3.0</div>
        <div className="flex items-center gap-4">
          <Link href="/login" className="hover:text-slate-300 transition">Login</Link>
          <Link href="/" className="hover:text-slate-300 transition">Workstation</Link>
          <Link href="/settings" className="hover:text-slate-300 transition">Settings</Link>
        </div>
      </footer>
    </div>
  );
}
