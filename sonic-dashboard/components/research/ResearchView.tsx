import React, { useState, useEffect } from "react";
import { Share2, RefreshCw, Layers, CircleDot, Loader2 } from "lucide-react";
import { api } from "../../lib/api";

export function ResearchView() {
  const [nodes, setNodes] = useState<any[]>([]);
  const [edges, setEdges] = useState<any[]>([]);
  const [backend, setBackend] = useState<string>("InMemoryGraph");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchGraph = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getGraph();
      setNodes(data.nodes || []);
      setEdges(data.edges || []);
      setBackend(data.backend || "InMemoryGraph");
    } catch (err: any) {
      setError(err.message || "Failed to load knowledge graph from backend.");
      setNodes([]);
      setEdges([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGraph();
  }, []);

  return (
    <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-[#30363D] pb-3">
        <div className="flex items-center gap-2">
          <Share2 className="w-4 h-4 text-purple-400" />
          <span className="text-sm font-bold text-white">Agent Knowledge Graph & Cognitive Memory</span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800">
            {backend}
          </span>
        </div>
        <button
          onClick={fetchGraph}
          className="px-2.5 py-1 bg-[#21262D] hover:bg-[#30363D] text-[#C9D1D9] hover:text-white rounded text-xs flex items-center gap-1.5 transition"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      {error ? (
        <div className="p-4 rounded-lg bg-red-950/40 border border-red-800/60 text-red-300 text-xs font-mono">
          <strong>Backend Error:</strong> {error}
        </div>
      ) : loading ? (
        <div className="my-auto text-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-purple-400 mx-auto mb-2" />
          <span className="text-xs text-[#8B949E] font-mono">Loading Graph Memory...</span>
        </div>
      ) : nodes.length === 0 ? (
        <div className="my-auto text-center py-12 space-y-2">
          <CircleDot className="w-8 h-8 text-[#484F58] mx-auto" />
          <h4 className="text-xs font-bold text-white">Graph Memory is Empty</h4>
          <p className="text-[11px] text-[#8B949E] max-w-sm mx-auto">
            Discovered assets, hypotheses, and verified findings will appear here during active missions.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2.5 overflow-y-auto">
          {nodes.map((node) => (
            <div key={node.id} className="p-2.5 rounded-lg border border-[#30363D] bg-[#0D1117] space-y-1">
              <span className="text-[10px] font-mono text-purple-400 block">{node.type}</span>
              <span className="text-xs font-semibold text-white truncate block">{node.label}</span>
              <span className="text-[9px] font-mono text-[#8B949E] block">ID: {node.id}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
