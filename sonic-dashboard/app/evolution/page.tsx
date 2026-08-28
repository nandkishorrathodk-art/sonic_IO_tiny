'use client';

import React, { useState } from 'react';
import {
  Dna,
  ShieldCheck,
  TrendingUp,
  Cpu,
  RefreshCw,
  GitBranch,
  CheckCircle2,
  AlertTriangle,
  Flame,
  ArrowRight,
  Sparkles,
  Lock,
  Layers,
  Activity,
  History,
  FileCheck2,
  Play,
  RotateCcw,
} from 'lucide-react';

interface GenerationSnapshot {
  version: string;
  milestone: string;
  f1: number;
  precision: number;
  recall: number;
  false_positives: number;
  cost: string;
  safety: number;
}

export default function EvolutionPage() {
  const [activeTab, setActiveTab] = useState<'generations' | 'candidates' | 'weaknesses' | 'memory'>('generations');

  const generations: GenerationSnapshot[] = [
    {
      version: 'v1.0.0',
      milestone: 'Initial Baseline: Basic pattern scanning without specialized reasoning',
      f1: 0.667,
      precision: 0.75,
      recall: 0.60,
      false_positives: 4,
      cost: '$0.080',
      safety: 0,
    },
    {
      version: 'v1.1.0',
      milestone: 'Evolved Domain Skills: Specialized JWT & IDOR analysis heuristics',
      f1: 0.797,
      precision: 0.85,
      recall: 0.75,
      false_positives: 2,
      cost: '$0.070',
      safety: 0,
    },
    {
      version: 'v1.2.0',
      milestone: 'Evolved Differential Testing Strategy: Multi-header authorization state probing',
      f1: 0.924,
      precision: 0.95,
      recall: 0.90,
      false_positives: 1,
      cost: '$0.060',
      safety: 0,
    },
    {
      version: 'v1.3.0',
      milestone: 'Optimized Routing & Verification: Fast tier model routing + strict SHA-256 evidence engine',
      f1: 0.974,
      precision: 1.00,
      recall: 0.95,
      false_positives: 0,
      cost: '$0.045',
      safety: 0,
    },
  ];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header & Global Status */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#0F131F]/90 border border-slate-800/80 p-5 rounded-2xl glow-blue">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-purple-600 via-pink-500 to-cyan-500 p-0.5 shadow-lg shadow-purple-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-[#0C0E16] rounded-[10px] flex items-center justify-center">
              <Dna className="w-6 h-6 text-pink-400 animate-pulse" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-wide">AUTONOMOUS SELF-EVOLUTION ENGINE</h2>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-purple-950 text-purple-300 border border-purple-800/60 rounded-full font-semibold">
                PHASE 8 LAB
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              Empirical weakness mining, isolated sandbox experimentation, ground-truth benchmarking, and strict multi-gate promotion.
            </p>
          </div>
        </div>

        {/* Global Action */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-950/60 border border-emerald-800/60 text-emerald-400 text-xs font-mono">
            <Lock className="w-3.5 h-3.5" />
            <span>Immutable Core Protected</span>
          </div>
          <button className="px-4 py-2 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/40 rounded-xl text-xs font-semibold flex items-center gap-2 transition glow-purple">
            <RefreshCw className="w-4 h-4 text-purple-400" />
            <span>Mine Weaknesses & Evolve</span>
          </button>
        </div>
      </div>

      {/* Top Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
          <span className="text-xs text-slate-400 font-mono">Active Production Version</span>
          <div className="text-2xl font-bold text-cyan-400 font-mono mt-1">v1.3.0</div>
          <p className="text-[10px] text-emerald-400 mt-1 font-mono">+46.0% F1 Gain over v1.0.0</p>
        </div>
        <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
          <span className="text-xs text-slate-400 font-mono">False Positive Rate</span>
          <div className="text-2xl font-bold text-emerald-400 font-mono mt-1">0.0%</div>
          <p className="text-[10px] text-slate-500 mt-1 font-mono">100% eliminated via independent verifiers</p>
        </div>
        <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
          <span className="text-xs text-slate-400 font-mono">Token Cost Efficiency</span>
          <div className="text-2xl font-bold text-purple-400 font-mono mt-1">$0.045 / task</div>
          <p className="text-[10px] text-emerald-400 mt-1 font-mono">-43.8% cost reduction</p>
        </div>
        <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
          <span className="text-xs text-slate-400 font-mono">Safety Regression Violations</span>
          <div className="text-2xl font-bold text-blue-400 font-mono mt-1">0</div>
          <p className="text-[10px] text-slate-500 mt-1 font-mono">100% security gate pass rate</p>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2 text-xs font-semibold font-mono">
        <button
          onClick={() => setActiveTab('generations')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'generations' ? 'bg-purple-950 text-purple-300 border border-purple-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Multi-Generation Progression
        </button>
        <button
          onClick={() => setActiveTab('candidates')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'candidates' ? 'bg-purple-950 text-purple-300 border border-purple-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Active Candidates & Lab
        </button>
        <button
          onClick={() => setActiveTab('weaknesses')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'weaknesses' ? 'bg-purple-950 text-purple-300 border border-purple-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Mined Failure Patterns
        </button>
        <button
          onClick={() => setActiveTab('memory')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'memory' ? 'bg-purple-950 text-purple-300 border border-purple-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Evolution Memory & Lessons
        </button>
      </div>

      {/* Tab 1: Multi-Generation Progression */}
      {activeTab === 'generations' && (
        <div className="space-y-4">
          <div className="text-xs text-slate-400 font-mono">
            Empirical benchmark metrics tracked across autonomous evolutionary generations:
          </div>

          <div className="space-y-3">
            {generations.map((g, idx) => (
              <div
                key={g.version}
                className="bg-[#0F131F]/90 border border-slate-800/80 rounded-xl p-5 flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center font-mono font-bold text-cyan-400 text-sm">
                    {g.version}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-white">Generation {idx + 1}</span>
                      {idx === generations.length - 1 && (
                        <span className="px-2 py-0.5 text-[10px] font-mono bg-emerald-950 text-emerald-300 rounded font-bold uppercase border border-emerald-800/40">
                          ACTIVE PRODUCTION
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-400 font-mono mt-0.5">{g.milestone}</p>
                  </div>
                </div>

                <div className="flex items-center gap-6 text-xs font-mono">
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase">F1 Score:</span>
                    <p className="text-emerald-400 font-bold">{(g.f1 * 100).toFixed(1)}%</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase">Recall:</span>
                    <p className="text-cyan-400 font-bold">{(g.recall * 100).toFixed(0)}%</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase">False Positives:</span>
                    <p className="text-red-400 font-bold">{g.false_positives}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase">Token Cost:</span>
                    <p className="text-purple-400 font-bold">{g.cost}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 2: Active Candidates & Why Promoted / Rejected */}
      {activeTab === 'candidates' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Why Promoted Panel */}
            <div className="bg-[#0F131F]/90 border border-emerald-500/30 rounded-xl p-5 space-y-3">
              <div className="flex items-center gap-2 text-emerald-400 font-mono font-bold text-xs">
                <CheckCircle2 className="w-4 h-4" />
                <span>WHY WAS v1.3.0 PROMOTED?</span>
              </div>
              <div className="text-xs text-slate-300 space-y-1.5 font-mono">
                <p>• <span className="text-emerald-400 font-bold">+5.0% F1 improvement</span> on security ground-truth benchmark suite.</p>
                <p>• <span className="text-emerald-400 font-bold">0 False Positives</span> introduced (100% precision maintained).</p>
                <p>• <span className="text-emerald-400 font-bold">0 Safety Violations</span> across all 20 security regression tests.</p>
                <p>• <span className="text-emerald-400 font-bold">25.0% Token Cost Reduction</span> via smart routing heuristics.</p>
                <p>• <span className="text-emerald-400 font-bold">100% Canary Health</span> with zero crashes or error spikes.</p>
              </div>
            </div>

            {/* Why Rejected Panel */}
            <div className="bg-[#0F131F]/90 border border-red-500/30 rounded-xl p-5 space-y-3">
              <div className="flex items-center gap-2 text-red-400 font-mono font-bold text-xs">
                <AlertTriangle className="w-4 h-4" />
                <span>WHY WAS CANDIDATE #0087 REJECTED?</span>
              </div>
              <div className="text-xs text-slate-300 space-y-1.5 font-mono">
                <p>• <span className="text-red-400 font-bold">Security Violation Detected:</span> Candidate mutation attempted to bypass egress domain allowlist.</p>
                <p>• <span className="text-red-400 font-bold">Immutable Core Policy Triggered:</span> Modification to `egress_policy` is strictly prohibited.</p>
                <p>• <span className="text-red-400 font-bold">Lab Verdict:</span> REJECTED immediately during stage 3 (Security Regression Suite).</p>
                <p>• <span className="text-red-400 font-bold">Action:</span> Archived to Evolution Memory to prevent duplicate proposal.</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Mined Weaknesses */}
      {activeTab === 'weaknesses' && (
        <div className="space-y-4">
          <div className="text-xs text-slate-400 font-mono">
            Recurring failure patterns discovered across mission executions:
          </div>
          <div className="p-4 bg-[#0F131F]/90 border border-slate-800 rounded-xl text-xs space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-mono text-cyan-400 font-bold">FP-01: FALSE_NEGATIVE</span>
              <span className="px-2 py-0.5 bg-red-950 text-red-300 rounded font-mono text-[10px] font-bold">CRITICAL SEVERITY</span>
            </div>
            <p className="text-white font-medium">Missed differential authorization states on /api/v2/tokens.</p>
            <p className="text-slate-400 font-mono text-[11px]">Root Cause: Discovery agents only tested valid tokens without fuzzing header algorithms.</p>
            <div className="pt-2 border-t border-slate-800/60 text-emerald-400 font-mono text-[11px]">
              ✓ Addressed in Generation v1.2.0 (F1 +12.7%)
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Evolution Memory */}
      {activeTab === 'memory' && (
        <div className="space-y-4">
          <div className="text-xs text-slate-400 font-mono">
            Historical lessons learned from evolution experiments:
          </div>
          <div className="p-4 bg-[#0F131F]/90 border border-slate-800 rounded-xl text-xs space-y-2 font-mono">
            <span className="text-purple-400 font-bold">[v1.2.0 Lesson]</span>
            <p className="text-slate-200">
              Adding multi-header authorization probes increased vulnerability recall by +15% with minimal latency overhead (+40ms). Promoted to default dynamic agent strategy.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
