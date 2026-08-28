"use client";

import React, { useState } from "react";
import {
  Compass,
  Play,
  Pause,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  Layers,
  Terminal,
  Cpu,
  ShieldCheck,
  Gauge,
  Activity,
  Code2,
  Eye,
  GitBranch,
  Sparkles,
  DollarSign,
  FileCheck2,
  Workflow,
  Clock,
  ListOrdered,
} from "lucide-react";

interface Milestone {
  id: string;
  name: string;
  status: "COMPLETED" | "ACTIVE" | "PENDING";
  progress: number;
}

const PHASES = [
  "DISCOVERY",
  "UNDERSTANDING",
  "RESEARCH",
  "ENGINEERING",
  "VERIFICATION",
  "REPORTING",
  "COMPLETED",
];

const INITIAL_MILESTONES: Milestone[] = [
  {
    id: "m1",
    name: "1. Repository & Defect Inspection",
    status: "COMPLETED",
    progress: 100,
  },
  {
    id: "m2",
    name: "2. Remediation & Unit Test Validation",
    status: "COMPLETED",
    progress: 100,
  },
  {
    id: "m3",
    name: "3. Git Commit & Deliverable Finalization",
    status: "COMPLETED",
    progress: 100,
  },
];

export default function LongHorizonMissionsPage() {
  const [currentPhaseIndex, setCurrentPhaseIndex] = useState(6); // COMPLETED
  const [missionStatus, setMissionStatus] = useState<"ACTIVE" | "PAUSED" | "COMPLETED">("COMPLETED");
  const [milestones] = useState<Milestone[]>(INITIAL_MILESTONES);
  const [activeMissionId] = useState("msn-84f9a120");

  const togglePause = () => {
    if (missionStatus === "ACTIVE") {
      setMissionStatus("PAUSED");
    } else if (missionStatus === "PAUSED") {
      setMissionStatus("ACTIVE");
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between border-b border-border/40 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
              <Compass className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight">Autonomous Mission Owner</h1>
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                  {activeMissionId}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                Top-level autonomous mission controller decomposing high-level objectives into long-horizon research and engineering.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={togglePause}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all shadow-md active:scale-95 ${
              missionStatus === "PAUSED"
                ? "bg-emerald-600 hover:bg-emerald-500 text-white"
                : "bg-amber-600/80 hover:bg-amber-500 text-white"
            }`}
          >
            {missionStatus === "PAUSED" ? (
              <>
                <Play className="h-4 w-4 fill-current" />
                Resume Mission
              </>
            ) : (
              <>
                <Pause className="h-4 w-4 fill-current" />
                Pause Mission
              </>
            )}
          </button>
        </div>
      </div>

      {/* Mission Phase Stepper */}
      <div className="p-4 rounded-xl border border-border/60 bg-card/40 backdrop-blur-sm space-y-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="font-semibold text-foreground flex items-center gap-1.5">
            <Workflow className="h-4 w-4 text-cyan-400" />
            Mission Lifecycle Progression
          </span>
          <span className="font-mono text-emerald-400 flex items-center gap-1">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Outcome: SUCCESS (Confidence: 1.00)
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2 pt-1">
          {PHASES.map((phase, idx) => {
            const isDone = idx <= currentPhaseIndex;
            const isCurrent = idx === currentPhaseIndex;
            return (
              <div
                key={phase}
                className={`p-2.5 rounded-lg border text-center text-xs font-mono transition-all ${
                  isCurrent
                    ? "border-emerald-500 bg-emerald-500/10 text-emerald-300 font-bold shadow-sm"
                    : isDone
                    ? "border-cyan-500/30 bg-cyan-500/5 text-cyan-400"
                    : "border-border/40 bg-muted/20 text-muted-foreground"
                }`}
              >
                <div className="text-[10px] text-muted-foreground">0{idx + 1}</div>
                <div className="truncate">{phase}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Telemetry Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl border border-border/60 bg-card/40 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Budget & Spending</span>
            <DollarSign className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold">$0.45 / $25.00</div>
          <div className="text-xs text-emerald-400 font-medium">$24.55 remaining budget</div>
        </div>

        <div className="p-4 rounded-xl border border-border/60 bg-card/40 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Time to Completion</span>
            <Clock className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold">79.0s</div>
          <div className="text-xs text-emerald-400 font-medium">+80.0% faster than human median</div>
        </div>

        <div className="p-4 rounded-xl border border-border/60 bg-card/40 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Sandbox Allocation</span>
            <Cpu className="h-4 w-4 text-primary" />
          </div>
          <div className="text-2xl font-bold">1 / 4 Sandboxes</div>
          <div className="text-xs text-muted-foreground">Isolated Mission Computer</div>
        </div>

        <div className="p-4 rounded-xl border border-border/60 bg-card/40 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Autonomy Score</span>
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold">100% (L3)</div>
          <div className="text-xs text-emerald-400 font-medium">Zero manual intervention required</div>
        </div>
      </div>

      {/* Main Grid: Multi-Track Board & Knowledge Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Milestones & Multi-Track Board */}
        <div className="lg:col-span-2 space-y-6">
          {/* Milestones */}
          <div className="p-5 rounded-xl border border-border/60 bg-card/40 space-y-4">
            <h2 className="text-base font-semibold flex items-center gap-2">
              <ListOrdered className="h-5 w-5 text-cyan-400" />
              Mission Milestones & Deliverable Verification
            </h2>

            <div className="space-y-3">
              {milestones.map((m) => (
                <div
                  key={m.id}
                  className="p-3.5 rounded-lg border border-border/60 bg-card/60 flex items-center justify-between"
                >
                  <div className="space-y-1">
                    <div className="text-sm font-medium text-foreground">{m.name}</div>
                    <div className="text-xs text-muted-foreground">Success conditions verified with evidence</div>
                  </div>
                  <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    {m.status} (100%)
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Validated Deliverables */}
          <div className="p-5 rounded-xl border border-border/60 bg-card/40 space-y-4">
            <h2 className="text-base font-semibold flex items-center gap-2">
              <FileCheck2 className="h-5 w-5 text-emerald-400" />
              Final Validated Deliverables
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-lg bg-muted/40 border border-border/60 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-amber-400">ENGINEERING_PATCH</span>
                  <span className="text-[11px] text-emerald-400 font-semibold">VALIDATED</span>
                </div>
                <div className="text-sm font-bold">Remediation Patch & Unit Tests</div>
                <p className="text-xs text-muted-foreground">
                  Applied security patch enforcing algorithm check; 14/14 unit tests passing.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-muted/40 border border-border/60 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-cyan-400">GIT_COMMIT</span>
                  <span className="text-[11px] text-emerald-400 font-semibold">VERIFIED</span>
                </div>
                <div className="text-sm font-bold">Commit 7b8e1f0a2c</div>
                <p className="text-xs text-muted-foreground">
                  Branch 'fix-jwt-none-alg' committed with signed evidence manifest.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Right Sidebar: Mission Knowledge Summary */}
        <div className="space-y-6">
          <div className="p-5 rounded-xl border border-border/60 bg-card/40 space-y-4">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-cyan-400" />
              Mission Knowledge Summary
            </h3>

            <div className="space-y-3 text-xs">
              <div className="p-3 rounded-lg bg-muted/30 border border-border/40 space-y-1">
                <span className="font-semibold text-emerald-400">What We Know:</span>
                <p className="text-muted-foreground text-[11px]">
                  Auth service accepted unverified alg=none; patch validated with 0 regression.
                </p>
              </div>

              <div className="p-3 rounded-lg bg-muted/30 border border-border/40 space-y-1">
                <span className="font-semibold text-cyan-300">Active Decisions:</span>
                <p className="text-muted-foreground text-[11px]">
                  Operated code-server IDE and container terminal; committed clean patch.
                </p>
              </div>

              <div className="p-3 rounded-lg bg-muted/30 border border-border/40 space-y-1">
                <span className="font-semibold text-primary">Next Best Action:</span>
                <p className="text-foreground text-[11px] font-mono">
                  Deliver validated security patch and Git commit to customer repository.
                </p>
              </div>
            </div>
          </div>

          {/* Standardized Benchmark Panel */}
          <div className="p-5 rounded-xl border border-border/60 bg-card/40 space-y-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Gauge className="h-4 w-4 text-yellow-400" />
              5-Trial Empirical Benchmark
            </h3>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-border/30">
                <span className="text-muted-foreground">MSN_ENG_01 (Training)</span>
                <span className="text-emerald-400 font-mono">+80.0% Faster</span>
              </div>
              <div className="flex justify-between py-1 border-b border-border/30">
                <span className="text-cyan-300">MSN_HOLDOUT_01 (Hold-Out)</span>
                <span className="text-emerald-400 font-mono">+81.0% Faster</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
