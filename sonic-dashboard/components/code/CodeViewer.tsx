import React, { useState } from "react";
import { FileCode, Copy, Check, Save, RotateCcw } from "lucide-react";

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
      <div className="flex-1 panel flex flex-col overflow-hidden p-4 font-mono text-xs space-y-2">
        <div className="flex items-center justify-between border-b border-ink-700 pb-2">
          <span className="font-semibold text-white">Live Git Diff</span>
          {onRefreshDiff && (
            <button onClick={onRefreshDiff} className="btn-ghost text-secondary-400">
              <RotateCcw className="w-3 h-3" />
              <span>Refresh Diff</span>
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto space-y-1 text-[11px] leading-relaxed whitespace-pre-wrap bg-ink-950 p-3 rounded border border-ink-700">
          {gitDiff ? (
            gitDiff.split("\n").map((l, i) => (
              <div
                key={i}
                className={
                  l.startsWith("+")
                    ? "text-success bg-success/10 px-1"
                    : l.startsWith("-")
                    ? "text-danger bg-danger/10 px-1"
                    : "text-muted"
                }
              >
                {l}
              </div>
            ))
          ) : (
            <span className="text-muted">Working tree clean. No uncommitted modifications.</span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 panel flex flex-col overflow-hidden shadow-xl">
      <div className="h-8 border-b border-ink-700 bg-ink-800 px-3 flex items-center justify-between text-xs font-mono text-muted">
        <div className="flex items-center gap-2 truncate">
          <FileCode className="w-3.5 h-3.5 text-secondary-400" />
          <span className="text-secondary-400 font-semibold truncate">{activeFile ? activeFile.split("/").pop() : "No file selected"}</span>
          {activeFile && <span className="text-[10px] text-muted-dim truncate">{activeFile}</span>}
        </div>
        <div className="flex items-center gap-2">
          {editable ? (
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-2 py-0.5 rounded bg-success/20 text-success border border-success/40 hover:bg-success/30 transition text-[11px] font-semibold flex items-center gap-1"
            >
              <Save className="w-3 h-3" />
              <span>{saving ? "Saving…" : "Save File"}</span>
            </button>
          ) : (
            <button
              onClick={handleStartEdit}
              disabled={!activeFile || !fileContent.length}
              className="btn-ghost disabled:opacity-40 disabled:cursor-not-allowed !px-2 !py-0.5"
            >
              Edit File
            </button>
          )}
          <button
            onClick={handleCopy}
            disabled={!fileContent.length}
            className="text-muted hover:text-white p-1 rounded hover:bg-ink-700 transition disabled:opacity-40 disabled:cursor-not-allowed"
            title="Copy content"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {editable ? (
        <textarea
          value={editedText}
          onChange={(e) => setEditedText(e.target.value)}
          className="flex-1 p-3 font-mono text-xs leading-relaxed bg-ink-950 text-slate-200 outline-none resize-none"
        />
      ) : (
        <div className="flex-1 overflow-y-auto p-3 font-mono text-xs leading-relaxed bg-ink-950">
          {fileContent.length ? fileContent.map((line, i) => (
            <div key={i} className="flex hover:bg-ink-850/50 leading-5">
              <span className="w-10 text-right pr-4 text-muted-dim font-mono text-[11px] select-none">
                {i + 1}
              </span>
              <span className="flex-1 whitespace-pre text-slate-200">{line}</span>
            </div>
          )) : (
            <div className="h-full flex items-center justify-center text-xs text-muted-dim">
              Select a real file from the agent worklog after a workspace is connected.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
