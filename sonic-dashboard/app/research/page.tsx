"use client";

import React, { useState, useEffect } from "react";
import {
  BrainCircuit,
  Compass,
  RefreshCw,
  Loader2,
  AlertCircle,
  Share2,
} from "lucide-react";
import { api } from "../../lib/api";

export default function ResearchDashboardPage() {
  const [nodes, setNodes] = useState<any[]>([]);
  const [edges, setEdges] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchResearch = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getGraph();
      setNodes(data.nodes || []);
      setEdges(data.edges || []);
    } catch (err: any) {
      setError(err.message || "Failed to load research memory.");
      setNodes([]);
      setEdges([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchResearch();
  }, []);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto font-sans">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#0F131F]/90 border border-slate-800/80 p-5 rounded-2xl">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-cyan-500 via-indigo-500 to-purple-600 p-0.5 shadow-lg shadow-indigo-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-[#0C0E16] rounded-[10px] flex items-center justify-center">
              <BrainCircuit className="w-6 h-6 text-cyan-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-wide">AUTONOMOUS RESEARCHER & COGNITIVE STATE</h2>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-cyan-950 text-cyan-300 border border-cyan-800/60 rounded-full font-semibold">
                GRAPH MEMORY
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              Hypothesis portfolio, research questions, anomalies, and inter-agent knowledge graph.
            </p>
          </div>
        </div>

        <button
          onClick={fetchResearch}
          className="px-3.5 py-1.5 bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-300 border border-cyan-500/40 rounded-xl font-semibold flex items-center gap-2 transition text-xs font-mono"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Refresh Knowledge</span>
        </button>
      </div>

      {/* Main Content */}
      {error ? (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/60 text-red-300 text-xs font-mono">
          <strong>Backend Error:</strong> {error}
        </div>
      ) : loading ? (
        <div className="py-20 text-center space-y-2">
          <Loader2 className="w-8 h-8 animate-spin text-cyan-400 mx-auto" />
          <span className="text-xs text-slate-400 font-mono">Querying Cognitive State & Graph Memory...</span>
        </div>
      ) : nodes.length === 0 ? (
        <div className="glass-card rounded-2xl p-12 border border-slate-800 text-center space-y-3">
          <AlertCircle className="w-10 h-10 text-slate-600 mx-auto" />
          <h3 className="text-sm font-bold text-white">No Research Hypotheses In Memory</h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto">
            When research missions run, discovered questions, attack hypotheses, and graph relationships will be populated here.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 font-mono text-xs">
          {nodes.map((node) => (
            <div key={node.id} className="glass-card p-4 rounded-xl border border-slate-800 space-y-1">
              <span className="text-[10px] text-cyan-400 font-bold uppercase">{node.type}</span>
              <div className="text-white font-bold truncate">{node.label}</div>
              <span className="text-[9px] text-slate-500">ID: {node.id}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
