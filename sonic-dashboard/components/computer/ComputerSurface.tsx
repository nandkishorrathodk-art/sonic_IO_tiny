import React, { useState } from "react";
import {
  Monitor,
  Terminal as TerminalIcon,
  ShieldCheck,
  Cpu,
  Copy,
  Check,
  Server,
  Cloud,
  ExternalLink,
} from "lucide-react";
import { DesktopState, CommandResult } from "../../types/workstation";

interface ComputerSurfaceProps {
  desktopState?: DesktopState & {
    sandbox_id?: string;
    image?: string;
    ssh_command?: string;
  };
  onRunCommand: (cmd: string) => Promise<CommandResult | null>;
  commandLogs: string[];
}

export function ComputerSurface({
  desktopState,
  onRunCommand,
  commandLogs,
}: ComputerSurfaceProps) {
  const [terminalInput, setTerminalInput] = useState("");
  const [running, setRunning] = useState(false);
  const [copiedSsh, setCopiedSsh] = useState(false);

  const sshCmd =
    desktopState?.ssh_command ||
    process.env.NEXT_PUBLIC_DAYTONA_SSH ||
    "ssh Mnbgd9ZivsOicPxxuHpF2PC5cM3IyjGX@ssh.app.daytona.io";

  const sandboxId =
    desktopState?.sandbox_id ||
    process.env.NEXT_PUBLIC_DAYTONA_SANDBOX_ID ||
    "d1654904-ec6d-40ad-9713-dceba7682147";

  const image =
    desktopState?.image ||
    process.env.NEXT_PUBLIC_DAYTONA_IMAGE ||
    "daytonaio/sandbox:0.8.0";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!terminalInput.trim() || running) return;
    const cmd = terminalInput;
    setTerminalInput("");
    setRunning(true);
    await onRunCommand(cmd);
    setRunning(false);
  };

  const handleCopySsh = () => {
    navigator.clipboard.writeText(sshCmd);
    setCopiedSsh(true);
    setTimeout(() => setCopiedSsh(false), 2000);
  };

  return (
    <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden shadow-2xl">
      {/* Computer OS Header */}
      <div className="h-10 border-b border-[#21262D] bg-[#1C2128] px-3 flex items-center justify-between text-xs font-mono text-[#8B949E]">
        <div className="flex items-center gap-2">
          <Cloud className="w-4 h-4 text-[#58A6FF]" />
          <span className="text-white font-semibold flex items-center gap-1.5">
            <span>Daytona Cloud Linux Sandbox</span>
            <span className="text-[10px] text-[#3FB950] font-normal font-mono">
              ({image})
            </span>
          </span>
        </div>
        <div className="flex items-center gap-2 text-[10px]">
          <span className="px-2 py-0.5 rounded bg-[#238636]/20 text-[#3FB950] border border-[#238636]/40 font-bold flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#3FB950] animate-pulse"></span>
            ACTIVE OS CONTAINER
          </span>
        </div>
      </div>

      {/* Daytona Sandbox OS Details Bar */}
      <div className="bg-[#12151A] border-b border-[#21262D] p-3 flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
        <div className="flex items-center gap-4 flex-wrap">
          <div>
            <span className="text-[#8B949E] text-[10px] block">SANDBOX UUID</span>
            <span className="text-[#58A6FF] font-bold text-[11px] select-all">
              {sandboxId}
            </span>
          </div>
          <div>
            <span className="text-[#8B949E] text-[10px] block">OS ENVIRONMENT</span>
            <span className="text-[#E6EDF3] text-[11px]">Debian/Ubuntu (1 vCPU, 1 GiB RAM)</span>
          </div>
        </div>

        {/* SSH Connection Chip */}
        <div className="flex items-center gap-2 bg-[#0D1117] border border-[#30363D] px-2.5 py-1 rounded-md">
          <span className="text-[#8B949E] text-[10px]">SSH:</span>
          <code className="text-[#79C0FF] text-[11px] truncate max-w-xs">{sshCmd}</code>
          <button
            onClick={handleCopySsh}
            className="text-[#8B949E] hover:text-white p-0.5 rounded hover:bg-[#21262D] transition ml-1"
            title="Copy SSH command"
          >
            {copiedSsh ? <Check className="w-3.5 h-3.5 text-[#3FB950]" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Terminal View inside Sandbox */}
      <div className="flex-1 bg-[#06080D] p-3 flex flex-col font-mono text-xs overflow-hidden">
        <div className="flex-1 overflow-y-auto space-y-1 text-[#C9D1D9] leading-tight select-text">
          <div className="text-[#8B949E] pb-2 border-b border-[#21262D] space-y-0.5">
            <div># Attached to Daytona Cloud Linux Container: {sandboxId}</div>
            <div># Snapshot: {image} | Direct host command execution is prohibited.</div>
          </div>
          {commandLogs.map((log, idx) => (
            <div key={idx} className="whitespace-pre-wrap">
              {log.startsWith("sonic@") ? (
                <span className="text-[#79C0FF] font-bold">{log}</span>
              ) : log.includes("PASSED") ? (
                <span className="text-[#3FB950]">{log}</span>
              ) : log.includes("FAILED") || log.includes("Error") || log.includes("prohibited") ? (
                <span className="text-[#FF7B72]">{log}</span>
              ) : (
                <span className="text-[#8B949E]">{log}</span>
              )}
            </div>
          ))}
        </div>

        {/* Input Box */}
        <form onSubmit={handleSubmit} className="mt-2 flex items-center gap-2 border-t border-[#21262D] pt-2">
          <span className="text-[#3FB950] font-bold">sonic@daytona:~$</span>
          <input
            type="text"
            value={terminalInput}
            onChange={(e) => setTerminalInput(e.target.value)}
            placeholder="Execute command inside Daytona sandbox (e.g. 'pytest tests/' or 'uname -a')..."
            className="flex-1 bg-transparent text-xs text-white outline-none font-mono placeholder-[#484F58]"
            disabled={running}
          />
          {running && (
            <span className="text-[10px] text-[#58A6FF] animate-pulse font-bold">
              EXECUTING IN SANDBOX...
            </span>
          )}
        </form>
      </div>
    </div>
  );
}
