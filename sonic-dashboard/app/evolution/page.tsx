"use client";

import React, { useState, useEffect } from "react";
import { Dna, Play, RefreshCw, ShieldCheck, AlertCircle } from "lucide-react";
import { api } from "../../lib/api";
import { PageShell, PageHeader, StateBlock } from "../../components/common/PageShell";

export default function EvolutionPage() {
  const [experiments, setExperiments] = useState<any[]>([]);
  const [challenges, setChallenges] = useState<any[]>([]);
  const [benchmarking, setBenchmarking] = useState(false);
  const [benchmarkResult, setBenchmarkResult] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchExperiments = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getExperiments();
      setExperiments(data.experiments || []);
      setChallenges(data.challenges || []);
    } catch (err: any) {
      setError(err.message || "Failed to load evolution experiments.");
      setExperiments([]);
      setChallenges([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExperiments();
  }, []);

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
  const hasScore =
    benchmarkResult?.metrics &&
    typeof benchmarkResult.f1_score === "number" &&
    typeof benchmarkResult.precision === "number" &&
    typeof benchmarkResult.recall === "number";

  return (
    <PageShell>
      <PageHeader
        accent="accent"
        icon={<Dna className="w-6 h-6 text-primary-400" />}
        title="AUTONOMOUS SELF-EVOLUTION ENGINE"
        badge="CANARY LAB"
        subtitle="Ground-truth canary benchmarking, zero-regression gating, and candidate skill evolution."
        actions={
          <>
            <button onClick={handleRunBenchmark} disabled={benchmarking} className="btn-secondary !px-4 !py-2 text-xs disabled:opacity-50">
              {benchmarking ? <span className="w-4 h-4 border-2 border-secondary-400/40 border-t-secondary-400 rounded-full animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
              <span>{benchmarking ? "Benchmarking…" : "Run Canary Lab"}</span>
            </button>
            <button onClick={fetchExperiments} className="btn-ghost">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </>
        }
      />

      {benchmarkResult && (
        <div className={`glass-card p-4 rounded-xl border text-xs font-mono space-y-2 ${hasScore ? "border-success/40 bg-success/10 text-success" : "border-warning/40 bg-warning/10 text-warning"}`}>
          <div className="flex items-center justify-between font-bold flex-wrap gap-2">
            <span className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4" />
              <span>
                {hasScore
                  ? `Canary Benchmark Completed: F1 Score ${pct(benchmarkResult.f1_score)}%`
                  : `Real lab command ${benchmarkResult.verified ? "passed" : "did not pass"}`}
              </span>
            </span>
            {hasScore && <span>Precision: {pct(benchmarkResult.precision)}% | Recall: {pct(benchmarkResult.recall)}%</span>}
          </div>
        </div>
      )}

      <StateBlock
        error={error}
        loading={loading}
        loadingText="Querying Self-Evolution Pipeline…"
        empty={experiments.length === 0 && challenges.length === 0}
        emptyIcon={<AlertCircle className="w-8 h-8" />}
        emptyTitle="No Evolution Experiments Active"
        emptyText='Click "Run Canary Lab" to test current agent skills against the ground-truth benchmark suite.'
        spinnerColor="border-t-primary-400"
      >
        <div className="space-y-4">
          <h3 className="text-xs font-mono font-bold text-muted uppercase tracking-wider">
            Ground-Truth Canary Challenges ({challenges.length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {challenges.map((c, i) => (
              <div key={c.id || i} className="glass-card p-4 rounded-xl flex items-center justify-between font-mono text-xs">
                <div>
                  <span className="font-bold text-white">{c.title || c.id}</span>
                  <p className="text-[10px] text-primary-400 mt-0.5">{c.vuln_class}</p>
                </div>
                <span className="chip border border-primary-500/40 bg-primary-600/10 text-primary-400">
                  {c.difficulty || "Canary"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </StateBlock>
    </PageShell>
  );
}
