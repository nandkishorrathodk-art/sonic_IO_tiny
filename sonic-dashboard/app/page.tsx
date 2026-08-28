"use client";

import { useState, useEffect, useCallback } from "react";
import { 
  Terminal, 
  ShieldAlert, 
  Radar, 
  Search, 
  Zap, 
  CheckCircle2, 
  AlertTriangle, 
  Flame, 
  Clock, 
  Play, 
  ChevronRight,
  TrendingUp,
  Share2,
  Loader2,
  WifiOff
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface LiveStats {
  assets_mapped: number;
  active_hypotheses: number;
  verified_findings: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  evidence_rate: string;
  false_positives: number;
  active_agents: number;
  total_agents: number;
  llm_requests: number;
  graph_nodes: number;
  memory_backend: string;
}

interface Agent {
  name: string;
  type: string;
  status: string;
  task: string;
  model: string;
  updated_at?: string;
}

interface Finding {
  title?: string;
  severity?: string;
  vulnerability_class?: string;
  confidence?: number;
  confidence_score?: number;
  target?: string;
  discovered_at?: string;
  status?: string;
}

export default function MissionControl() {
  const [targetInput, setTargetInput] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [apiOnline, setApiOnline] = useState(false);
  const [stats, setStats] = useState<LiveStats | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [scanResult, setScanResult] = useState<string>("");

  // Fetch live data from backend
  const fetchLiveData = useCallback(async () => {
    try {
      const [statsRes, agentsRes, findingsRes] = await Promise.all([
        fetch(`${API_BASE}/live/stats`),
        fetch(`${API_BASE}/live/agents`),
        fetch(`${API_BASE}/live/findings`),
      ]);

      if (statsRes.ok) {
        setStats(await statsRes.json());
        setApiOnline(true);
      }
      if (agentsRes.ok) {
        const data = await agentsRes.json();
        setAgents(data.agents || []);
      }
      if (findingsRes.ok) {
        const data = await findingsRes.json();
        setFindings(data.findings || []);
      }
    } catch {
      setApiOnline(false);
    }
  }, []);

  // Poll every 3 seconds
  useEffect(() => {
    fetchLiveData();
    const interval = setInterval(fetchLiveData, 3000);
    return () => clearInterval(interval);
  }, [fetchLiveData]);

  const handleLaunch = async () => {
    if (!targetInput.trim()) return;
    setIsRunning(true);
    setScanResult("");

    try {
      const res = await fetch(`${API_BASE}/live/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: targetInput }),
      });
      const data = await res.json();
      setScanResult(data.status === "completed"
        ? `✅ Scan complete: ${data.findings_count} findings, ${data.assets_count} assets`
        : `⚠️ ${data.error || "Scan finished with issues"}`
      );
      await fetchLiveData(); // Refresh immediately
    } catch (e) {
      setScanResult("❌ Failed to connect to SONIC-REDA API");
    } finally {
      setIsRunning(false);
    }
  };

  const assetsMapped = stats?.assets_mapped ?? 0;
  const activeHypotheses = stats?.active_hypotheses ?? 0;
  const verifiedFindings = stats?.verified_findings ?? 0;
  const evidenceRate = stats?.evidence_rate ?? "N/A";

  return (
    <div className="space-y-6">
      {/* API Status Banner */}
      {!apiOnline && (
        <div className="glass-card rounded-xl p-3 border border-amber-800/60 bg-amber-950/30 flex items-center gap-2 text-xs text-amber-400">
          <WifiOff className="w-4 h-4" />
          <span><strong>Backend Offline</strong> — Start the API server: <code className="bg-slate-800 px-1.5 py-0.5 rounded">cd sonic-core && uvicorn sonic.api.main:app --reload</code></span>
        </div>
      )}

      {/* Top Banner & Quick Engagement Launcher */}
      <div className="glass-card rounded-xl p-5 border border-slate-800 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono text-cyan-400 uppercase tracking-wider">Mission Control Center</span>
            {apiOnline && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 animate-pulse">LIVE</span>
            )}
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 font-mono">
              {stats?.memory_backend || "—"}
            </span>
          </div>
          <h2 className="text-xl font-bold text-white tracking-tight">Active Swarm Operations</h2>
          <p className="text-xs text-slate-400">Real-time autonomous multi-agent intelligence. All data fetched from live backend.</p>
        </div>

        <div className="flex items-center gap-3 w-full lg:w-auto">
          <div className="relative flex-1 lg:w-80">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={targetInput}
              onChange={(e) => setTargetInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLaunch()}
              placeholder="Enter target (e.g. scanme.nmap.org)..."
              className="w-full pl-9 pr-3 py-2 bg-slate-900/90 border border-slate-700/80 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-mono"
            />
          </div>
          <button
            onClick={handleLaunch}
            disabled={isRunning || !targetInput.trim()}
            className="px-4 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white font-bold text-xs rounded-lg flex items-center gap-2 transition duration-150 glow-red flex-shrink-0"
          >
            {isRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-current" />}
            <span>{isRunning ? "SCANNING..." : "ENGAGE TARGET"}</span>
          </button>
        </div>
      </div>

      {/* Scan Result Banner */}
      {scanResult && (
        <div className={`glass-card rounded-xl p-3 border text-xs font-mono ${
          scanResult.startsWith("✅") ? "border-emerald-800/60 text-emerald-400 bg-emerald-950/30" :
          scanResult.startsWith("⚠️") ? "border-amber-800/60 text-amber-400 bg-amber-950/30" :
          "border-red-800/60 text-red-400 bg-red-950/30"
        }`}>
          {scanResult}
        </div>
      )}

      {/* Metrics Row — LIVE DATA */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass-card p-4 rounded-xl border border-slate-800/80">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
            <span>Assets Mapped</span>
            <Radar className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-white">{assetsMapped}</div>
          <div className="text-[11px] text-cyan-400 mt-1 flex items-center gap-1">
            <TrendingUp className="w-3 h-3" /> From live scan
          </div>
        </div>

        <div className="glass-card p-4 rounded-xl border border-slate-800/80">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
            <span>Graph Nodes</span>
            <Share2 className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-white">{stats?.graph_nodes ?? 0}</div>
          <div className="text-[11px] text-purple-400 mt-1">{stats?.memory_backend || "—"}</div>
        </div>

        <div className="glass-card p-4 rounded-xl border border-slate-800/80">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
            <span>Verified Findings</span>
            <ShieldAlert className="w-4 h-4 text-red-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-red-400">{verifiedFindings}</div>
          <div className="text-[11px] text-slate-400 mt-1">
            {stats ? `${stats.critical_count}C ${stats.high_count}H ${stats.medium_count}M` : "—"}
          </div>
        </div>

        <div className="glass-card p-4 rounded-xl border border-slate-800/80">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
            <span>LLM Requests</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-400">{stats?.llm_requests ?? 0}</div>
          <div className="text-[11px] text-emerald-400 mt-1">{evidenceRate} evidence rate</div>
        </div>
      </div>

      {/* Main Grid: Agent Swarm Matrix & Live Finding Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Agent Swarm Grid */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              {agents.length > 0 && <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>}
              Agentic Graph Swarm ({agents.length} Agents{agents.filter(a => a.status === "active" || a.status === "running").length > 0 ? " Active" : ""})
            </h3>
            <span className="text-xs text-slate-500 font-mono">
              {apiOnline ? `Backend: ${stats?.memory_backend || "Connected"}` : "Offline"}
            </span>
          </div>

          {agents.length === 0 ? (
            <div className="glass-card p-8 rounded-xl border border-slate-800/70 text-center">
              <Terminal className="w-8 h-8 text-slate-600 mx-auto mb-3" />
              <p className="text-sm text-slate-500">No agents registered yet.</p>
              <p className="text-xs text-slate-600 mt-1">Launch a scan to activate the swarm.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {agents.map((ag, idx) => (
                <div key={idx} className="glass-card p-4 rounded-xl border border-slate-800/70 hover:border-slate-700 transition">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-xs text-white">{ag.name}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-semibold uppercase ${
                      ag.status === "running" ? "bg-cyan-950 text-cyan-400 border border-cyan-800" :
                      ag.status === "active" ? "bg-emerald-950 text-emerald-400 border border-emerald-800" :
                      ag.status === "error" ? "bg-red-950 text-red-400 border border-red-800" :
                      "bg-slate-800 text-slate-400"
                    }`}>
                      {ag.status}
                    </span>
                  </div>
                  <p className="text-xs text-slate-300 mb-3 line-clamp-1">{ag.task}</p>
                  <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between text-[10px] text-slate-400 font-mono">
                    <span>MODEL: <strong className="text-slate-200">{ag.model}</strong></span>
                    <span className="text-cyan-400 flex items-center gap-0.5 hover:underline cursor-pointer">
                      Inspect <ChevronRight className="w-3 h-3" />
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Col: Live Findings Stream */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Flame className="w-4 h-4 text-red-500" />
              Verified Findings Feed
            </h3>
            <span className="text-xs text-slate-500 font-mono">{apiOnline ? "Live" : "Offline"}</span>
          </div>

          {findings.length === 0 ? (
            <div className="glass-card p-6 rounded-xl border border-slate-800 text-center">
              <ShieldAlert className="w-6 h-6 text-slate-600 mx-auto mb-2" />
              <p className="text-xs text-slate-500">No findings yet. Run a scan to discover vulnerabilities.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {findings.slice(0, 10).map((f, idx) => (
                <div key={idx} className="glass-card p-4 rounded-xl border border-slate-800 hover:border-red-500/40 transition">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono ${
                      (f.severity || "").toUpperCase() === "CRITICAL" ? "bg-red-950 text-red-400 border border-red-800" :
                      (f.severity || "").toUpperCase() === "HIGH" ? "bg-orange-950 text-orange-400 border border-orange-800" :
                      "bg-yellow-950 text-yellow-400 border border-yellow-800"
                    }`}>
                      {(f.severity || "UNKNOWN").toUpperCase()}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      {f.discovered_at ? new Date(f.discovered_at).toLocaleTimeString() : "—"}
                    </span>
                  </div>
                  <h4 className="text-xs font-semibold text-slate-100 hover:text-cyan-400 transition cursor-pointer mb-2">
                    {f.title || "Untitled Finding"}
                  </h4>
                  <div className="flex items-center justify-between text-[10px] text-slate-400 pt-2 border-t border-slate-800/60 font-mono">
                    <span>Class: <strong className="text-slate-300">{f.vulnerability_class || "—"}</strong></span>
                    <span className="text-emerald-400 font-bold">
                      Conf: {f.confidence ?? f.confidence_score ?? 0}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
