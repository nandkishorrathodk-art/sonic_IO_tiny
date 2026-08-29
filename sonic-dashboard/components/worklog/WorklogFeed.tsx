import React, { useState, useRef, useEffect } from "react";
import {
  Clock,
  Terminal as TerminalIcon,
  BookOpen,
  ChevronDown,
  Square,
  Sliders,
  Send,
  Loader2,
  Sparkles,
  Info,
} from "lucide-react";
import { WorklogItem } from "../../types/workstation";

interface WorklogFeedProps {
  worklog: WorklogItem[];
  currentAction?: string;
  loading: boolean;
  onSendPrompt: (prompt: string) => Promise<void>;
  onSelectFile?: (filePath: string) => void;
}

export function WorklogFeed({
  worklog,
  currentAction,
  loading,
  onSendPrompt,
  onSelectFile,
}: WorklogFeedProps) {
  const [promptText, setPromptText] = useState("");
  const worklogEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    worklogEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [worklog, currentAction]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!promptText.trim() || loading) return;
    const text = promptText;
    setPromptText("");
    await onSendPrompt(text);
  };

  return (
    <div className="flex flex-col h-full bg-[#0D0F12] overflow-hidden">
      {/* Scrollable Events Feed */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 font-sans text-xs text-[#8B949E]">
        {worklog.length === 0 ? (
          <div className="text-center py-16 px-4 space-y-2">
            <Sparkles className="w-8 h-8 text-[#58A6FF] mx-auto opacity-70" />
            <h4 className="text-sm font-semibold text-white">Workstation Ready</h4>
            <p className="text-xs text-[#8B949E] max-w-xs mx-auto">
              Assign an autonomous engineering, research, or remediation goal to begin execution.
            </p>
          </div>
        ) : (
          worklog.map((item, idx) => {
            if (item.type === "command") {
              return (
                <div key={item.id || idx} className="space-y-1">
                  <div className="flex items-start gap-2 text-[#C9D1D9] font-mono text-[11px]">
                    <TerminalIcon className="w-3.5 h-3.5 text-[#8B949E] mt-0.5 flex-shrink-0" />
                    <span className="break-all text-[#79C0FF]">$ {item.command}</span>
                  </div>
                  {item.output && (
                    <div className="pl-5 font-mono text-[10px] text-[#8B949E] bg-[#12151A] p-2 rounded border border-[#21262D] whitespace-pre-wrap max-h-48 overflow-y-auto">
                      {item.output}
                    </div>
                  )}
                </div>
              );
            }

            if (item.type === "read") {
              return (
                <div
                  key={item.id || idx}
                  onClick={() => item.file && onSelectFile?.(item.file)}
                  className="flex items-center gap-2 text-[#C9D1D9] font-mono text-[11px] cursor-pointer hover:underline"
                >
                  <BookOpen className="w-3.5 h-3.5 text-[#8B949E]" />
                  <span>
                    Read <span className="text-[#58A6FF]">{item.file}</span>
                    {item.lines ? `:${item.lines}` : ""}
                  </span>
                </div>
              );
            }

            return (
              <div key={item.id || idx} className="rounded-lg border border-[#21262D] bg-[#12151A] p-3 space-y-1">
                <div className="flex items-center gap-2 font-medium text-white text-[11px]">
                  <Info className="w-3.5 h-3.5 text-[#58A6FF]" />
                  <span>{item.title || "Action Event"}</span>
                </div>
                {item.content && (
                  <p className="text-[#8B949E] text-[11px] leading-relaxed font-sans">{item.content}</p>
                )}
              </div>
            );
          })
        )}

        {/* Current Real Action Status */}
        {currentAction && (
          <div className="flex items-center gap-2 text-[#58A6FF] text-xs pt-2">
            <span className="w-1.5 h-1.5 rounded-full bg-[#58A6FF] animate-pulse"></span>
            <span className="text-[#C9D1D9]">{currentAction}</span>
          </div>
        )}

        <div ref={worklogEndRef} />
      </div>

      {/* Mission Prompt Input */}
      <div className="p-3 border-t border-[#21262D] bg-[#12151A]">
        <form onSubmit={handleSubmit} className="rounded-lg border border-[#30363D] bg-[#161B22] p-2.5 space-y-2">
          <input
            type="text"
            value={promptText}
            onChange={(e) => setPromptText(e.target.value)}
            placeholder="Assign autonomous mission objective (e.g. 'Run pytest' or 'Inspect security invariants')..."
            className="w-full bg-transparent text-xs text-[#E6EDF3] placeholder-[#8B949E] outline-none font-sans"
          />
          <div className="flex items-center justify-between pt-1">
            <span className="text-[10px] font-mono text-[#8B949E]">
              Execution Environment: <strong className="text-white">Isolated Sandbox</strong>
            </span>
            <button
              type="submit"
              disabled={loading || !promptText.trim()}
              className="px-3 py-1 bg-white text-black text-xs font-semibold rounded-md flex items-center gap-1.5 hover:bg-slate-200 transition disabled:opacity-40"
            >
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
              <span>Execute</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
