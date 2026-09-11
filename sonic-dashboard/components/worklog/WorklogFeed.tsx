"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Terminal,
  FileCode,
  Send,
  Square,
  Sparkles,
  GitBranch,
  MoreHorizontal,
  Maximize2,
  PanelRightOpen,
  PanelRightClose,
  Bot,
  User,
  Shield,
  Copy,
  Check,
  Zap,
  Brain,
  MousePointer,
  Eye,
  Monitor,
  AppWindow,
} from "lucide-react";
import { WorklogItem } from "../../types/workstation";
import { MarkdownText } from "./MarkdownText";
import { ThinkingBlock } from "./ThinkingBlock";
import { CommandBlock } from "./CommandBlock";
import { FileActionBlock } from "./FileActionBlock";
import { FollowupChips } from "./FollowupChips";

type Mode = "Normal" | "Autonomous" | "Pair-Program";
const MODES: Mode[] = ["Normal", "Autonomous", "Pair-Program"];

interface WorklogFeedProps {
  worklog: WorklogItem[];
  currentAction?: string;
  loading: boolean;
  status?: string;
  onSendPrompt: (prompt: string, mode: Mode) => Promise<void>;
  onInterrupt?: () => Promise<void> | void;
  onSelectFile?: (filePath: string) => void;
  sessionName?: string;
  gitBranch?: string;
  rightPanelOpen?: boolean;
  onToggleRightPanel?: () => void;
}

export function WorklogFeed({
  worklog,
  currentAction,
  loading,
  status,
  onSendPrompt,
  onInterrupt,
  onSelectFile,
  sessionName = "",
  gitBranch = "",
  rightPanelOpen = true,
  onToggleRightPanel,
}: WorklogFeedProps) {
  const [promptText, setPromptText] = useState("");
  const [activeMode, setActiveMode] = useState<Mode>("Normal");
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const worklogEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const displayItems: WorklogItem[] = worklog || [];

  const normalizedStatus = (status || "").toUpperCase();
  const isFinished =
    normalizedStatus === "IDLE" ||
    normalizedStatus === "PAUSED" ||
    normalizedStatus === "BLOCKED" ||
    normalizedStatus === "COMPLETED" ||
    normalizedStatus === "ERROR" ||
    (!loading && normalizedStatus !== "RUNNING");

  // Check if the latest item in the worklog feed is a finished response
  const lastItem = displayItems.length > 0 ? displayItems[displayItems.length - 1] : null;
  const lastIsResponse = Boolean(
    lastItem && (lastItem.type === "response" || lastItem.title === "SONIC Response")
  );

  // If state is finished OR if the actual response is already shown at the bottom,
  // do not render any spinner!
  const shouldShowAction = !isFinished && !lastIsResponse;

  const cleanActionText = (() => {
    if (!shouldShowAction) return undefined;
    const text = (currentAction || "").trim();
    if (!text) {
      return loading || normalizedStatus === "RUNNING"
        ? "Thinking..."
        : undefined;
    }
    const lower = text.toLowerCase();
    if (
      lower.includes("queued") ||
      lower.includes("reasoning queued") ||
      lower.includes("autonomous reasoning") ||
      lower.startsWith("idle") ||
      lower.startsWith("ready") ||
      lower === "thinking" ||
      lower.startsWith("thinking:")
    ) {
      return normalizedStatus === "RUNNING" || loading
        ? "Thinking..."
        : undefined;
    }
    return text;
  })();

  useEffect(() => {
    worklogEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [worklog, cleanActionText]);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!promptText.trim() || (loading && normalizedStatus === "RUNNING")) return;
    const text = promptText;
    setPromptText("");
    await onSendPrompt(text, activeMode);
  };

  const handleCopyResponse = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      // ignore
    }
  };

  const handleTopicClick = (tagPrompt: string) => {
    setPromptText(tagPrompt);
    textareaRef.current?.focus();
  };

  // Find the index of the last response item to display follow-ups underneath
  let lastResponseIdx = -1;
  for (let i = displayItems.length - 1; i >= 0; i--) {
    if (displayItems[i].type === "response" || displayItems[i].title === "SONIC Response") {
      lastResponseIdx = i;
      break;
    }
  }


  return (
    <div className="flex flex-col h-full bg-ink-900 text-slate-200 overflow-hidden font-sans">
      {/* Session Header */}
      <div className="h-10 border-b border-ink-800 bg-ink-900 px-4 flex items-center justify-between text-xs shrink-0 select-none">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-white tracking-wide truncate text-[13px]">
            {sessionName || "New conversation"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {gitBranch && (
            <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-success/10 text-success border border-success/40 text-[11px] font-mono font-medium">
              <GitBranch className="w-3 h-3 text-success" />
              <span>{gitBranch}</span>
            </div>
          )}
          <button
            type="button"
            className="p-1 rounded text-muted hover:text-white hover:bg-ink-800 transition"
            title="Session options"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>
          <button
            type="button"
            className="p-1 rounded text-muted hover:text-white hover:bg-ink-800 transition"
            title="Expand stream"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
          {onToggleRightPanel && (
            <button
              type="button"
              onClick={onToggleRightPanel}
              className="p-1 rounded text-muted hover:text-white hover:bg-ink-800 transition"
              title={rightPanelOpen ? "Hide Computer panel" : "Show Computer panel"}
              aria-label={rightPanelOpen ? "Hide Computer panel" : "Show Computer panel"}
            >
              {rightPanelOpen ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
            </button>
          )}
        </div>
      </div>

      {/* Main Process Timeline */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 text-xs">
        {displayItems.length === 0 ? (
          <div className="h-full min-h-[320px] flex flex-col items-center justify-center text-center p-6 text-muted-dim space-y-2 select-none">
            <div className="w-10 h-10 rounded-full bg-ink-850 border border-ink-800 flex items-center justify-center text-secondary-400 font-mono text-sm shadow-inner">
              &gt;_
            </div>
            <p className="text-xs text-slate-300 font-mono font-medium">Ready</p>
            <p className="text-[11.5px] text-muted-dim max-w-xs leading-relaxed">
              Type an objective or instruction below to operate the graphical workstation.
            </p>
          </div>
        ) : (
          displayItems.map((item, idx) => {
            const itemId = item.id || `item-${idx}`;

            // 1. Thinking / Thought Block (matching Devin's Thought for Xs & v Thinking)
            if (item.type === "thought" || item.title === "Thinking") {
              const thoughtContent = item.content || item.title;
              const isLatestThought = idx === displayItems.length - 1;
              return (
                <ThinkingBlock
                  key={itemId}
                  content={thoughtContent}
                  durationSeconds={item.duration_seconds}
                  initiallyExpanded={isLatestThought}
                />
              );
            }

            // 2. Terminal Shell Command (matching Devin's code pill)
            const isTerminalExec =
              item.type === "command" ||
              Boolean(item.command) ||
              item.title?.includes("TERMINAL_EXEC") ||
              item.title?.toLowerCase().includes("terminal_exec");

            if (isTerminalExec) {
              let cmdText = item.command || "";
              let outText = item.output || item.content || "";
              if (!cmdText) {
                const targetMatch = item.content?.match(/Target:\s*(\{[^}]+\}|[^\n]+)/);
                if (targetMatch) {
                  const rawTarget = targetMatch[1].trim();
                  try {
                    const parsed = JSON.parse(rawTarget);
                    cmdText = parsed.command || rawTarget;
                  } catch {
                    cmdText = rawTarget.replace(/^\{['"]command['"]:\s*['"](.*)['"]\}$/, "$1");
                  }
                } else {
                  cmdText = item.title?.replace(/^Step \d+:\s*/, "") || "command";
                }
              }
              return (
                <CommandBlock
                  key={itemId}
                  command={cmdText}
                  output={outText}
                  durationSeconds={item.duration_seconds}
                  exitCode={item.exit_code}
                />
              );
            }

            // 3. File Operations (matching Devin's Read <file>:<lines> badge)
            const isFileOp =
              item.type === "read" ||
              item.type === "write" ||
              item.title?.startsWith("Read ") ||
              item.title?.startsWith("Write ") ||
              item.title?.includes("FILE_READ") ||
              item.title?.includes("FILE_WRITE");

            if (isFileOp) {
              const opType =
                item.type === "write" ||
                item.title?.startsWith("Write ") ||
                item.title?.includes("FILE_WRITE")
                  ? "write"
                  : "read";
              let targetFile = item.file || "";
              if (!targetFile) {
                const targetMatch = item.content?.match(/Target:\s*([^\n]+)/);
                targetFile = targetMatch ? targetMatch[1].trim() : item.title?.replace(/^(Read|Write)\s+/, "") || "file";
              }
              return (
                <FileActionBlock
                  key={itemId}
                  type={opType}
                  file={targetFile}
                  lines={item.lines}
                  onSelectFile={onSelectFile}
                />
              );
            }

            // 4. GUI & Desktop Interactions (GUI_CLICK, APP_LAUNCH, APP_FOCUS, GUI_TYPE, GUI_WAIT)
            const isGuiOp =
              item.title?.includes("GUI_") ||
              item.title?.includes("APP_") ||
              item.title?.includes("SECURITY_TOOL");

            if (isGuiOp) {
              const actionTitle = item.title?.replace(/^Step \d+:\s*/, "") || "GUI Action";
              let targetText = "";
              const targetMatch = item.content?.match(/Target:\s*([^\n]+)/);
              if (targetMatch) {
                targetText = targetMatch[1].trim();
              }
              const isClick = actionTitle.includes("CLICK");
              const isType = actionTitle.includes("TYPE");
              const isLaunch = actionTitle.includes("LAUNCH") || actionTitle.includes("FOCUS");
              const isSecurity = actionTitle.includes("SECURITY_TOOL");

              const icon = isClick ? (
                <MousePointer className="w-3.5 h-3.5 text-accent-cyan shrink-0" />
              ) : isLaunch ? (
                <AppWindow className="w-3.5 h-3.5 text-secondary-400 shrink-0" />
              ) : isSecurity ? (
                <Shield className="w-3.5 h-3.5 text-accent-purple shrink-0" />
              ) : isType ? (
                <Terminal className="w-3.5 h-3.5 text-accent-amber shrink-0" />
              ) : (
                <Eye className="w-3.5 h-3.5 text-muted-bright shrink-0" />
              );

              return (
                <div key={itemId} className="my-1 flex items-center gap-2 font-mono text-[11px] py-1 px-2.5 rounded-lg bg-ink-850/60 border border-ink-800/80 hover:border-ink-750 transition">
                  {icon}
                  <span className="font-semibold text-slate-200">{actionTitle}</span>
                  {targetText && (
                    <span className="text-secondary-300 bg-ink-900 px-1.5 py-0.5 rounded border border-ink-800 text-[10.5px] truncate max-w-xs font-mono">
                      {targetText}
                    </span>
                  )}
                  {item.duration_seconds && item.duration_seconds > 0 ? (
                    <span className="ml-auto text-[9.5px] text-muted-dim">{item.duration_seconds}s</span>
                  ) : null}
                </div>
              );
            }

            // 5. Desktop Observation Brief Banner
            if (item.title === "Agent Desktop Observation" || item.title === "Agent Visual Computer Use") {
              const isObservation = item.title === "Agent Desktop Observation";
              return (
                <div key={itemId} className="my-1.5 flex items-center gap-2 text-[10.5px] font-mono text-muted-bright py-1 px-2.5 rounded-lg bg-ink-900 border border-ink-800">
                  <Monitor className="w-3.5 h-3.5 text-secondary-400 shrink-0" />
                  <span className="text-slate-300 font-medium">
                    {isObservation ? "🖥️ Desktop Observation Synchronized" : "🎯 Autonomous Visual Objective"}
                  </span>
                  <span className="text-muted-dim text-[9.5px] ml-auto">1280x800</span>
                </div>
              );
            }

            // 4. User Chat Message
            if (item.title === "Objective Received" || item.type === "event" || item.role === "user") {
              const userText = item.content || item.title;
              return (
                <div key={itemId} className="flex justify-end pl-8 my-2 animate-fade-in-up">
                  <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-secondary-900/40 border border-secondary-600/40 px-3.5 py-2.5 text-slate-100 shadow-md">
                    <div className="flex items-center justify-between gap-3 text-[10.5px] text-secondary-400 font-mono font-medium mb-1">
                      <div className="flex items-center gap-1.5">
                        <User className="w-3 h-3 text-secondary-400" />
                        <span>You</span>
                      </div>
                      {item.timestamp && (
                        <span className="text-[9.5px] text-muted-dim font-normal">
                          {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      )}
                    </div>
                    <p className="text-[12.5px] leading-relaxed whitespace-pre-wrap">{userText}</p>
                  </div>
                </div>
              );
            }

            // 5. SONIC Assistant Response
            if (item.type === "response" || item.title === "SONIC Response") {
              const responseText = item.content || "";
              const isCopied = copiedId === itemId;
              const isLast = idx === lastResponseIdx;

              return (
                <div key={itemId} className="space-y-1.5 my-2.5 animate-fade-in-up">
                  <div className="flex justify-start pr-4">
                    <div className="max-w-[92%] rounded-2xl rounded-bl-sm bg-ink-850 border border-ink-750 p-3.5 text-slate-200 shadow-lg">
                      <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-ink-800 text-[10.5px]">
                        <div className="flex items-center gap-1.5 text-secondary-400 font-semibold font-mono">
                          <Bot className="w-3.5 h-3.5 text-secondary-400" />
                          <span>SONIC</span>
                          <span className="text-[9px] text-muted-dim uppercase px-1 rounded bg-ink-900 border border-ink-750">
                            A-SEA
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleCopyResponse(itemId, responseText)}
                          className="flex items-center gap-1 text-muted hover:text-white transition px-1.5 py-0.5 rounded hover:bg-ink-800 text-[10px]"
                          title="Copy response"
                        >
                          {isCopied ? (
                            <>
                              <Check className="w-3 h-3 text-success" />
                              <span className="text-success">Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3 h-3" />
                              <span>Copy</span>
                            </>
                          )}
                        </button>
                      </div>

                      <MarkdownText content={responseText} />
                    </div>
                  </div>

                  {/* Contextual Smart Follow-up Chips directly under latest response */}
                  {isLast && (
                    <div className="pl-1">
                      <FollowupChips onSelect={handleTopicClick} contextText={responseText} />
                    </div>
                  )}
                </div>
              );
            }

            // 6. Parallel Specialist Step (e.g. [NetworkSpecialist] Scanning ports...)
            const specialistMatch =
              item.title?.match(/^\[([a-zA-Z0-9_-]+)\]\s*(.*)/) ||
              item.content?.match(/^\[([a-zA-Z0-9_-]+)\]\s*(.*)/);
            if (specialistMatch) {
              const specialistName = specialistMatch[1];
              const specialistMsg = specialistMatch[2];
              return (
                <div key={itemId} className="my-1 flex items-center gap-2 font-mono text-[11px]">
                  <Shield className="w-3.5 h-3.5 text-secondary-400 shrink-0" />
                  <span className="px-1.5 py-0.2 rounded bg-secondary-950/60 border border-secondary-800 text-secondary-300 font-semibold text-[10px]">
                    {specialistName}
                  </span>
                  <span className="text-muted-bright">{specialistMsg || item.content}</span>
                </div>
              );
            }

            // 7. Generic Action Item
            return (
              <div key={itemId} className="flex items-center gap-2 text-muted text-[11px] py-0.5">
                <Zap className="w-3.5 h-3.5 text-secondary-400 shrink-0" />
                <span className="text-slate-300 font-medium">{item.title}</span>
                {item.content && <span className="text-muted-dim truncate max-w-sm">({item.content})</span>}
              </div>
            );
          })
        )}

        {/* Real-time active thinking / action indicator */}
        {cleanActionText && (
          <div className="pt-2 pb-1 flex items-center gap-2 text-xs text-secondary-400 pl-1 animate-fade-in-up">
            <Brain className="w-3.5 h-3.5 text-secondary-400 animate-pulse shrink-0" />
            <div className="w-1.5 h-1.5 rounded-full bg-secondary-400 animate-ping shrink-0" />
            <span className="text-secondary-300 font-mono font-medium text-[11.5px]">
              {cleanActionText}
            </span>
          </div>
        )}


        <div ref={worklogEndRef} />
      </div>

      {/* Prompt Area */}
      <div className="p-3 border-t border-ink-800 bg-ink-900 space-y-2">
        {/* Input Bar */}
        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-ink-750 bg-ink-850 p-2.5 space-y-2 shadow-lg focus-within:border-secondary-500/70 transition relative"
        >
          <textarea
            ref={textareaRef}
            value={promptText}
            onChange={(e) => setPromptText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit();
              }
            }}
            rows={2}
            placeholder="Instruct SONIC or ask a question (e.g. 'Scan ports', 'Open Burp Suite', 'Audit JWT')..."
            className="w-full resize-none bg-transparent text-[12.5px] text-slate-100 placeholder:text-muted-dim outline-none font-sans px-1 leading-relaxed"
          />

          <div className="flex items-center justify-between pt-0.5">
            <div className="flex items-center gap-1.5 relative">
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setModeMenuOpen(!modeMenuOpen)}
                  className="px-2 py-0.5 rounded-md bg-ink-800 hover:bg-ink-750 border border-ink-700 text-muted-bright hover:text-white flex items-center gap-1 text-[11px] font-medium transition"
                >
                  <Sparkles className="w-3 h-3 text-secondary-400" />
                  <span>{activeMode}</span>
                </button>

                {modeMenuOpen && (
                  <div className="absolute bottom-8 left-0 w-36 rounded-lg bg-ink-850 border border-ink-700 shadow-xl py-1 z-30 text-xs text-muted-bright">
                    {MODES.map((m) => (
                      <div
                        key={m}
                        onClick={() => {
                          setActiveMode(m);
                          setModeMenuOpen(false);
                        }}
                        className={`px-3 py-1.5 hover:bg-ink-800 cursor-pointer flex items-center justify-between text-[11px] ${
                          activeMode === m ? "text-secondary-400 font-semibold" : ""
                        }`}
                      >
                        <span>{m}</span>
                        {activeMode === m && <Check className="w-3 h-3" />}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center gap-1.5">
              {(loading || normalizedStatus === "RUNNING") && onInterrupt && (
                <button
                  type="button"
                  onClick={onInterrupt}
                  className="px-2.5 py-1 rounded-lg bg-danger/20 hover:bg-danger/30 border border-danger/40 text-danger text-xs font-semibold flex items-center gap-1 transition"
                  title="Interrupt current execution"
                >
                  <Square className="w-3 h-3 fill-current" />
                  <span>Stop</span>
                </button>
              )}

              <button
                type="submit"
                disabled={!promptText.trim() || (loading && normalizedStatus === "RUNNING")}
                className="w-7 h-7 rounded-lg bg-secondary-600 hover:bg-secondary-500 disabled:opacity-40 disabled:hover:bg-secondary-600 text-white flex items-center justify-center transition shadow-glow cursor-pointer"
                title="Send instruction"
              >
                {loading && normalizedStatus === "RUNNING" ? (
                  <div className="w-3.5 h-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                ) : (
                  <Send className="w-3.5 h-3.5" />
                )}
              </button>
            </div>

          </div>
        </form>
      </div>
    </div>
  );
}
