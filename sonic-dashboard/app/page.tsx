"use client";

import React, { useState, useEffect } from "react";
import {
  Monitor,
  Terminal,
  Code2,
  Brain,
  ShieldCheck,
  FileCheck2,
  Dna,
  Play,
  Pause,
  RotateCcw,
  GitBranch,
  GitPullRequest,
  CheckCircle2,
  AlertCircle,
  Clock,
  Cpu,
  Layers,
  Send,
  Sparkles,
  ChevronRight,
  ChevronDown,
  Folder,
  FileCode,
  Globe,
  Maximize2,
  Minimize2,
  ExternalLink,
  ShieldAlert,
  Search,
  Plus,
  Compass,
  ArrowUpRight,
  Database,
  Lock,
  TerminalSquare
} from "lucide-react";

export default function SonicWorkstation() {
  const [activeTab, setActiveTab] = useState<"computer" | "worklog" | "code" | "research" | "security" | "evidence" | "evolution">("computer");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [missionStatus, setMissionStatus] = useState<"RUNNING" | "PAUSED" | "COMPLETED">("RUNNING");
  const [objectiveInput, setObjectiveInput] = useState("");
  const [currentMission, setCurrentMission] = useState({
    id: "mission-prod-109",
    title: "Investigate & Remediate Token Replay Vulnerability in Auth Subsystem",
    target: "github.com/nandkishorrathodk-art/sonic",
    branch: "feat/fix-token-replay-guard",
    autonomyLevel: "L4 Autonomous Mission Owner",
    activeComputer: "Docker Sandbox (Ubuntu 22.04 / PTY + IDE)",
    elapsedSeconds: 274,
    currentStep: 4,
    totalSteps: 6,
    currentAction: "Running automated regression tests in sandbox container terminal...",
    currentResult: "All 8 cryptographic replay test fixtures passed (0 failures).",
  });

  const [timer, setTimer] = useState(274);

  useEffect(() => {
    let interval: any = null;
    if (missionStatus === "RUNNING") {
      interval = setInterval(() => {
        setTimer((prev) => prev + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [missionStatus]);

  const formatTime = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const remainingSecs = secs % 60;
    return `${mins.toString().padStart(2, "0")}:${remainingSecs.toString().padStart(2, "0")}`;
  };

  const sessions = [
    {
      id: "mission-prod-109",
      title: "Fix Token Replay Flaw in Auth",
      status: "RUNNING",
      branch: "feat/fix-token-replay-guard",
      time: "Active now",
      domain: "Security / Bug Fix",
    },
    {
      id: "mission-prod-108",
      title: "Resolve Concurrency Race in Counter",
      status: "COMPLETED",
      branch: "feat/fix-concurrency-race",
      time: "15m ago",
      domain: "Concurrency",
    },
    {
      id: "mission-prod-107",
      title: "Continuous Self-Dev Cycle (v1 -> v2)",
      status: "COMPLETED",
      branch: "feat/gen-1-stream-buffer",
      time: "1h ago",
      domain: "Self-Evolution",
    },
    {
      id: "mission-prod-106",
      title: "Unprompted RouterTable Optimization",
      status: "COMPLETED",
      branch: "perf/hashmap-router",
      time: "3h ago",
      domain: "Performance (+98.1%)",
    },
  ];

  const worklogEvents = [
    {
      time: "00:00:12",
      type: "OBSERVE",
      icon: <Monitor className="w-3.5 h-3.5 text-blue-400" />,
      title: "Spawned Isolated Mission Computer Workspace",
      detail: "Initialized Docker sandbox with virtual desktop, PTY terminal, and code-server environment.",
    },
    {
      time: "00:01:05",
      type: "RESEARCH",
      icon: <Brain className="w-3.5 h-3.5 text-purple-400" />,
      title: "Formulated Vulnerability Hypothesis #1",
      detail: "Suspect `TokenValidator` lacks nonce deduplication cache, permitting replay of valid signature payloads.",
    },
    {
      time: "00:02:18",
      type: "CODE",
      icon: <Code2 className="w-3.5 h-3.5 text-cyan-400" />,
      title: "Checked out Git Branch `feat/fix-token-replay-guard`",
      detail: "Opened `sonic-core/sonic/production_gate/scenario_matrix.py` in workspace IDE.",
    },
    {
      time: "00:03:10",
      type: "MUTATE",
      icon: <Sparkles className="w-3.5 h-3.5 text-amber-400" />,
      title: "Applied Source Code Patch to `TokenValidator`",
      detail: "Added thread-safe `_seen_nonces` set with TTL eviction and duplicate rejection.",
    },
    {
      time: "00:04:12",
      type: "VERIFY",
      icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />,
      title: "Executed Sandbox Regression Test Suite",
      detail: "Running `python -m pytest tests/test_phase19/ -v` inside sandbox PTY terminal. 4/4 passed.",
    },
  ];

  const handleQuickAction = (actionText: string) => {
    setObjectiveInput(actionText);
  };

  const handleStartMission = (e: React.FormEvent) => {
    e.preventDefault();
    if (!objectiveInput.trim()) return;
    setCurrentMission((prev) => ({
      ...prev,
      title: objectiveInput,
      elapsedSeconds: 0,
      currentStep: 1,
      currentAction: "Initializing new mission workspace and analyzing repository architecture...",
    }));
    setTimer(0);
    setMissionStatus("RUNNING");
    setActiveTab("computer");
    setObjectiveInput("");
  };

  return (
    <div className="flex h-screen w-screen bg-[#0A0C10] text-slate-200 overflow-hidden font-sans">
      {/* LEFT SESSIONS SIDEBAR */}
      <aside
        className={`${
          sidebarOpen ? "w-72" : "w-0"
        } transition-all duration-300 ease-in-out border-r border-slate-800/80 bg-[#0D1017] flex flex-col flex-shrink-0 z-20 overflow-hidden`}
      >
        {/* Workspace Brand Header */}
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-md bg-blue-600/20 border border-blue-500/50 flex items-center justify-center text-blue-400 font-bold text-xs tracking-wider">
              SN
            </div>
            <div>
              <h1 className="font-bold text-xs tracking-wide text-white uppercase">SONIC Workstation</h1>
              <p className="text-[10px] text-slate-400 font-mono">Autonomous AI Engineer</p>
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition"
            title="Collapse Sidebar"
          >
            <ChevronRight className="w-4 h-4 rotate-180" />
          </button>
        </div>

        {/* New Mission Button */}
        <div className="p-3">
          <button
            onClick={() => handleQuickAction("Fix repository issue autonomously and open Pull Request")}
            className="w-full py-2 px-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs flex items-center justify-center gap-2 shadow-lg shadow-blue-900/30 transition duration-150"
          >
            <Plus className="w-4 h-4" />
            <span>New Mission</span>
          </button>
        </div>

        {/* Sessions List */}
        <div className="flex-1 overflow-y-auto px-3 space-y-1 py-1">
          <div className="text-[10px] font-mono tracking-wider text-slate-400 uppercase px-2 py-1">
            Active Mission
          </div>
          <div className="p-3 rounded-lg bg-blue-950/30 border border-blue-600/40 shadow-sm space-y-2 cursor-pointer">
            <div className="flex items-center justify-between text-[10px] font-mono">
              <span className="flex items-center gap-1.5 text-blue-400 font-semibold">
                <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse"></span>
                ACTIVE
              </span>
              <span className="text-slate-400">{formatTime(timer)}</span>
            </div>
            <div className="font-semibold text-xs text-white leading-snug line-clamp-2">
              {currentMission.title}
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono">
              <GitBranch className="w-3 h-3 text-cyan-400" />
              <span className="truncate">{currentMission.branch}</span>
            </div>
          </div>

          <div className="text-[10px] font-mono tracking-wider text-slate-400 uppercase px-2 pt-4 pb-1">
            Recent Missions
          </div>
          {sessions.slice(1).map((s) => (
            <div
              key={s.id}
              className="p-2.5 rounded-lg hover:bg-slate-800/50 border border-transparent hover:border-slate-800 transition cursor-pointer space-y-1 group"
            >
              <div className="flex items-center justify-between text-[10px] font-mono">
                <span className="text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-2.5 h-2.5" />
                  DONE
                </span>
                <span className="text-slate-400">{s.time}</span>
              </div>
              <div className="text-xs font-medium text-slate-300 group-hover:text-white line-clamp-1">
                {s.title}
              </div>
              <div className="text-[10px] text-slate-400 font-mono truncate">{s.domain}</div>
            </div>
          ))}
        </div>

        {/* Runtime Environment Context */}
        <div className="p-3 border-t border-slate-800/80 bg-[#0A0C10] space-y-2 text-[11px]">
          <div className="flex items-center justify-between text-slate-400">
            <span className="flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-purple-400" />
              Engine
            </span>
            <span className="font-mono text-slate-200">Claude 3.7 / Grok</span>
          </div>
          <div className="flex items-center justify-between text-slate-400">
            <span className="flex items-center gap-1.5">
              <Lock className="w-3.5 h-3.5 text-emerald-400" />
              Safety Gate
            </span>
            <span className="font-mono text-emerald-400 font-bold">FAIL-CLOSED</span>
          </div>
        </div>
      </aside>

      {/* MAIN WORKSPACE VIEWPORT */}
      <main className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        {/* TOP MISSION HEADER BAR */}
        <header className="h-14 border-b border-slate-800/80 bg-[#0D1017] px-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-3 min-w-0">
            {!sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(true)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
                title="Expand Sidebar"
              >
                <Layers className="w-4 h-4" />
              </button>
            )}
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-white truncate max-w-xl">
                  {currentMission.title}
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-blue-950/80 text-blue-400 border border-blue-800/60 font-semibold flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse"></span>
                  {missionStatus}
                </span>
              </div>
              <div className="text-[11px] text-slate-400 font-mono flex items-center gap-3">
                <span>Target: <strong className="text-slate-300">{currentMission.target}</strong></span>
                <span>•</span>
                <span>Branch: <strong className="text-cyan-400">{currentMission.branch}</strong></span>
                <span>•</span>
                <span>Time: <strong className="text-slate-200">{formatTime(timer)}</strong></span>
              </div>
            </div>
          </div>

          {/* Mission Control Buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setMissionStatus(missionStatus === "RUNNING" ? "PAUSED" : "RUNNING")}
              className="py-1.5 px-3 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-xs font-semibold text-slate-200 flex items-center gap-1.5 transition"
            >
              {missionStatus === "RUNNING" ? (
                <>
                  <Pause className="w-3.5 h-3.5 text-amber-400" />
                  <span>Pause</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Resume</span>
                </>
              )}
            </button>
            <button
              onClick={() => setActiveTab("code")}
              className="py-1.5 px-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold flex items-center gap-1.5 transition shadow-sm"
            >
              <GitPullRequest className="w-3.5 h-3.5" />
              <span>Review PR</span>
            </button>
          </div>
        </header>

        {/* WORKSPACE NAVIGATION TABS */}
        <div className="h-11 border-b border-slate-800/80 bg-[#0A0C10] px-4 flex items-center justify-between text-xs">
          <div className="flex items-center gap-1 overflow-x-auto">
            <button
              onClick={() => setActiveTab("computer")}
              className={`px-3.5 py-2 rounded-t-md font-semibold flex items-center gap-2 border-b-2 transition ${
                activeTab === "computer"
                  ? "border-blue-500 text-white bg-slate-800/40"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/20"
              }`}
            >
              <Monitor className="w-4 h-4 text-blue-400" />
              <span>Live Computer</span>
            </button>

            <button
              onClick={() => setActiveTab("worklog")}
              className={`px-3.5 py-2 rounded-t-md font-semibold flex items-center gap-2 border-b-2 transition ${
                activeTab === "worklog"
                  ? "border-blue-500 text-white bg-slate-800/40"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/20"
              }`}
            >
              <TerminalSquare className="w-4 h-4 text-emerald-400" />
              <span>Worklog</span>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            </button>

            <button
              onClick={() => setActiveTab("code")}
              className={`px-3.5 py-2 rounded-t-md font-semibold flex items-center gap-2 border-b-2 transition ${
                activeTab === "code"
                  ? "border-blue-500 text-white bg-slate-800/40"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/20"
              }`}
            >
              <Code2 className="w-4 h-4 text-cyan-400" />
              <span>Code & Diff</span>
            </button>

            <button
              onClick={() => setActiveTab("research")}
              className={`px-3.5 py-2 rounded-t-md font-semibold flex items-center gap-2 border-b-2 transition ${
                activeTab === "research"
                  ? "border-blue-500 text-white bg-slate-800/40"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/20"
              }`}
            >
              <Brain className="w-4 h-4 text-purple-400" />
              <span>Research Lab</span>
            </button>

            <button
              onClick={() => setActiveTab("security")}
              className={`px-3.5 py-2 rounded-t-md font-semibold flex items-center gap-2 border-b-2 transition ${
                activeTab === "security"
                  ? "border-blue-500 text-white bg-slate-800/40"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/20"
              }`}
            >
              <ShieldCheck className="w-4 h-4 text-amber-400" />
              <span>Security & Scope</span>
            </button>

            <button
              onClick={() => setActiveTab("evidence")}
              className={`px-3.5 py-2 rounded-t-md font-semibold flex items-center gap-2 border-b-2 transition ${
                activeTab === "evidence"
                  ? "border-blue-500 text-white bg-slate-800/40"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/20"
              }`}
            >
              <FileCheck2 className="w-4 h-4 text-pink-400" />
              <span>Evidence Vault</span>
            </button>

            <button
              onClick={() => setActiveTab("evolution")}
              className={`px-3.5 py-2 rounded-t-md font-semibold flex items-center gap-2 border-b-2 transition ${
                activeTab === "evolution"
                  ? "border-blue-500 text-white bg-slate-800/40"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/20"
              }`}
            >
              <Dna className="w-4 h-4 text-indigo-400" />
              <span>Self-Evolution</span>
            </button>
          </div>

          <div className="text-[11px] font-mono text-slate-400 flex items-center gap-2">
            <span>Autonomy:</span>
            <span className="text-slate-200 font-semibold">L4 Full</span>
          </div>
        </div>

        {/* ACTIVE STAGE CONTENT AREA */}
        <div className="flex-1 min-h-0 bg-[#07090E] p-4 overflow-y-auto flex flex-col gap-3">
          {/* TAB 1: LIVE COMPUTER VIEW */}
          {activeTab === "computer" && (
            <div className="flex-1 flex flex-col rounded-xl border border-slate-800 bg-[#0B0E14] overflow-hidden shadow-2xl">
              {/* Virtual OS Window Topbar */}
              <div className="h-9 border-b border-slate-800 bg-[#10141D] px-3 flex items-center justify-between text-xs font-mono text-slate-400">
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-red-500/80 inline-block"></span>
                    <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/80 inline-block"></span>
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80 inline-block"></span>
                  </div>
                  <span className="text-slate-500">|</span>
                  <span className="text-slate-300 font-semibold flex items-center gap-1.5">
                    <Monitor className="w-3.5 h-3.5 text-blue-400" />
                    SONIC Mission Computer — Screen Display (1920x1080 @ 60Hz)
                  </span>
                </div>
                <div className="flex items-center gap-3 text-[11px]">
                  <span className="text-emerald-400 flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                    VNC Stream Live
                  </span>
                  <span>PTY #1 Active</span>
                </div>
              </div>

              {/* Virtual Computer Workspace Canvas */}
              <div className="flex-1 grid grid-cols-12 gap-3 p-3 bg-[#080A0F] overflow-hidden">
                {/* Left Pane: Embedded VS Code Editor */}
                <div className="col-span-7 rounded-lg border border-slate-800/90 bg-[#0D111A] flex flex-col overflow-hidden shadow-inner">
                  <div className="h-8 border-b border-slate-800 bg-[#121722] px-3 flex items-center justify-between text-xs font-mono text-slate-400">
                    <div className="flex items-center gap-2">
                      <FileCode className="w-3.5 h-3.5 text-cyan-400" />
                      <span className="text-slate-200">token_validator.py</span>
                      <span className="text-[10px] text-amber-400 bg-amber-950/60 px-1.5 rounded">Modified ●</span>
                    </div>
                    <span className="text-[10px] text-slate-400">Line 14:28</span>
                  </div>
                  <div className="flex-1 p-3 font-mono text-xs text-slate-300 overflow-y-auto leading-relaxed bg-[#0A0D14]">
                    <p className="text-slate-400"># SONIC Autonomous Patch for Replay Defense</p>
                    <p className="text-purple-400">class <span className="text-yellow-300">TokenValidator</span>:</p>
                    <p className="pl-4 text-blue-300">def <span className="text-yellow-300">__init__</span>(self):</p>
                    <p className="pl-8 text-emerald-400">self._seen_nonces = set()</p>
                    <p className="pl-8 text-emerald-400">self._max_cache = 10000</p>
                    <p className="mt-2 pl-4 text-blue-300">def <span className="text-yellow-300">validate</span>(self, nonce: str) -&gt; bool:</p>
                    <p className="pl-8 text-slate-400"># Autonomous anti-replay check</p>
                    <p className="pl-8 text-emerald-300 bg-emerald-950/30 border-l-2 border-emerald-500 py-0.5">if nonce in self._seen_nonces:</p>
                    <p className="pl-12 text-red-400 bg-red-950/20 py-0.5">return False</p>
                    <p className="pl-8 text-emerald-300 py-0.5">self._seen_nonces.add(nonce)</p>
                    <p className="pl-8 text-cyan-300">return True</p>
                  </div>
                </div>

                {/* Right Pane: Embedded Terminal & Browser Inspection */}
                <div className="col-span-5 flex flex-col gap-3">
                  {/* Top: Terminal Shell */}
                  <div className="flex-1 rounded-lg border border-slate-800 bg-[#090C12] flex flex-col overflow-hidden">
                    <div className="h-7 border-b border-slate-800 bg-[#121620] px-3 flex items-center justify-between text-[11px] font-mono text-slate-400">
                      <span className="flex items-center gap-1.5 text-slate-300">
                        <Terminal className="w-3.5 h-3.5 text-emerald-400" />
                        bash (sonic@sandbox: ~/workspace)
                      </span>
                      <span className="text-emerald-400 text-[10px]">exit: 0</span>
                    </div>
                    <div className="flex-1 p-2.5 font-mono text-[11px] text-slate-300 overflow-y-auto leading-tight space-y-1 bg-[#06080D]">
                      <p className="text-slate-400">$ python -m pytest tests/test_phase19/ -v</p>
                      <p className="text-slate-300">collected 4 items</p>
                      <p className="text-emerald-400">test_4_tier_reality_classification.py PASSED [ 25%]</p>
                      <p className="text-emerald-400">test_expanded_8_scenario_matrix.py PASSED [ 50%]</p>
                      <p className="text-emerald-400">test_independent_evaluator_harness.py PASSED [ 75%]</p>
                      <p className="text-emerald-400">test_temporal_post_hoc_holdout.py PASSED [100%]</p>
                      <p className="text-emerald-300 font-bold pt-1">================== 4 passed in 1.48s ==================</p>
                      <p className="text-cyan-400">$ git commit -m &quot;fix(crypto): prevent token replay attacks&quot;</p>
                      <p className="text-slate-400">[feat/fix-token-replay-guard c03a9b] commit verified.</p>
                    </div>
                  </div>

                  {/* Bottom: Browser / Target Observation Frame */}
                  <div className="h-44 rounded-lg border border-slate-800 bg-[#0D1017] flex flex-col overflow-hidden">
                    <div className="h-7 border-b border-slate-800 bg-[#121722] px-3 flex items-center justify-between text-[11px] font-mono text-slate-400">
                      <span className="flex items-center gap-1.5 text-slate-300">
                        <Globe className="w-3.5 h-3.5 text-blue-400" />
                        Chromium Headless: http://127.0.0.1:8000/auth/validate
                      </span>
                      <span className="text-blue-400 text-[10px]">HTTP 200 OK</span>
                    </div>
                    <div className="flex-1 p-2 flex items-center justify-center bg-[#07090E] text-center">
                      <div className="space-y-1">
                        <div className="w-8 h-8 rounded-full bg-emerald-600/20 border border-emerald-500/50 flex items-center justify-center mx-auto text-emerald-400">
                          <CheckCircle2 className="w-4 h-4" />
                        </div>
                        <p className="text-xs font-semibold text-white">Replay Attack Verification Blocked</p>
                        <p className="text-[10px] text-slate-400 font-mono">Payload HTTP 403: Duplicate nonce rejected.</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Real-Time Action Status Overlay Footer */}
              <div className="h-10 border-t border-slate-800 bg-[#0E121B] px-4 flex items-center justify-between text-xs">
                <div className="flex items-center gap-2 text-slate-300">
                  <span className="w-2 h-2 rounded-full bg-blue-400 animate-ping"></span>
                  <span className="font-semibold text-blue-400">SONIC Current Action:</span>
                  <span className="font-mono text-slate-200">{currentMission.currentAction}</span>
                </div>
                <div className="text-[11px] font-mono text-slate-400">
                  Step {currentMission.currentStep} of {currentMission.totalSteps} (66% complete)
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: CHRONOLOGICAL WORKLOG VIEW */}
          {activeTab === "worklog" && (
            <div className="flex-1 flex flex-col rounded-xl border border-slate-800 bg-[#0B0E14] overflow-hidden p-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div>
                  <h2 className="font-bold text-sm text-white">Mission Worklog & Auditable Action Stream</h2>
                  <p className="text-xs text-slate-400">Chronological decisions, perception events, tool calls, and test results.</p>
                </div>
                <span className="text-xs font-mono text-slate-400">{worklogEvents.length} Recorded Milestones</span>
              </div>

              <div className="flex-1 overflow-y-auto py-4 space-y-4">
                {worklogEvents.map((evt, idx) => (
                  <div key={idx} className="flex items-start gap-3 relative">
                    <div className="flex flex-col items-center">
                      <div className="w-7 h-7 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center flex-shrink-0">
                        {evt.icon}
                      </div>
                      {idx !== worklogEvents.length - 1 && (
                        <div className="w-px h-full bg-slate-800 my-1"></div>
                      )}
                    </div>
                    <div className="flex-1 p-3 rounded-lg border border-slate-800/80 bg-[#0E121A] space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-xs text-white">{evt.title}</span>
                        <span className="text-[10px] font-mono text-slate-400">{evt.time}</span>
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed">{evt.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 3: CODE & DIFF VIEW */}
          {activeTab === "code" && (
            <div className="flex-1 flex flex-col rounded-xl border border-slate-800 bg-[#0B0E14] overflow-hidden">
              <div className="h-10 border-b border-slate-800 bg-[#10141D] px-4 flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <GitPullRequest className="w-4 h-4 text-cyan-400" />
                  <span className="font-bold text-white">PR #109: Prevent Cryptographic Token Replay via Nonce Cache</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-emerald-400 font-mono">+12</span>
                  <span className="text-xs text-red-400 font-mono">-3</span>
                  <button className="py-1 px-3 rounded bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs ml-2">
                    Merge to main
                  </button>
                </div>
              </div>

              <div className="flex-1 grid grid-cols-12 overflow-hidden">
                {/* File Tree */}
                <div className="col-span-3 border-r border-slate-800 bg-[#090C12] p-3 text-xs font-mono space-y-1">
                  <div className="text-[10px] text-slate-400 uppercase font-bold px-2 py-1">Files Changed (1)</div>
                  <div className="p-2 rounded bg-blue-950/40 text-blue-300 border border-blue-800/40 flex items-center gap-2 cursor-pointer">
                    <FileCode className="w-3.5 h-3.5 text-cyan-400" />
                    <span className="truncate">token_validator.py</span>
                  </div>
                </div>

                {/* Diff Viewer */}
                <div className="col-span-9 bg-[#07090E] p-4 font-mono text-xs overflow-y-auto leading-relaxed">
                  <div className="text-slate-400 pb-2">@@ -10,8 +10,17 @@ class TokenValidator:</div>
                  <div className="text-slate-400">     def __init__(self):</div>
                  <div className="text-red-400 bg-red-950/30 px-2 py-0.5 border-l-2 border-red-500">-        pass</div>
                  <div className="text-emerald-400 bg-emerald-950/30 px-2 py-0.5 border-l-2 border-emerald-500">+        self._seen_nonces = set()</div>
                  <div className="text-emerald-400 bg-emerald-950/30 px-2 py-0.5 border-l-2 border-emerald-500">+        self._max_cache = 10000</div>
                  <div className="text-slate-400">     def validate(self, nonce: str) -&gt; bool:</div>
                  <div className="text-red-400 bg-red-950/30 px-2 py-0.5 border-l-2 border-red-500">-        return True</div>
                  <div className="text-emerald-400 bg-emerald-950/30 px-2 py-0.5 border-l-2 border-emerald-500">+        if nonce in self._seen_nonces:</div>
                  <div className="text-emerald-400 bg-emerald-950/30 px-2 py-0.5 border-l-2 border-emerald-500">+            return False</div>
                  <div className="text-emerald-400 bg-emerald-950/30 px-2 py-0.5 border-l-2 border-emerald-500">+        self._seen_nonces.add(nonce)</div>
                  <div className="text-emerald-400 bg-emerald-950/30 px-2 py-0.5 border-l-2 border-emerald-500">+        return True</div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: RESEARCH LAB */}
          {activeTab === "research" && (
            <div className="flex-1 grid grid-cols-2 gap-4">
              <div className="p-4 rounded-xl border border-slate-800 bg-[#0B0E14] space-y-3">
                <h3 className="font-bold text-sm text-white flex items-center gap-2">
                  <Brain className="w-4 h-4 text-purple-400" />
                  Active Hypotheses & Unknowns
                </h3>
                <div className="p-3 rounded-lg border border-purple-800/40 bg-purple-950/20 space-y-1.5">
                  <div className="flex items-center justify-between text-xs font-semibold text-purple-300">
                    <span>H-01: Replay Flaw via Stale Nonce</span>
                    <span className="text-emerald-400">96% Confirmed</span>
                  </div>
                  <p className="text-xs text-slate-300">Token validation function accepted duplicate JWT signatures without timestamp freshness check.</p>
                </div>
              </div>
              <div className="p-4 rounded-xl border border-slate-800 bg-[#0B0E14] space-y-3">
                <h3 className="font-bold text-sm text-white flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-cyan-400" />
                  Next Best Action Selected
                </h3>
                <div className="p-3 rounded-lg border border-cyan-800/40 bg-cyan-950/20 space-y-1">
                  <p className="text-xs font-semibold text-cyan-300">Run differential replay probe with identical cryptographic payload</p>
                  <p className="text-xs text-slate-400">Expected Information Gain: 0.94</p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: SECURITY & SCOPE */}
          {activeTab === "security" && (
            <div className="flex-1 p-4 rounded-xl border border-slate-800 bg-[#0B0E14] space-y-3">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-amber-400" />
                Security Invariants & Verified Findings
              </h3>
              <div className="grid grid-cols-3 gap-3">
                <div className="p-3 rounded-lg border border-slate-800 bg-[#0E121A]">
                  <div className="text-[10px] text-slate-400 uppercase font-mono">Fail-Closed Boundary</div>
                  <div className="text-sm font-bold text-emerald-400">LOCKED (Exit 126)</div>
                </div>
                <div className="p-3 rounded-lg border border-slate-800 bg-[#0E121A]">
                  <div className="text-[10px] text-slate-400 uppercase font-mono">Scope Target</div>
                  <div className="text-sm font-bold text-slate-200 truncate">github.com/nandkishorrathodk-art/sonic</div>
                </div>
                <div className="p-3 rounded-lg border border-slate-800 bg-[#0E121A]">
                  <div className="text-[10px] text-slate-400 uppercase font-mono">Cross-Tenant Isolation</div>
                  <div className="text-sm font-bold text-emerald-400">0 Leaks Detected</div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 6: EVIDENCE VAULT */}
          {activeTab === "evidence" && (
            <div className="flex-1 p-4 rounded-xl border border-slate-800 bg-[#0B0E14] space-y-3">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <FileCheck2 className="w-4 h-4 text-pink-400" />
                Cryptographic Evidence Custody Vault
              </h3>
              <div className="p-3 rounded-lg border border-slate-800 bg-[#0E121A] space-y-1 font-mono text-xs">
                <div className="flex items-center justify-between text-slate-300">
                  <span>Artifact: replay_poc_stream.json</span>
                  <span className="text-pink-400 font-bold">SHA-256 Verified</span>
                </div>
                <p className="text-slate-400 text-[11px] truncate">Hash: 8c2e4f1a9b734892c9081e289f8c12a7812903ef8912389a</p>
              </div>
            </div>
          )}

          {/* TAB 7: SELF-EVOLUTION */}
          {activeTab === "evolution" && (
            <div className="flex-1 p-4 rounded-xl border border-slate-800 bg-[#0B0E14] space-y-3">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <Dna className="w-4 h-4 text-indigo-400" />
                Continuous Self-Development Lineage (v1 -&gt; v2 -&gt; v3)
              </h3>
              <div className="grid grid-cols-3 gap-3">
                <div className="p-3 rounded-lg border border-slate-800 bg-[#0E121A] space-y-1">
                  <div className="text-[10px] text-slate-400 font-mono">v1.0.0 (Base)</div>
                  <div className="text-xs font-bold text-slate-300">Standard Agent</div>
                </div>
                <div className="p-3 rounded-lg border border-indigo-800/60 bg-indigo-950/20 space-y-1">
                  <div className="text-[10px] text-indigo-400 font-mono">v2.0.0 (Promoted)</div>
                  <div className="text-xs font-bold text-white">+ Buffer Optimization</div>
                </div>
                <div className="p-3 rounded-lg border border-emerald-800/60 bg-emerald-950/20 space-y-1">
                  <div className="text-[10px] text-emerald-400 font-mono">v3.0.0 (Active)</div>
                  <div className="text-xs font-bold text-emerald-300">+ Query Cache Indexing</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* BOTTOM FULL-WIDTH AGENT OBJECTIVE INPUT BAR */}
        <div className="border-t border-slate-800/80 bg-[#0D1017] p-3 space-y-2">
          {/* Fast Action Chips */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
            <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-blue-400" />
              Quick Mission:
            </span>
            <button
              onClick={() => handleQuickAction("Fix concurrency race condition in counter module and verify tests")}
              className="px-2.5 py-1 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition whitespace-nowrap"
            >
              ⚡ Fix Concurrency Bug
            </button>
            <button
              onClick={() => handleQuickAction("Investigate API token authentication flaws and verify PoC")}
              className="px-2.5 py-1 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition whitespace-nowrap"
            >
              🔍 Security Investigation
            </button>
            <button
              onClick={() => handleQuickAction("Run continuous self-development loop on repository (v1 -> v2 -> v3)")}
              className="px-2.5 py-1 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition whitespace-nowrap"
            >
              🚀 Run Self-Evolution
            </button>
            <button
              onClick={() => handleQuickAction("Improve this system.")}
              className="px-2.5 py-1 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition whitespace-nowrap"
            >
              🌐 Unprompted Optimization
            </button>
          </div>

          {/* Main Input Bar */}
          <form onSubmit={handleStartMission} className="flex items-center gap-2">
            <div className="flex-1 relative flex items-center">
              <input
                type="text"
                value={objectiveInput}
                onChange={(e) => setObjectiveInput(e.target.value)}
                placeholder="Tell SONIC what you want accomplished (e.g. 'Investigate auth subsystem, fix vulnerabilities, and create PR')..."
                className="w-full py-2.5 pl-4 pr-10 rounded-lg bg-[#090C12] border border-slate-700/80 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 text-xs text-white placeholder-slate-400 outline-none transition"
              />
            </div>
            <button
              type="submit"
              disabled={!objectiveInput.trim()}
              className="py-2.5 px-5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:hover:bg-blue-600 text-white font-semibold text-xs flex items-center gap-1.5 shadow-md transition"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Send Objective</span>
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
