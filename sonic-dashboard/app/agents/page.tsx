"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Cpu,
  RefreshCw,
  AlertCircle,
  Activity,
  Bot,
  Network,
} from "lucide-react";
import { api } from "../../lib/api";
import { PageShell, PageHeader, StateBlock } from "../../components/common/PageShell";

interface AgentEntry {
  name: string;
  type: string;
  status: string;
  task: string;
  model: string;
  source?: string;
}

const STATUS_STYLE: Record<string, string> = {
  running: "text-warning border-warning/40 bg-warning/10",
  active: "text-warning border-warning/40 bg-warning/10",
  idle: "text-muted border-ink-600 bg-ink-800",
  completed: "text-success border-success/40 bg-success/10",
  blocked: "text-danger border-danger/40 bg-danger/10",
  error: "text-danger border-danger/40 bg-danger/10",
};

function StatusDot({ status }: { status: string }) {
  const s = (status || "idle").toLowerCase();
  const color =
    s === "running" || s === "active"
      ? "bg-warning animate-pulse"
      : s === "completed" || s === "success"
        ? "bg-success"
        : s === "blocked" || s === "error"
          ? "bg-danger"
          : "bg-muted-dim";
  return <span className={`inline-block w-2 h-2 rounded-full ${color}`} />;
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentEntry[]>([]);
  const [source, setSource] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getAgents();
      setAgents(data.agents || []);
      setSource(data.source || "");
    } catch (err: any) {
      setError(err.message || "Failed to load agents.");
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const activeCount = agents.filter((a) =>
    ["running", "active"].includes((a.status || "").toLowerCase()),
  ).length;

  return (
    <PageShell>
      <PageHeader
        accent="secondary"
        icon={<Cpu className="w-6 h-6 text-secondary-400" />}
        title="AGENT SWARM REGISTRY"
        badge={`${agents.length} agents · ${activeCount} active`}
        subtitle="Live view of the real SwarmRunner agent registry"
        actions={
          <button
            onClick={fetchAgents}
            disabled={loading}
            className="btn-ghost inline-flex items-center gap-2 text-xs font-mono"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            REFRESH
          </button>
        }
      />

      {error && (
        <div className="p-4 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs font-mono flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      <StateBlock
        loading={loading}
        loadingText="Loading agent registry…"
        empty={!loading && agents.length === 0}
        emptyIcon={<Bot className="w-6 h-6" />}
        emptyTitle="No agents registered"
        emptyText="The SwarmRunner has not initialized any agents yet, or the swarm backend is offline."
        children={
          <>
            {source && (
              <div className="flex items-center gap-2 text-[10px] font-mono text-muted-dim">
                <Network className="w-3 h-3" />
                SOURCE: {source}
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {agents.map((a, i) => {
                const s = (a.status || "idle").toLowerCase();
                return (
                  <div
                    key={`${a.name}-${i}`}
                    className="glass-card rounded-2xl p-4 space-y-3"
                  >
                    <div className="flex items-start gap-3">
                      <div className="grid place-items-center w-10 h-10 rounded-xl bg-ink-850 border border-ink-700 shrink-0">
                        <Bot className="w-5 h-5 text-secondary-400" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-bold text-white font-mono truncate">
                          {a.name}
                        </div>
                        <div className="text-xs text-muted-dim font-mono">
                          {a.type}
                        </div>
                      </div>
                      <span
                        className={`text-[10px] font-mono px-2 py-1 rounded border uppercase ${
                          STATUS_STYLE[s] || STATUS_STYLE.idle
                        }`}
                      >
                        {a.status}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-xs text-muted font-mono">
                      <StatusDot status={a.status} />
                      <span className="truncate">{a.task || "Ready"}</span>
                    </div>

                    <div className="flex items-center gap-2 pt-2 border-t border-ink-800/60 text-[10px] font-mono text-muted-dim">
                      <Activity className="w-3 h-3" />
                      model: {a.model || "Configured LLM"}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        }
      />
    </PageShell>
  );
}
