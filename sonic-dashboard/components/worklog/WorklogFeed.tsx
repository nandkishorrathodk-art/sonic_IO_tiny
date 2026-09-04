"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Info,
  Terminal,
  FileCode,
  ChevronDown,
  ChevronRight,
  Plus,
  Mic,
  Send,
  Square,
  Sparkles,
  CheckCircle2,
  GitBranch,
  MoreHorizontal,
  Maximize2,
  PanelRightOpen,
  PanelRightClose,
} from "lucide-react";
import { WorklogItem } from "../../types/workstation";

type Mode = "Normal" | "Autonomous" | "Pair-Program";
const MODES: Mode[] = ["Normal", "Autonomous", "Pair-Program"];

interface WorklogFeedProps {
  worklog: WorklogItem[];
  currentAction?: string;
  loading: boolean;
  onSendPrompt: (prompt: string, mode: Mode) => Promise<void>;
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
  onSendPrompt,
  onSelectFile,
  sessionName = "",
  gitBranch = "",
  rightPanelOpen = true,
  onToggleRightPanel,
}: WorklogFeedProps) {
  const [promptText, setPromptText] = useState("");
  const [activeMode, setActiveMode] = useState<Mode>("Normal");
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>({});
  const [isRecording, setIsRecording] = useState(false);
  const worklogEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    worklogEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [worklog, currentAction]);

  const toggleExpand = (id: string) => {
    setExpandedItems((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!promptText.trim() || loading) return;
    const text = promptText;
    setPromptText("");
    await onSendPrompt(text, activeMode);
  };

  const displayItems: WorklogItem[] = worklog || [];

  return (
    <div className="flex flex-col h-full bg-ink-900 text-slate-200 overflow-hidden font-sans">
      {/* Session header */}
      <div className="h-10 border-b border-ink-800 bg-ink-900 px-4 flex items-center justify-between text-xs shrink-0">
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
          <button type="button" className="p-1 rounded text-muted hover:text-white hover:bg-ink-800 transition" title="Session options">
            <MoreHorizontal className="w-4 h-4" />
          </button>
          <button type="button" className="p-1 rounded text-muted hover:text-white hover:bg-ink-800 transition" title="Expand stream">
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

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 text-xs text-muted">
        {displayItems.length === 0 && (
          <div className="max-w-md mx-auto text-center py-20 px-4 space-y-3 animate-fade-in-up">
            <div className="w-10 h-10 rounded-xl bg-ink-850 border border-ink-700 flex items-center justify-center mx-auto">
              <Sparkles className="w-5 h-5 text-secondary-400" />
            </div>
            <h4 className="text-base font-semibold text-white">What should SONIC work on?</h4>
            <p className="text-xs text-muted max-w-xs mx-auto">Start a conversation to see real agent activity here.</p>
          </div>
        )}
        {displayItems.map((item, idx) => {
          const itemId = item.id || `item-${idx}`;
          const isExpanded = expandedItems[itemId] ?? (item.title === "Thinking" || item.type === "command");

          if (item.type === "thought") {
            const titleText = item.title || "Agent reasoning";
            return (
              <div key={itemId} className="space-y-1">
                <div
                  onClick={() => item.content && toggleExpand(itemId)}
                  className="inline-flex items-center gap-2 text-muted hover:text-muted-bright cursor-pointer text-[12px] py-0.5 transition"
                >
                  <Info className="w-3.5 h-3.5 text-muted shrink-0" />
                  <span>{titleText}</span>
                </div>
                {item.content && expandedItems[itemId] && (
                  <div className="pl-5 text-[11px] text-muted-dim leading-relaxed max-w-lg">{item.content}</div>
                )}
              </div>
            );
          }

          if (item.type === "response") {
            return (
              <div key={itemId} className="flex justify-start pr-8 my-2 animate-fade-in-up">
                <div className="max-w-[90%] rounded-2xl rounded-bl-sm bg-ink-850 border border-ink-700 px-4 py-2.5 text-slate-200 text-xs">
                  <div className="text-[10px] text-secondary-400 font-medium mb-0.5">SONIC</div>
                  <p className="text-[12px] leading-relaxed whitespace-pre-wrap">{item.content}</p>
                </div>
              </div>
            );
          }

          if (item.type === "command") {
            return (
              <div key={itemId} className="space-y-1 my-1">
                <div
                  onClick={() => toggleExpand(itemId)}
                  className="flex items-start gap-2 text-muted-bright font-mono text-[11px] hover:text-white cursor-pointer py-0.5 group"
                >
                  <Terminal className="w-3.5 h-3.5 text-muted mt-0.5 shrink-0 group-hover:text-secondary-400" />
                  <span className="break-all text-secondary-400 leading-snug">{item.command || item.title}</span>
                </div>
                {item.output && isExpanded && (
                  <div className="ml-5 font-mono text-[10px] text-muted bg-ink-950 p-2.5 rounded-md border border-ink-700 whitespace-pre-wrap max-h-36 overflow-y-auto leading-relaxed">
                    {item.output}
                  </div>
                )}
              </div>
            );
          }

          if (item.type === "read") {
            const fileName = item.file || item.title.replace(/^Read\s+/, "");
            const lineInfo = item.lines ? `:${item.lines}` : "";
            return (
              <div
                key={itemId}
                onClick={() => { if (item.file && onSelectFile) onSelectFile(item.file); }}
                className="flex items-center gap-2 text-muted-bright font-mono text-[11px] cursor-pointer hover:underline py-0.5 group"
              >
                <FileCode className="w-3.5 h-3.5 text-muted group-hover:text-secondary-400 shrink-0" />
                <span className="text-muted group-hover:text-muted-bright">
                  Read <span className="text-secondary-400 font-medium">{fileName}{lineInfo}</span>
                </span>
              </div>
            );
          }

          if (item.title === "Objective Received") {
            return (
              <div key={itemId} className="flex justify-end pl-8 my-2 animate-fade-in-up">
                <div className="max-w-[90%] rounded-2xl rounded-br-sm bg-primary-600/20 border border-primary-500/40 px-4 py-2.5 text-slate-100 text-xs">
                  <div className="text-[10px] text-primary-400 font-medium mb-0.5">You</div>
                  <p className="text-[12px] leading-relaxed">{item.content || item.title}</p>
                </div>
              </div>
            );
          }

          if (item.title === "Thinking" || item.type === "action") {
            const isPureThinking = item.title === "Thinking";
            const displayTitle = isPureThinking ? "Thinking" : (item.title || "Action Executed");
            return (
              <div key={itemId} className="rounded-lg border border-ink-700 bg-ink-850 p-3 space-y-2 my-2 shadow-sm">
                <div
                  onClick={() => toggleExpand(itemId)}
                  className="flex items-center justify-between cursor-pointer text-muted-bright hover:text-white font-medium text-[12px]"
                >
                  <div className="flex items-center gap-1.5">
                    {isExpanded ? <ChevronDown className="w-3.5 h-3.5 text-muted" /> : <ChevronRight className="w-3.5 h-3.5 text-muted" />}
                    <span className={isPureThinking ? "text-cyan-400 font-medium" : "text-white font-medium"}>{displayTitle}</span>
                  </div>
                </div>
                {isExpanded && item.content && (
                  <div className="pt-1 text-[12px] leading-relaxed text-muted font-sans whitespace-pre-wrap">
                    {item.content}
                  </div>
                )}
              </div>
            );
          }

          if (item.type === "event") {
            return (
              <div key={itemId} className="flex justify-end pl-8 my-2 animate-fade-in-up">
                <div className="max-w-[90%] rounded-2xl rounded-br-sm bg-ink-800 border border-ink-700 px-4 py-2.5 text-slate-200 text-xs">
                  <div className="text-[10px] text-secondary-400 font-medium mb-0.5">You</div>
                  <p className="text-[12px] leading-relaxed">{item.content || item.title}</p>
                </div>
              </div>
            );
          }

          return (
            <div key={itemId} className="flex items-center gap-2 text-muted text-[11px] py-0.5">
              <Info className="w-3.5 h-3.5 text-muted shrink-0" />
              <span>{item.title}</span>
            </div>
          );
        })}

        {currentAction && (
          <div className="pt-3 pb-1 flex items-center gap-2.5 text-xs text-secondary-400 pl-0.5">
            <div className="w-3.5 h-3.5 rounded-full border-2 border-secondary-400 border-t-transparent animate-spin shrink-0" />
            <span className="text-secondary-400 font-medium text-[12px]">{currentAction}</span>
          </div>
        )}
        <div ref={worklogEndRef} />
      </div>

      {/* Prompt input */}
      <div className="p-3 border-t border-ink-800 bg-ink-900">
        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-ink-700 bg-ink-850 p-2.5 space-y-2 shadow-lg focus-within:border-secondary-500/60 transition relative"
        >
          <textarea
            value={promptText}
            onChange={(e) => setPromptText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
            rows={2}
            placeholder="Guide SONIC while it works"
            className="w-full resize-none bg-transparent text-[13px] text-slate-100 placeholder:text-muted-dim outline-none font-sans px-1"
          />

          <div className="flex items-center justify-between pt-0.5">
            <div className="flex items-center gap-1.5 relative">
              <button
                type="button"
                className="w-6 h-6 rounded-full border border-ink-700 text-muted hover:text-white hover:border-muted flex items-center justify-center transition"
                title="Attach context / file"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>

              <div className="relative">
                <button
                  type="button"
                  onClick={() => setModeMenuOpen(!modeMenuOpen)}
                  className="px-2 py-0.5 rounded-md bg-ink-800 hover:bg-ink-700 border border-ink-700 text-muted-bright hover:text-white flex items-center gap-1 text-[11px] font-medium transition"
                >
                  <Sparkles className="w-3 h-3 text-secondary-400" />
                  <span>{activeMode}</span>
                  <ChevronDown className="w-2.5 h-2.5 text-muted" />
                </button>

                {modeMenuOpen && (
                  <div className="absolute bottom-8 left-0 w-36 rounded-lg bg-ink-850 border border-ink-700 shadow-xl py-1 z-30 text-xs text-muted-bright">
                    {MODES.map((m) => (
                      <div
                        key={m}
                        onClick={() => { setActiveMode(m); setModeMenuOpen(false); }}
                        className="px-3 py-1.5 hover:bg-ink-800 cursor-pointer flex items-center justify-between"
                      >
                        <span>{m}</span>
                        {activeMode === m && <CheckCircle2 className="w-3 h-3 text-success" />}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIsRecording(!isRecording)}
                className={`p-1.5 rounded-full transition ${
                  isRecording
                    ? "bg-danger/20 text-danger border border-danger/50 animate-pulse"
                    : "text-muted hover:text-white hover:bg-ink-800"
                }`}
                title={isRecording ? "Stop voice dictation" : "Voice dictation"}
              >
                <Mic className="w-4 h-4" />
              </button>

              <button
                type="submit"
                disabled={loading && !promptText.trim()}
                className="w-7 h-7 rounded-full bg-white text-ink-950 hover:bg-slate-200 flex items-center justify-center transition disabled:opacity-40"
                title={loading ? "Interrupt agent" : "Send instruction"}
              >
                {loading ? <Square className="w-3 h-3 fill-current" /> : <Send className="w-3.5 h-3.5 fill-current ml-0.5" />}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
