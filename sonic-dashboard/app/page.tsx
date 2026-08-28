"use client";

import React, { useState, useEffect } from "react";
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
  Monitor
} from "lucide-react";

export default function SonicDevinWorkstation() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [thinkingOpen, setThinkingOpen] = useState(true);
  const [rightView, setRightView] = useState<"code" | "desktop" | "changes" | "pr66" | "pr67">("code");
  const [activeTab, setActiveTab] = useState<"worklog" | "changes" | "pr66" | "pr67">("worklog");
  const [promptText, setPromptText] = useState("");
  const [copied, setCopied] = useState(false);
  const [activeFile, setActiveFile] = useState("index.html");
  const [fileContent, setFileContent] = useState<string[]>([]);
  const [liveState, setLiveState] = useState<any>(null);

  // Default real index.html code lines from repository / session
  const defaultHtmlLines = [
    "<!doctype html>",
    "<html lang=\"en\">",
    "  <head>",
    "    <meta charset=\"UTF-8\" />",
    "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />",
    "    <title>Graph Game</title>",
    "    <style>",
    "      html,",
    "      body {",
    "        margin: 0;",
    "        padding: 0;",
    "        background: #1d1f27;",
    "        height: 100%;",
    "      }",
    "      #game {",
    "        display: flex;",
    "        justify-content: center;",
    "        align-items: center;",
    "        height: 100%;",
    "      }",
    "    </style>",
    "  </head>",
    "  <body>",
    "    <div id=\"game\"></div>",
    "    <script type=\"module\" src=\"/src/main.ts\"></script>",
    "  </body>",
    "</html>",
  ];

  useEffect(() => {
    setFileContent(defaultHtmlLines);
    // Fetch live state from real FastAPI backend
    fetch("http://127.0.0.1:8000/workstation/state")
      .then((res) => res.json())
      .then((data) => {
        if (data) setLiveState(data);
      })
      .catch(() => {});
  }, []);

  const handleCopy = () => {
    navigator.clipboard.writeText(fileContent.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSendPrompt = (e: React.FormEvent) => {
    e.preventDefault();
    if (!promptText.trim()) return;

    fetch("http://127.0.0.1:8000/workstation/prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: promptText }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data?.state) setLiveState(data.state);
      })
      .catch(() => {});

    setPromptText("");
  };

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
              B
            </div>
            <span className="text-xs font-semibold text-white tracking-wide">bquiz-exp</span>
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

        {/* Recent Sessions Header */}
        <div className="px-3 pt-3 pb-1 flex items-center justify-between text-xs text-[#8B949E]">
          <span className="font-semibold text-[11px]">Recent</span>
          <div className="flex items-center gap-1">
            <Search className="w-3.5 h-3.5 hover:text-white cursor-pointer" />
            <Plus className="w-3.5 h-3.5 hover:text-white cursor-pointer" />
            <MoreHorizontal className="w-3.5 h-3.5 hover:text-white cursor-pointer" />
          </div>
        </div>

        {/* Active Session Item */}
        <div className="px-2 flex-1 overflow-y-auto space-y-1">
          <div className="p-2.5 rounded-md bg-[#181C23] border border-[#30363D] cursor-pointer">
            <div className="text-xs font-semibold text-white truncate">
              {liveState?.session_id ? "graph-game-devin" : "graph-game-devin"}
            </div>
            <div className="flex items-center gap-2 text-[11px] text-[#8B949E] font-mono mt-1">
              <span>Working</span>
              <span>·</span>
              <span className="text-[#3FB950] flex items-center gap-0.5">
                <GitBranch className="w-3 h-3" /> 1
              </span>
              <span className="text-[#D2A8FF] flex items-center gap-0.5">
                <GitPullRequest className="w-3 h-3" /> 1
              </span>
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
          <div className="flex items-center gap-2">
            {!sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(true)}
                className="text-[#8B949E] hover:text-white p-1 rounded hover:bg-[#21262D] transition mr-1"
                title="Open sidebar"
              >
                <PanelLeft className="w-4 h-4" />
              </button>
            )}
            <span className="font-semibold text-white">Graph-game-devin</span>
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
            <div className="flex-1 overflow-y-auto p-4 space-y-2 font-sans text-xs text-[#8B949E]">
              {/* Event 1 */}
              <div className="flex items-center gap-2 text-[#8B949E]">
                <Clock className="w-3.5 h-3.5 text-[#8B949E]" />
                <span>Thought for 3s</span>
              </div>

              {/* Event 2 */}
              <div className="flex items-center gap-2 text-[#8B949E]">
                <Clock className="w-3.5 h-3.5 text-[#8B949E]" />
                <span>Thought for 20s</span>
              </div>

              {/* Event 3 */}
              <div className="flex items-center gap-2 text-[#8B949E]">
                <Clock className="w-3.5 h-3.5 text-[#8B949E]" />
                <span>Thought for 11s</span>
              </div>

              {/* Terminal Command 1 */}
              <div className="flex items-start gap-2 text-[#C9D1D9] font-mono text-[11px]">
                <TerminalIcon className="w-3.5 h-3.5 text-[#8B949E] mt-0.5 flex-shrink-0" />
                <span className="break-all">
                  cd /home/ubuntu/repos/graph-game-devin && grep -rn &quot;phaser-dom&quot; node_modules/phaser/dist/phaser.js | head; echo &quot;===&quot;; grep -n &quot;...&quot; ...
                </span>
              </div>

              {/* Terminal Command 2 */}
              <div className="flex items-start gap-2 text-[#C9D1D9] font-mono text-[11px]">
                <TerminalIcon className="w-3.5 h-3.5 text-[#8B949E] mt-0.5 flex-shrink-0" />
                <span className="break-all">
                  cd /home/ubuntu/repos/graph-game-devin && ls node_modules/phaser/dist/ 2&gt;/dev/null; echo &quot;===&quot;; grep -n &quot;...&quot; node_modules/phaser/dist/phaser.js
                </span>
              </div>

              {/* Terminal Command 3 */}
              <div className="flex items-start gap-2 text-[#C9D1D9] font-mono text-[11px]">
                <TerminalIcon className="w-3.5 h-3.5 text-[#8B949E] mt-0.5 flex-shrink-0" />
                <span className="break-all">
                  cd /home/ubuntu/repos/graph-game-devin && grep -n &quot;...&quot; node_modules/phaser/dist/phaser.js
                </span>
              </div>

              {/* Read file 1 */}
              <div className="flex items-center gap-2 text-[#C9D1D9] font-mono text-[11px]">
                <BookOpen className="w-3.5 h-3.5 text-[#8B949E]" />
                <span>Read <span className="text-[#58A6FF]">phaser.js:58624-58733</span></span>
              </div>

              {/* Thought */}
              <div className="flex items-center gap-2 text-[#8B949E]">
                <Clock className="w-3.5 h-3.5 text-[#8B949E]" />
                <span>Thought for 23s</span>
              </div>

              {/* Read file 2 */}
              <div className="flex items-center gap-2 text-[#C9D1D9] font-mono text-[11px]">
                <BookOpen className="w-3.5 h-3.5 text-[#8B949E]" />
                <span>Read <span className="text-[#58A6FF]">GameScene.ts:31-40</span></span>
              </div>

              {/* Thoughts */}
              <div className="flex items-center gap-2 text-[#8B949E]">
                <Clock className="w-3.5 h-3.5 text-[#8B949E]" />
                <span>Thought for 6s</span>
              </div>
              <div className="flex items-center gap-2 text-[#8B949E]">
                <Clock className="w-3.5 h-3.5 text-[#8B949E]" />
                <span>Thought for 9s</span>
              </div>
              <div className="flex items-center gap-2 text-[#8B949E]">
                <Clock className="w-3.5 h-3.5 text-[#8B949E]" />
                <span>Thought for 15s</span>
              </div>

              {/* Read file 3 */}
              <div className="flex items-center gap-2 text-[#C9D1D9] font-mono text-[11px]">
                <BookOpen className="w-3.5 h-3.5 text-[#8B949E]" />
                <span>Read <span className="text-[#58A6FF]">index.html:1-27</span></span>
              </div>

              {/* Expandable Thinking Box */}
              <div className="rounded-lg border border-[#21262D] bg-[#12151A] p-3 space-y-2 text-xs">
                <div
                  onClick={() => setThinkingOpen(!thinkingOpen)}
                  className="flex items-center gap-1.5 text-[#8B949E] hover:text-white cursor-pointer font-medium"
                >
                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${thinkingOpen ? "" : "-rotate-90"}`} />
                  <span>Thinking</span>
                </div>

                {thinkingOpen && (
                  <div className="text-[#C9D1D9] leading-relaxed text-[11px] font-sans pt-1">
                    I see the root cause now—#game is a flex container that&apos;s centering the canvas, but the DOM container is absolutely positioned, which removes it from the flex flow and causes Phaser&apos;s positioning to conflict with the flex centering. The solution is to stop using flex to center the canvas and instead size #game to match the canvas dimensions, then center #game itself. The real issue is that flexbox centering on the parent is conflicting with Phaser&apos;s own centering logic. I should remove the flex styling from #game, set it to match exact viewport bounds, and let Phaser coordinate canvas coordinates directly.
                  </div>
                )}
              </div>

              {/* Active Spinner Status */}
              <div className="flex items-center gap-2 text-[#58A6FF] text-xs pt-2">
                <div className="flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#58A6FF] animate-bounce"></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3FB950] animate-bounce [animation-delay:0.2s]"></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-[#D2A8FF] animate-bounce [animation-delay:0.4s]"></span>
                </div>
                <span className="text-[#C9D1D9]">Checking page CSS</span>
              </div>
            </div>

            {/* Bottom Input Box in Left Column */}
            <div className="p-3 border-t border-[#21262D] bg-[#12151A]">
              <form onSubmit={handleSendPrompt} className="rounded-lg border border-[#30363D] bg-[#161B22] p-2.5 space-y-2">
                <input
                  type="text"
                  value={promptText}
                  onChange={(e) => setPromptText(e.target.value)}
                  placeholder="Guide Devin while it works"
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
                      className="w-6 h-6 rounded-full bg-white text-black flex items-center justify-center hover:bg-slate-200 transition"
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
                    activeTab === "worklog"
                      ? "bg-[#21262D] text-white font-semibold"
                      : "text-[#8B949E] hover:text-white"
                  }`}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>Worklog</span>
                </button>

                <button
                  onClick={() => {
                    setActiveTab("changes");
                    setRightView("changes");
                  }}
                  className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                    activeTab === "changes"
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
                    activeTab === "pr66"
                      ? "bg-[#21262D] text-white font-semibold"
                      : "text-[#8B949E] hover:text-white"
                  }`}
                >
                  <GitPullRequest className="w-3.5 h-3.5 text-[#D2A8FF]" />
                  <span>PR #66</span>
                </button>

                <button
                  onClick={() => {
                    setActiveTab("pr67");
                    setRightView("pr67");
                  }}
                  className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                    activeTab === "pr67"
                      ? "bg-[#21262D] text-white font-semibold"
                      : "text-[#8B949E] hover:text-white"
                  }`}
                >
                  <GitPullRequest className="w-3.5 h-3.5 text-[#3FB950]" />
                  <span>PR #67</span>
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
              <span className="text-[#C9D1D9]">Read <strong className="text-white">index.html</strong></span>
            </div>

            {/* Code / Desktop View Body */}
            <div className="flex-1 overflow-hidden p-3 flex flex-col">
              {rightView === "code" && (
                <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden shadow-xl">
                  {/* File Header Bar */}
                  <div className="h-8 border-b border-[#21262D] bg-[#1C2128] px-3 flex items-center justify-between text-xs font-mono text-[#8B949E]">
                    <div className="flex items-center gap-2">
                      <ChevronDown className="w-3.5 h-3.5 text-[#8B949E]" />
                      <span className="text-[#58A6FF] font-semibold">index.html</span>
                      <span className="text-[11px] text-[#8B949E]">graph-game-devin</span>
                    </div>
                    <button
                      onClick={handleCopy}
                      className="text-[#8B949E] hover:text-white p-1 rounded hover:bg-[#2D333B] transition"
                      title="Copy file contents"
                    >
                      {copied ? <Check className="w-3.5 h-3.5 text-[#3FB950]" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                  </div>

                  {/* Line Numbered Syntax Highlighted Code Viewer */}
                  <div className="flex-1 overflow-y-auto p-3 font-mono text-xs leading-relaxed bg-[#0D1117]">
                    {fileContent.map((line, i) => (
                      <div key={i} className="flex hover:bg-[#161B22]/50 leading-5">
                        <span className="w-8 text-right pr-4 text-[#484F58] select-none font-mono text-[11px]">
                          {i + 1}
                        </span>
                        <span className="flex-1 whitespace-pre">
                          {line.startsWith("<!doctype") ? (
                            <span className="text-[#FF7B72]">{line}</span>
                          ) : line.includes("<style>") || line.includes("</style>") ? (
                            <span className="text-[#7EE787]">{line}</span>
                          ) : line.includes("<script") ? (
                            <span className="text-[#FFA657]">{line}</span>
                          ) : line.includes("background:") || line.includes("display:") ? (
                            <span className="text-[#79C0FF]">{line}</span>
                          ) : line.includes("<") ? (
                            <span className="text-[#7EE787]">{line}</span>
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
                        Devin Live Desktop (Ubuntu 22.04 / Chromium &amp; VSCode)
                      </span>
                    </div>
                    <span className="text-[#3FB950] text-[10px] font-mono">1920x1080 60fps</span>
                  </div>

                  {/* Embedded Desktop Screen Canvas */}
                  <div className="flex-1 bg-[#1A1D24] p-3 flex flex-col justify-center items-center text-center relative overflow-hidden">
                    {/* Simulated Game/Canvas Window */}
                    <div className="w-full max-w-md h-64 rounded bg-[#1D1F27] border border-[#30363D] flex flex-col shadow-2xl relative">
                      <div className="h-6 bg-[#282C34] border-b border-[#30363D] px-2 flex items-center justify-between text-[10px] text-[#8B949E]">
                        <span>Graph Game - Phaser Canvas</span>
                        <span>FPS: 60</span>
                      </div>
                      <div className="flex-1 flex items-center justify-center relative">
                        <div className="w-32 h-32 rounded-lg border-2 border-dashed border-[#58A6FF]/60 flex items-center justify-center text-[#58A6FF] text-xs font-mono">
                          #game canvas
                        </div>
                        {/* Live AI Cursor */}
                        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-1.5 bg-[#58A6FF] text-black px-2 py-0.5 rounded text-[10px] font-bold shadow-lg">
                          <span>Devin</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {(rightView === "changes" || rightView === "pr66" || rightView === "pr67") && (
                <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden p-4 font-mono text-xs space-y-2">
                  <div className="flex items-center justify-between border-b border-[#30363D] pb-2">
                    <span className="font-semibold text-white">Diff: index.html</span>
                    <span className="text-[#3FB950]">+3 / -2 lines</span>
                  </div>
                  <div className="space-y-1 text-[11px] leading-relaxed">
                    <div className="text-[#8B949E]">@@ -14,5 +14,6 @@</div>
                    <div className="text-[#FF7B72] bg-[#FF7B72]/10 px-2 py-0.5">- display: flex;</div>
                    <div className="text-[#FF7B72] bg-[#FF7B72]/10 px-2 py-0.5">- justify-content: center;</div>
                    <div className="text-[#7EE787] bg-[#7EE787]/10 px-2 py-0.5">+ position: relative;</div>
                    <div className="text-[#7EE787] bg-[#7EE787]/10 px-2 py-0.5">+ margin: 0 auto;</div>
                  </div>
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
