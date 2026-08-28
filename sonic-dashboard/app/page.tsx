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
  CheckCircle2
} from "lucide-react";

export default function SonicDevinWorkstation() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [thinkingOpen, setThinkingOpen] = useState(true);
  const [rightView, setRightView] = useState<"code" | "desktop" | "changes" | "pr66">("code");
  const [activeTab, setActiveTab] = useState<"worklog" | "desktop" | "changes" | "pr66">("worklog");
  const [promptText, setPromptText] = useState("");
  const [copied, setCopied] = useState(false);
  const [activeFile, setActiveFile] = useState("sonic-core/sonic/production_gate/scenario_matrix.py");
  const [fileContent, setFileContent] = useState<string[]>([]);
  const [fileTotalLines, setFileTotalLines] = useState(0);
  const [fileTree, setFileTree] = useState<string[]>([]);
  const [gitDiff, setGitDiff] = useState("");
  const [liveState, setLiveState] = useState<any>(null);
  const [terminalInput, setTerminalInput] = useState("");
  const [terminalLogs, setTerminalLogs] = useState<string[]>([
    "sonic-workstation: sandbox container attached.",
    "workspace root: /home/sonic/society",
    "git branch: main",
    "all 225 unit tests verified (Phases 1-19).",
  ]);
  const [loading, setLoading] = useState(false);
  const worklogEndRef = useRef<HTMLDivElement>(null);

  // 1. Fetch live workstation state & file tree on mount
  useEffect(() => {
    fetchState();
    fetchTree();
    fetchFile(activeFile);
    fetchDiff();

    // Live refresh interval
    const interval = setInterval(() => {
      fetchState();
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  const fetchState = () => {
    fetch("http://127.0.0.1:8000/workstation/state")
      .then((res) => res.json())
      .then((data) => {
        if (data) setLiveState(data);
      })
      .catch(() => {});
  };

  const fetchTree = () => {
    fetch("http://127.0.0.1:8000/workstation/tree")
      .then((res) => res.json())
      .then((data) => {
        if (data?.files) setFileTree(data.files);
      })
      .catch(() => {});
  };

  const fetchFile = (path: string) => {
    setActiveFile(path);
    fetch(`http://127.0.0.1:8000/workstation/file?path=${encodeURIComponent(path)}`)
      .then((res) => res.json())
      .then((data) => {
        if (data?.lines) {
          setFileContent(data.lines);
          setFileTotalLines(data.total_lines || data.lines.length);
        } else if (data?.content) {
          const lines = data.content.split("\n");
          setFileContent(lines);
          setFileTotalLines(lines.length);
        }
      })
      .catch((err) => {
        setFileContent([`# Error reading ${path}: ${err}`]);
      });
  };

  const fetchDiff = () => {
    fetch("http://127.0.0.1:8000/workstation/git-diff")
      .then((res) => res.json())
      .then((data) => {
        if (data?.diff) setGitDiff(data.diff);
      })
      .catch(() => {});
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
    setTerminalLogs((prev) => [...prev, `$ ${cmd}`]);

    try {
      const res = await fetch("http://127.0.0.1:8000/workstation/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd }),
      });
      const data = await res.json();
      if (data?.output) {
        setTerminalLogs((prev) => [...prev, data.output]);
      }
      fetchState();
    } catch (err: any) {
      setTerminalLogs((prev) => [...prev, `Error: ${err.message}`]);
    }
  };

  const sessionName = liveState?.mission_name || "graph-game-devin";
  const gitBranch = liveState?.git_branch || "main";
  const worklog = liveState?.worklog || [];

  return (
    <div className="flex h-screen w-screen bg-[#0D0F12] text-[#E6EDF3] overflow-hidden font-sans select-none">
      {/* 1. LEFT NAVIGATION SIDEBAR */}
      <aside
        className={`${
          sidebarOpen ? "w-[240px]" : "w-0"
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

        {/* Real Files Quick Picker */}
        <div className="px-3 pt-3 pb-1 flex items-center justify-between text-xs text-[#8B949E]">
          <span className="font-semibold text-[11px] uppercase tracking-wider">Repository Files</span>
          <span className="text-[10px] font-mono">{fileTree.length} files</span>
        </div>

        <div className="px-2 flex-1 overflow-y-auto space-y-0.5 font-mono text-[11px]">
          {fileTree.slice(0, 15).map((f) => (
            <div
              key={f}
              onClick={() => {
                fetchFile(f);
                setRightView("code");
              }}
              className={`p-1.5 rounded flex items-center gap-2 cursor-pointer transition truncate ${
                activeFile === f
                  ? "bg-[#1F242C] text-[#58A6FF] font-semibold"
                  : "text-[#8B949E] hover:text-white hover:bg-[#161B22]"
              }`}
            >
              <FileCode className="w-3.5 h-3.5 flex-shrink-0 text-[#8B949E]" />
              <span className="truncate">{f.split("/").pop()}</span>
            </div>
          ))}
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
                        <div className="pl-5 font-mono text-[10px] text-[#8B949E] bg-[#12151A] p-1.5 rounded border border-[#21262D] whitespace-pre-wrap max-h-32 overflow-y-auto">
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
          {/* RIGHT SUB-COLUMN: CODE VIEWER / LIVE DESKTOP / CHANGES (COL-SPAN 6)      */}
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
                  className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                    activeTab === "worklog" && rightView === "code"
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
                  className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                    rightView === "desktop"
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
                  className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                    rightView === "changes"
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
                  className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                    rightView === "pr66"
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

            {/* Sub-Header: Active File / Action Badge */}
            <div className="px-4 py-2 text-xs text-[#8B949E] flex items-center gap-2 border-b border-[#1E232B] bg-[#0F1116]">
              <Eye className="w-3.5 h-3.5 text-[#58A6FF]" />
              <span className="text-[#C9D1D9]">
                Read <strong className="text-white">{activeFile.split("/").pop()}</strong>
              </span>
            </div>

            {/* Code / Desktop View Body */}
            <div className="flex-1 overflow-hidden p-3 flex flex-col">
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

              {rightView === "desktop" && (
                <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden shadow-xl">
                  {/* Virtual Desktop Window Header */}
                  <div className="h-8 border-b border-[#21262D] bg-[#1C2128] px-3 flex items-center justify-between text-xs font-mono text-[#8B949E]">
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-[#FF5F56]"></span>
                        <span className="w-2 h-2 rounded-full bg-[#FFBD2E]"></span>
                        <span className="w-2 h-2 rounded-full bg-[#27C93F]"></span>
                      </div>
                      <span className="text-white font-semibold flex items-center gap-1.5 ml-2">
                        <Monitor className="w-3.5 h-3.5 text-[#58A6FF]" />
                        SONIC Interactive Sandbox PTY Shell
                      </span>
                    </div>
                    <span className="text-[#3FB950] text-[10px] font-mono">1920x1080 60fps</span>
                  </div>

                  {/* Embedded Real Interactive Terminal Shell */}
                  <div className="flex-1 bg-[#06080D] p-3 flex flex-col font-mono text-xs overflow-hidden">
                    <div className="flex-1 overflow-y-auto space-y-1 text-[#C9D1D9] leading-tight select-text">
                      {terminalLogs.map((log, idx) => (
                        <div key={idx} className="whitespace-pre-wrap">
                          {log.startsWith("$") ? (
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

                    {/* Interactive Command Input in Shell */}
                    <form onSubmit={handleRunTerminalCommand} className="mt-2 flex items-center gap-2 border-t border-[#21262D] pt-2">
                      <span className="text-[#3FB950]">$</span>
                      <input
                        type="text"
                        value={terminalInput}
                        onChange={(e) => setTerminalInput(e.target.value)}
                        placeholder="type command (e.g. pytest tests/ or git status)..."
                        className="flex-1 bg-transparent text-xs text-white outline-none font-mono placeholder-[#484F58]"
                      />
                    </form>
                  </div>
                </div>
              )}

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

              {rightView === "pr66" && (
                <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden p-4 font-mono text-xs space-y-3">
                  <div className="flex items-center justify-between border-b border-[#30363D] pb-2">
                    <span className="font-semibold text-white">Pull Request #19: Release Production Gate & Autonomy Engine</span>
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
