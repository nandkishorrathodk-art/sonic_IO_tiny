"use client";

import React, { useState } from "react";
import { Check, Copy } from "lucide-react";

interface MarkdownTextProps {
  content: string;
  className?: string;
}

export function MarkdownText({ content, className = "" }: MarkdownTextProps) {
  if (!content) return null;

  // Split content by code blocks first
  const parts: React.ReactNode[] = [];
  const codeBlockRegex = /```([a-zA-Z0-9_-]*)\r?\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  let blockIdx = 0;
  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      const textBefore = content.substring(lastIndex, match.index);
      parts.push(
        <span key={`text-${blockIdx}`}>
          {renderFormattedText(textBefore)}
        </span>
      );
    }

    const language = match[1] || "bash";
    const code = match[2];
    parts.push(
      <CodeBlock key={`code-${blockIdx}`} code={code} language={language} />
    );

    lastIndex = match.index + match[0].length;
    blockIdx++;
  }

  if (lastIndex < content.length) {
    parts.push(
      <span key={`text-end`}>
        {renderFormattedText(content.substring(lastIndex))}
      </span>
    );
  }

  return (
    <div className={`space-y-1.5 leading-relaxed text-[12.5px] ${className}`}>
      {parts}
    </div>
  );
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(code.trim());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  return (
    <div className="my-2 rounded-lg border border-ink-700/80 bg-ink-950 overflow-hidden font-mono text-[11px] shadow-sm">
      <div className="flex items-center justify-between px-3 py-1.5 bg-ink-900 border-b border-ink-800 text-[10px] text-muted">
        <span className="font-semibold text-secondary-400 uppercase tracking-wider">
          {language}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-white transition px-1.5 py-0.5 rounded hover:bg-ink-800"
          title="Copy code"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-success" />
              <span className="text-success font-medium">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto text-slate-200 leading-relaxed max-h-72">
        <code>{code.trim()}</code>
      </pre>
    </div>
  );
}

function renderFormattedText(text: string): React.ReactNode[] {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Bullet points
    if (/^\s*[-*•]\s+/.test(line)) {
      const bulletText = line.replace(/^\s*[-*•]\s+/, "");
      nodes.push(
        <div key={`line-${i}`} className="flex items-start gap-2 pl-2 py-0.5">
          <span className="text-secondary-400 mt-1 shrink-0">•</span>
          <span>{parseInlineStyles(bulletText)}</span>
        </div>
      );
      continue;
    }

    // Numbered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const matchNum = line.match(/^\s*(\d+)\.\s+(.*)/);
      if (matchNum) {
        nodes.push(
          <div key={`line-${i}`} className="flex items-start gap-2 pl-2 py-0.5">
            <span className="text-secondary-400 font-mono text-[10.5px] mt-0.5 shrink-0">
              {matchNum[1]}.
            </span>
            <span>{parseInlineStyles(matchNum[2])}</span>
          </div>
        );
        continue;
      }
    }

    // Blockquote
    if (/^>\s+/.test(line)) {
      nodes.push(
        <div
          key={`line-${i}`}
          className="border-l-2 border-secondary-500/60 pl-3 my-1 italic text-muted-bright bg-ink-850/40 py-1 rounded-r"
        >
          {parseInlineStyles(line.replace(/^>\s+/, ""))}
        </div>
      );
      continue;
    }

    // Empty line (paragraph break)
    if (line.trim() === "") {
      nodes.push(<div key={`empty-${i}`} className="h-2" />);
      continue;
    }

    // Normal line
    nodes.push(
      <p key={`p-${i}`} className="my-0.5">
        {parseInlineStyles(line)}
      </p>
    );
  }

  return nodes;
}

function parseInlineStyles(text: string): React.ReactNode[] {
  const tokenRegex = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  let idx = 0;
  while ((match = tokenRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith("`") && token.endsWith("`")) {
      const code = token.slice(1, -1);
      parts.push(
        <code
          key={`inline-code-${idx}`}
          className="px-1.5 py-0.5 rounded bg-ink-950 border border-ink-700 text-secondary-300 font-mono text-[11px] font-medium select-all"
        >
          {code}
        </code>
      );
    } else if (token.startsWith("**") && token.endsWith("**")) {
      const bold = token.slice(2, -2);
      parts.push(
        <strong key={`bold-${idx}`} className="text-white font-semibold">
          {bold}
        </strong>
      );
    } else if (token.startsWith("[") && token.includes("](")) {
      const linkMatch = token.match(/\[([^\]]+)\]\(([^)]+)\)/);
      if (linkMatch) {
        parts.push(
          <a
            key={`link-${idx}`}
            href={linkMatch[2]}
            target="_blank"
            rel="noopener noreferrer"
            className="text-secondary-400 hover:text-secondary-300 underline font-medium"
          >
            {linkMatch[1]}
          </a>
        );
      } else {
        parts.push(token);
      }
    } else {
      parts.push(token);
    }

    lastIndex = match.index + token.length;
    idx++;
  }

  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }

  return parts;
}
