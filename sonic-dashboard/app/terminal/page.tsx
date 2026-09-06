"use client";

import { useEffect, useRef, useState } from "react";
import { Terminal as TerminalIcon, Maximize2, Minimize2, RotateCcw, Wifi, WifiOff } from "lucide-react";
import { createTerminalWebSocket } from "../../lib/ws";
import { AnsiText } from "../../components/common/AnsiText";

export default function TerminalPage() {
  const termRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [buffer, setBuffer] = useState<string[]>([
    "\x1b[1;36m╔══════════════════════════════════════════════════════════════╗\x1b[0m",
    "\x1b[1;36m║\x1b[0m  \x1b[1;33m⚡ SONIC-REDA\x1b[0m — \x1b[1;37mVirtual Computer Terminal\x1b[0m                    \x1b[1;36m║\x1b[0m",
    "\x1b[1;36m║\x1b[0m  \x1b[90mIsolated Sandbox Shell • Docker Cyber Workstation\x1b[0m           \x1b[1;36m║\x1b[0m",
    "\x1b[1;36m╚══════════════════════════════════════════════════════════════╝\x1b[0m",
    "",
  ]);
  const [inputLine, setInputLine] = useState("");
  const [commandHistory, setCommandHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [fullscreen, setFullscreen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const connectWs = () => {
    if (wsRef.current) wsRef.current.close();

    const ws = createTerminalWebSocket({
      onOpen: () => {
        setConnected(true);
        setBuffer((prev) => [...prev, "\x1b[32m[Connected to Sandbox PTY Session]\x1b[0m\n"]);
      },
      onClose: () => {
        setConnected(false);
        setBuffer((prev) => [...prev, "\x1b[31m[WebSocket Closed - Sandbox Disconnected]\x1b[0m\n"]);
      },
      onError: () => {
        setConnected(false);
        setBuffer((prev) => [...prev, "\x1b[31m[WebSocket Error: Ensure backend is running with valid JWT]\x1b[0m\n"]);
      },
      onMessage: (msg) => {
        if (msg.type === "connected") {
          setSessionId(msg.session_id);
          setBuffer((prev) => [...prev, `\x1b[90m[Session ${msg.session_id} attached]\x1b[0m\n`]);
        } else if (msg.type === "output" && msg.data) {
          setBuffer((prev) => [...prev, msg.data]);
        } else if (msg.type === "error" && msg.data) {
          setBuffer((prev) => [...prev, msg.data]);
        }
      },
    });

    wsRef.current = ws;
  };

  const sendCommand = (cmd: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "input", data: cmd + "\n" }));
    } else {
      setBuffer((prev) => [
        ...prev,
        "\x1b[31m[FAIL-CLOSED]: Cannot send command. Terminal is DISCONNECTED from sandbox.\x1b[0m\n",
      ]);
    }
    if (cmd.trim()) setCommandHistory((prev) => [cmd, ...prev.slice(0, 50)]);
    setHistoryIdx(-1);
    setInputLine("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      sendCommand(inputLine);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const newIdx = Math.min(historyIdx + 1, commandHistory.length - 1);
      setHistoryIdx(newIdx);
      if (commandHistory[newIdx]) setInputLine(commandHistory[newIdx]);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const newIdx = Math.max(historyIdx - 1, -1);
      setHistoryIdx(newIdx);
      setInputLine(newIdx >= 0 ? commandHistory[newIdx] : "");
    } else if (e.key === "c" && e.ctrlKey) {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "input", data: "\x03" }));
      }
    }
  };

  useEffect(() => {
    connectWs();
    return () => { wsRef.current?.close(); };
  }, []);

  useEffect(() => {
    if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight;
  }, [buffer]);

  return (
    <div className={`min-h-screen bg-ink-950 bg-grid-glow ${fullscreen ? "fixed inset-0 z-50 p-4" : "p-6"} space-y-4 max-w-7xl mx-auto`}>
      <div className="flex items-center justify-between pb-4 border-b border-ink-800">
        <div className="flex items-center gap-2">
          <TerminalIcon className="w-5 h-5 text-success" />
          <h2 className="text-xl font-bold text-white tracking-tight">Virtual Computer Terminal</h2>
          {connected ? (
            <span className="chip border border-success/40 bg-success/10 text-success">
              <Wifi className="w-3 h-3" /> LIVE (SANDBOX BOUND)
            </span>
          ) : (
            <span className="chip border border-danger/40 bg-danger/10 text-danger">
              <WifiOff className="w-3 h-3" /> DISCONNECTED
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button onClick={connectWs} className="btn-secondary !px-3 !py-1.5 text-xs font-mono">
            <RotateCcw className="w-3 h-3" /> {connected ? "Reconnect" : "Connect"}
          </button>
          <button
            onClick={() => setFullscreen(!fullscreen)}
            className="p-1.5 bg-ink-800 hover:bg-ink-700 border border-ink-700 text-muted-bright rounded-lg transition"
          >
            {fullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </div>

      <div className="glass-card rounded-xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2 bg-ink-900/90 border-b border-ink-800">
          <div className="flex gap-1.5">
            <div className="w-3 h-3 rounded-full bg-danger/80" />
            <div className="w-3 h-3 rounded-full bg-warning/80" />
            <div className="w-3 h-3 rounded-full bg-success/80" />
          </div>
          <span className="text-[11px] text-muted-dim font-mono ml-2">
            sonic@sandbox:{sessionId || "~"} — /bin/bash (Isolated)
          </span>
        </div>

        <div
          ref={termRef}
          onClick={() => inputRef.current?.focus()}
          className="bg-ink-950 p-4 font-mono text-sm text-success overflow-y-auto cursor-text"
          style={{ minHeight: fullscreen ? "calc(100vh - 160px)" : "500px", maxHeight: fullscreen ? "calc(100vh - 160px)" : "500px" }}
        >
          {buffer.map((line, i) => (
            <pre key={i} className="whitespace-pre-wrap leading-relaxed">
              <AnsiText text={line} />
            </pre>
          ))}

          <div className="flex items-center gap-2 mt-2 pt-2 border-t border-ink-800">
            <span className="text-success font-bold">sonic@sandbox:~$</span>
            <input
              ref={inputRef}
              type="text"
              value={inputLine}
              onChange={(e) => setInputLine(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!connected}
              className="flex-1 bg-transparent text-sm text-white outline-none font-mono placeholder:text-muted-dim disabled:opacity-50"
              placeholder={connected ? "Type container command…" : "Terminal disconnected. Connect to sandbox first."}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
