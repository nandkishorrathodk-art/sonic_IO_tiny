import React, { useState } from "react";
import { FileCode, Copy, Check, Save, ChevronDown, RotateCcw } from "lucide-react";

interface CodeViewerProps {
  activeFile: string;
  fileContent: string[];
  gitDiff: string;
  viewMode: "code" | "changes";
  onRefreshDiff?: () => void;
  onSaveFile?: (content: string) => Promise<void>;
}

export function CodeViewer({
  activeFile,
  fileContent,
  gitDiff,
  viewMode,
  onRefreshDiff,
  onSaveFile,
}: CodeViewerProps) {
  const [copied, setCopied] = useState(false);
  const [editable, setEditable] = useState(false);
  const [editedText, setEditedText] = useState("");
  const [saving, setSaving] = useState(false);

  const handleCopy = () => {
    if (!fileContent.length) return;
    navigator.clipboard.writeText(fileContent.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleStartEdit = () => {
    if (!activeFile || !fileContent.length) return;
    setEditedText(fileContent.join("\n"));
    setEditable(true);
  };

  const handleSave = async () => {
    if (!onSaveFile) return;
    setSaving(true);
    await onSaveFile(editedText);
    setSaving(false);
    setEditable(false);
  };

  if (viewMode === "changes") {
    return (
      <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden p-4 font-mono text-xs space-y-2">
        <div className="flex items-center justify-between border-b border-[#30363D] pb-2">
          <span className="font-semibold text-white">Live Git Diff</span>
          {onRefreshDiff && (
            <button
              onClick={onRefreshDiff}
              className="text-[#58A6FF] hover:underline text-[11px] flex items-center gap-1"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Refresh Diff</span>
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto space-y-1 text-[11px] leading-relaxed whitespace-pre-wrap bg-[#0D1117] p-3 rounded border border-[#21262D]">
          {gitDiff ? (
            gitDiff.split("\n").map((l, i) => (
              <div
                key={i}
                className={
                  l.startsWith("+")
                    ? "text-[#7EE787] bg-[#7EE787]/10 px-1"
                    : l.startsWith("-")
                    ? "text-[#FF7B72] bg-[#FF7B72]/10 px-1"
                    : "text-[#8B949E]"
                }
              >
                {l}
              </div>
            ))
          ) : (
            <span className="text-[#8B949E]">Working tree clean. No uncommitted modifications.</span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden shadow-xl">
      {/* File Header */}
      <div className="h-8 border-b border-[#21262D] bg-[#1C2128] px-3 flex items-center justify-between text-xs font-mono text-[#8B949E]">
        <div className="flex items-center gap-2 truncate">
          <FileCode className="w-3.5 h-3.5 text-[#58A6FF]" />
          <span className="text-[#58A6FF] font-semibold truncate">{activeFile ? activeFile.split("/").pop() : "No file selected"}</span>
          {activeFile && <span className="text-[10px] text-[#8B949E] truncate">{activeFile}</span>}
        </div>
        <div className="flex items-center gap-2">
          {editable ? (
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-2 py-0.5 rounded bg-[#238636] text-white hover:bg-[#2ea043] transition text-[11px] font-semibold flex items-center gap-1"
            >
              <Save className="w-3 h-3" />
              <span>{saving ? "Saving..." : "Save File"}</span>
            </button>
          ) : (
            <button
              onClick={handleStartEdit}
              disabled={!activeFile || !fileContent.length}
              className="px-2 py-0.5 rounded bg-[#21262D] text-[#C9D1D9] hover:text-white transition text-[11px] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Edit File
            </button>
          )}
          <button
            onClick={handleCopy}
            disabled={!fileContent.length}
            className="text-[#8B949E] hover:text-white p-1 rounded hover:bg-[#2D333B] transition disabled:opacity-40 disabled:cursor-not-allowed"
            title="Copy content"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-[#3FB950]" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Editor Body */}
      {editable ? (
        <textarea
          value={editedText}
          onChange={(e) => setEditedText(e.target.value)}
          className="flex-1 p-3 font-mono text-xs leading-relaxed bg-[#0D1117] text-[#C9D1D9] outline-none resize-none"
        />
      ) : (
        <div className="flex-1 overflow-y-auto p-3 font-mono text-xs leading-relaxed bg-[#0D1117]">
          {fileContent.length ? fileContent.map((line, i) => (
            <div key={i} className="flex hover:bg-[#161B22]/50 leading-5">
              <span className="w-10 text-right pr-4 text-[#484F58] font-mono text-[11px]">
                {i + 1}
              </span>
              <span className="flex-1 whitespace-pre text-[#C9D1D9]">{line}</span>
            </div>
          )) : (
            <div className="h-full flex items-center justify-center text-xs text-[#6E7681]">
              Select a real file from the agent worklog after a workspace is connected.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
