"use client";

import React, { useState, useEffect } from "react";
import {
  Dna,
  ShieldCheck,
  RefreshCw,
  Play,
  Loader2,
  AlertCircle,
  TrendingUp,
} from "lucide-react";
import { api } from "../../lib/api";

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

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto font-sans">
      {/* Header & Global Status */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#0F131F]/90 border border-slate-800/80 p-5 rounded-2xl">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-purple-600 via-pink-500 to-cyan-500 p-0.5 shadow-lg shadow-purple-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-[#0C0E16] rounded-[10px] flex items-center justify-center">
              <Dna className="w-6 h-6 text-pink-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-wide">AUTONOMOUS SELF-EVOLUTION ENGINE</h2>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-purple-950 text-purple-300 border border-purple-800/60 rounded-full font-semibold">
                CANARY LAB
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              Ground-truth canary benchmarking, zero-regression gating, and candidate skill evolution.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleRunBenchmark}
            disabled={benchmarking}
            className="px-4 py-2 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/40 rounded-xl text-xs font-semibold flex items-center gap-2 transition disabled:opacity-50"
          >
            {benchmarking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
            <span>{benchmarking ? "Benchmarking..." : "Run Canary Lab"}</span>
          </button>
          <button
            onClick={fetchExperiments}
            className="px-3.5 py-2 bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Benchmark Result Banner */}
      {benchmarkResult && (
        <div className="glass-card p-4 rounded-xl border border-emerald-800 bg-emerald-950/30 text-xs font-mono space-y-2">
          <div className="flex items-center justify-between text-emerald-400 font-bold">
            <span className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4" />
              Canary Benchmark Completed: F1 Score {(benchmarkResult.f1_score * 100).toFixed(1)}%
            </span>
            <span>Precision: {(benchmarkResult.precision * 100).toFixed(1)}% | Recall: {(benchmarkResult.recall * 100).toFixed(1)}%</span>
          </div>
        </div>
      )}

      {/* Main Content */}
      {error ? (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/60 text-red-300 text-xs font-mono">
          <strong>Backend Error:</strong> {error}
        </div>
      ) : loading ? (
        <div className="py-20 text-center space-y-2">
          <Loader2 className="w-8 h-8 animate-spin text-pink-400 mx-auto" />
          <span className="text-xs text-slate-400 font-mono">Querying Self-Evolution Pipeline...</span>
        </div>
      ) : experiments.length === 0 && challenges.length === 0 ? (
        <div className="glass-card rounded-2xl p-12 border border-slate-800 text-center space-y-3">
          <AlertCircle className="w-10 h-10 text-slate-600 mx-auto" />
          <h3 className="text-sm font-bold text-white">No Evolution Experiments Active</h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto">
            Click "Run Canary Lab" to test current agent skills against the ground-truth benchmark suite.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <h3 className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider">
            Ground-Truth Canary Challenges ({challenges.length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {challenges.map((c, i) => (
              <div key={c.id || i} className="glass-card p-4 rounded-xl border border-slate-800 flex items-center justify-between font-mono text-xs">
                <div>
                  <span className="font-bold text-white">{c.title || c.id}</span>
                  <p className="text-[10px] text-purple-400 mt-0.5">{c.vuln_class}</p>
                </div>
                <span className="px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800 text-[10px]">
                  {c.difficulty || "Canary"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
