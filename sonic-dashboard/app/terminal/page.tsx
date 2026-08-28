"use client";

import { useEffect, useRef, useState } from "react";
import { Terminal as TerminalIcon, Maximize2, Minimize2, RotateCcw, Wifi, WifiOff } from "lucide-react";

export default function TerminalPage() {
  const termRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [buffer, setBuffer] = useState<string[]>([
    "\x1b[1;36m╔══════════════════════════════════════════════════════════════╗\x1b[0m",
    "\x1b[1;36m║\x1b[0m  \x1b[1;33m⚡ SONIC-REDA\x1b[0m — \x1b[1;37mVirtual Computer Terminal\x1b[0m                    \x1b[1;36m║\x1b[0m",
    "\x1b[1;36m║\x1b[0m  \x1b[90mIsolated Sandbox Shell • Daytona Container\x1b[0m                 \x1b[1;36m║\x1b[0m",
    "\x1b[1;36m╚══════════════════════════════════════════════════════════════╝\x1b[0m",
    "",
    "\x1b[32m[sonic@sandbox]\x1b[0m $ ",
  ]);
  const [inputLine, setInputLine] = useState("");
  const [commandHistory, setCommandHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [fullscreen, setFullscreen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const connectWs = () => {
    const ws = new WebSocket("ws://localhost:8000/terminal/ws/terminal");
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "connected") {
          setSessionId(msg.session_id);
          setBuffer(prev => [...prev, `\x1b[90m[Session ${msg.session_id} attached]\x1b[0m\n`]);
        } else if (msg.type === "output") {
          setBuffer(prev => [...prev, msg.data]);
        }
      } catch { /* ignore non-JSON */ }
    };
  };

  const sendCommand = (cmd: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "input", data: cmd + "\n" }));
    }
    // Local echo for offline/simulation
    setBuffer(prev => [
      ...prev,
      `\x1b[32m[sonic@sandbox]\x1b[0m $ ${cmd}\n`,
    ]);
    if (cmd.trim()) {
      setCommandHistory(prev => [cmd, ...prev.slice(0, 50)]);
    }
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
      sendCommand("\x03");
    }
  };

  useEffect(() => {
    if (termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight;
    }
  }, [buffer]);

  return (
    <div className={`space-y-4 ${fullscreen ? 'fixed inset-0 z-50 bg-slate-950 p-4' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TerminalIcon className="w-5 h-5 text-emerald-400" />
          <h2 className="text-xl font-bold text-white tracking-tight">Virtual Computer Terminal</h2>
          {connected ? (
            <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono font-bold">
              <Wifi className="w-3 h-3" /> LIVE
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-red-950 text-red-400 border border-red-800 font-mono font-bold">
              <WifiOff className="w-3 h-3" /> OFFLINE
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={connectWs}
            className="px-3 py-1.5 bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-800/80 text-emerald-400 text-xs font-mono font-bold rounded-lg flex items-center gap-1.5 transition"
          >
            <RotateCcw className="w-3 h-3" /> {connected ? "Reconnect" : "Connect"}
          </button>
          <button
            onClick={() => setFullscreen(!fullscreen)}
            className="p-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 rounded-lg transition"
          >
            {fullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Terminal Window */}
      <div className="glass-card rounded-xl border border-slate-800 overflow-hidden">
        {/* Title bar */}
        <div className="flex items-center gap-2 px-4 py-2 bg-slate-900/90 border-b border-slate-800">
          <div className="flex gap-1.5">
            <div className="w-3 h-3 rounded-full bg-red-500/80"></div>
            <div className="w-3 h-3 rounded-full bg-yellow-500/80"></div>
            <div className="w-3 h-3 rounded-full bg-emerald-500/80"></div>
          </div>
          <span className="text-[11px] text-slate-500 font-mono ml-2">
            sonic@sandbox:{sessionId || "~"} — bash
          </span>
        </div>

        {/* Terminal body */}
        <div
          ref={termRef}
          onClick={() => inputRef.current?.focus()}
          className="bg-[#0a0e14] p-4 font-mono text-sm text-emerald-300 overflow-y-auto cursor-text"
          style={{ minHeight: fullscreen ? "calc(100vh - 160px)" : "500px", maxHeight: fullscreen ? "calc(100vh - 160px)" : "500px" }}
        >
          {buffer.map((line, i) => (
            <pre key={i} className="whitespace-pre-wrap leading-relaxed" dangerouslySetInnerHTML={{
              __html: line
                .replace(/\x1b\[1;36m/g, '<span class="text-cyan-400 font-bold">')
                .replace(/\x1b\[1;33m/g, '<span class="text-amber-400 font-bold">')
                .replace(/\x1b\[1;37m/g, '<span class="text-white font-bold">')
                .replace(/\x1b\[32m/g, '<span class="text-emerald-400">')
                .replace(/\x1b\[90m/g, '<span class="text-slate-500">')
                .replace(/\x1b\[0m/g, '</span>')
            }} />
          ))}

          {/* Input line */}
          <div className="flex items-center gap-0">
            <span className="text-emerald-400">[sonic@sandbox]</span>
            <span className="text-white mx-1">$</span>
            <input
              ref={inputRef}
              type="text"
              value={inputLine}
              onChange={(e) => setInputLine(e.target.value)}
              onKeyDown={handleKeyDown}
              className="flex-1 bg-transparent text-emerald-300 outline-none font-mono text-sm caret-emerald-400"
              autoFocus
              spellCheck={false}
              autoComplete="off"
            />
          </div>
        </div>
      </div>

      {/* Quick Commands */}
      <div className="flex flex-wrap gap-2">
        {["nmap -sV target.com", "nuclei -u http://target.com", "ffuf -u http://target.com/FUZZ -w /usr/share/seclists/Discovery/Web-Content/common.txt", "curl -I http://target.com", "httpx -u http://target.com -title -tech-detect"].map((cmd) => (
          <button
            key={cmd}
            onClick={() => sendCommand(cmd)}
            className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 text-[11px] font-mono rounded-lg transition truncate max-w-xs"
          >
            $ {cmd}
          </button>
        ))}
      </div>
    </div>
  );
}
