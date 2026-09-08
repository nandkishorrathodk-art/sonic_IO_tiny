"use client";

import React, { useState } from "react";
import { Brain, ChevronDown, ChevronRight, Sparkles } from "lucide-react";

interface ThinkingBlockProps {
  content: string;
  durationSeconds?: number;
  initiallyExpanded?: boolean;
}

export function ThinkingBlock({
  content,
  durationSeconds,
  initiallyExpanded = false,
}: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(initiallyExpanded);

  // Parse structured cognitive sections if present
  const cognitiveSections = parseCognitiveSections(content);
  const durationLabel = durationSeconds
    ? `${Math.max(1, Math.round(durationSeconds))}s`
    : "";

  return (
    <div className="my-1 font-sans text-xs select-text">
      {/* Collapsed single-line view matching Devin: "Brain icon - Thought for Xs" + preview snippet */}
      {!expanded ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="flex items-center gap-2 text-muted hover:text-muted-bright py-0.5 px-1 rounded hover:bg-ink-800/40 transition group cursor-pointer w-full text-left"
          title="Click to view complete thought process"
        >
          <Brain className="w-3.5 h-3.5 text-secondary-400 group-hover:text-secondary-300 shrink-0 transition" />
          <span className="text-[11.5px] font-semibold text-secondary-300 font-mono tracking-tight shrink-0">
            {durationLabel ? `Thought for ${durationLabel}` : "Thinking"}
          </span>
          <ChevronRight className="w-3 h-3 text-muted-dim group-hover:text-muted shrink-0 transition" />
          <span className="text-[11px] text-muted-dim truncate font-sans italic ml-1 max-w-[80%]">
            {content ? (content.length > 95 ? `${content.slice(0, 95)}...` : content) : "Click to view reasoning"}
          </span>
        </button>
      ) : (
        /* Expanded Thinking Card matching Devin: "v Thinking" with left border guide */
        <div className="space-y-1 my-1.5 animate-fade-in-up">
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="flex items-center gap-1.5 text-muted hover:text-white py-0.5 cursor-pointer text-[12px] font-medium transition"
          >
            <ChevronDown className="w-3.5 h-3.5 text-muted shrink-0" />
            <span className="text-slate-200 font-semibold tracking-wide">Thinking</span>
            {durationLabel && (
              <span className="text-[10px] font-mono text-muted-dim ml-1 bg-ink-800 px-1.5 py-0.2 rounded border border-ink-700/60">
                {durationLabel}
              </span>
            )}
          </button>

          {/* Indented thought container with left vertical border */}
          <div className="ml-2 pl-3.5 border-l-2 border-ink-700/80 hover:border-secondary-500/50 transition text-[12px] text-muted-bright leading-relaxed space-y-2 py-0.5">
            {cognitiveSections.length > 0 ? (
              cognitiveSections.map((sec, i) => (
                <div key={i} className="space-y-0.5">
                  <div className={`inline-flex items-center gap-1.5 text-[10px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${sec.colorBadge}`}>
                    <span>{sec.title}</span>
                  </div>
                  <p className="text-slate-300 text-[11.5px] leading-relaxed whitespace-pre-wrap pl-0.5">
                    {sec.text}
                  </p>
                </div>
              ))
            ) : (
              <p className="text-slate-300 text-[12px] leading-relaxed whitespace-pre-wrap">
                {content}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface CognitiveSection {
  title: string;
  text: string;
  colorBadge: string;
}

function parseCognitiveSections(rawContent: string): CognitiveSection[] {
  if (!rawContent) return [];

  const headers = [
    { regex: /^(?:\*{1,2}|_)?WHAT DO I KNOW\??(?:\*{1,2}|_)?:/i, label: "Knowledge", color: "text-emerald-400 bg-emerald-950/40 border-emerald-700/50" },
    { regex: /^(?:\*{1,2}|_)?WHAT DO I NOT KNOW\??(?:\*{1,2}|_)?:/i, label: "Unknowns", color: "text-amber-400 bg-amber-950/40 border-amber-700/50" },
    { regex: /^(?:\*{1,2}|_)?WHAT FAILED\??(?:\*{1,2}|_)?:/i, label: "Failed", color: "text-rose-400 bg-rose-950/40 border-rose-700/50" },
    { regex: /^(?:\*{1,2}|_)?WHY DID IT FAIL\??(?:\*{1,2}|_)?:/i, label: "Root Cause", color: "text-rose-400 bg-rose-950/40 border-rose-700/50" },
    { regex: /^(?:\*{1,2}|_)?WHAT HYPOTHESIS DOES THIS SUPPORT\/?DISPROVE\??(?:\*{1,2}|_)?:/i, label: "Hypothesis", color: "text-purple-400 bg-purple-950/40 border-purple-700/50" },
    { regex: /^(?:\*{1,2}|_)?WHAT IS THE HIGHEST[\s_-]INFORMATION NEXT ACTION\??(?:\*{1,2}|_)?:/i, label: "Next Action", color: "text-cyan-400 bg-cyan-950/40 border-cyan-700/50" },
    { regex: /^(?:\*{1,2}|_)?(?:THOUGHT|REASONING|DEDUCTION)(?:\*{1,2}|_)?:/i, label: "Deduction", color: "text-secondary-400 bg-secondary-950/40 border-secondary-700/50" },
  ];

  const lines = rawContent.split("\n");
  const sections: CognitiveSection[] = [];
  let currentHeader: typeof headers[0] | null = null;
  let currentLines: string[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    const matchedHeader = headers.find((h) => h.regex.test(trimmed));
    if (matchedHeader) {
      if (currentHeader && currentLines.length > 0) {
        sections.push({
          title: currentHeader.label,
          text: currentLines.join("\n").trim(),
          colorBadge: currentHeader.color,
        });
      }
      currentHeader = matchedHeader;
      const remainder = trimmed.replace(matchedHeader.regex, "").trim();
      currentLines = remainder ? [remainder] : [];
    } else if (currentHeader) {
      currentLines.push(line);
    }
  }

  if (currentHeader && currentLines.length > 0) {
    sections.push({
      title: currentHeader.label,
      text: currentLines.join("\n").trim(),
      colorBadge: currentHeader.color,
    });
  }

  return sections;
}
