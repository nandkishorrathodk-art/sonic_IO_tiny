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
} from "lucide-react";
import { WorklogItem } from "../../types/workstation";

interface WorklogFeedProps {
  worklog: WorklogItem[];
  currentAction?: string;
  loading: boolean;
  onSendPrompt: (prompt: string) => Promise<void>;
  onSelectFile?: (filePath: string) => void;
  sessionName?: string;
  gitBranch?: string;
}

export function WorklogFeed({
  worklog,
  currentAction,
  loading,
  onSendPrompt,
  onSelectFile,
  sessionName = "",
  gitBranch = "",
}: WorklogFeedProps) {
  const [promptText, setPromptText] = useState("");
  const [activeMode, setActiveMode] = useState<"Normal" | "Autonomous" | "Pair-Program">("Normal");
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>({});
  const [isRecording, setIsRecording] = useState(false);
  const worklogEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    worklogEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [worklog, currentAction]);

  const toggleExpand = (id: string) => {
    setExpandedItems((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!promptText.trim() || loading) return;
    const text = promptText;
    setPromptText("");
    await onSendPrompt(text);
  };

  // Empty means a genuinely new chat. Never seed fabricated timeline entries.
  const displayItems: WorklogItem[] = worklog || [];

  return (
    <div className="flex flex-col h-full bg-[#0D1117] text-[#C9D1D9] overflow-hidden select-none font-sans">
      {/* Devin Stream Session Header */}
      <div className="h-10 border-b border-[#21262D] bg-[#0D1117] px-4 flex items-center justify-between text-xs shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-white tracking-wide truncate text-[13px]">
            {sessionName || "New conversation"}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Real Git metadata only appears after the backend returns it. */}
          {gitBranch && (
            <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#1F2E23] text-[#3FB950] border border-[#238636]/40 text-[11px] font-mono font-medium">
              <GitBranch className="w-3 h-3 text-[#3FB950]" />
              <span>{gitBranch}</span>
            </div>
          )}

          <button
            type="button"
            className="p-1 rounded text-[#8B949E] hover:text-white hover:bg-[#21262D] transition"
            title="Session options"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>
          <button
            type="button"
            className="p-1 rounded text-[#8B949E] hover:text-white hover:bg-[#21262D] transition"
            title="Expand stream"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Timeline Stream */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 text-xs text-[#8B949E]">
        {displayItems.length === 0 && (
          <div className="max-w-md mx-auto text-center py-20 px-4 space-y-3">
            <div className="w-10 h-10 rounded-xl bg-[#1C2430] border border-[#303B4A] flex items-center justify-center mx-auto">
              <Sparkles className="w-5 h-5 text-[#8AB4F8]" />
            </div>
            <h4 className="text-base font-semibold text-white">What should SONIC work on?</h4>
            <p className="text-xs text-[#8B949E] max-w-xs mx-auto">Start a conversation to see real agent activity here.</p>
          </div>
        )}
        {displayItems.map((item, idx) => {
          const itemId = item.id || `item-${idx}`;
          const isExpanded = expandedItems[itemId] ?? (item.title === "Thinking" || item.type === "command");

          // 1. Real thought entry. Never invent a duration or content.
          if (item.type === "thought") {
            const titleText = item.title || "Agent reasoning";

            return (
              <div key={itemId} className="space-y-1">
                <div
                  onClick={() => item.content && toggleExpand(itemId)}
                  className="inline-flex items-center gap-2 text-[#8B949E] hover:text-[#C9D1D9] cursor-pointer text-[12px] font-sans py-0.5 transition"
                >
                  <Info className="w-3.5 h-3.5 text-[#8B949E] shrink-0" />
                  <span className="font-normal">{titleText}</span>
                </div>
                {item.content && expandedItems[itemId] && (
                  <div className="pl-5 text-[11px] text-[#7D8590] leading-relaxed max-w-lg">
                    {item.content}
                  </div>
                )}
              </div>
            );
          }

          // 2. Terminal command block
          if (item.type === "command") {
            return (
              <div key={itemId} className="space-y-1 my-1">
                <div
                  onClick={() => toggleExpand(itemId)}
                  className="flex items-start gap-2 text-[#C9D1D9] font-mono text-[11px] hover:text-white cursor-pointer py-0.5 group"
                >
                  <Terminal className="w-3.5 h-3.5 text-[#8B949E] mt-0.5 shrink-0 group-hover:text-[#58A6FF]" />
                  <span className="break-all text-[#79C0FF] leading-snug">
                    {item.command || item.title}
                  </span>
                </div>
                {item.output && isExpanded && (
                  <div className="ml-5 font-mono text-[10px] text-[#8B949E] bg-[#161B22] p-2.5 rounded-md border border-[#21262D] whitespace-pre-wrap max-h-36 overflow-y-auto leading-relaxed">
                    {item.output}
                  </div>
                )}
              </div>
            );
          }

          // 3. Real filesystem read action
          if (item.type === "read") {
            const fileName = item.file || item.title.replace(/^Read\s+/, "");
            const lineInfo = item.lines ? `:${item.lines}` : "";

            return (
              <div
                key={itemId}
                onClick={() => {
                  if (item.file && onSelectFile) {
                    onSelectFile(item.file);
                  }
                }}
                className="flex items-center gap-2 text-[#C9D1D9] font-mono text-[11px] cursor-pointer hover:underline py-0.5 group"
              >
                <FileCode className="w-3.5 h-3.5 text-[#8B949E] group-hover:text-[#58A6FF] shrink-0" />
                <span className="text-[#8B949E] group-hover:text-[#C9D1D9]">
                  Read{" "}
                  <span className="text-[#58A6FF] font-medium">
                    {fileName}
                    {lineInfo}
                  </span>
                </span>
              </div>
            );
          }

          // User objective must stay a chat bubble, even though the API marks
          // it as an action event.
          if (item.title === "Objective Received") {
            return (
              <div key={itemId} className="flex justify-end pl-8 my-2">
                <div className="max-w-[90%] rounded-2xl rounded-br-sm bg-[#263445] border border-[#3A4D66] px-4 py-2.5 text-[#E6EDF3] text-xs">
                  <div className="text-[10px] text-[#9FBCE4] font-medium mb-0.5">You</div>
                  <p className="text-[12px] leading-relaxed">{item.content || item.title}</p>
                </div>
              </div>
            );
          }

          // 4. Expandable agent action/thinking block (⌄ Thinking)
          if (item.title === "Thinking" || item.type === "action") {
            return (
              <div
                key={itemId}
                className="rounded-lg border border-[#21262D] bg-[#161B22] p-3 space-y-2 my-2 shadow-sm"
              >
                <div
                  onClick={() => toggleExpand(itemId)}
                  className="flex items-center justify-between cursor-pointer text-[#C9D1D9] hover:text-white font-medium text-[12px]"
                >
                  <div className="flex items-center gap-1.5">
                    {isExpanded ? (
                      <ChevronDown className="w-3.5 h-3.5 text-[#8B949E]" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 text-[#8B949E]" />
                    )}
                    <span className="text-white font-medium">Thinking</span>
                  </div>
                </div>

                {isExpanded && item.content && (
                  <div className="pt-1 text-[12px] leading-relaxed text-[#8B949E] font-sans whitespace-pre-wrap selection:bg-[#1F6FEB]/30">
                    {item.content}
                  </div>
                )}
              </div>
            );
          }

          // 5. Legacy event bubble (only when supplied by the backend)
          if (item.type === "event" || item.title === "Objective Received") {
            return (
              <div key={itemId} className="flex justify-end pl-8 my-2">
                <div className="max-w-[90%] rounded-2xl rounded-br-sm bg-[#1F242C] border border-[#30363D] px-4 py-2.5 text-[#E6EDF3] text-xs">
                  <div className="text-[10px] text-[#58A6FF] font-medium mb-0.5">You</div>
                  <p className="text-[12px] leading-relaxed">{item.content || item.title}</p>
                </div>
              </div>
            );
          }

          // Fallback Generic Event
          return (
            <div key={itemId} className="flex items-center gap-2 text-[#8B949E] text-[11px] py-0.5">
              <Info className="w-3.5 h-3.5 text-[#8B949E] shrink-0" />
              <span>{item.title}</span>
            </div>
          );
        })}

        {/* Live Status Footer with rotating spinner */}
        {currentAction && (
          <div className="pt-3 pb-1 flex items-center gap-2.5 text-xs text-[#58A6FF] pl-0.5">
            <div className="w-3.5 h-3.5 rounded-full border-2 border-[#58A6FF] border-t-transparent animate-spin shrink-0"></div>
            <span className="text-[#58A6FF] font-medium text-[12px]">{currentAction}</span>
          </div>
        )}

        <div ref={worklogEndRef} />
      </div>

      {/* Devin Bottom Prompt Input Bar: "Guide SONIC while it works" */}
      <div className="p-3 border-t border-[#21262D] bg-[#0D1117]">
        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-[#30363D] bg-[#161B22] p-2.5 space-y-2 shadow-lg focus-within:border-[#58A6FF]/60 transition relative"
        >
          {/* Text Area */}
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
            className="w-full resize-none bg-transparent text-[13px] text-[#E6EDF3] placeholder-[#6E7681] outline-none font-sans px-1"
          />

          {/* Bottom Toolbar inside the pill */}
          <div className="flex items-center justify-between pt-0.5">
            {/* Left Options */}
            <div className="flex items-center gap-1.5 relative">
              {/* + Attach Context Button */}
              <button
                type="button"
                className="w-6 h-6 rounded-full border border-[#30363D] text-[#8B949E] hover:text-white hover:border-[#8B949E] flex items-center justify-center transition"
                title="Attach context / file"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>

              {/* Mode Selector Pill (Normal / Autonomous) */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setModeMenuOpen(!modeMenuOpen)}
                  className="px-2 py-0.5 rounded-md bg-[#21262D] hover:bg-[#30363D] border border-[#30363D] text-[#C9D1D9] hover:text-white flex items-center gap-1 text-[11px] font-medium transition"
                >
                  <Sparkles className="w-3 h-3 text-[#58A6FF]" />
                  <span>{activeMode}</span>
                  <ChevronDown className="w-2.5 h-2.5 text-[#8B949E]" />
                </button>

                {/* Dropdown Menu */}
                {modeMenuOpen && (
                  <div className="absolute bottom-8 left-0 w-36 rounded-lg bg-[#161B22] border border-[#30363D] shadow-xl py-1 z-30 text-xs text-[#C9D1D9]">
                    <div
                      onClick={() => {
                        setActiveMode("Normal");
                        setModeMenuOpen(false);
                      }}
                      className="px-3 py-1.5 hover:bg-[#21262D] cursor-pointer flex items-center justify-between"
                    >
                      <span>Normal</span>
                      {activeMode === "Normal" && <CheckCircle2 className="w-3 h-3 text-[#3FB950]" />}
                    </div>
                    <div
                      onClick={() => {
                        setActiveMode("Autonomous");
                        setModeMenuOpen(false);
                      }}
                      className="px-3 py-1.5 hover:bg-[#21262D] cursor-pointer flex items-center justify-between"
                    >
                      <span>Autonomous</span>
                      {activeMode === "Autonomous" && <CheckCircle2 className="w-3 h-3 text-[#3FB950]" />}
                    </div>
                    <div
                      onClick={() => {
                        setActiveMode("Pair-Program");
                        setModeMenuOpen(false);
                      }}
                      className="px-3 py-1.5 hover:bg-[#21262D] cursor-pointer flex items-center justify-between"
                    >
                      <span>Pair-Program</span>
                      {activeMode === "Pair-Program" && <CheckCircle2 className="w-3 h-3 text-[#3FB950]" />}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Right Controls: Mic + Send/Stop Button */}
            <div className="flex items-center gap-2">
              {/* Mic Dictation */}
              <button
                type="button"
                onClick={() => setIsRecording(!isRecording)}
                className={`p-1.5 rounded-full transition ${
                  isRecording
                    ? "bg-red-500/20 text-red-400 border border-red-500/50 animate-pulse"
                    : "text-[#8B949E] hover:text-white hover:bg-[#21262D]"
                }`}
                title={isRecording ? "Stop voice dictation" : "Voice dictation"}
              >
                <Mic className="w-4 h-4" />
              </button>

              {/* Circular Send / Stop button */}
              <button
                type="submit"
                disabled={loading && !promptText.trim()}
                className="w-7 h-7 rounded-full bg-white text-black hover:bg-[#E6EDF3] flex items-center justify-center transition disabled:opacity-40"
                title={loading ? "Interrupt agent" : "Send instruction"}
              >
                {loading ? (
                  <Square className="w-3 h-3 fill-black text-black" />
                ) : (
                  <Send className="w-3.5 h-3.5 fill-black text-black ml-0.5" />
                )}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
