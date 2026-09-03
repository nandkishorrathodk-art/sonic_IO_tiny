"use client";

import { useState, useEffect } from "react";
import {
  FlaskConical,
  TrendingUp,
  Activity,
  Play,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { api } from "../../lib/api";
import { PageShell, PageHeader } from "../../components/common/PageShell";

interface Experiment {
  experiment_id: string;
  title: string;
  description?: string;
  experiment_type?: string;
  target_component?: string;
  status: string;
  baseline_f1?: number;
  candidate_f1?: number;
  f1_delta?: number;
  safety_violations?: number;
  created_at?: string;
}

const pct = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : "—");

export default function ExperimentLab() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [challenges, setChallenges] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [benchmarking, setBenchmarking] = useState(false);
  const [benchmarkResult, setBenchmarkResult] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchExperiments = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getExperiments();
      if (data) {
        setExperiments(data.experiments || []);
        setChallenges(data.challenges || []);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load experiments.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExperiments();
  }, []);

  const runCanaryBenchmark = async () => {
    setBenchmarking(true);
    setBenchmarkResult(null);
    try {
      const data = await api.runBenchmark();
      if (data) setBenchmarkResult(data);
    } catch (err: any) {
      alert(`Benchmark failed: ${err.message}`);
    } finally {
      setBenchmarking(false);
    }
  };

  const activeVersion = experiments.length > 0 ? experiments[0].target_component || "Unknown" : "Not available";
  const rolledBackCount = experiments.filter((e) => e.status === "ROLLED_BACK").length;
  const regressionRate = experiments.length > 0 ? ((rolledBackCount / experiments.length) * 100).toFixed(1) : "0.0";
  const displayF1 = benchmarkResult
    ? pct(benchmarkResult.f1_score)
    : experiments.length > 0 && experiments[0].candidate_f1
    ? pct(experiments[0].candidate_f1)
    : "Not measured";

  const hasScore = benchmarkResult && typeof benchmarkResult.f1_score === "number";

  return (
    <PageShell>
      <PageHeader
        accent="accent"
        icon={<FlaskConical className="w-6 h-6 text-warning" />}
        title="EXPERIMENT LAB & SELF-EVOLUTION"
        badge="CANARY"
        subtitle="Automated canary benchmarking, zero-regression evaluation, and self-evolution pipeline."
        actions={
          <>
            <button onClick={runCanaryBenchmark} disabled={benchmarking} className="btn-primary !px-4 !py-2 text-xs disabled:opacity-50">
              {benchmarking ? <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" /> : <Play className="w-3.5 h-3.5 fill-current" />}
              <span>{benchmarking ? "RUNNING…" : "RUN CANARY LAB"}</span>
            </button>
            <span className="chip border border-success/40 bg-success/10 text-success">
              <ShieldCheck className="w-3.5 h-3.5" /> Immutable Safety
            </span>
          </>
        }
      />

      {benchmarkResult && (
        <div className={`glass-card p-4 rounded-xl border text-xs font-mono space-y-2 ${hasScore ? "border-success/40 bg-success/10 text-success" : "border-warning/40 bg-warning/10 text-warning"}`}>
          <div className="flex items-center justify-between font-bold flex-wrap gap-2">
            <span>✅ Canary Benchmark Completed: F1 {pct(benchmarkResult.f1_score)}</span>
            {hasScore && <span>Precision: {pct(benchmarkResult.precision)} | Recall: {pct(benchmarkResult.recall)}</span>}
          </div>
          <p className="text-muted-bright text-[11px]">
            Validated on {challenges.length} ground-truth challenges returned by the backend.
          </p>
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass-card p-4 rounded-xl">
          <div className="flex items-center justify-between text-xs text-muted mb-1">
            <span>Active Skill Architecture</span>
            <Sparkles className="w-4 h-4 text-warning" />
          </div>
          <div className="text-2xl font-bold font-mono text-white truncate">{activeVersion}</div>
          <div className="text-[11px] text-success mt-1 flex items-center gap-1">
            <TrendingUp className="w-3 h-3" /> F1 Metric: {displayF1}
          </div>
        </div>
        <div className="glass-card p-4 rounded-xl">
          <div className="flex items-center justify-between text-xs text-muted mb-1">
            <span>Canary Regression Rate</span>
            <Activity className="w-4 h-4 text-secondary-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-secondary-400">{experiments.length ? `${regressionRate}%` : "Not measured"}</div>
          <div className="text-[11px] text-muted-dim mt-1">Based on recorded experiments only</div>
        </div>
        <div className="glass-card p-4 rounded-xl">
          <div className="flex items-center justify-between text-xs text-muted mb-1">
            <span>Benchmark Challenges</span>
            <FlaskConical className="w-4 h-4 text-accent-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-accent-400">{challenges.length} Active</div>
          <div className="text-[11px] text-muted-dim mt-1">Ground-truth verification suite</div>
        </div>
      </div>

      {/* Challenges */}
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-muted-bright uppercase tracking-wider">Ground Truth Benchmark Lab Suite</h3>
        {loading ? (
          <div className="py-12 text-center text-xs text-muted font-mono">Loading challenges…</div>
        ) : challenges.length === 0 ? (
          <div className="glass-card p-6 rounded-xl text-center text-xs text-muted">
            No benchmark challenges loaded. Run the canary lab to benchmark current prompts.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {challenges.map((c, i) => (
              <div key={c.id || i} className="glass-card p-3.5 rounded-xl space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="chip border border-warning/40 bg-warning/10 text-warning text-[10px]">
                    {String(c.difficulty || "Canary").toUpperCase()}
                  </span>
                  <span className="text-[10px] text-muted-dim font-mono">{c.id}</span>
                </div>
                <h4 className="text-xs font-bold text-white">{c.title}</h4>
                <p className="text-[11px] text-muted font-mono">Class: {c.vuln_class}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Experiments */}
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-muted-bright uppercase tracking-wider">Recent Self-Evolution Experiments</h3>
        {experiments.length === 0 ? (
          <div className="glass-card p-6 rounded-xl text-center text-xs text-muted">
            No mutation experiments proposed yet. Run the canary lab to benchmark current prompts.
          </div>
        ) : (
          <div className="space-y-2">
            {experiments.map((exp) => (
              <div key={exp.experiment_id} className="glass-card p-4 rounded-xl flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold text-white truncate">{exp.title}</span>
                    <span className="chip border border-ink-700 bg-ink-800 text-muted-bright text-[10px]">{exp.status}</span>
                  </div>
                  {exp.description && <p className="text-[11px] text-muted truncate">{exp.description}</p>}
                </div>
                <div className="flex items-center gap-3 text-[11px] font-mono shrink-0">
                  <span className="text-muted-dim">Δ {exp.f1_delta != null ? (exp.f1_delta >= 0 ? "+" : "") + (exp.f1_delta * 100).toFixed(1) + "%" : "—"}</span>
                  <span className={exp.safety_violations ? "text-danger" : "text-success"}>
                    {exp.safety_violations || 0} violations
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </PageShell>
  );
}
