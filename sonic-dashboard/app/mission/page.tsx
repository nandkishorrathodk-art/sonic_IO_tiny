'use client';

import React, { useState } from 'react';
import {
  Brain,
  CheckCircle2,
  HelpCircle,
  Lightbulb,
  AlertTriangle,
  Play,
  RotateCcw,
  Sparkles,
  ArrowRight,
  TrendingUp,
  Activity,
  Layers,
  Pause,
  RefreshCw,
  Search,
  ShieldCheck,
  Target,
  FileQuestion,
  GitCompare,
  Flame,
  Info,
  Scale,
} from 'lucide-react';

interface CompetingHypo {
  id: string;
  statement: string;
  status: 'proposed' | 'candidate' | 'validating' | 'confirmed' | 'disproved';
  confidence: number;
  supporting_count: number;
  contradicting_count: number;
  falsification_test: string;
}

interface ContradictionItem {
  id: string;
  statement_a: string;
  statement_b: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  resolved: boolean;
}

interface DecisionTraceItem {
  decision_id: string;
  selected_action: string;
  unknown_addressed: string;
  selection_reason: string;
  expected_info_gain: number;
  predicted_outcome: string;
  actual_outcome: string;
  prediction_error: number;
  confidence_shift: string;
  time: string;
}

export default function CognitiveMissionPage() {
  const [activeTab, setActiveTab] = useState<'world_model' | 'hypotheses' | 'predictions' | 'decisions'>('world_model');

  // Competing Hypotheses State
  const [hypotheses, setHypotheses] = useState<CompetingHypo[]>([
    {
      id: 'hypo-01',
      statement: 'Endpoint /api/v2/tokens allows signature bypass via alg=None header',
      status: 'validating',
      confidence: 0.82,
      supporting_count: 2,
      contradicting_count: 0,
      falsification_test: 'Send alg=None token and verify if server rejects with 401/403',
    },
    {
      id: 'hypo-02',
      statement: 'Authorization bypass is due to reverse proxy path normalization inconsistency',
      status: 'candidate',
      confidence: 0.45,
      supporting_count: 1,
      contradicting_count: 1,
      falsification_test: 'Compare direct upstream port response with gateway response',
    },
    {
      id: 'hypo-03',
      statement: 'Observed behavior is an intentional guest token renewal mechanism (non-vulnerable)',
      status: 'proposed',
      confidence: 0.15,
      supporting_count: 0,
      contradicting_count: 2,
      falsification_test: 'Inspect returned claims for elevated admin privileges',
    },
  ]);

  // Contradictions State
  const [contradictions, setContradictions] = useState<ContradictionItem[]>([
    {
      id: 'ctrd-01',
      statement_a: 'Endpoint /api/v2/tokens returned 403 Forbidden under standard GET request',
      statement_b: 'Endpoint /api/v2/tokens returned 200 OK when X-Custom-Auth header is absent',
      severity: 'high',
      resolved: false,
    },
  ]);

  // Decision Traces State ("Why this action?")
  const [decisions, setDecisions] = useState<DecisionTraceItem[]>([
    {
      decision_id: 'dec-101',
      selected_action: 'Dynamic: Fuzz JWT None-Algorithm on /api/v2/tokens',
      unknown_addressed: 'Does /api/v2/tokens enforce signature verification?',
      selection_reason: 'Highest expected information gain (0.90) with minimal safety risk (0.05)',
      expected_info_gain: 0.90,
      predicted_outcome: 'HTTP 200 with admin claims if vulnerable, HTTP 401 if secure',
      actual_outcome: 'HTTP 200 OK with admin session token returned',
      prediction_error: 0.00,
      confidence_shift: '45.0% → 82.5%',
      time: '12:48 UTC',
    },
    {
      decision_id: 'dec-100',
      selected_action: 'Static: Analyze JWKS endpoints and public key formats',
      unknown_addressed: 'What cryptographic keys and algorithms are accepted?',
      selection_reason: 'Prerequisite reconnaissance with zero network side-effects',
      expected_info_gain: 0.75,
      predicted_outcome: 'RS256 and ES256 key definitions in JWKS JSON',
      actual_outcome: 'Valid RSA public keys found on /.well-known/jwks.json',
      prediction_error: 0.05,
      confidence_shift: '25.0% → 45.0%',
      time: '12:44 UTC',
    },
  ]);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Top Banner & Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#0F131F]/90 border border-slate-800/80 p-5 rounded-2xl glow-blue">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-cyan-600 via-blue-500 to-purple-600 p-0.5 shadow-lg shadow-cyan-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-[#0C0E16] rounded-[10px] flex items-center justify-center">
              <Brain className="w-6 h-6 text-cyan-400 animate-pulse" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-wide">CRITICAL THINKING & RESEARCH ENGINE</h2>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-purple-950 text-purple-300 border border-purple-800/60 rounded-full font-semibold">
                PHASE 6 REASONING
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              Hypothesis testing, prediction error tracking, information gain scoring & contradiction resolution.
            </p>
          </div>
        </div>

        {/* Global Controls */}
        <div className="flex items-center gap-2.5">
          <button className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 flex items-center gap-2 transition">
            <Pause className="w-3.5 h-3.5 text-amber-400" />
            <span>Pause Mission</span>
          </button>
          <button className="px-3.5 py-2 rounded-lg bg-cyan-600/20 hover:bg-cyan-600/30 text-xs font-semibold text-cyan-300 border border-cyan-500/40 flex items-center gap-2 transition glow-cyan">
            <RefreshCw className="w-3.5 h-3.5 text-cyan-400" />
            <span>Evaluate Next Action</span>
          </button>
        </div>
      </div>

      {/* Active Contradiction Alert Banner (if any) */}
      {contradictions.some((c) => !c.resolved) && (
        <div className="bg-amber-950/40 border border-amber-500/40 p-4 rounded-xl flex items-start gap-3 glow-amber">
          <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-amber-300 uppercase tracking-wider font-mono text-[11px]">
                ACTIVE CONTRADICTION DETECTED — DISCRIMINATING TEST REQUIRED
              </span>
              <span className="px-1.5 py-0.5 rounded bg-amber-900/60 text-amber-300 text-[10px] font-mono">HIGH SEVERITY</span>
            </div>
            <p className="text-slate-300 mt-1">
              <span className="text-slate-400">Observation A:</span> "{contradictions[0].statement_a}" <br />
              <span className="text-slate-400">Observation B:</span> "{contradictions[0].statement_b}"
            </p>
            <div className="mt-2 flex items-center gap-2">
              <button className="px-2.5 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/50 rounded font-semibold text-[10px]">
                Launch Discriminating Experiment
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2 text-xs font-semibold font-mono">
        <button
          onClick={() => setActiveTab('world_model')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'world_model' ? 'bg-cyan-950/80 text-cyan-400 border border-cyan-800/60' : 'text-slate-400 hover:text-slate-200'}`}
        >
          World Model & Facts
        </button>
        <button
          onClick={() => setActiveTab('hypotheses')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'hypotheses' ? 'bg-cyan-950/80 text-cyan-400 border border-cyan-800/60' : 'text-slate-400 hover:text-slate-200'}`}
        >
          Competing Hypotheses ({hypotheses.length})
        </button>
        <button
          onClick={() => setActiveTab('decisions')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'decisions' ? 'bg-cyan-950/80 text-cyan-400 border border-cyan-800/60' : 'text-slate-400 hover:text-slate-200'}`}
        >
          "Why This Action?" Decision Traces
        </button>
      </div>

      {/* Tab 1: World Model & Quick Metrics */}
      {activeTab === 'world_model' && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
              <span className="text-xs text-slate-400">Multi-Factor Confidence</span>
              <div className="text-2xl font-bold text-emerald-400 font-mono mt-1">82.5%</div>
              <p className="text-[10px] text-slate-500 mt-1 font-mono">Evidence + Independence - Contradictions</p>
            </div>
            <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
              <span className="text-xs text-slate-400">Prediction Accuracy</span>
              <div className="text-2xl font-bold text-cyan-400 font-mono mt-1">95.0%</div>
              <p className="text-[10px] text-slate-500 mt-1 font-mono">Mean Prediction Error: 0.05</p>
            </div>
            <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
              <span className="text-xs text-slate-400">Information Gain Rate</span>
              <div className="text-2xl font-bold text-purple-400 font-mono mt-1">0.82 / task</div>
              <p className="text-[10px] text-slate-500 mt-1 font-mono">Zero repeated failed attempts</p>
            </div>
            <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
              <span className="text-xs text-slate-400">Stop Condition Status</span>
              <div className="text-2xl font-bold text-blue-400 font-mono mt-1">Active</div>
              <p className="text-[10px] text-slate-500 mt-1 font-mono">Goal satisfaction in progress</p>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Competing Hypotheses & Anti-Bias Board */}
      {activeTab === 'hypotheses' && (
        <div className="space-y-4">
          <div className="text-xs text-slate-400 font-mono">
            Evaluating competing explanations simultaneously to eliminate confirmation bias:
          </div>
          <div className="grid grid-cols-1 gap-4">
            {hypotheses.map((h) => (
              <div key={h.id} className="bg-[#0F131F]/90 border border-slate-800/80 rounded-xl p-5 space-y-3">
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono font-bold text-cyan-400">{h.id.toUpperCase()}</span>
                      <span className="text-xs font-mono uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-semibold">
                        {h.status}
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-white">{h.statement}</p>
                  </div>
                  <div className="text-right">
                    <span className="text-lg font-bold font-mono text-emerald-400">{(h.confidence * 100).toFixed(0)}%</span>
                    <p className="text-[10px] text-slate-500 font-mono">Confidence</p>
                  </div>
                </div>

                <div className="p-3 bg-slate-900/60 border border-slate-800/60 rounded-lg text-xs space-y-1">
                  <span className="text-slate-400 font-mono text-[10px] uppercase font-bold flex items-center gap-1.5">
                    <Target className="w-3.5 h-3.5 text-purple-400" />
                    Adversarial Falsification Challenge:
                  </span>
                  <p className="text-slate-200">{h.falsification_test}</p>
                </div>

                <div className="flex items-center justify-between text-xs text-slate-400 pt-1 border-t border-slate-800/40">
                  <div className="flex items-center gap-4">
                    <span className="text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> {h.supporting_count} Supporting Evidence
                    </span>
                    <span className="text-red-400 flex items-center gap-1">
                      <AlertTriangle className="w-3.5 h-3.5" /> {h.contradicting_count} Contradicting Evidence
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 3: "Why this action?" Decision Traces */}
      {activeTab === 'decisions' && (
        <div className="space-y-4">
          <div className="text-xs text-slate-400 font-mono">
            Auditable Decision Trace showing the exact uncertainty, expected information gain, and prediction comparison for every action:
          </div>
          <div className="space-y-4">
            {decisions.map((dec) => (
              <div key={dec.decision_id} className="bg-[#0F131F]/90 border border-slate-800/80 rounded-xl p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold text-purple-400">{dec.decision_id}</span>
                    <span className="text-xs font-bold text-white">{dec.selected_action}</span>
                  </div>
                  <span className="text-xs font-mono text-slate-500">{dec.time}</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                  <div className="p-3 bg-slate-900/60 border border-slate-800/60 rounded-lg">
                    <span className="text-[10px] text-slate-500 font-mono uppercase">Unknown Addressed:</span>
                    <p className="text-slate-200 font-medium mt-0.5">{dec.unknown_addressed}</p>
                  </div>
                  <div className="p-3 bg-slate-900/60 border border-slate-800/60 rounded-lg">
                    <span className="text-[10px] text-slate-500 font-mono uppercase">Selection Reason:</span>
                    <p className="text-slate-200 font-medium mt-0.5">{dec.selection_reason}</p>
                  </div>
                  <div className="p-3 bg-slate-900/60 border border-slate-800/60 rounded-lg">
                    <span className="text-[10px] text-slate-500 font-mono uppercase">Confidence Shift:</span>
                    <p className="text-emerald-400 font-mono font-bold mt-0.5">{dec.confidence_shift}</p>
                  </div>
                </div>

                {/* Prediction vs Actual */}
                <div className="p-3 bg-cyan-950/20 border border-cyan-800/40 rounded-lg text-xs space-y-1">
                  <div className="flex items-center justify-between font-mono text-[10px]">
                    <span className="text-cyan-400 font-bold uppercase">PREDICTION VS ACTUAL COMPARISON</span>
                    <span className="text-emerald-400 font-bold">Error Score: {dec.prediction_error.toFixed(2)} (Match)</span>
                  </div>
                  <p className="text-slate-300"><span className="text-slate-500">Predicted:</span> {dec.predicted_outcome}</p>
                  <p className="text-slate-200"><span className="text-slate-500">Observed:</span> {dec.actual_outcome}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
