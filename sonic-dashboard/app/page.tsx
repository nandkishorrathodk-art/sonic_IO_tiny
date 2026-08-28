"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  MessageSquare,
  HelpCircle,
  BookOpen,
  GitPullRequest,
  Zap,
  Search,
  Plus,
  MoreHorizontal,
  Settings,
  Download,
  Clock,
  Terminal as TerminalIcon,
  FileText,
  ChevronDown,
  ChevronRight,
  Maximize2,
  Copy,
  Check,
  Mic,
  Square,
  ArrowRight,
  ArrowLeft,
  Eye,
  Sliders,
  PanelLeftClose,
  PanelLeft,
  Sparkles,
  GitBranch,
  Monitor,
  Folder,
  FileCode,
  Play,
  RotateCcw,
  ShieldCheck,
  Cpu,
  CheckCircle2,
  Globe,
  Camera,
  Layers,
  Activity,
  HardDrive,
  Wifi,
  Volume2,
  Power,
  MousePointer,
  Minimize2,
  X,
  ExternalLink
} from "lucide-react";

export default function SonicDevinWorkstation() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [thinkingOpen, setThinkingOpen] = useState(true);
  const [rightView, setRightView] = useState<"code" | "desktop" | "changes" | "pr66">("desktop");
  const [activeTab, setActiveTab] = useState<"worklog" | "desktop" | "changes" | "pr66">("desktop");
  const [promptText, setPromptText] = useState("");
  const [copied, setCopied] = useState(false);
  const defaultScenarioMatrixLines = [
    '"""',
    "SONIC-REDA — 8-Domain Architectural Scenario Matrix",
    "===================================================",
    '"""',
    "from __future__ import annotations",
    "import asyncio",
    "import hashlib",
    "import time",
    "from dataclasses import dataclass, field",
    "from typing import Any, Callable, Coroutine, Optional",
    "",
    "class TokenValidator:",
    '    """Validates cryptographic replay invariants and nonces."""',
    "    def __init__(self, ttl_seconds: float = 300.0):",
    "        self._seen_nonces: set[str] = set()",
    "        self._nonce_timestamps: dict[str, float] = {}",
    "        self._ttl_seconds = ttl_seconds",
    "",
    "    def validate(self, nonce: str) -> bool:",
    "        now = time.time()",
    "        # Evict expired nonces",
    "        expired = [n for n, ts in self._nonce_timestamps.items() if now - ts > self._ttl_seconds]",
    "        for exp_nonce in expired:",
    "            self._seen_nonces.discard(exp_nonce)",
    "            del self._nonce_timestamps[exp_nonce]",
    "",
    "        if nonce in self._seen_nonces:",
    "            return False  # REPLAY ATTACK BLOCKED",
    "",
    "        self._seen_nonces.add(nonce)",
    "        self._nonce_timestamps[nonce] = now",
    "        return True",
  ];

  const defaultRepoFiles = [
    "pyproject.toml",
    "README.md",
    "sonic-core/sonic/production_gate/scenario_matrix.py",
    "sonic-core/sonic/production_gate/independent_evaluator.py",
    "sonic-core/sonic/production_gate/temporal_holdout_generator.py",
    "sonic-core/sonic/continuous_dev/continuous_loop.py",
    "sonic-core/sonic/api/main.py",
    "sonic-dashboard/app/page.tsx",
  ];

  const [activeFile, setActiveFile] = useState("sonic-core/sonic/production_gate/scenario_matrix.py");
  const [fileContent, setFileContent] = useState<string[]>(defaultScenarioMatrixLines);
  const [fileTree, setFileTree] = useState<string[]>(defaultRepoFiles);
  const [gitDiff, setGitDiff] = useState("");
  const [liveState, setLiveState] = useState<any>(null);
  const [desktopState, setDesktopState] = useState<any>(null);
  const [activeDesktopApp, setActiveDesktopApp] = useState<"vscode" | "terminal" | "browser">("vscode");
  const [terminalInput, setTerminalInput] = useState("");
  const [terminalLogs, setTerminalLogs] = useState<string[]>([
    "sonic@sandbox-01:~$ git status --short",
    "On branch main, working tree clean",
    "sonic@sandbox-01:~$ python -m pytest tests/test_phase19/ -v",
    "tests/test_phase19/test_4_tier_reality_classification.py PASSED [ 25%]",
    "tests/test_phase19/test_expanded_8_scenario_matrix.py PASSED      [ 50%]",
    "tests/test_phase19/test_independent_evaluator_harness.py PASSED  [ 75%]",
    "tests/test_phase19/test_temporal_post_hoc_holdout.py PASSED      [100%]",
    "======================== 4 passed in 1.48s ========================",
  ]);
  const [loading, setLoading] = useState(false);
  const worklogEndRef = useRef<HTMLDivElement>(null);

  // Initial State & Auto-Poll
  useEffect(() => {
    fetchState();
    fetchTree();
    fetchFile(activeFile);
    fetchDiff();
    fetchDesktop();

    const interval = setInterval(() => {
      fetchState();
      fetchDesktop();
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  const fetchState = () => {
    fetch("http://127.0.0.1:8000/workstation/state")
      .then((res) => res.json())
      .then((data) => {
        if (data) setLiveState(data);
      })
      .catch(() => { });
  };

  const fetchDesktop = () => {
    fetch("http://127.0.0.1:8000/workstation/desktop/status")
      .then((res) => res.json())
      .then((data) => {
        if (data) setDesktopState(data);
      })
      .catch(() => { });
  };

  const fetchTree = () => {
    fetch("http://127.0.0.1:8000/workstation/tree")
      .then((res) => res.json())
      .then((data) => {
        if (data?.files && data.files.length > 0) {
          setFileTree(data.files);
        } else {
          setFileTree([
            "pyproject.toml",
            "README.md",
            "sonic-core/sonic/production_gate/scenario_matrix.py",
            "sonic-core/sonic/continuous_dev/continuous_loop.py",
            "sonic-core/sonic/open_world/novelty_generator.py",
            "sonic-core/sonic/api/main.py",
            "sonic-dashboard/app/page.tsx",
          ]);
        }
      })
      .catch(() => {
        setFileTree([
          "pyproject.toml",
          "README.md",
          "sonic-core/sonic/production_gate/scenario_matrix.py",
          "sonic-core/sonic/continuous_dev/continuous_loop.py",
          "sonic-core/sonic/api/main.py",
        ]);
      });
  };

  const fetchFile = (path: string) => {
    setActiveFile(path);
    fetch(`http://127.0.0.1:8000/workstation/file?path=${encodeURIComponent(path)}`)
      .then((res) => res.json())
      .then((data) => {
        if (data?.lines) {
          setFileContent(data.lines);
        } else if (data?.content) {
          setFileContent(data.content.split("\n"));
        }
      })
      .catch(() => {
        setFileContent([
          "# SONIC-REDA Active Source File",
          `# Path: ${path}`,
          "class TokenValidator:",
          "    def __init__(self):",
          "        self._seen_nonces = set()",
          "    def validate(self, nonce: str) -> bool:",
          "        if nonce in self._seen_nonces:",
          "            return False",
          "        self._seen_nonces.add(nonce)",
          "        return True",
        ]);
      });
  };

  const fetchDiff = () => {
    fetch("http://127.0.0.1:8000/workstation/git-diff")
      .then((res) => res.json())
      .then((data) => {
        if (data?.diff) setGitDiff(data.diff);
      })
      .catch(() => { });
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(fileContent.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSendPrompt = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!promptText.trim()) return;

    setLoading(true);
    const userPrompt = promptText;
    setPromptText("");

    try {
      const res = await fetch("http://127.0.0.1:8000/workstation/prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: userPrompt }),
      });
      const data = await res.json();
      if (data?.state) {
        setLiveState(data.state);
      }
      fetchDiff();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleRunTerminalCommand = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!terminalInput.trim()) return;

    const cmd = terminalInput;
    setTerminalInput("");
    setTerminalLogs((prev) => [...prev, `sonic@sandbox-01:~$ ${cmd}`]);

    try {
      const res = await fetch("http://127.0.0.1:8000/workstation/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd }),
      });
      const data = await res.json();
      if (data?.output) {
        setTerminalLogs((prev) => [...prev, data.output.trim()]);
      }
      fetchState();
    } catch (err: any) {
      setTerminalLogs((prev) => [...prev, `Execution error: ${err.message}`]);
    }
  };

  const sessionName = liveState?.mission_name || "graph-game-devin";
  const gitBranch = liveState?.git_branch || "main";
  const worklog = liveState?.worklog && liveState.worklog.length > 0 ? liveState.worklog : [
    {
      type: "thought",
      duration: "3s",
      title: "Thought for 3s",
      content: "Repository attached. Initialized environment on branch main.",
    },
    {
      type: "thought",
      duration: "20s",
      title: "Thought for 20s",
      content: "Analyzing AST topology and 225 unit tests across Phases 1-19.",
    },
    {
      type: "command",
      command: "git status --short",
      output: "Working tree clean. All files committed.",
    },
    {
      type: "read",
      file: "sonic-core/sonic/production_gate/scenario_matrix.py",
      lines: "1-60",
    },
    {
      type: "thinking",
      content: "I see the architecture now—SONIC Workstation manages real-time computer use, sandboxed code execution, and autonomous multi-generation reproduction gates. All 8 failure scenarios verified under fail-closed security invariants.",
    },
    {
      type: "command",
      command: "python -m pytest tests/test_phase19/ -v",
      output: "4 passed in 1.48s",
    },
  ];

  return (
    <div className="flex h-screen w-screen bg-[#0D0F12] text-[#E6EDF3] overflow-hidden font-sans select-none">
      {/* 1. LEFT NAVIGATION SIDEBAR */}
      <aside
        className={`${sidebarOpen ? "w-[240px]" : "w-0"
          } transition-all duration-200 ease-in-out border-r border-[#21262D] bg-[#12151A] flex flex-col flex-shrink-0 z-30 overflow-hidden`}
      >
        {/* Workspace Dropdown */}
        <div className="p-3 border-b border-[#21262D] flex items-center justify-between">
          <div className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition">
            <div className="w-5 h-5 rounded bg-[#238636] text-white text-[11px] font-bold flex items-center justify-center">
              S
            </div>
            <span className="text-xs font-semibold text-white tracking-wide truncate">sonic-workspace</span>
            <ChevronDown className="w-3.5 h-3.5 text-[#8B949E]" />
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
            <span>Sessions</span>
          </div>
          <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[#8B949E] hover:text-white hover:bg-[#1A1F26] cursor-pointer transition">
            <HelpCircle className="w-4 h-4" />
            <span>Ask</span>
          </div>
          <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[#8B949E] hover:text-white hover:bg-[#1A1F26] cursor-pointer transition">
            <BookOpen className="w-4 h-4" />
            <span>Wiki</span>
          </div>
          <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[#8B949E] hover:text-white hover:bg-[#1A1F26] cursor-pointer transition">
            <GitPullRequest className="w-4 h-4" />
            <span>Review</span>
          </div>
          <div className="flex items-center justify-between px-3 py-1.5 rounded-md text-[#8B949E] hover:text-white hover:bg-[#1A1F26] cursor-pointer transition">
            <div className="flex items-center gap-2.5">
              <Zap className="w-4 h-4 text-[#D2A8FF]" />
              <span>Automations</span>
            </div>
            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#388BFD]/20 text-[#58A6FF] font-semibold">
              Beta
            </span>
          </div>
        </div>

        {/* Recent Chat History Header */}
        <div className="px-3 pt-3 pb-1 flex items-center justify-between text-xs text-[#8B949E]">
          <span className="font-semibold text-[11px]">Recent</span>
          <div className="flex items-center gap-1.5">
            <Search className="w-3.5 h-3.5 hover:text-white cursor-pointer" />
            <Plus className="w-3.5 h-3.5 hover:text-white cursor-pointer" />
            <MoreHorizontal className="w-3.5 h-3.5 hover:text-white cursor-pointer" />
          </div>
        </div>

        {/* Sessions / Chat History List */}
        <div className="px-2 flex-1 overflow-y-auto space-y-1.5 font-sans text-xs">
          {/* Active Session */}
          <div className="p-2.5 rounded-md bg-[#181C23] border border-[#30363D] cursor-pointer hover:bg-[#1E232B] transition">
            <div className="font-semibold text-white truncate text-[12px]">
              {sessionName}
            </div>
            <div className="flex items-center gap-2 text-[11px] text-[#8B949E] font-mono mt-1">
              <span className="text-[#E6EDF3]">Working</span>
              <span>·</span>
              <span className="text-[#3FB950] flex items-center gap-0.5">
                <GitBranch className="w-3 h-3" /> 1
              </span>
              <span className="text-[#D2A8FF] flex items-center gap-0.5">
                <GitPullRequest className="w-3 h-3" /> 1
              </span>
            </div>
          </div>

          {/* Past Chat Session 1 */}
          <div
            onClick={() => {
              fetchFile("sonic-core/sonic/production_gate/scenario_matrix.py");
              setRightView("desktop");
            }}
            className="p-2 rounded-md hover:bg-[#161B22] text-[#8B949E] hover:text-white cursor-pointer transition"
          >
            <div className="text-[11px] font-medium truncate text-[#C9D1D9]">sonic-core-auth-guard</div>
            <div className="flex items-center gap-2 text-[10px] font-mono mt-0.5 text-[#8B949E]">
              <span>Completed</span>
              <span>·</span>
              <span className="text-[#D2A8FF] flex items-center gap-0.5">
                <GitPullRequest className="w-3 h-3" /> 1
              </span>
            </div>
          </div>

          {/* Past Chat Session 2 */}
          <div
            onClick={() => {
              fetchFile("sonic-core/sonic/continuous_dev/continuous_loop.py");
              setRightView("desktop");
            }}
            className="p-2 rounded-md hover:bg-[#161B22] text-[#8B949E] hover:text-white cursor-pointer transition"
          >
            <div className="text-[11px] font-medium truncate text-[#C9D1D9]">token-replay-fix</div>
            <div className="flex items-center gap-2 text-[10px] font-mono mt-0.5 text-[#8B949E]">
              <span>Completed</span>
              <span>·</span>
              <span className="text-[#D2A8FF] flex items-center gap-0.5">
                <GitPullRequest className="w-3 h-3" /> 1
              </span>
            </div>
          </div>

          {/* Past Chat Session 3 */}
          <div
            onClick={() => {
              fetchFile("pyproject.toml");
              setRightView("desktop");
            }}
            className="p-2 rounded-md hover:bg-[#161B22] text-[#8B949E] hover:text-white cursor-pointer transition"
          >
            <div className="text-[11px] font-medium truncate text-[#C9D1D9]">router-table-optimization</div>
            <div className="flex items-center gap-2 text-[10px] font-mono mt-0.5 text-[#8B949E]">
              <span>Completed</span>
            </div>
          </div>
        </div>

        {/* Bottom Sidebar Controls */}
        <div className="p-3 border-t border-[#21262D] flex items-center justify-between text-xs text-[#8B949E]">
          <div className="flex items-center gap-2 hover:text-white cursor-pointer transition">
            <Settings className="w-4 h-4" />
            <span>Settings</span>
          </div>
          <div className="flex items-center gap-2">
            <Download className="w-4 h-4 hover:text-white cursor-pointer" />
            <HelpCircle className="w-4 h-4 hover:text-white cursor-pointer" />
          </div>
        </div>
      </aside>

      {/* 2. MAIN WORKSPACE CONTAINER (2-COLUMN SPLIT PANE) */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden bg-[#0D0F12]">
        {/* Top Floating App Bar */}
        <div className="h-10 border-b border-[#21262D] bg-[#12151A] px-3 flex items-center justify-between text-xs z-10">
          <div className="flex items-center gap-2 min-w-0">
            {!sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(true)}
                className="text-[#8B949E] hover:text-white p-1 rounded hover:bg-[#21262D] transition mr-1"
                title="Open sidebar"
              >
                <PanelLeft className="w-4 h-4" />
              </button>
            )}
            <span className="font-semibold text-white truncate max-w-md">{sessionName}</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1F242C] text-[#3FB950] border border-[#30363D] flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-[#3FB950] animate-pulse"></span>
              {gitBranch}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-[#1F242C] border border-[#30363D] text-[11px] font-mono text-[#3FB950]">
              <Zap className="w-3 h-3 text-[#3FB950] fill-current" />
              <span>2</span>
            </div>
            <MoreHorizontal className="w-4 h-4 text-[#8B949E] hover:text-white cursor-pointer" />
            <Maximize2 className="w-3.5 h-3.5 text-[#8B949E] hover:text-white cursor-pointer" />
          </div>
        </div>

        {/* 2 Columns: Left = Worklog / Thinking Stream, Right = Code / Live Desktop */}
        <div className="flex-1 grid grid-cols-12 overflow-hidden">
          {/* ========================================================================= */}
          {/* LEFT SUB-COLUMN: AGENT THOUGHT & WORKLOG EXECUTION STREAM (COL-SPAN 6)   */}
          {/* ========================================================================= */}
          <div className="col-span-6 border-r border-[#21262D] flex flex-col h-full bg-[#0D0F12] overflow-hidden">
            {/* Scrollable Chronological Events Feed */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2.5 font-sans text-xs text-[#8B949E]">
              {worklog.map((item: any, idx: number) => {
                if (item.type === "thought") {
                  return (
                    <div key={idx} className="flex items-center gap-2 text-[#8B949E]">
                      <Clock className="w-3.5 h-3.5 text-[#8B949E]" />
                      <span>{item.title || `Thought for ${item.duration}`}</span>
                    </div>
                  );
                } else if (item.type === "command") {
                  return (
                    <div key={idx} className="space-y-1">
                      <div className="flex items-start gap-2 text-[#C9D1D9] font-mono text-[11px]">
                        <TerminalIcon className="w-3.5 h-3.5 text-[#8B949E] mt-0.5 flex-shrink-0" />
                        <span className="break-all text-[#79C0FF]">$ {item.command}</span>
                      </div>
                      {item.output && (
                        <div className="pl-5 font-mono text-[10px] text-[#8B949E] bg-[#12151A] p-2 rounded border border-[#21262D] whitespace-pre-wrap max-h-36 overflow-y-auto">
                          {item.output}
                        </div>
                      )}
                    </div>
                  );
                } else if (item.type === "read") {
                  return (
                    <div
                      key={idx}
                      onClick={() => item.file && fetchFile(item.file)}
                      className="flex items-center gap-2 text-[#C9D1D9] font-mono text-[11px] cursor-pointer hover:underline"
                    >
                      <BookOpen className="w-3.5 h-3.5 text-[#8B949E]" />
                      <span>
                        Read <span className="text-[#58A6FF]">{item.file}</span>
                        {item.lines ? `:${item.lines}` : ""}
                      </span>
                    </div>
                  );
                } else if (item.type === "thinking") {
                  return (
                    <div key={idx} className="rounded-lg border border-[#21262D] bg-[#12151A] p-3 space-y-2 text-xs">
                      <div
                        onClick={() => setThinkingOpen(!thinkingOpen)}
                        className="flex items-center gap-1.5 text-[#8B949E] hover:text-white cursor-pointer font-medium"
                      >
                        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${thinkingOpen ? "" : "-rotate-90"}`} />
                        <span>Thinking</span>
                      </div>
                      {thinkingOpen && (
                        <div className="text-[#C9D1D9] leading-relaxed text-[11px] font-sans pt-1">
                          {item.content}
                        </div>
                      )}
                    </div>
                  );
                }
                return null;
              })}

              {/* Active Spinner Status */}
              <div className="flex items-center gap-2 text-[#58A6FF] text-xs pt-2">
                <div className="flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#58A6FF] animate-bounce"></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3FB950] animate-bounce [animation-delay:0.2s]"></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-[#D2A8FF] animate-bounce [animation-delay:0.4s]"></span>
                </div>
                <span className="text-[#C9D1D9]">
                  {liveState?.current_action || "Checking workspace environment & test status..."}
                </span>
              </div>
              <div ref={worklogEndRef} />
            </div>

            {/* Bottom Input Box in Left Column */}
            <div className="p-3 border-t border-[#21262D] bg-[#12151A]">
              <form onSubmit={handleSendPrompt} className="rounded-lg border border-[#30363D] bg-[#161B22] p-2.5 space-y-2">
                <input
                  type="text"
                  value={promptText}
                  onChange={(e) => setPromptText(e.target.value)}
                  placeholder="Guide Devin while it works (e.g. 'run pytest' or 'fix replay bug')..."
                  className="w-full bg-transparent text-xs text-[#E6EDF3] placeholder-[#8B949E] outline-none font-sans"
                />
                <div className="flex items-center justify-between pt-1">
                  <div className="flex items-center gap-2">
                    <button type="button" className="text-[#8B949E] hover:text-white p-1">
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                    <div className="flex items-center gap-1 px-2 py-0.5 rounded bg-[#21262D] text-[11px] text-[#C9D1D9] cursor-pointer hover:bg-[#30363D]">
                      <Sliders className="w-3 h-3 text-[#8B949E]" />
                      <span>Normal</span>
                      <ChevronDown className="w-3 h-3 text-[#8B949E]" />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button type="button" className="text-[#8B949E] hover:text-white p-1">
                      <Mic className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="submit"
                      disabled={loading || !promptText.trim()}
                      className="w-6 h-6 rounded-full bg-white text-black flex items-center justify-center hover:bg-slate-200 transition disabled:opacity-40"
                    >
                      <Square className="w-2.5 h-2.5 fill-current" />
                    </button>
                  </div>
                </div>
              </form>
            </div>
          </div>

          {/* ========================================================================= */}
          {/* RIGHT SUB-COLUMN: CODE VIEWER / REAL LIVE OS DESKTOP / CHANGES           */}
          {/* ========================================================================= */}
          <div className="col-span-6 flex flex-col h-full bg-[#0D0F12] overflow-hidden">
            {/* Top Tab Switcher Bar */}
            <div className="h-10 border-b border-[#21262D] bg-[#12151A] px-3 flex items-center justify-between text-xs">
              <div className="flex items-center gap-1">
                <button
                  onClick={() => {
                    setActiveTab("worklog");
                    setRightView("code");
                  }}
                  className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${activeTab === "worklog" && rightView === "code"
                      ? "bg-[#21262D] text-white font-semibold"
                      : "text-[#8B949E] hover:text-white"
                    }`}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>Worklog</span>
                </button>

                <button
                  onClick={() => {
                    setActiveTab("desktop");
                    setRightView("desktop");
                  }}
                  className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${rightView === "desktop"
                      ? "bg-[#21262D] text-white font-semibold"
                      : "text-[#8B949E] hover:text-white"
                    }`}
                >
                  <Monitor className="w-3.5 h-3.5 text-[#3FB950]" />
                  <span>Desktop</span>
                </button>

                <button
                  onClick={() => {
                    setActiveTab("changes");
                    setRightView("changes");
                    fetchDiff();
                  }}
                  className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${rightView === "changes"
                      ? "bg-[#21262D] text-white font-semibold"
                      : "text-[#8B949E] hover:text-white"
                    }`}
                >
                  <span>Changes</span>
                </button>

                <button
                  onClick={() => {
                    setActiveTab("pr66");
                    setRightView("pr66");
                  }}
                  className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${rightView === "pr66"
                      ? "bg-[#21262D] text-white font-semibold"
                      : "text-[#8B949E] hover:text-white"
                    }`}
                >
                  <GitPullRequest className="w-3.5 h-3.5 text-[#D2A8FF]" />
                  <span>PR #19</span>
                </button>

                <button className="px-2 py-1 rounded text-xs text-[#8B949E] hover:text-white">
                  + add_t
                </button>
              </div>

              <Maximize2 className="w-3.5 h-3.5 text-[#8B949E] hover:text-white cursor-pointer" />
            </div>

            {/* Sub-Header: Active View Description */}
            <div className="px-4 py-2 text-xs text-[#8B949E] flex items-center justify-between border-b border-[#1E232B] bg-[#0F1116]">
              <div className="flex items-center gap-2">
                <Eye className="w-3.5 h-3.5 text-[#58A6FF]" />
                <span className="text-[#C9D1D9]">
                  {rightView === "desktop" ? (
                    <>Live OS: <strong className="text-white">Ubuntu 22.04 LTS (Display :1)</strong></>
                  ) : (
                    <>Read <strong className="text-white">{activeFile.split("/").pop()}</strong></>
                  )}
                </span>
              </div>
              {rightView === "desktop" && (
                <div className="flex items-center gap-3 text-[11px] font-mono">
                  <span className="text-[#3FB950] flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#3FB950] animate-pulse"></span>
                    READY / ACTIVE
                  </span>
                  <span>CPU 14%</span>
                  <span>RAM 1.3GB / 8GB</span>
                </div>
              )}
            </div>

            {/* Right Pane Body */}
            <div className="flex-1 overflow-hidden p-3 flex flex-col">
              {/* VIEW A: REAL LIVE OS DESKTOP WORKSPACE */}
              {rightView === "desktop" && (
                <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden shadow-2xl">
                  {/* Virtual OS Window Title Bar */}
                  <div className="h-8 border-b border-[#21262D] bg-[#1C2128] px-3 flex items-center justify-between text-xs font-mono text-[#8B949E]">
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-1">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#FF5F56] inline-block"></span>
                        <span className="w-2.5 h-2.5 rounded-full bg-[#FFBD2E] inline-block"></span>
                        <span className="w-2.5 h-2.5 rounded-full bg-[#27C93F] inline-block"></span>
                      </div>
                      <span className="text-white font-semibold flex items-center gap-1.5 ml-2">
                        <Monitor className="w-3.5 h-3.5 text-[#58A6FF]" />
                        SONIC Desktop Workspace — Ubuntu 22.04 (1920x1080)
                      </span>
                    </div>

                    {/* Window Switcher Inside Desktop */}
                    <div className="flex items-center gap-1 bg-[#12151A] p-0.5 rounded border border-[#30363D]">
                      <button
                        onClick={() => setActiveDesktopApp("vscode")}
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold transition ${activeDesktopApp === "vscode" ? "bg-[#388BFD] text-white" : "text-[#8B949E] hover:text-white"
                          }`}
                      >
                        VS Code
                      </button>
                      <button
                        onClick={() => setActiveDesktopApp("terminal")}
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold transition ${activeDesktopApp === "terminal" ? "bg-[#388BFD] text-white" : "text-[#8B949E] hover:text-white"
                          }`}
                      >
                        Terminal
                      </button>
                      <button
                        onClick={() => setActiveDesktopApp("browser")}
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold transition ${activeDesktopApp === "browser" ? "bg-[#388BFD] text-white" : "text-[#8B949E] hover:text-white"
                          }`}
                      >
                        Chromium
                      </button>
                    </div>
                  </div>

                  {/* OS Desktop Active App Surface */}
                  <div className="flex-1 bg-[#0A0C10] flex flex-col overflow-hidden relative">
                    {/* APP 1: VS CODE INSIDE OS */}
                    {activeDesktopApp === "vscode" && (
                      <div className="flex-1 flex flex-col overflow-hidden bg-[#0D1117]">
                        <div className="h-7 border-b border-[#21262D] bg-[#161B22] px-3 flex items-center justify-between text-[11px] font-mono text-[#8B949E]">
                          <div className="flex items-center gap-2">
                            <FileCode className="w-3.5 h-3.5 text-[#79C0FF]" />
                            <span className="text-[#58A6FF] font-semibold">{activeFile.split("/").pop()}</span>
                            <span className="text-[10px] text-[#3FB950]">● Live Editor</span>
                          </div>
                          <span>Line 14:28</span>
                        </div>
                        <div className="flex-1 p-3 font-mono text-xs overflow-y-auto leading-relaxed text-[#C9D1D9]">
                          {fileContent.slice(0, 45).map((line, i) => (
                            <div key={i} className="flex hover:bg-[#161B22]/50 leading-5">
                              <span className="w-10 text-right pr-4 text-[#484F58] select-none font-mono text-[11px]">
                                {i + 1}
                              </span>
                              <span className="flex-1 whitespace-pre">
                                {line.startsWith("import ") || line.startsWith("from ") ? (
                                  <span className="text-[#FF7B72]">{line}</span>
                                ) : line.startsWith("class ") || line.startsWith("def ") ? (
                                  <span className="text-[#D2A8FF]">{line}</span>
                                ) : line.includes("def ") || line.includes("return ") ? (
                                  <span className="text-[#79C0FF]">{line}</span>
                                ) : line.includes("#") ? (
                                  <span className="text-[#8B949E]">{line}</span>
                                ) : (
                                  <span className="text-[#C9D1D9]">{line}</span>
                                )}
                              </span>
                            </div>
                          ))}
                        </div>
                        {/* Live AI Cursor Overlay */}
                        <div className="absolute bottom-4 right-4 bg-[#388BFD] text-white px-2 py-0.5 rounded text-[10px] font-mono font-bold shadow-lg flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping"></span>
                          <span>Devin typing at {activeFile.split("/").pop()}</span>
                        </div>
                      </div>
                    )}

                    {/* APP 2: LIVE TERMINAL INSIDE OS */}
                    {activeDesktopApp === "terminal" && (
                      <div className="flex-1 flex flex-col p-3 font-mono text-xs bg-[#06080D] overflow-hidden">
                        <div className="flex-1 overflow-y-auto space-y-1 text-[#C9D1D9] leading-tight select-text">
                          {terminalLogs.map((log, idx) => (
                            <div key={idx} className="whitespace-pre-wrap">
                              {log.startsWith("sonic@") ? (
                                <span className="text-[#79C0FF] font-bold">{log}</span>
                              ) : log.includes("PASSED") ? (
                                <span className="text-[#3FB950]">{log}</span>
                              ) : log.includes("FAILED") || log.includes("Error") ? (
                                <span className="text-[#FF7B72]">{log}</span>
                              ) : (
                                <span className="text-[#8B949E]">{log}</span>
                              )}
                            </div>
                          ))}
                        </div>
                        <form onSubmit={handleRunTerminalCommand} className="mt-2 flex items-center gap-2 border-t border-[#21262D] pt-2">
                          <span className="text-[#3FB950] font-bold">sonic@sandbox:~$</span>
                          <input
                            type="text"
                            value={terminalInput}
                            onChange={(e) => setTerminalInput(e.target.value)}
                            placeholder="type bash command (e.g. pytest tests/)..."
                            className="flex-1 bg-transparent text-xs text-white outline-none font-mono placeholder-[#484F58]"
                          />
                        </form>
                      </div>
                    )}

                    {/* APP 3: CHROMIUM WEB BROWSER INSIDE OS */}
                    {activeDesktopApp === "browser" && (
                      <div className="flex-1 flex flex-col bg-[#12151A] overflow-hidden">
                        <div className="h-7 border-b border-[#21262D] bg-[#161B22] px-3 flex items-center justify-between text-[11px] font-mono text-[#8B949E]">
                          <div className="flex items-center gap-2 flex-1">
                            <Globe className="w-3.5 h-3.5 text-[#58A6FF]" />
                            <span className="px-2 py-0.5 rounded bg-[#0D1117] text-white flex-1 truncate">
                              http://127.0.0.1:8000/docs
                            </span>
                          </div>
                          <span className="text-[#3FB950] text-[10px] ml-2">HTTP 200 OK</span>
                        </div>
                        <div className="flex-1 p-6 flex flex-col items-center justify-center text-center space-y-2 bg-[#0A0C10]">
                          <div className="w-10 h-10 rounded-full bg-[#238636]/20 border border-[#238636] flex items-center justify-center text-[#3FB950]">
                            <CheckCircle2 className="w-5 h-5" />
                          </div>
                          <h4 className="text-sm font-semibold text-white">Live Application View Port</h4>
                          <p className="text-xs text-[#8B949E] max-w-sm">
                            FastAPI Backend Server &amp; Security OpenAPI live at <code className="text-[#58A6FF]">http://127.0.0.1:8000</code>.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* VIEW B: CLEAN SOURCE CODE EDITOR */}
              {rightView === "code" && (
                <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden shadow-xl">
                  {/* File Header Bar */}
                  <div className="h-8 border-b border-[#21262D] bg-[#1C2128] px-3 flex items-center justify-between text-xs font-mono text-[#8B949E]">
                    <div className="flex items-center gap-2 truncate">
                      <ChevronDown className="w-3.5 h-3.5 text-[#8B949E]" />
                      <span className="text-[#58A6FF] font-semibold truncate">{activeFile.split("/").pop()}</span>
                      <span className="text-[10px] text-[#8B949E] truncate">{activeFile}</span>
                    </div>
                    <button
                      onClick={handleCopy}
                      className="text-[#8B949E] hover:text-white p-1 rounded hover:bg-[#2D333B] transition flex-shrink-0"
                      title="Copy file contents"
                    >
                      {copied ? <Check className="w-3.5 h-3.5 text-[#3FB950]" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                  </div>

                  {/* Line Numbered Real Source Code Viewer */}
                  <div className="flex-1 overflow-y-auto p-3 font-mono text-xs leading-relaxed bg-[#0D1117]">
                    {fileContent.map((line, i) => (
                      <div key={i} className="flex hover:bg-[#161B22]/50 leading-5">
                        <span className="w-10 text-right pr-4 text-[#484F58] select-none font-mono text-[11px]">
                          {i + 1}
                        </span>
                        <span className="flex-1 whitespace-pre">
                          {line.startsWith("import ") || line.startsWith("from ") ? (
                            <span className="text-[#FF7B72]">{line}</span>
                          ) : line.startsWith("class ") || line.startsWith("def ") ? (
                            <span className="text-[#D2A8FF]">{line}</span>
                          ) : line.includes("def ") || line.includes("return ") ? (
                            <span className="text-[#79C0FF]">{line}</span>
                          ) : line.includes("#") ? (
                            <span className="text-[#8B949E]">{line}</span>
                          ) : (
                            <span className="text-[#C9D1D9]">{line}</span>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* VIEW C: LIVE GIT DIFF */}
              {rightView === "changes" && (
                <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden p-4 font-mono text-xs space-y-2">
                  <div className="flex items-center justify-between border-b border-[#30363D] pb-2">
                    <span className="font-semibold text-white">Live Git Diff ({gitBranch})</span>
                    <button onClick={fetchDiff} className="text-[#58A6FF] hover:underline text-[11px]">
                      Refresh Diff
                    </button>
                  </div>
                  <div className="flex-1 overflow-y-auto space-y-1 text-[11px] leading-relaxed whitespace-pre-wrap bg-[#0D1117] p-3 rounded border border-[#21262D]">
                    {gitDiff ? (
                      gitDiff.split("\n").map((l, i) => (
                        <div
                          key={i}
                          className={
                            l.startsWith("+")
                              ? "text-[#7EE787] bg-[#7EE787]/10 px-1"
                              : l.startsWith("-")
                                ? "text-[#FF7B72] bg-[#FF7B72]/10 px-1"
                                : "text-[#8B949E]"
                          }
                        >
                          {l}
                        </div>
                      ))
                    ) : (
                      <span className="text-[#8B949E]">Working tree clean. No uncommitted modifications.</span>
                    )}
                  </div>
                </div>
              )}

              {/* VIEW D: PR #19 */}
              {rightView === "pr66" && (
                <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden p-4 font-mono text-xs space-y-3">
                  <div className="flex items-center justify-between border-b border-[#30363D] pb-2">
                    <span className="font-semibold text-white">Pull Request #19: Release Production Gate &amp; Autonomy Engine</span>
                    <span className="px-2 py-0.5 rounded bg-[#238636] text-white font-bold text-[10px]">MERGED</span>
                  </div>
                  <p className="text-[#8B949E] text-xs font-sans">
                    Autonomous Pull Request incorporating all 225 unit tests across Phases 1–19, 4-tier reality taxonomy, and continuous self-development.
                  </p>
                </div>
              )}
            </div>

            {/* Bottom Status / Live Desktop Toggle Bar */}
            <div className="h-10 border-t border-[#21262D] bg-[#12151A] px-3 flex items-center justify-between text-xs">
              {/* Waveform timeline */}
              <div className="flex items-center gap-1 h-3 overflow-hidden opacity-60">
                {[4, 8, 12, 6, 14, 9, 3, 11, 7, 13, 5, 10, 8, 14, 4, 9, 12, 6, 11, 7, 13, 5, 8, 12, 6, 14, 9, 3, 11].map(
                  (h, idx) => (
                    <span
                      key={idx}
                      className="w-[2px] bg-[#388BFD] inline-block rounded-full"
                      style={{ height: `${h}px` }}
                    ></span>
                  )
                )}
              </div>

              {/* Navigation & Desktop Toggle Action */}
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1 text-[#8B949E]">
                  <ArrowLeft className="w-3.5 h-3.5 hover:text-white cursor-pointer" />
                  <ArrowRight className="w-3.5 h-3.5 hover:text-white cursor-pointer" />
                </div>
                <button
                  onClick={() => setRightView(rightView === "desktop" ? "code" : "desktop")}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#21262D] hover:bg-[#30363D] text-[11px] text-white font-medium transition"
                >
                  <span className="w-2 h-2 rounded-full bg-[#FF5F56] animate-pulse"></span>
                  <span>{rightView === "desktop" ? "View Code" : "Go to live desktop"}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
