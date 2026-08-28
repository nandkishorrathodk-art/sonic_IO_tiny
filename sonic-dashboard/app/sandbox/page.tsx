"use client";

import { useState } from "react";
import { Monitor, Play, Square, RefreshCw, Cpu, HardDrive, Wifi } from "lucide-react";

export default function SandboxViewer() {
  const [sandboxes] = useState([
    {
      id: "ws-recon-01",
      name: "Recon Sandbox",
      status: "running",
      image: "daytonaio/workspace-project:latest",
      agent: "ReconAgent",
      uptime: "14m 32s",
      cpu: "12%",
      ram: "256MB / 2GB",
      tools: ["nmap", "ffuf", "httpx"],
    },
    {
      id: "ws-dynamic-01",
      name: "Dynamic Testing Sandbox",
      status: "running",
      image: "sonic/pentest-suite:v1",
      agent: "DynamicExecution",
      uptime: "8m 15s",
      cpu: "34%",
      ram: "512MB / 4GB",
      tools: ["nuclei", "sqlmap", "burp-proxy"],
    },
    {
      id: "ws-canary-01",
      name: "Canary Experiment Sandbox",
      status: "stopped",
      image: "daytonaio/workspace-project:latest",
      agent: "SelfDevAgent",
      uptime: "—",
      cpu: "0%",
      ram: "0MB / 2GB",
      tools: ["python3", "pytest"],
    },
  ]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Monitor className="w-5 h-5 text-cyan-400" />
          <h2 className="text-xl font-bold text-white tracking-tight">Sandbox Fleet Manager</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800 font-mono font-bold">
            {sandboxes.filter(s => s.status === "running").length} Active Containers
          </span>
          <button className="px-3 py-1.5 bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-800/80 text-emerald-400 text-xs font-mono font-bold rounded-lg flex items-center gap-1.5 transition">
            <Play className="w-3 h-3" /> Spawn New
          </button>
        </div>
      </div>

      {/* Sandbox Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        {sandboxes.map((sb) => (
          <div
            key={sb.id}
            className={`glass-card rounded-xl border p-5 space-y-4 transition ${
              sb.status === "running" ? "border-emerald-800/50 hover:border-emerald-700" : "border-slate-800 opacity-60"
            }`}
          >
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-white">{sb.name}</h3>
                <p className="text-[10px] text-slate-500 font-mono">{sb.id}</p>
              </div>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono ${
                sb.status === "running"
                  ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                  : "bg-slate-800 text-slate-500 border border-slate-700"
              }`}>
                {sb.status.toUpperCase()}
              </span>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-3 gap-3 text-xs font-mono">
              <div className="text-center">
                <Cpu className="w-3 h-3 mx-auto text-cyan-400 mb-1" />
                <div className="text-white font-bold">{sb.cpu}</div>
                <div className="text-slate-500 text-[10px]">CPU</div>
              </div>
              <div className="text-center">
                <HardDrive className="w-3 h-3 mx-auto text-purple-400 mb-1" />
                <div className="text-white font-bold text-[11px]">{sb.ram}</div>
                <div className="text-slate-500 text-[10px]">RAM</div>
              </div>
              <div className="text-center">
                <Wifi className="w-3 h-3 mx-auto text-amber-400 mb-1" />
                <div className="text-white font-bold">{sb.uptime}</div>
                <div className="text-slate-500 text-[10px]">Uptime</div>
              </div>
            </div>

            {/* Details */}
            <div className="text-xs space-y-1.5 pt-2 border-t border-slate-800/60">
              <div className="flex justify-between">
                <span className="text-slate-500">Agent:</span>
                <span className="text-cyan-400 font-mono">{sb.agent}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Image:</span>
                <span className="text-slate-300 font-mono text-[10px]">{sb.image}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Tools:</span>
                <span className="text-slate-300 font-mono text-[10px]">{sb.tools.join(", ")}</span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-2 pt-2">
              {sb.status === "running" ? (
                <>
                  <a href="/terminal" className="flex-1 px-3 py-1.5 bg-emerald-950/60 hover:bg-emerald-900/80 border border-emerald-800/60 text-emerald-400 text-xs font-semibold rounded-lg text-center transition">
                    Open Terminal
                  </a>
                  <button className="px-2.5 py-1.5 bg-red-950/60 hover:bg-red-900/80 border border-red-800/60 text-red-400 text-xs font-semibold rounded-lg flex items-center gap-1 transition">
                    <Square className="w-3 h-3" /> Stop
                  </button>
                </>
              ) : (
                <button className="flex-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs font-semibold rounded-lg flex items-center justify-center gap-1 transition">
                  <RefreshCw className="w-3 h-3" /> Restart
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
