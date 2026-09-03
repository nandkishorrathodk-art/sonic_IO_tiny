"use client";

import React, { useState, useEffect } from "react";
import { BrainCircuit, RefreshCw, AlertCircle } from "lucide-react";
import { api } from "../../lib/api";
import { PageShell, PageHeader, StateBlock } from "../../components/common/PageShell";

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
    <PageShell>
      <PageHeader
        accent="secondary"
        icon={<BrainCircuit className="w-6 h-6 text-secondary-400" />}
        title="AUTONOMOUS RESEARCHER & COGNITIVE STATE"
        badge={`${nodes.length} NODES · ${edges.length} EDGES`}
        subtitle="Hypothesis portfolio, research questions, anomalies, and inter-agent knowledge graph."
        actions={
          <button onClick={fetchResearch} className="btn-ghost text-secondary-400">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh Knowledge</span>
          </button>
        }
      />

      <StateBlock
        error={error}
        loading={loading}
        loadingText="Querying Cognitive State & Graph Memory…"
        empty={nodes.length === 0}
        emptyIcon={<AlertCircle className="w-8 h-8" />}
        emptyTitle="No Research Hypotheses In Memory"
        emptyText="When research missions run, discovered questions, attack hypotheses, and graph relationships will be populated here."
        spinnerColor="border-t-secondary-400"
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 font-mono text-xs">
          {nodes.map((node) => (
            <div key={node.id} className="glass-card p-4 rounded-xl space-y-1 hover:-translate-y-0.5 transition">
              <span className="text-[10px] text-secondary-400 font-bold uppercase tracking-wide">{node.type}</span>
              <div className="text-white font-bold truncate">{node.label}</div>
              <span className="text-[9px] text-muted-dim">ID: {node.id}</span>
            </div>
          ))}
        </div>
      </StateBlock>
    </PageShell>
  );
}
