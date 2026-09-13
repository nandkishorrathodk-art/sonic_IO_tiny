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
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Play,
  X,
  Loader2,
  ShieldAlert,
} from "lucide-react";
import { WorklogItem } from "../../types/workstation";
import { api } from "../../lib/api";
import { MarkdownText } from "./MarkdownText";
import { ThinkingBlock } from "./ThinkingBlock";
import { CommandBlock } from "./CommandBlock";
import { FileActionBlock } from "./FileActionBlock";

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
  sessionId?: string;
  onRefreshState?: () => void;
}

function ProbeProposalCard({
  item,
  sessionId = "default",
  onActionComplete,
}: {
  item: WorklogItem;
  sessionId?: string;
  onActionComplete?: () => void;
}) {
  const [loadingActionId, setLoadingActionId] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { status: string; output?: string }>>({});
  const [error, setError] = useState<string | null>(null);

  const actions: any[] =
    item.proposed_actions && item.proposed_actions.length > 0
      ? item.proposed_actions
      : (item as any).action_id
      ? [{ action_id: (item as any).action_id, tool: item.title, input: { tool: "probe", target: item.content } }]
      : [];

  const handleApprove = async (actionId: string) => {
    setLoadingActionId(actionId);
    setError(null);
    try {
      const res = await api.approveMissionProbe(actionId, true, sessionId);
      setResults((prev) => ({
        ...prev,
        [actionId]: { status: res?.status || "SUCCESS", output: res?.output },
      }));
      onActionComplete?.();
    } catch (err: any) {
      setError(err?.message || "Failed to execute approved probe");
    } finally {
      setLoadingActionId(null);
    }
  };

  const handleDismiss = async (actionId: string) => {
    setLoadingActionId(actionId);
    setError(null);
    try {
      const res = await api.approveMissionProbe(actionId, false, sessionId);
      setResults((prev) => ({
        ...prev,
        [actionId]: { status: "dismissed" },
      }));
      onActionComplete?.();
    } catch (err: any) {
      setError(err?.message || "Failed to dismiss probe");
    } finally {
      setLoadingActionId(null);
    }
  };

  return (
    <div className="my-2.5 rounded-xl border border-amber-500/40 bg-amber-500/5 p-3.5 text-xs shadow-md">
      <div className="flex items-center gap-2 mb-2">
        <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0" />
        <span className="font-semibold text-slate-100 text-[12.5px]">
          {item.title || "Operator Approval Required: Active Security Probes"}
        </span>
        <span className="ml-auto px-2 py-0.5 rounded bg-amber-500/20 border border-amber-500/30 text-amber-400 font-mono font-semibold text-[10px]">
          OPERATOR-GATED
        </span>
      </div>

      {item.content && (
        <p className="text-[11.5px] text-slate-300 leading-relaxed mb-3 whitespace-pre-wrap">
          {item.content}
        </p>
      )}

      {error && (
        <div className="mb-2.5 p-2 rounded bg-rose-500/10 border border-rose-500/30 text-rose-400 text-[11px] flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {actions.length > 0 && (
        <div className="space-y-2">
          {actions.map((act: any, idx: number) => {
            const actId = act.action_id || `probe-${idx}`;
            const toolName = act.input?.tool || act.tool || "probe";
            const targetHost = act.input?.target || act.target || "";
            const options = act.input?.options || {};
            const preview =
              act.command ||
              (options.args ? `${toolName} ${options.args} ${targetHost}` : `${toolName} ${targetHost}`);
            const resultState = results[actId];
            const isProcessing = loadingActionId === actId;

            return (
              <div
                key={actId}
                className="p-2.5 rounded-lg bg-ink-900/90 border border-ink-750 flex flex-col gap-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="px-2 py-0.5 rounded bg-secondary-500/20 border border-secondary-500/40 text-secondary-300 font-mono font-semibold text-[11px] uppercase">
                      {toolName}
                    </span>
                    <span className="text-slate-200 font-mono text-[11.5px] truncate" title={targetHost}>
                      Target: <span className="text-cyan-400 font-mono">{targetHost}</span>
                    </span>
                  </div>

                  {resultState ? (
                    <span
                      className={`px-2 py-0.5 rounded font-mono text-[10px] font-medium ${
                        resultState.status === "dismissed"
                          ? "bg-ink-800 text-muted-dim border border-ink-700"
                          : resultState.status === "SUCCESS"
                          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                          : "bg-rose-500/20 text-rose-400 border border-rose-500/40"
                      }`}
                    >
                      {resultState.status === "dismissed" ? "DISMISSED" : resultState.status}
                    </span>
                  ) : (
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        type="button"
                        disabled={isProcessing}
                        onClick={() => handleApprove(actId)}
                        className="px-2.5 py-1 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-[11px] flex items-center gap-1 transition shadow-sm disabled:opacity-50"
                      >
                        {isProcessing ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Play className="w-3 h-3 fill-current" />
                        )}
                        <span>Approve &amp; Run</span>
                      </button>
                      <button
                        type="button"
                        disabled={isProcessing}
                        onClick={() => handleDismiss(actId)}
                        className="px-2 py-1 rounded-md bg-ink-800 hover:bg-ink-750 text-slate-300 hover:text-white border border-ink-700 text-[11px] flex items-center gap-1 transition disabled:opacity-50"
                      >
                        <X className="w-3 h-3" />
                        <span>Dismiss</span>
                      </button>
                    </div>
                  )}
                </div>

                {preview && (
                  <div className="font-mono text-[10.5px] text-muted-bright bg-ink-950 px-2 py-1 rounded border border-ink-800 truncate">
                    <code>$ {preview}</code>
                  </div>
                )}

                {resultState?.output && (
                  <div className="mt-1 font-mono text-[10.5px] text-slate-300 bg-ink-950 p-2 rounded border border-ink-800 max-h-32 overflow-y-auto whitespace-pre-wrap">
                    {resultState.output}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SubReportCard({ item }: { item: WorklogItem }) {
  const [expanded, setExpanded] = useState(false);
  const isSuccess = item.success !== false && !item.content?.toLowerCase().includes("subagent execution failed");
  const subNum = item.sub_agent_number ?? item.title?.match(/SubAgent #(\d+)/)?.[1] ?? "";

  return (
    <div className="my-2 rounded-xl border border-ink-750 bg-ink-850/80 p-3 text-xs shadow-sm transition hover:border-ink-700">
      <div
        className="flex items-center justify-between cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded-md bg-secondary-500/10 border border-secondary-500/30 text-secondary-300 font-mono font-semibold text-[11px]">
            SubAgent {subNum ? `#${subNum}` : ""}
          </span>
          <span className="font-semibold text-slate-200 text-[12px]">{item.title}</span>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-medium ${
              isSuccess
                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
            }`}
          >
            {isSuccess ? "SUCCESS" : "FAILED"}
          </span>
        </div>
        <div className="flex items-center gap-2 text-muted-dim text-[11px]">
          {item.duration_seconds ? <span>{item.duration_seconds}s</span> : null}
          <button type="button" className="p-0.5 hover:text-white transition">
            {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {item.goal && (
        <div className="mt-2 text-[11.5px] text-muted-bright bg-ink-900/60 p-2 rounded-lg border border-ink-800/80">
          <span className="text-secondary-400 font-mono text-[10.5px] block font-medium mb-0.5">Objective:</span>
          {item.goal}
        </div>
      )}

      {expanded && (
        <div className="mt-2.5 pt-2.5 border-t border-ink-800 space-y-2 text-[11.5px] text-slate-300">
          <div>
            <span className="text-secondary-400 font-mono text-[10.5px] block font-medium mb-1">Findings Summary:</span>
            <div className="bg-ink-900/80 p-2.5 rounded-lg border border-ink-800 whitespace-pre-wrap font-sans leading-relaxed">
              {item.findings_summary || item.content || "No summary recorded."}
            </div>
          </div>
          {item.key_discoveries && item.key_discoveries.length > 0 && (
            <div>
              <span className="text-secondary-400 font-mono text-[10.5px] block font-medium mb-1">Key Discoveries:</span>
              <div className="flex flex-wrap gap-1.5">
                {item.key_discoveries.map((disc: string, dIdx: number) => (
                  <span key={dIdx} className="px-2 py-0.5 rounded bg-ink-900 text-secondary-300 border border-secondary-900/60 font-mono text-[10.5px]">
                    {disc}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SubDispatchPill({ item }: { item: WorklogItem }) {
  const subNum = item.sub_agent_number ?? item.title?.match(/SubAgent #(\d+)/)?.[1] ?? "";
  return (
    <div className="my-1.5 flex items-center gap-2 rounded-lg bg-secondary-950/40 border border-secondary-500/20 px-2.5 py-1.5 text-xs text-secondary-200">
      <Zap className="w-3.5 h-3.5 text-secondary-400 animate-pulse shrink-0" />
      <span className="font-mono font-semibold text-[11px] text-secondary-300">
        Dispatching SubAgent {subNum ? `#${subNum}` : ""}
      </span>
      <span className="text-muted-bright text-[11px] truncate max-w-md">
        {item.goal || item.content?.replace(/^Goal:\s*/, "").split("\n")[0] || ""}
      </span>
    </div>
  );
}

function PhaseCompleteBanner({ item }: { item: WorklogItem }) {
  return (
    <div className="my-3 flex items-center gap-2 rounded-xl bg-ink-850 border border-secondary-500/30 px-3 py-2 text-xs">
      <Check className="w-4 h-4 text-secondary-400 shrink-0" />
      <span className="font-semibold text-slate-100">{item.title}</span>
      <span className="text-muted-dim text-[11px] ml-auto font-mono">{item.content}</span>
    </div>
  );
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
  sessionId = "default",
  onRefreshState,
}: WorklogFeedProps) {
  const [promptText, setPromptText] = useState("");
  const [activeMode, setActiveMode] = useState<Mode>("Normal");
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const worklogEndRef = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const shouldFollowTailRef = useRef(true);
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
    const timeline = timelineRef.current;
    if (!timeline || !shouldFollowTailRef.current) return;
    // Keep live output readable without overriding an operator who is
    // reviewing an earlier event in the same conversation.
    timeline.scrollTop = timeline.scrollHeight;
  }, [worklog, cleanActionText]);

  useEffect(() => {
    // A newly selected conversation should start at its latest event.
    shouldFollowTailRef.current = true;
  }, [sessionId]);

  const handleTimelineScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const timeline = event.currentTarget;
    const distanceFromBottom = timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight;
    // Once the operator scrolls away from the tail, pause auto-follow. It is
    // re-enabled only when they deliberately return to the bottom.
    shouldFollowTailRef.current = distanceFromBottom <= 24;
  };

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
      <div
        ref={timelineRef}
        onScroll={handleTimelineScroll}
        className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 py-3 space-y-2 text-xs"
      >
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

            // 0. Operator Gate / Active Probe Approval Proposals
            const isApprovalProposal =
              item.type === "approval" ||
              (item.proposed_actions && item.proposed_actions.length > 0) ||
              item.title?.toLowerCase().includes("probe proposal") ||
              item.title?.toLowerCase().includes("awaiting operator approval");

            if (isApprovalProposal) {
              return (
                <ProbeProposalCard
                  key={itemId}
                  item={item}
                  sessionId={sessionId}
                  onActionComplete={onRefreshState}
                />
              );
            }

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

            // 7. SubAgent Reports
            const isSubReport =
              (item.title?.includes("SubAgent") && item.title?.includes("Report")) ||
              (item.type === "info" && item.title?.startsWith("SubAgent #"));
            if (isSubReport) {
              return <SubReportCard key={itemId} item={item} />;
            }

            // 8. SubAgent Dispatches
            if (item.title?.startsWith("Dispatching SubAgent")) {
              return <SubDispatchPill key={itemId} item={item} />;
            }

            // 9. Phase Completion
            if (item.title?.startsWith("Phase ") && item.title?.includes("Complete")) {
              return <PhaseCompleteBanner key={itemId} item={item} />;
            }

            // 10. Generic Action Item
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
            placeholder="Instruct SONIC or ask a question about a supplied target, application, or workspace..."
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
