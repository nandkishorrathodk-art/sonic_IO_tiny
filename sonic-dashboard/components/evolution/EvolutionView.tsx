import React, { useState, useEffect } from "react";
import { Dna, Play, RefreshCw, ShieldCheck, FlaskConical, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import { StateBlock } from "../common/PageShell";

export function EvolutionView({ sessionId = "default" }: { sessionId?: string }) {
  const [experiments, setExperiments] = useState<any[]>([]);
  const [benchmarking, setBenchmarking] = useState(false);
  const [benchmarkResult, setBenchmarkResult] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [researchLab, setResearchLab] = useState<any | null>(null);
  const [labBusy, setLabBusy] = useState(false);

  const fetchExperiments = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getExperiments();
      setExperiments(data.experiments || []);
    } catch (err: any) {
      setError(err.message || "Failed to load evolution experiments.");
      setExperiments([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExperiments();
    api.getResearchLabStatus(sessionId).then(setResearchLab).catch(() => setResearchLab(null));
  }, [sessionId]);

  const handleProvisionLab = async () => {
    setLabBusy(true);
    try {
      const data = await api.provisionResearchLab(sessionId);
      setResearchLab(data.research_lab);
    } catch (err: any) {
      setError(err.message || "Research lab provisioning failed.");
    } finally {
      setLabBusy(false);
    }
  };

  const handleDestroyLab = async () => {
    setLabBusy(true);
    try {
      const data = await api.destroyResearchLab(sessionId);
      setResearchLab(data.research_lab);
    } catch (err: any) {
      setError(err.message || "Research lab cleanup failed.");
    } finally {
      setLabBusy(false);
    }
  };

  const handleRunBenchmark = async () => {
    setBenchmarking(true);
    setBenchmarkResult(null);
    try {
      const data = await api.runBenchmark();
      setBenchmarkResult(data);
    } catch (err: any) {
      alert(`Benchmark error: ${err.message}`);
    } finally {
      setBenchmarking(false);
    }
  };

  const pct = (v: unknown) =>
    typeof v === "number" && Number.isFinite(v) ? (v * 100).toFixed(1) : "—";
  const hasMetrics = benchmarkResult && benchmarkResult.metrics;
  const hasScore =
    hasMetrics &&
    typeof benchmarkResult.f1_score === "number" &&
    typeof benchmarkResult.precision === "number" &&
    typeof benchmarkResult.recall === "number";

  return (
    <div className="flex-1 panel flex flex-col overflow-hidden p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-ink-700 pb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Dna className="w-4 h-4 text-primary-400" />
          <span className="text-sm font-bold text-white">Autonomous Self-Evolution & Canary Benchmarks</span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`chip border ${researchLab?.workspace_id ? "text-warning border-warning/40 bg-warning/10" : "text-muted border-ink-700 bg-ink-850"}`}>
            Lab: {researchLab?.status || "NO_ACTIVE_LAB"}
          </span>
          {researchLab?.workspace_id ? (
            <button onClick={handleDestroyLab} disabled={labBusy} className="btn-ghost text-danger border-danger/40 hover:bg-danger/10 disabled:opacity-50">
              <Trash2 className="w-3 h-3" /> Destroy Lab
            </button>
          ) : (
            <button onClick={handleProvisionLab} disabled={labBusy} className="btn-ghost text-warning border-warning/40 hover:bg-warning/10 disabled:opacity-50">
              <FlaskConical className="w-3 h-3" /> Provision Lab
            </button>
          )}
          <button
            onClick={handleRunBenchmark}
            disabled={benchmarking}
            className="btn-secondary !px-3 !py-1.5 text-xs disabled:opacity-50"
          >
            <Play className="w-3 h-3 fill-current" />
            <span>{benchmarking ? "Benchmarking…" : "Run Canary Lab"}</span>
          </button>
          <button onClick={fetchExperiments} className="btn-ghost">
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {benchmarkResult && (
        <div
          className={`p-3 rounded-lg border text-xs font-mono space-y-1 ${
            hasScore ? "bg-success/10 border-success/40 text-success" : "bg-warning/10 border-warning/40 text-warning"
          }`}
        >
          <div className="font-bold flex items-center gap-2">
            <ShieldCheck className="w-4 h-4" />
            <span>
              {hasScore
                ? `Canary Benchmark Complete: F1 Score ${pct(benchmarkResult.f1_score)}%`
                : `Real lab command ${benchmarkResult.verified ? "passed" : "did not pass"}`}
            </span>
          </div>
          <div className="text-muted">
            {hasScore
              ? `Precision: ${pct(benchmarkResult.precision)}% | Recall: ${pct(benchmarkResult.recall)}%`
              : "No vulnerability score was generated without an authorized evaluator."}
          </div>
        </div>
      )}

      <StateBlock
        error={error}
        loading={loading}
        loadingText="Loading Evolution Lab…"
        empty={experiments.length === 0}
        emptyIcon={<Dna className="w-7 h-7" />}
        emptyTitle="No Active Evolution Experiments"
        emptyText='Click "Run Canary Lab" to benchmark self-evolution skills against ground-truth security fixtures.'
        spinnerColor="border-t-primary-400"
      >
        <div className="space-y-2 overflow-y-auto">
          {experiments.map((exp, idx) => (
            <div key={exp.experiment_id || idx} className="panel p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-white">{exp.title}</span>
                <span className="text-[10px] font-mono text-primary-400">{exp.status}</span>
              </div>
            </div>
          ))}
        </div>
      </StateBlock>
    </div>
  );
}
