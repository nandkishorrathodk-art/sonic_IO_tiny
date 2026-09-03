import React, { useState, useEffect } from "react";
import { Share2, RefreshCw, CircleDot } from "lucide-react";
import { api } from "../../lib/api";
import { StateBlock } from "../common/PageShell";

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
    <div className="flex-1 panel flex flex-col overflow-hidden p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-ink-700 pb-3">
        <div className="flex items-center gap-2">
          <Share2 className="w-4 h-4 text-accent-400" />
          <span className="text-sm font-bold text-white">Agent Knowledge Graph & Cognitive Memory</span>
          <span className="chip border border-ink-700 bg-ink-850 text-accent-400">{backend}</span>
          <span className="chip border border-ink-700 bg-ink-850 text-muted">{nodes.length} nodes · {edges.length} edges</span>
        </div>
        <button onClick={fetchGraph} className="btn-ghost">
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      <StateBlock
        error={error}
        loading={loading}
        loadingText="Loading Graph Memory…"
        empty={nodes.length === 0}
        emptyIcon={<CircleDot className="w-7 h-7" />}
        emptyTitle="Graph Memory is Empty"
        emptyText="Discovered assets, hypotheses, and verified findings will appear here during active missions."
        spinnerColor="border-t-accent-400"
      >
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2.5 overflow-y-auto">
          {nodes.map((node) => (
            <div key={node.id} className="panel p-2.5 space-y-1 hover:border-accent-500/40 transition">
              <span className="text-[10px] font-mono text-accent-400 block">{node.type}</span>
              <span className="text-xs font-semibold text-white truncate block">{node.label}</span>
              <span className="text-[9px] font-mono text-muted-dim block truncate">ID: {node.id}</span>
            </div>
          ))}
        </div>
      </StateBlock>
    </div>
  );
}
