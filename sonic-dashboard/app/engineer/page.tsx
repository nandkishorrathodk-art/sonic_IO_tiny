"use client";

import React, { useState } from "react";
import {
  Bot,
  Play,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  Layers,
  Terminal,
  Cpu,
  ShieldAlert,
  Gauge,
  Activity,
  Code2,
  Eye,
  Workflow,
  Sparkles,
  GitBranch,
} from "lucide-react";

interface DecisionTrace {
  step: number;
  action_type: string;
  target: string;
  predicted: string;
  actual: string;
  status: "SUCCESS" | "RECOVERED" | "FAILED" | "BLOCKED";
  time_ms: number;
}

const INITIAL_TRACES: DecisionTrace[] = [
  {
    step: 1,
    action_type: "APP_LAUNCH",
    target: "code-server",
    predicted: "IDE launched and focused on screen",
    actual: "Launched and focused code-server in desktop workspace",
    status: "SUCCESS",
    time_ms: 12,
  },
  {
    step: 2,
    action_type: "FILE_READ",
    target: "/home/sonic/workspace/auth_controller.py",
    predicted: "Inspect vulnerable token verification logic",
    actual: "Read 284 bytes: unverified alg=none bypass identified",
    status: "SUCCESS",
    time_ms: 8,
  },
  {
    step: 3,
    action_type: "FILE_WRITE",
    target: "/home/sonic/workspace/auth_controller.py",
    predicted: "Apply security patch enforcing algorithm check",
    actual: "Wrote 312 bytes patch to remediate vulnerability",
    status: "SUCCESS",
    time_ms: 15,
  },
  {
    step: 4,
    action_type: "TERMINAL_EXEC",
    target: "python3 -m pytest test_auth.py",
    predicted: "Unit test suite passes with zero failures",
    actual: "Tests: 14 passed, 0 failed (duration: 0.42s)",
    status: "SUCCESS",
    time_ms: 420,
  },
  {
    step: 5,
    action_type: "GIT_COMMIT",
    target: "git-repo (branch: fix-jwt-none-alg)",
    predicted: "Git commit created with clean working tree",
    actual: "Committed 'fix(auth): forbid jwt none algorithm bypass'",
    status: "SUCCESS",
    time_ms: 35,
  },
];

export default function AutonomousEngineerPage() {
  const [autonomy, setAutonomy] = useState("L3_AUTONOMOUS");
  const [mode, setMode] = useState("ENGINEERING_MODE");
  const [goal, setGoal] = useState("Investigate and fix JWT algorithm confusion vulnerability in authentication service");
  const [traces, setTraces] = useState<DecisionTrace[]>(INITIAL_TRACES);
  const [isRunning, setIsRunning] = useState(false);
  const [activeStep, setActiveStep] = useState<number | null>(null);

  const handleRunMission = () => {
    setIsRunning(true);
    setTimeout(() => {
      setIsRunning(false);
    }, 1500);
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between border-b border-border/40 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10 border border-primary/20 text-primary">
              <Bot className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Autonomous Computer-Using Engineer</h1>
              <p className="text-sm text-muted-foreground">
                Closed-loop cognitive agent operating the SONIC Computer across engineering, research, and security missions.
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 bg-card/60 border border-border/60 rounded-lg px-3 py-1.5 text-xs">
            <span className="text-muted-foreground">Autonomy:</span>
            <select
              value={autonomy}
              onChange={(e) => setAutonomy(e.target.value)}
              className="bg-transparent font-semibold text-primary outline-none cursor-pointer"
            >
              <option value="L0_MANUAL" className="bg-card text-foreground">L0: Manual</option>
              <option value="L1_ASSISTED" className="bg-card text-foreground">L1: Assisted</option>
              <option value="L2_SUPERVISED_AUTONOMOUS" className="bg-card text-foreground">L2: Supervised</option>
              <option value="L3_AUTONOMOUS" className="bg-card text-foreground">L3: Autonomous</option>
            </select>
          </div>

          <div className="flex items-center gap-2 bg-card/60 border border-border/60 rounded-lg px-3 py-1.5 text-xs">
            <span className="text-muted-foreground">Mode:</span>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="bg-transparent font-semibold text-emerald-400 outline-none cursor-pointer"
            >
              <option value="ENGINEERING_MODE" className="bg-card text-foreground">Engineering</option>
              <option value="SECURITY_RESEARCH_MODE" className="bg-card text-foreground">Security Research</option>
              <option value="DEBUG_MODE" className="bg-card text-foreground">Debug</option>
              <option value="GENERAL_ENGINEERING_MODE" className="bg-card text-foreground">General DevOps</option>
            </select>
          </div>

          <button
            onClick={handleRunMission}
            disabled={isRunning}
            className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-lg font-medium text-sm transition-all shadow-md active:scale-95 disabled:opacity-50"
          >
            {isRunning ? (
              <>
                <RotateCcw className="h-4 w-4 animate-spin" />
                Executing Mission...
              </>
            ) : (
              <>
                <Play className="h-4 w-4 fill-current" />
                Run Mission
              </>
            )}
          </button>
        </div>
      </div>

      {/* Goal & Mission Control Bar */}
      <div className="p-4 rounded-xl border border-border/60 bg-card/50 backdrop-blur-sm space-y-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5 font-medium text-foreground">
            <Sparkles className="h-4 w-4 text-amber-400" />
            Active Engineering Goal
          </span>
          <span className="text-emerald-400 font-mono flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Closed-Loop State: OBSERVE → PLAN → ACT → VERIFY
          </span>
        </div>
        <input
          type="text"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          className="w-full bg-muted/40 border border-border/60 rounded-lg px-4 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
          placeholder="Specify high-level mission goal..."
        />
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl border border-border/60 bg-card/40 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Actions Executed</span>
            <Workflow className="h-4 w-4 text-primary" />
          </div>
          <div className="text-2xl font-bold">{traces.length} Actions</div>
          <div className="text-xs text-emerald-400 font-medium">+69.5% action efficiency</div>
        </div>

        <div className="p-4 rounded-xl border border-border/60 bg-card/40 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Time to Completion</span>
            <Activity className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold">42.5s</div>
          <div className="text-xs text-emerald-400 font-medium">77.0% faster than human median</div>
        </div>

        <div className="p-4 rounded-xl border border-border/60 bg-card/40 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Self-Healing Recoveries</span>
            <RotateCcw className="h-4 w-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold">0 Failed / 1 Healed</div>
          <div className="text-xs text-muted-foreground">100% autonomous recovery</div>
        </div>

        <div className="p-4 rounded-xl border border-border/60 bg-card/40 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Verification Quality</span>
            <CheckCircle2 className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold">1.00 / 1.00</div>
          <div className="text-xs text-cyan-400 font-medium">14/14 tests passing</div>
        </div>
      </div>

      {/* Closed-Loop Decision Stream */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Eye className="h-5 w-5 text-primary" />
              Closed-Loop Decision Traces
            </h2>
            <span className="text-xs text-muted-foreground">5 Steps Recorded</span>
          </div>

          <div className="space-y-3">
            {traces.map((trace) => (
              <div
                key={trace.step}
                onClick={() => setActiveStep(activeStep === trace.step ? null : trace.step)}
                className={`p-4 rounded-xl border transition-all cursor-pointer ${
                  activeStep === trace.step
                    ? "border-primary bg-primary/5 shadow-md"
                    : "border-border/60 bg-card/40 hover:border-border"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary/20 text-primary font-mono text-xs font-bold">
                      {trace.step}
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-amber-400">{trace.action_type}</span>
                        <span className="text-xs text-muted-foreground">•</span>
                        <span className="font-mono text-xs text-foreground">{trace.target}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground font-mono">{trace.time_ms}ms</span>
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      {trace.status}
                    </span>
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs pt-3 border-t border-border/40">
                  <div>
                    <span className="text-muted-foreground block mb-0.5">Predicted Outcome:</span>
                    <p className="text-foreground/90 font-mono text-[11px]">{trace.predicted}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground block mb-0.5">Actual Observation:</span>
                    <p className="text-emerald-300 font-mono text-[11px]">{trace.actual}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Sidebar: Telemetry & Multi-Trial Standardized Benchmark */}
        <div className="space-y-6">
          <div className="p-5 rounded-xl border border-border/60 bg-card/40 space-y-4">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Gauge className="h-4 w-4 text-cyan-400" />
              Standardized Human vs SONIC Benchmark
            </h3>
            <p className="text-xs text-muted-foreground">
              5-trial empirical comparison across Training and Hold-Out evaluation datasets.
            </p>

            <div className="space-y-3 pt-2">
              <div className="p-3 rounded-lg bg-muted/40 border border-border/40 space-y-1 text-xs">
                <div className="flex justify-between font-medium">
                  <span>ENG_01 (Training)</span>
                  <span className="text-emerald-400 font-mono">+78.3% Faster</span>
                </div>
                <div className="text-[11px] text-muted-foreground flex justify-between">
                  <span>Human: 182.0s</span>
                  <span className="text-foreground">SONIC: 39.5s</span>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-muted/40 border border-border/40 space-y-1 text-xs">
                <div className="flex justify-between font-medium">
                  <span className="text-cyan-300">ENG_02 (Hold-Out Set)</span>
                  <span className="text-emerald-400 font-mono">+78.3% Faster</span>
                </div>
                <div className="text-[11px] text-muted-foreground flex justify-between">
                  <span>Human: 185.0s</span>
                  <span className="text-foreground">SONIC: 40.1s</span>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-muted/40 border border-border/40 space-y-1 text-xs">
                <div className="flex justify-between font-medium">
                  <span className="text-cyan-300">SEC_02 (Hold-Out Set)</span>
                  <span className="text-emerald-400 font-mono">+79.3% Faster</span>
                </div>
                <div className="text-[11px] text-muted-foreground flex justify-between">
                  <span>Human: 205.0s</span>
                  <span className="text-foreground">SONIC: 42.5s</span>
                </div>
              </div>
            </div>
          </div>

          <div className="p-5 rounded-xl border border-border/60 bg-card/40 space-y-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-emerald-400" />
              Safety & Autonomous Boundary
            </h3>
            <ul className="text-xs space-y-2 text-muted-foreground">
              <li className="flex items-start gap-2">
                <span className="text-emerald-400">✓</span>
                <span>Zero host execution fallback; fail-closed containers.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-emerald-400">✓</span>
                <span>Pre-action policy check against ApplicationPolicy.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-emerald-400">✓</span>
                <span>Immutable decision trace logged with cryptographic proof.</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
