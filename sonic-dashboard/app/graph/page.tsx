"use client";

import { useState, useEffect } from "react";
import { Share2, RefreshCw, CircleDot, X } from "lucide-react";
import { api } from "../../lib/api";
import { PageShell, PageHeader, StateBlock } from "../../components/common/PageShell";

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

function nodeAccent(type: string): { border: string; text: string; bg: string } {
  const t = type.toLowerCase();
  if (t.includes("finding")) return { border: "border-danger/50", text: "text-danger", bg: "bg-danger/10" };
  if (t.includes("asset")) return { border: "border-secondary-500/50", text: "text-secondary-400", bg: "bg-secondary-600/10" };
  if (t.includes("evidence")) return { border: "border-success/50", text: "text-success", bg: "bg-success/10" };
  if (t.includes("hypothesis")) return { border: "border-warning/50", text: "text-warning", bg: "bg-warning/10" };
  return { border: "border-accent-500/50", text: "text-accent-400", bg: "bg-accent-600/10" };
}

export default function GraphExplorer() {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [backend, setBackend] = useState<string>("InMemoryGraph");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  const fetchGraph = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getGraph();
      setNodes(data.nodes || []);
      setEdges(data.edges || []);
      setBackend(data.backend || "InMemoryGraph");
    } catch (err: any) {
      setError(err.message || "Failed to load graph memory.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGraph();
  }, []);

  return (
    <PageShell>
      <PageHeader
        accent="accent"
        icon={<Share2 className="w-6 h-6 text-accent-400" />}
        title="GRAPH MEMORY EXPLORER"
        badge={backend}
        subtitle={`${nodes.length} nodes · ${edges.length} edges — the agent's persistent threat knowledge graph.`}
        actions={
          <button onClick={fetchGraph} className="btn-ghost text-accent-400">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        }
      />

      <StateBlock
        error={error}
        loading={loading}
        loadingText="Loading Graph Memory…"
        empty={nodes.length === 0}
        emptyIcon={<CircleDot className="w-8 h-8" />}
        emptyTitle="Graph Memory is Empty"
        emptyText="Discovered assets, hypotheses, and verified findings will appear here during active missions."
        spinnerColor="border-t-accent-400"
      >
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {nodes.map((node) => {
            const a = nodeAccent(node.type);
            return (
              <button
                key={node.id}
                onClick={() => setSelectedNode(node)}
                className={`panel p-3 text-left space-y-1 hover:-translate-y-0.5 transition border ${a.border}`}
              >
                <span className={`text-[10px] font-mono ${a.text} block uppercase tracking-wide`}>{node.type}</span>
                <span className="text-xs font-semibold text-white truncate block">{node.label}</span>
                <span className="text-[9px] font-mono text-muted-dim block truncate">ID: {node.id}</span>
              </button>
            );
          })}
        </div>
      </StateBlock>

      {/* Node detail drawer */}
      {selectedNode && (
        <div
          className="fixed inset-0 z-50 flex items-end md:items-center md:justify-end bg-black/60 backdrop-blur-sm p-4"
          onClick={() => setSelectedNode(null)}
        >
          <div
            className="glass-card rounded-2xl p-6 w-full max-w-md space-y-4 animate-fade-in-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <span className={`chip border ${nodeAccent(selectedNode.type).border} ${nodeAccent(selectedNode.type).bg} ${nodeAccent(selectedNode.type).text}`}>
                  {selectedNode.type}
                </span>
                <h3 className="text-lg font-bold text-white">{selectedNode.label}</h3>
              </div>
              <button onClick={() => setSelectedNode(null)} className="p-1 rounded text-muted hover:text-white hover:bg-ink-800 transition">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-2">
              <div className="text-[10px] font-mono text-muted-dim">ID</div>
              <div className="text-xs font-mono text-muted-bright break-all">{selectedNode.id}</div>
            </div>
            {Object.keys(selectedNode.properties || {}).length > 0 && (
              <div className="space-y-2">
                <div className="text-[10px] font-mono text-muted-dim uppercase tracking-wide">Properties</div>
                <pre className="text-[11px] font-mono text-muted-bright bg-ink-950 border border-ink-700 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(selectedNode.properties, null, 2)}
                </pre>
              </div>
            )}
            {edges.filter((e) => e.source === selectedNode.id || e.target === selectedNode.id).length > 0 && (
              <div className="space-y-2">
                <div className="text-[10px] font-mono text-muted-dim uppercase tracking-wide">
                  Relationships ({edges.filter((e) => e.source === selectedNode.id || e.target === selectedNode.id).length})
                </div>
                <div className="space-y-1">
                  {edges
                    .filter((e) => e.source === selectedNode.id || e.target === selectedNode.id)
                    .map((e, i) => (
                      <div key={i} className="text-[11px] font-mono text-muted flex items-center gap-2">
                        <span className="text-accent-400">{e.type}</span>
                        <span className="text-muted-dim">→</span>
                        <span className="text-secondary-400 truncate">
                          {e.target === selectedNode.id ? e.source : e.target}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </PageShell>
  );
}
