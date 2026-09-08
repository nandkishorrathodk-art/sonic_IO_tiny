"use client";

import React from "react";
import { FileCode, FileEdit, FilePlus, ChevronRight } from "lucide-react";

interface FileActionBlockProps {
  type: "read" | "write" | "edit";
  file: string;
  lines?: string;
  onSelectFile?: (file: string) => void;
}

export function FileActionBlock({
  type,
  file,
  lines,
  onSelectFile,
}: FileActionBlockProps) {
  // Extract basename if full path (supports both / and \ safely)
  const safeFile = file || "";
  const basename = safeFile.split(/[/\\]/).pop() || safeFile;
  const lineSuffix = lines ? `:${lines}` : "";
  const displayLabel = `${basename}${lineSuffix}`;

  const handleClick = () => {
    if (onSelectFile && file) {
      onSelectFile(file);
    }
  };

  const isRead = type === "read";
  const isWrite = type === "write";

  return (
    <div className="my-0.5 py-0.5 flex items-center gap-2 font-mono text-[11px] select-text">
      {isRead ? (
        <FileCode className="w-3.5 h-3.5 text-muted-dim shrink-0" />
      ) : isWrite ? (
        <FilePlus className="w-3.5 h-3.5 text-secondary-400 shrink-0" />
      ) : (
        <FileEdit className="w-3.5 h-3.5 text-warning shrink-0" />
      )}

      <div
        onClick={handleClick}
        className="inline-flex items-center gap-1.5 cursor-pointer group"
        title={onSelectFile ? `Click to inspect ${file} in Code Viewer` : file}
      >
        <span className="text-muted group-hover:text-muted-bright transition text-[11.5px] font-sans">
          {isRead ? "Read" : isWrite ? "Wrote" : "Edited"}
        </span>

        {/* Badge matching Devin style */}
        <span className="px-1.5 py-0.2 rounded bg-ink-800/90 hover:bg-ink-750 border border-ink-700/70 group-hover:border-secondary-500/50 text-slate-300 group-hover:text-secondary-400 font-mono text-[11px] transition shadow-sm flex items-center gap-1">
          <span>{displayLabel}</span>
          {onSelectFile && (
            <ChevronRight className="w-2.5 h-2.5 text-muted-dim group-hover:text-secondary-400 transition" />
          )}
        </span>
      </div>
    </div>
  );
}
