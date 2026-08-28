"use client";

import { useState, useEffect } from "react";
import { Share2, Search, Filter, Layers, Database, RefreshCw, Loader2, CircleDot } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface GraphNode {
  id: string;
  label: string;
  type: string;
  properties: Record<string, any>;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export default function GraphExplorer() {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [backend, setBackend] = useState<string>("InMemoryGraph");
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  const fetchGraph = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/live/graph`);
      if (res.ok) {
        const data = await res.json();
        setNodes(data.nodes || []);
        setEdges(data.edges || []);
        setBackend(data.backend || "InMemoryGraph");
      }
    } catch {
      // Offline fallback
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGraph();
  }, []);

  const getNodeColor = (type: string) => {
    const t = type.toLowerCase();
    if (t.includes("finding")) return "border-red-500 text-red-400 bg-red-950/40";
    if (t.includes("asset")) return "border-cyan-500 text-cyan-400 bg-cyan-950/40";
    if (t.includes("hypothesis")) return "border-purple-500 text-purple-400 bg-purple-950/40";
    if (t.includes("evidence")) return "border-emerald-500 text-emerald-400 bg-emerald-950/40";
    if (t.includes("agent")) return "border-blue-500 text-blue-400 bg-blue-950/40";
    if (t.includes("engagement")) return "border-amber-500 text-amber-400 bg-amber-950/40";
    return "border-slate-700 text-slate-300 bg-slate-900/40";
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <Share2 className="w-5 h-5 text-purple-400" />
            <h2 className="text-xl font-bold text-white tracking-tight">Agent-to-Agent Graph Memory</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Inter-agent shared knowledge graph ({backend} powered) mapping assets, hypotheses, and findings.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchGraph}
            className="px-3 py-2 bg-slate-900 hover:bg-slate-800 border border-slate-700 rounded-lg text-xs font-semibold text-slate-200 flex items-center gap-2 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${loading ? 'animate-spin' : ''}`} />
            <span>Sync Graph</span>
          </button>
        </div>
      </div>

      {/* Graph Visual Canvas */}
      <div className="glass-card rounded-xl p-6 border border-slate-800 min-h-[480px] relative overflow-hidden flex flex-col justify-between">
        <div className="flex items-center justify-between z-10 flex-wrap gap-2">
          <div className="flex items-center gap-2 bg-slate-900/90 px-3 py-1.5 rounded-lg border border-slate-800 text-xs font-mono">
            <Layers className="w-3.5 h-3.5 text-purple-400" />
            <span>Nodes: {nodes.length} | Edges: {edges.length}</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] font-mono text-slate-400">Legend:</span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800">Asset</span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-red-950 text-red-400 border border-red-800">Finding</span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-purple-950 text-purple-400 border border-purple-800">Hypothesis</span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">Evidence</span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800">Agent</span>
          </div>
        </div>

        {loading ? (
          <div className="my-auto text-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-purple-400 mx-auto mb-2" />
            <p className="text-xs text-slate-400 font-mono">Querying Graph Memory...</p>
          </div>
        ) : nodes.length === 0 ? (
          <div className="my-auto text-center py-12">
            <CircleDot className="w-10 h-10 text-slate-600 mx-auto mb-2" />
            <h4 className="text-sm font-bold text-white mb-1">Graph Memory is Empty</h4>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              Run an engagement from Mission Control to populate the graph with discovered assets, hypotheses, and findings.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 my-6 z-10">
            {nodes.map((n) => (
              <div
                key={n.id}
                onClick={() => setSelectedNode(n)}
                className={`p-3.5 rounded-xl border backdrop-blur-md transition hover:scale-105 cursor-pointer ${getNodeColor(n.type)} ${
                  selectedNode?.id === n.id ? 'ring-2 ring-white/50' : ''
                }`}
              >
                <span className="text-[10px] font-mono block opacity-70 mb-1">{n.type}</span>
                <span className="text-xs font-bold font-mono block truncate">{n.label}</span>
                <span className="text-[9px] font-mono text-slate-400 block mt-1">ID: {n.id}</span>
              </div>
            ))}
          </div>
        )}

        {/* Selected Node Inspector */}
        {selectedNode && (
          <div className="glass-card p-4 rounded-xl border border-slate-700/80 bg-slate-950/80 z-20 mt-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-white font-mono">Node Inspector: {selectedNode.id}</span>
              <button onClick={() => setSelectedNode(null)} className="text-xs text-slate-400 hover:text-white">✕</button>
            </div>
            <pre className="bg-[#0a0d14] p-3 rounded-lg text-[11px] font-mono text-cyan-300 overflow-x-auto max-h-40">
              {JSON.stringify(selectedNode.properties, null, 2)}
            </pre>
          </div>
        )}

        <div className="text-center text-xs text-slate-500 font-mono z-10 pt-4">
          Live Graph Engine Active • Total Nodes: {nodes.length} • Total Relationships: {edges.length}
        </div>
      </div>
    </div>
  );
}
