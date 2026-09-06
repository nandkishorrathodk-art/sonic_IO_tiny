"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Lock,
  ChevronRight,
  ShieldCheck,
  Cpu,
  Cloud,
  Database,
  Bot,
  Network,
  Dna,
  FileCheck2,
  Crosshair,
  GitBranch,
  Radio,
  ScanLine,
  Layers,
  Workflow,
  Terminal as TerminalIcon,
  Server,
  Brain,
  Boxes,
  ShieldAlert,
} from "lucide-react";
import { API_BASE } from "../../lib/api";
import { BrandMark } from "../../components/common/BrandMark";

const TECH_STACK = [
  { layer: "Frontend", tech: "Next.js 14 · TypeScript · Tailwind", icon: Layers, color: "secondary" },
  { layer: "API / Backend", tech: "FastAPI · Pydantic · JWT Auth", icon: Server, color: "primary" },
  { layer: "Agent Core", tech: "ReAct Engine · Tool-calling · Replanner", icon: Brain, color: "accent" },
  { layer: "Memory", tech: "Neo4j · SQLite fallback · Graph schemas", icon: Database, color: "success" },
  { layer: "Sandbox", tech: "Docker Cyber Workstation · Kali · Local sandbox", icon: Cloud, color: "warning" },
  { layer: "LLM Router", tech: "NVIDIA NIM · Anthropic · OpenAI · xAI", icon: Cpu, color: "secondary" },
];

const AGENT_DETAIL = [
  {
    name: "Recon Agent",
    icon: Radio,
    color: "secondary",
    phase: "OBSERVE",
    desc: "Enumerates the attack surface via live HTTP probing, header fingerprinting, and LLM-reasoned asset planning. Every asset is stored in the graph memory with provenance.",
    capabilities: ["Live HTTP probe", "Tech-stack fingerprint", "Scope enforcement"],
  },
  {
    name: "Static Reasoning",
    icon: ScanLine,
    color: "accent",
    phase: "REASON",
    desc: "Analyzes responses, configs, and code for injection sinks, misconfigurations, and logic flaws. Generates structured hypotheses ranked by exploitability.",
    capabilities: ["Sink detection", "Config audit", "Hypothesis ranking"],
  },
  {
    name: "Hypothesis Agent",
    icon: Crosshair,
    color: "primary",
    phase: "REASON",
    desc: "Formulates concrete attack vectors from static findings. Each hypothesis carries an expected outcome, risk level, and the exact PoC strategy to test it.",
    capabilities: ["Vector generation", "Risk scoring", "PoC strategy"],
  },
  {
    name: "Dynamic Execution",
    icon: Bot,
    color: "warning",
    phase: "ACT",
    desc: "Executes PoCs inside isolated sandboxes with real tools. The autonomous pentest loop re-engages when findings appear, bounded by a configurable pivot limit.",
    capabilities: ["Sandbox PoC execution", "Sustained pivot loop", "Real tool invocation"],
  },
  {
    name: "Verifier",
    icon: FileCheck2,
    color: "success",
    phase: "PROVE",
    desc: "Reproduces each candidate finding against the live target, captures full request + response, and locks cryptographic evidence. No finding ships without proof.",
    capabilities: ["Reproduction gate", "Evidence capture", "Confidence scoring"],
  },
  {
    name: "CodeFix",
    icon: GitBranch,
    color: "secondary",
    phase: "EVOLVE",
    desc: "Authors a patch diff and regression test for verified findings, ready for a pull request. Honest failure when the LLM cannot produce a parseable patch.",
    capabilities: ["Patch generation", "Regression tests", "PR-ready output"],
  },
];

const SAFETY = [
  {
    title: "Default-Deny Safety Layer",
    desc: "An immutable layer that blocks risky actions before they reach any sandbox. Every GUI action, tool invocation, and PoC is evaluated against risk rules — fail-closed, never fail-open.",
    icon: ShieldAlert,
  },
  {
    title: "Scope Enforcement",
    desc: "Targets are checked against an allow-list before any probe. Out-of-scope or unauthorized targets are blocked at the recon stage — the system never touches what it shouldn't.",
    icon: ShieldCheck,
  },
  {
    title: "Tenant Isolation",
    desc: "Cryptographically signed JWT auth, path-traversal-proof filesystems, and zero host command execution guarantee that workloads from different tenants never cross.",
    icon: Lock,
  },
];

const PRINCIPLES = [
  {
    n: "01",
    title: "Evidence over Claims",
    desc: "A finding is not a finding until it has been reproduced against the real target with captured proof. Unverified hypotheses stay hypotheses.",
    icon: FileCheck2,
  },
  {
    n: "02",
    title: "Sonic, never reckless",
    desc: "The system is fast because it is disciplined. Speed lives under an immutable, default-deny safety layer — never by bypassing it.",
    icon: Crosshair,
  },
  {
    n: "03",
    title: "Measured self-evolution",
    desc: "Agents improve only through verified canary experiments — proposed, approved, run in isolation, measured, then promoted or rejected. No blind mutation.",
    icon: Dna,
  },
];

const FLOW = [
  { label: "TARGET", desc: "In-scope target approved", icon: Crosshair },
  { label: "OBSERVE", desc: "Recon enumerates surface", icon: Radio },
  { label: "REASON", desc: "Static + hypotheses", icon: ScanLine },
  { label: "ACT", desc: "PoC in sandbox", icon: Bot },
  { label: "PROVE", desc: "Verifier locks proof", icon: FileCheck2 },
  { label: "EVOLVE", desc: "Patch + regression", icon: GitBranch },
];

export default function AboutPage() {
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
    <div className="min-h-screen bg-ink-950 text-slate-200 flex flex-col font-sans relative overflow-x-hidden">
      {/* Ambient background */}
      <div className="fixed inset-0 bg-grid-glow pointer-events-none" />
      <div className="absolute top-[-10%] right-[15%] w-[500px] h-[500px] bg-primary-600/10 rounded-full blur-[130px] pointer-events-none" />
      <div className="absolute top-[40%] left-[-8%] w-[450px] h-[450px] bg-secondary-600/8 rounded-full blur-[120px] pointer-events-none" />

      {/* Top Navbar */}
      <header className="h-16 border-b border-ink-800/80 backdrop-blur-xl bg-ink-950/70 px-6 md:px-12 flex items-center justify-between sticky top-0 z-50">
        <BrandMark withWordmark href="/landing" />
        <div className="flex items-center gap-3 text-xs font-mono">
          <Link href="/landing" className="btn-ghost hidden sm:inline-flex">Home</Link>
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
      <section className="relative px-6 md:px-12 pt-20 pb-12 max-w-4xl mx-auto text-center z-10 w-full">
        <div className="chip border bg-ink-850/80 border-ink-700 text-muted-bright mx-auto animate-fade-in-up">
          <span className={`w-2 h-2 rounded-full ${isHealthy ? "bg-success animate-pulse" : "bg-muted-dim"}`} />
          <span>{isHealthy ? "SYSTEM ONLINE" : "SYSTEM STATUS UNKNOWN"}</span>
        </div>
        <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-white mt-6 leading-[1.08] animate-fade-in-up">
          How <span className="text-gradient">SONIC-REDA</span> works
        </h1>
        <p className="text-base text-muted mt-6 font-mono leading-relaxed max-w-2xl mx-auto animate-fade-in-up">
          An autonomous red-team system built around one idea: a finding is only real when it has
          been proven against the target with captured evidence. Here is the architecture, the
          agents, the safety model, and the principles that hold it together.
        </p>
      </section>

      {/* Tech stack */}
      <section className="relative px-6 md:px-12 py-12 max-w-5xl mx-auto z-10 w-full">
        <div className="text-center space-y-2 mb-10 animate-fade-in-up">
          <div className="chip border border-secondary-500/30 bg-secondary-600/10 text-secondary-400 mx-auto">
            <Boxes className="w-3 h-3" />
            <span>ARCHITECTURE</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Layer by layer
          </h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {TECH_STACK.map((t, i) => (
            <div
              key={t.layer}
              className="glass-card rounded-2xl p-5 space-y-3 hover:-translate-y-1 transition animate-fade-in-up"
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <div
                className={`grid place-items-center w-10 h-10 rounded-xl border ${
                  t.color === "primary"
                    ? "bg-primary-600/15 border-primary-500/40 text-primary-400"
                    : t.color === "secondary"
                      ? "bg-secondary-600/15 border-secondary-500/40 text-secondary-400"
                      : t.color === "accent"
                        ? "bg-accent-600/15 border-accent-500/40 text-accent-400"
                        : t.color === "warning"
                          ? "bg-warning/15 border-warning/40 text-warning"
                          : "bg-success/15 border-success/40 text-success"
                }`}
              >
                <t.icon className="w-5 h-5" />
              </div>
              <div className="text-sm font-bold text-white">{t.layer}</div>
              <div className="text-xs text-muted font-mono leading-relaxed">{t.tech}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Agents deep dive */}
      <section className="relative px-6 md:px-12 py-16 max-w-6xl mx-auto z-10 w-full">
        <div className="text-center space-y-2 mb-12 animate-fade-in-up">
          <div className="chip border border-primary-500/30 bg-primary-600/10 text-primary-400 mx-auto">
            <Network className="w-3 h-3" />
            <span>THE SWARM</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Six specialists, one engagement
          </h2>
          <p className="text-xs text-muted font-mono max-w-2xl mx-auto">
            The Director builds and dispatches a task-graph. Each agent owns a phase; findings
            flow through verification before they reach a report.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {AGENT_DETAIL.map((a, i) => (
            <div
              key={a.name}
              className="glass-card rounded-2xl p-6 space-y-4 hover:-translate-y-0.5 transition animate-fade-in-up"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className={`grid place-items-center w-11 h-11 rounded-xl border ${
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
                  <div>
                    <h3 className="text-sm font-bold text-white">{a.name}</h3>
                    <span className="text-[10px] font-mono text-muted-dim uppercase tracking-wider">
                      Phase: {a.phase}
                    </span>
                  </div>
                </div>
                <span className="text-2xl font-extrabold text-ink-600 font-mono">
                  {String(i + 1).padStart(2, "0")}
                </span>
              </div>
              <p className="text-xs text-muted font-mono leading-relaxed">{a.desc}</p>
              <div className="flex flex-wrap gap-2 pt-1">
                {a.capabilities.map((c) => (
                  <span
                    key={c}
                    className="text-[10px] font-mono px-2 py-1 rounded-md bg-ink-800 border border-ink-700 text-muted-bright"
                  >
                    {c}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Engagement flow */}
      <section className="relative px-6 md:px-12 py-12 max-w-5xl mx-auto z-10 w-full">
        <div className="glass-card rounded-2xl p-8 animate-fade-in-up">
          <div className="text-center space-y-2 mb-10">
            <div className="chip border border-accent-500/30 bg-accent-600/10 text-accent-400 mx-auto">
              <Workflow className="w-3 h-3" />
              <span>ENGAGEMENT FLOW</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-white">
              From target to verified evidence
            </h2>
          </div>
          <div className="flex flex-col md:flex-row items-stretch gap-2">
            {FLOW.map((step, i, arr) => (
              <React.Fragment key={step.label}>
                <div className="flex-1 panel p-4 space-y-2 text-center min-w-0">
                  <div className="grid place-items-center w-9 h-9 mx-auto rounded-lg bg-ink-900 border border-ink-700">
                    <step.icon className="w-4 h-4 text-secondary-400" />
                  </div>
                  <div className="text-xs font-bold text-white font-mono tracking-wider">{step.label}</div>
                  <div className="text-[10px] text-muted-dim font-mono">{step.desc}</div>
                </div>
                {i < arr.length - 1 && (
                  <div className="hidden md:flex items-center justify-center">
                    <ChevronRight className="w-5 h-5 text-ink-500" />
                  </div>
                )}
              </React.Fragment>
            ))}
          </div>
        </div>
      </section>

      {/* Safety model */}
      <section className="relative px-6 md:px-12 py-16 max-w-5xl mx-auto z-10 w-full">
        <div className="text-center space-y-2 mb-12 animate-fade-in-up">
          <div className="chip border border-danger/30 bg-danger/10 text-danger mx-auto">
            <ShieldCheck className="w-3 h-3" />
            <span>SAFETY MODEL</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Sonic, never reckless
          </h2>
          <p className="text-xs text-muted font-mono max-w-2xl mx-auto">
            Three invariants hold the system back from harm — enforced in code, not in policy docs.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {SAFETY.map((s, i) => (
            <div
              key={s.title}
              className="glass-card rounded-2xl p-6 space-y-4 animate-fade-in-up"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <div className="grid place-items-center w-11 h-11 rounded-xl border bg-danger/10 border-danger/30 text-danger">
                <s.icon className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-white">{s.title}</h3>
              <p className="text-xs text-muted font-mono leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Principles */}
      <section className="relative px-6 md:px-12 py-16 max-w-5xl mx-auto z-10 w-full">
        <div className="text-center space-y-2 mb-12 animate-fade-in-up">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Operating principles
          </h2>
        </div>
        <div className="space-y-4">
          {PRINCIPLES.map((p, i) => (
            <div
              key={p.n}
              className="glass-card rounded-2xl p-6 flex items-start gap-5 animate-fade-in-up"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <span className="text-3xl font-extrabold text-ink-600 font-mono shrink-0">{p.n}</span>
              <div className="space-y-2 min-w-0">
                <div className="flex items-center gap-2">
                  <p.icon className="w-4 h-4 text-secondary-400 shrink-0" />
                  <h3 className="text-sm font-bold text-white">{p.title}</h3>
                </div>
                <p className="text-xs text-muted font-mono leading-relaxed">{p.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="relative px-6 md:px-12 py-16 max-w-3xl mx-auto z-10 w-full">
        <div className="glass-card rounded-2xl p-10 text-center space-y-6 animate-fade-in-up">
          <div className="grid place-items-center w-14 h-14 mx-auto rounded-2xl bg-gradient-to-tr from-primary-600 to-primary-700 shadow-glow">
            <div className="bg-ink-950/40 w-full h-full rounded-xl grid place-items-center">
              <TerminalIcon className="w-7 h-7 text-white" />
            </div>
          </div>
          <h2 className="text-xl sm:text-2xl font-bold text-white">
            Ready to see it run?
          </h2>
          <p className="text-xs text-muted font-mono max-w-md mx-auto">
            Launch the workstation, give it an in-scope target, and watch the swarm observe,
            reason, act, and prove — with every finding backed by real evidence.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Link href="/" className="btn-primary !px-7 !py-3.5 text-sm hover:scale-[1.02]">
              <span>Open Workstation</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link href="/landing" className="btn-ghost !px-5 !py-3.5 text-sm border border-ink-700 hover:border-ink-600 font-mono">
              <span>Back to home</span>
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative mt-auto border-t border-ink-800/80 px-6 md:px-12 py-6 flex flex-col sm:flex-row items-center justify-between text-xs font-mono text-muted-dim gap-3 z-10">
        <div>SONIC-REDA Autonomous Workstation Core v1.3.0</div>
        <div className="flex items-center gap-4">
          <Link href="/landing" className="hover:text-slate-300 transition">Home</Link>
          <Link href="/about" className="hover:text-slate-300 transition">About</Link>
          <Link href="/login" className="hover:text-slate-300 transition">Login</Link>
          <Link href="/" className="hover:text-slate-300 transition">Workstation</Link>
        </div>
      </footer>
    </div>
  );
}
