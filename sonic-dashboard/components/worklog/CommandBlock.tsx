"use client";

import React, { useState } from "react";
import { Terminal, ChevronDown, ChevronRight, Copy, Check } from "lucide-react";

interface CommandBlockProps {
  command: string;
  output?: string;
  durationSeconds?: number;
  exitCode?: number;
  initiallyExpanded?: boolean;
}

export function CommandBlock({
  command,
  output,
  durationSeconds,
  exitCode,
  initiallyExpanded = false,
}: CommandBlockProps) {
  const [expanded, setExpanded] = useState(initiallyExpanded);
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  const hasOutput = Boolean(output && output.trim().length > 0);

  return (
    <div className="my-1 font-mono text-[11px] select-text">
      {/* Command Pill */}
      <div
        onClick={() => hasOutput && setExpanded(!expanded)}
        className={`flex items-start justify-between gap-2.5 px-2.5 py-1.5 rounded-lg border border-ink-800/90 bg-ink-950 hover:bg-ink-900/60 hover:border-ink-700 transition ${
          hasOutput ? "cursor-pointer" : "cursor-default"
        } group`}
        title={hasOutput ? (expanded ? "Click to collapse output" : "Click to view real sandbox output") : undefined}
      >
        <div className="flex items-start gap-2 min-w-0 flex-1">
          <Terminal className="w-3.5 h-3.5 text-muted-dim mt-0.5 shrink-0 group-hover:text-secondary-400 transition" />
          <span className="text-slate-300 group-hover:text-white break-all leading-snug font-medium">
            {command}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 ml-2">
          {durationSeconds !== undefined && durationSeconds > 0 && (
            <span className="text-[10px] text-muted-dim px-1.5 py-0.2 rounded bg-ink-900 border border-ink-800">
              {Math.max(0.1, Math.round(durationSeconds * 10) / 10)}s
            </span>
          )}

          <button
            type="button"
            onClick={handleCopy}
            className="p-1 rounded text-muted-dim hover:text-white hover:bg-ink-800 transition opacity-0 group-hover:opacity-100"
            title="Copy command"
          >
            {copied ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
          </button>

          {hasOutput && (
            <div className="text-muted-dim group-hover:text-muted transition">
              {expanded ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )}
            </div>
          )}
        </div>
      </div>

      {/* Expanded Sandbox Output */}
      {hasOutput && expanded && (
        <div className="ml-3 mt-1 mr-1 p-2.5 rounded-md border border-ink-800 bg-black/90 text-muted-bright text-[10.5px] leading-relaxed max-h-60 overflow-y-auto whitespace-pre-wrap break-all shadow-inner animate-fade-in-up">
          <div className="text-[9px] uppercase tracking-wider text-muted-dim font-sans font-semibold mb-1 pb-1 border-b border-ink-850 flex items-center justify-between">
            <span>Terminal Sandbox Output</span>
            {exitCode !== undefined ? (
              <span className={exitCode === 0 ? "text-success font-medium" : "text-danger font-medium"}>
                Exit {exitCode}
              </span>
            ) : (
              <span className="text-secondary-400">Sandbox</span>
            )}
          </div>
          {output}
        </div>
      )}
    </div>
  );
}
