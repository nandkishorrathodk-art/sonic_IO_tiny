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
  Bot,
  Network,
  Activity,
  Database,
  GitBranch,
  Radio,
  ScanLine,
  Workflow,
} from "lucide-react";
import { API_BASE } from "../../lib/api";
import { BrandMark } from "../../components/common/BrandMark";

const SCAN_LINES = [
  { tag: "recon", text: "Enumerating assets on target.acme.io — HTTP probe + header fingerprint", status: "ok" },
  { tag: "static", text: "Analyzing response patterns → 3 candidate injection sinks detected", status: "ok" },
  { tag: "hypothesis", text: "Formulating 5 attack vectors ranked by exploitability", status: "ok" },
  { tag: "dynamic", text: "Executing PoC #3 in isolated Cyber Workstation sandbox — SSTI confirmed", status: "hit" },
  { tag: "verifier", text: "Reproducing → captured request + response evidence locked", status: "ok" },
  { tag: "codefix", text: "Generating regression test + patch diff for verified finding", status: "ok" },
];

const AGENTS = [
  { name: "Recon", icon: Radio, color: "secondary", role: "Asset & surface enumeration" },
  { name: "Static Reasoning", icon: ScanLine, color: "accent", role: "Pattern & sink analysis" },
  { name: "Hypothesis", icon: Crosshair, color: "primary", role: "Attack vector generation" },
  { name: "Dynamic Execution", icon: Bot, color: "warning", role: "PoC execution in sandbox" },
  { name: "Verifier", icon: FileCheck2, color: "success", role: "Evidence reproduction & lock" },
  { name: "CodeFix", icon: GitBranch, color: "secondary", role: "Patch + regression authoring" },
];

const PIPELINE = [
  { label: "OBSERVE", desc: "Recon & live HTTP probing", icon: Radio },
  { label: "REASON", desc: "Static analysis + hypotheses", icon: ScanLine },
  { label: "ACT", desc: "Dynamic PoC in sandbox", icon: Bot },
  { label: "PROVE", desc: "Verifier locks evidence", icon: FileCheck2 },
  { label: "EVOLVE", desc: "Canary experiments + patch", icon: Dna },
];

export default function LandingPage() {
  const [systemHealth, setSystemHealth] = useState<any>(null);
  const [activeScanLine, setActiveScanLine] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE}/health`, { signal: controller.signal })
      .then((res) => res.json())
      .then((data) => setSystemHealth(data))
      .catch(() => {});
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const t = setInterval(() => {
      setActiveScanLine((p) => (p + 1) % SCAN_LINES.length);
    }, 1800);
    return () => clearInterval(t);
  }, []);

  const isHealthy =
    systemHealth?.overall_status === "healthy" ||
    systemHealth?.overall_status === "degraded" ||
    systemHealth?.components?.control_plane_api?.status === "healthy";

  const stats = [
    { label: "Autonomous Agents", value: "6", icon: Bot },
    { label: "Evidence-Secured Findings", value: "0", icon: FileCheck2 },
    { label: "Sandbox Isolation", value: "3", icon: Cloud, sub: "Docker · Kali · Local" },
    { label: "LLM Providers", value: "5", icon: Cpu, sub: "Multi-failover router" },
  ];

  return (
    <div className="min-h-screen bg-ink-950 text-slate-200 flex flex-col font-sans relative overflow-x-hidden">
      {/* Ambient background */}
      <div className="fixed inset-0 bg-grid-glow pointer-events-none" />
      <div className="absolute top-[-15%] left-[20%] w-[600px] h-[600px] bg-primary-600/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute top-[30%] right-[-10%] w-[500px] h-[500px] bg-secondary-600/10 rounded-full blur-[130px] pointer-events-none" />
      <div className="absolute bottom-[10%] left-[-5%] w-[400px] h-[400px] bg-accent-600/8 rounded-full blur-[120px] pointer-events-none" />

      {/* Top Navbar */}
      <header className="h-16 border-b border-ink-800/80 backdrop-blur-xl bg-ink-950/70 px-6 md:px-12 flex items-center justify-between sticky top-0 z-50">
        <BrandMark withWordmark href="/landing" />
        <div className="flex items-center gap-3 text-xs font-mono">
          <Link href="/about" className="btn-ghost hidden sm:inline-flex">About</Link>
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

      {/* Hero with split layout */}
      <section className="relative px-6 md:px-12 pt-20 pb-12 max-w-7xl mx-auto z-10 w-full">
        <div className="grid lg:grid-cols-[1.1fr_0.9fr] gap-12 items-center">
          {/* Left: headline */}
          <div className="flex flex-col items-start space-y-7 animate-fade-in-up">
            <div className="chip border bg-ink-850/80 border-ink-700 text-muted-bright">
              <span className={`w-2 h-2 rounded-full ${isHealthy ? "bg-success animate-pulse" : "bg-muted-dim"}`} />
              <span>{isHealthy ? "CONTROL PLANE ONLINE" : "CONTROL PLANE STATUS UNKNOWN"}</span>
            </div>

            <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-white leading-[1.05]">
              The Autonomous AI
              <br />
              <span className="text-gradient">Red Team</span> Workstation
            </h1>

            <p className="text-base text-muted max-w-xl font-mono leading-relaxed">
              A self-evolving multi-agent swarm that observes, reasons, and proves real
              kill-chains — backed by full Linux GUI streaming, isolated sandboxes, and
              cryptographic evidence.
            </p>

            <div className="flex flex-wrap items-center gap-4 pt-1">
              <Link href="/" className="btn-primary !px-7 !py-3.5 text-sm hover:scale-[1.02]">
                <span>Open Workstation</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link href="/terminal" className="btn-ghost !px-5 !py-3.5 text-sm border border-ink-700 hover:border-ink-600 font-mono">
                <TerminalIcon className="w-4 h-4 text-secondary-400" />
                <span>Interactive Shell</span>
              </Link>
              <Link href="/about" className="btn-ghost !px-5 !py-3.5 text-sm font-mono text-muted-bright">
                <span>Learn how it works</span>
                <ChevronRight className="w-4 h-4" />
              </Link>
            </div>
          </div>

          {/* Right: live scan terminal */}
          <div className="animate-fade-in-up" style={{ animationDelay: "120ms" }}>
            <div className="glass-card rounded-2xl overflow-hidden shadow-2xl">
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-ink-800 bg-ink-900/60">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-danger/80" />
                    <span className="w-2.5 h-2.5 rounded-full bg-warning/80" />
                    <span className="w-2.5 h-2.5 rounded-full bg-success/80" />
                  </div>
                  <span className="text-[10px] font-mono text-muted-dim ml-2">sonic-swarm — live engagement</span>
                </div>
                <div className="flex items-center gap-1.5 text-[10px] font-mono text-success">
                  <Activity className="w-3 h-3" />
                  <span>ACTIVE</span>
                </div>
              </div>
              <div className="p-4 font-mono text-[11px] space-y-2 min-h-[260px]">
                {SCAN_LINES.map((line, i) => {
                  const isActive = i === activeScanLine;
                  const isPast = i < activeScanLine;
                  return (
                    <div
                      key={i}
                      className={`flex items-start gap-2.5 transition-all duration-300 ${
                        isActive ? "opacity-100" : isPast ? "opacity-50" : "opacity-25"
                      }`}
                    >
                      <span
                        className={`mt-0.5 shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded uppercase ${
                          line.status === "hit"
                            ? "bg-danger/20 text-danger border border-danger/40"
                            : isPast || isActive
                              ? "bg-secondary-600/15 text-secondary-400 border border-secondary-500/30"
                              : "bg-ink-800 text-muted-dim border border-ink-700"
                        }`}
                      >
                        {line.tag}
                      </span>
                      <span className={`leading-relaxed ${isActive ? "text-white" : isPast ? "text-muted" : "text-muted-dim"}`}>
                        {line.text}
                        {isActive && <span className="animate-blink text-secondary-400">▋</span>}
                      </span>
                    </div>
                  );
                })}
              </div>
              <div className="px-4 py-2 border-t border-ink-800 bg-ink-900/60 flex items-center justify-between text-[10px] font-mono text-muted-dim">
                <span className="flex items-center gap-1.5">
                  <Workflow className="w-3 h-3" />
                  Director → task-graph dispatch
                </span>
                <span className="text-success">evidence-secured ✓</span>
              </div>
            </div>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-14 animate-fade-in-up" style={{ animationDelay: "200ms" }}>
          {stats.map((s) => (
            <div key={s.label} className="panel p-4 space-y-1.5">
              <div className="flex items-center justify-between">
                <s.icon className="w-4 h-4 text-secondary-400" />
                <span className="text-2xl font-extrabold text-white font-mono">{s.value}</span>
              </div>
              <div className="text-[11px] text-muted font-mono">{s.label}</div>
              {s.sub && <div className="text-[10px] text-muted-dim font-mono">{s.sub}</div>}
            </div>
          ))}
        </div>
      </section>

      {/* Agent Swarm Registry */}
      <section className="relative px-6 md:px-12 py-16 max-w-7xl mx-auto z-10 w-full">
        <div className="text-center space-y-2 mb-12 animate-fade-in-up">
          <div className="chip border border-primary-500/30 bg-primary-600/10 text-primary-400 mx-auto">
            <Network className="w-3 h-3" />
            <span>SWARM ARCHITECTURE</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Six specialists. One autonomous kill-chain.
          </h2>
          <p className="text-xs text-muted font-mono max-w-2xl mx-auto">
            Each agent owns a phase of the engagement. The Director orchestrates the task-graph;
            findings flow through verification before they ever touch a report.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {AGENTS.map((a, i) => (
            <div
              key={a.name}
              className="glass-card rounded-2xl p-5 space-y-3 hover:-translate-y-1 transition group animate-fade-in-up"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <div className="flex items-center justify-between">
                <div
                  className={`grid place-items-center w-10 h-10 rounded-xl border ${
                    a.color === "primary"
                      ? "bg-primary-600/15 border-primary-500/40 text-primary-400"
                      : a.color === "secondary"
                        ? "bg-secondary-600/15 border-secondary-500/40 text-secondary-400"
                        : a.color === "accent"
                          ? "bg-accent-600/15 border-accent-500/40 text-accent-400"
                          : a.color === "warning"
                            ? "bg-warning/15 border-warning/40 text-warning"
                            : "bg-success/15 border-success/40 text-success"
                  }`}
                >
                  <a.icon className="w-5 h-5" />
                </div>
                <span className="text-[10px] font-mono text-muted-dim">
                  {String(i + 1).padStart(2, "0")}
                </span>
              </div>
              <h3 className="text-sm font-bold text-white">{a.name}</h3>
              <p className="text-xs text-muted font-mono leading-relaxed">{a.role}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Kill-chain pipeline */}
      <section className="relative px-6 md:px-12 py-16 max-w-7xl mx-auto z-10 w-full">
        <div className="glass-card rounded-2xl p-8 animate-fade-in-up">
          <div className="text-center space-y-2 mb-10">
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-white">
              The Evidence-Secured Kill-Chain
            </h2>
            <p className="text-xs text-muted font-mono">
              Observe → Reason → Act → Prove → Evolve. No finding ships without real proof.
            </p>
          </div>
          <div className="flex flex-col md:flex-row items-stretch gap-3">
            {PIPELINE.map((step, i) => (
              <React.Fragment key={step.label}>
                <div className="flex-1 panel p-4 space-y-2 text-center min-w-0">
                  <div className="grid place-items-center w-9 h-9 mx-auto rounded-lg bg-ink-900 border border-ink-700">
                    <step.icon className="w-4 h-4 text-secondary-400" />
                  </div>
                  <div className="text-xs font-bold text-white font-mono tracking-wider">{step.label}</div>
                  <div className="text-[10px] text-muted-dim font-mono">{step.desc}</div>
                </div>
                {i < PIPELINE.length - 1 && (
                  <div className="hidden md:flex items-center justify-center">
                    <ChevronRight className="w-5 h-5 text-ink-500" />
                  </div>
                )}
              </React.Fragment>
            ))}
          </div>
        </div>
      </section>

      {/* Feature grid */}
      <section className="relative px-6 md:px-12 py-16 max-w-7xl mx-auto z-10 w-full">
        <div className="text-center space-y-2 mb-12 animate-fade-in-up">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Architecture & Engineering
          </h2>
          <p className="text-xs text-muted font-mono">
            Engineered for high-assurance autonomous mission execution and live verification.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            {
              icon: <Monitor className="w-5 h-5" />,
              accent: "secondary",
              title: "Native Cyber Workstation",
              desc: "A real interactive Linux GUI powered by Xvfb, XFCE, and x11vnc — streamed live via noVNC directly into the dashboard, with full mouse & keyboard takeover.",
              tag: "Port 6080 WebSocket Stream",
            },
            {
              icon: <Cpu className="w-5 h-5" />,
              accent: "success",
              title: "Multi-Model Reasoning Core",
              desc: "Direct integration with NVIDIA NIM and OpenAI-compatible endpoints, executing Meta Llama 3.2 Vision, 90B reasoning, and DeepSeek-Coder for autonomous plan formulation.",
              tag: "Universal OpenAI-Compatible Router",
            },
            {
              icon: <ShieldCheck className="w-5 h-5" />,
              accent: "accent",
              title: "Fail-Closed Tenant Isolation",
              desc: "Path-traversal proof filesystem, cryptographically signed JWT auth, and zero host command execution guarantee absolute workload isolation per tenant.",
              tag: "Security Invariant Enforced",
            },
          ].map((f) => (
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
          <Link href="/about" className="hover:text-slate-300 transition">About</Link>
          <Link href="/login" className="hover:text-slate-300 transition">Login</Link>
          <Link href="/" className="hover:text-slate-300 transition">Workstation</Link>
          <Link href="/settings" className="hover:text-slate-300 transition">Settings</Link>
        </div>
      </footer>
    </div>
  );
}
