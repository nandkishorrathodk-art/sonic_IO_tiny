import React, { useState, useEffect } from "react";
import { Dna, Play, RefreshCw, Loader2, ShieldCheck, FlaskConical, Trash2 } from "lucide-react";
import { api } from "../../lib/api";

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

  return (
    <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-[#30363D] pb-3">
        <div className="flex items-center gap-2">
          <Dna className="w-4 h-4 text-pink-400" />
          <span className="text-sm font-bold text-white">Autonomous Self-Evolution & Canary Benchmarks</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`px-2 py-1 rounded text-[10px] font-mono border ${researchLab?.workspace_id ? "text-amber-300 border-amber-700/50 bg-amber-950/30" : "text-[#8B949E] border-[#30363D]"}`}>
            Lab: {researchLab?.status || "NO_ACTIVE_LAB"}
          </span>
          {researchLab?.workspace_id ? (
            <button onClick={handleDestroyLab} disabled={labBusy} className="px-2 py-1 rounded text-[10px] font-mono text-red-300 border border-red-800/50 hover:bg-red-950/40 disabled:opacity-50 flex items-center gap-1">
              <Trash2 className="w-3 h-3" /> Destroy Lab
            </button>
          ) : (
            <button onClick={handleProvisionLab} disabled={labBusy} className="px-2 py-1 rounded text-[10px] font-mono text-amber-300 border border-amber-700/50 hover:bg-amber-950/40 disabled:opacity-50 flex items-center gap-1">
              <FlaskConical className="w-3 h-3" /> Provision Lab
            </button>
          )}
          <button
            onClick={handleRunBenchmark}
            disabled={benchmarking}
            className="px-3 py-1 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/40 rounded text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-50"
          >
            {benchmarking ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3 fill-current" />}
            <span>{benchmarking ? "Benchmarking..." : "Run Canary Lab"}</span>
          </button>
          <button
            onClick={fetchExperiments}
            className="px-2.5 py-1 bg-[#21262D] hover:bg-[#30363D] text-[#C9D1D9] hover:text-white rounded text-xs flex items-center gap-1.5 transition"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {benchmarkResult && benchmarkResult.metrics && (
        <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-800 text-emerald-300 text-xs font-mono space-y-1">
          <div className="font-bold flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Canary Benchmark Complete: F1 Score {(benchmarkResult.f1_score * 100).toFixed(1)}%</span>
          </div>
          <div className="text-[#8B949E]">
            Precision: {(benchmarkResult.precision * 100).toFixed(1)}% | Recall: {(benchmarkResult.recall * 100).toFixed(1)}%
          </div>
        </div>
      )}
      {benchmarkResult && !benchmarkResult.metrics && (
        <div className={`p-3 rounded-lg border text-xs font-mono space-y-1 ${benchmarkResult.verified ? "bg-emerald-950/40 border-emerald-800 text-emerald-300" : "bg-amber-950/30 border-amber-800 text-amber-300"}`}>
          <div className="font-bold flex items-center gap-2"><ShieldCheck className="w-4 h-4" />
            <span>Real lab command {benchmarkResult.verified ? "passed" : "did not pass"}</span>
          </div>
          <div className="text-[#8B949E]">No vulnerability score was generated without an authorized evaluator.</div>
        </div>
      )}

      {error ? (
        <div className="p-4 rounded-lg bg-red-950/40 border border-red-800/60 text-red-300 text-xs font-mono">
          <strong>Backend Error:</strong> {error}
        </div>
      ) : loading ? (
        <div className="my-auto text-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-pink-400 mx-auto mb-2" />
          <span className="text-xs text-[#8B949E] font-mono">Loading Evolution Lab...</span>
        </div>
      ) : experiments.length === 0 ? (
        <div className="my-auto text-center py-12 space-y-2">
          <Dna className="w-8 h-8 text-[#484F58] mx-auto" />
          <h4 className="text-xs font-bold text-white">No Active Evolution Experiments</h4>
          <p className="text-[11px] text-[#8B949E] max-w-sm mx-auto">
            Click "Run Canary Lab" to benchmark self-evolution skills against ground-truth security fixtures.
          </p>
        </div>
      ) : (
        <div className="space-y-2 overflow-y-auto">
          {experiments.map((exp, idx) => (
            <div key={exp.experiment_id || idx} className="p-3 rounded-lg border border-[#30363D] bg-[#0D1117]">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-white">{exp.title}</span>
                <span className="text-[10px] font-mono text-purple-400">{exp.status}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
