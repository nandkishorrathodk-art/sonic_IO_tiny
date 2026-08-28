'use client';

import React, { useState } from 'react';
import {
  BrainCircuit,
  Compass,
  GitFork,
  HelpCircle,
  Lightbulb,
  AlertOctagon,
  Shuffle,
  Ban,
  CheckCircle2,
  Play,
  Pause,
  Layers,
  ArrowRight,
  TrendingUp,
  Activity,
  FileText,
} from 'lucide-react';

export default function ResearchDashboardPage() {
  const [activeTab, setActiveTab] = useState<'tracks' | 'questions' | 'hypotheses' | 'anomalies' | 'report'>('tracks');

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#0F131F]/90 border border-slate-800/80 p-5 rounded-2xl glow-blue">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-cyan-500 via-indigo-500 to-purple-600 p-0.5 shadow-lg shadow-indigo-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-[#0C0E16] rounded-[10px] flex items-center justify-center">
              <BrainCircuit className="w-6 h-6 text-cyan-400 animate-pulse" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-wide">AUTONOMOUS RESEARCHER ENGINE</h2>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-cyan-950 text-cyan-300 border border-cyan-800/60 rounded-full font-semibold">
                PHASE 12
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              Disciplined long-horizon research: hypothesis portfolios, parallel tracks, anomaly detection, dead-end avoidance, and strategy switching.
            </p>
          </div>
        </div>

        {/* Mode Selector & Actions */}
        <div className="flex items-center gap-3 font-mono text-xs">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-950/60 border border-indigo-800/60 text-indigo-300 font-bold">
            <Compass className="w-4 h-4 text-cyan-400" />
            <span>MODE: AUTONOMOUS</span>
          </div>
          <button className="px-3.5 py-1.5 bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-300 border border-cyan-500/40 rounded-xl font-semibold flex items-center gap-2 transition glow-cyan">
            <Play className="w-3.5 h-3.5 text-cyan-400" />
            <span>Active Mission</span>
          </button>
        </div>
      </div>

      {/* Top Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 font-mono text-xs">
        <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
          <span className="text-slate-400">Parallel Tracks</span>
          <div className="text-2xl font-bold text-cyan-400 mt-1">2 Active</div>
          <p className="text-[10px] text-slate-500 mt-1">1 Track paused (Dead-end)</p>
        </div>
        <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
          <span className="text-slate-400">Questions Resolved</span>
          <div className="text-2xl font-bold text-emerald-400 mt-1">2 / 3</div>
          <p className="text-[10px] text-emerald-400 mt-1">66.7% Resolution Rate</p>
        </div>
        <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
          <span className="text-slate-400">Hypothesis Portfolio</span>
          <div className="text-2xl font-bold text-purple-400 mt-1">1 Confirmed</div>
          <p className="text-[10px] text-slate-500 mt-1">1 Rejected | 1 In-Progress</p>
        </div>
        <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
          <span className="text-slate-400">Action Efficiency</span>
          <div className="text-2xl font-bold text-amber-400 mt-1">+66.7%</div>
          <p className="text-[10px] text-emerald-400 mt-1">Wasted actions eliminated</p>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2 text-xs font-semibold font-mono">
        <button
          onClick={() => setActiveTab('tracks')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'tracks' ? 'bg-cyan-950 text-cyan-300 border border-cyan-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Investigation Tracks
        </button>
        <button
          onClick={() => setActiveTab('questions')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'questions' ? 'bg-cyan-950 text-cyan-300 border border-cyan-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Research Questions
        </button>
        <button
          onClick={() => setActiveTab('hypotheses')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'hypotheses' ? 'bg-cyan-950 text-cyan-300 border border-cyan-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Hypothesis Portfolio
        </button>
        <button
          onClick={() => setActiveTab('anomalies')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'anomalies' ? 'bg-cyan-950 text-cyan-300 border border-cyan-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Anomalies & Strategy Pivots
        </button>
        <button
          onClick={() => setActiveTab('report')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'report' ? 'bg-cyan-950 text-cyan-300 border border-cyan-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Research Notebook
        </button>
      </div>

      {/* Tab 1: Investigation Tracks */}
      {activeTab === 'tracks' && (
        <div className="space-y-3 font-mono text-xs">
          <div className="bg-[#0F131F]/90 border border-slate-800/80 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <div className="text-white font-bold flex items-center gap-2">
                <GitFork className="w-4 h-4 text-cyan-400" />
                <span>Track 1: Differential JWT Token & Signature Probe</span>
              </div>
              <span className="text-[10px] text-slate-400">Objective: Test algorithm confusion and alg=none forgery</span>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-yellow-400 font-bold">Priority: 2.140</span>
              <span className="px-2.5 py-1 rounded text-xs font-bold bg-emerald-950 text-emerald-300 border border-emerald-800/40">
                ACTIVE (2 Slots)
              </span>
            </div>
          </div>

          <div className="bg-[#0F131F]/90 border border-slate-800/80 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <div className="text-white font-bold flex items-center gap-2">
                <GitFork className="w-4 h-4 text-indigo-400" />
                <span>Track 2: Client-Side DOM State & Role Hydration</span>
              </div>
              <span className="text-[10px] text-slate-400">Objective: Inspect React client context for privileged views</span>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-yellow-400 font-bold">Priority: 1.650</span>
              <span className="px-2.5 py-1 rounded text-xs font-bold bg-emerald-950 text-emerald-300 border border-emerald-800/40">
                ACTIVE (1 Slot)
              </span>
            </div>
          </div>

          <div className="bg-[#0F131F]/90 border border-slate-800/80 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 opacity-60">
            <div>
              <div className="text-white font-bold flex items-center gap-2">
                <Ban className="w-4 h-4 text-red-400" />
                <span>Track 3: Rate-Limit Header Exhaustion Probe</span>
              </div>
              <span className="text-[10px] text-slate-400">Objective: Test WAF IP rotation reset</span>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-slate-500">Priority: 0.450</span>
              <span className="px-2.5 py-1 rounded text-xs font-bold bg-red-950 text-red-300 border border-red-800/40">
                PAUSED (Dead-End Detected)
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Research Questions */}
      {activeTab === 'questions' && (
        <div className="space-y-3 font-mono text-xs">
          <div className="bg-[#0F131F]/90 border border-slate-800/80 rounded-xl p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-white font-bold flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-cyan-400" />
                <span>Does the backend verify JWT HMAC signature strictly?</span>
              </span>
              <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800/60 rounded text-[10px] font-bold">
                RESOLVED
              </span>
            </div>
            <p className="text-slate-400 text-[11px]">
              Answer: <span className="text-emerald-400 font-bold">No, changing alg to 'none' bypasses verification and yields HTTP 200 Admin Token.</span>
            </p>
          </div>

          <div className="bg-[#0F131F]/90 border border-slate-800/80 rounded-xl p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-white font-bold flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-cyan-400" />
                <span>Can user roles be escalated via header injection?</span>
              </span>
              <span className="px-2 py-0.5 bg-yellow-950 text-yellow-300 border border-yellow-800/60 rounded text-[10px] font-bold">
                INVESTIGATING
              </span>
            </div>
            <p className="text-slate-400 text-[11px]">Currently being probed on Track 1.</p>
          </div>
        </div>
      )}

      {/* Tab 3: Hypothesis Portfolio */}
      {activeTab === 'hypotheses' && (
        <div className="space-y-3 font-mono text-xs">
          <div className="bg-[#0F131F]/90 border border-emerald-800/60 rounded-xl p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-white font-bold flex items-center gap-2">
                <Lightbulb className="w-4 h-4 text-emerald-400" />
                <span>H1: JWT signature algorithm 'none' allows admin privilege escalation</span>
              </span>
              <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800/60 rounded text-[10px] font-bold">
                CONFIRMED (Confidence: 0.85)
              </span>
            </div>
            <p className="text-slate-400 text-[11px]">Supporting Evidence: ev-jwt-admin-200 (SHA-256 Verified)</p>
          </div>

          <div className="bg-[#0F131F]/90 border border-red-800/40 rounded-xl p-4 space-y-2 opacity-70">
            <div className="flex items-center justify-between">
              <span className="text-white font-bold flex items-center gap-2">
                <Lightbulb className="w-4 h-4 text-red-400" />
                <span>H2: Endpoint protected solely by network-level rate limit</span>
              </span>
              <span className="px-2 py-0.5 bg-red-950 text-red-300 border border-red-800/60 rounded text-[10px] font-bold">
                REJECTED (Confidence: 0.10)
              </span>
            </div>
            <p className="text-slate-400 text-[11px]">Contradictory Evidence: Rate limit does not protect backend admin handler</p>
          </div>
        </div>
      )}

      {/* Tab 4: Anomalies & Strategy Pivots */}
      {activeTab === 'anomalies' && (
        <div className="space-y-3 font-mono text-xs">
          <div className="bg-[#0F131F]/90 border border-red-800/60 rounded-xl p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-white font-bold flex items-center gap-2">
                <AlertOctagon className="w-4 h-4 text-red-400" />
                <span>Prediction Deviation: Expected 401 Unauthorized, Observed 200 OK</span>
              </span>
              <span className="px-2 py-0.5 bg-red-950 text-red-300 border border-red-800/60 rounded text-[10px] font-bold">
                NOVEL ANOMALY
              </span>
            </div>
            <p className="text-slate-400 text-[11px]">
              Automatically generated high-value research lead: <span className="text-yellow-400">lead-01 (Priority: 0.85)</span>
            </p>
          </div>

          <div className="bg-[#0F131F]/90 border border-slate-800/80 rounded-xl p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-white font-bold flex items-center gap-2">
                <Shuffle className="w-4 h-4 text-cyan-400" />
                <span>Strategy Pivot on Track 3: HTTP_DIFFERENTIAL_PROBE → BROWSER_DOM_ANALYSIS</span>
              </span>
              <span className="px-2 py-0.5 bg-indigo-950 text-indigo-300 border border-indigo-800/60 rounded text-[10px] font-bold">
                STRATEGY SWITCHED
              </span>
            </div>
            <p className="text-slate-400 text-[11px]">Reason: 3 consecutive identical 429 probe responses with zero information gain.</p>
          </div>
        </div>
      )}

      {/* Tab 5: Research Notebook Report */}
      {activeTab === 'report' && (
        <div className="bg-[#0F131F]/90 border border-slate-800 rounded-xl p-6 space-y-4 font-mono text-xs">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <span className="text-white font-bold text-sm flex items-center gap-2">
              <FileText className="w-4 h-4 text-cyan-400" />
              <span>RESEARCH NOTEBOOK SUMMARY</span>
            </span>
            <span className="px-3 py-1 bg-emerald-950 text-emerald-300 border border-emerald-800/60 rounded font-bold">
              STOP CONDITION: GOAL_SATISFIED
            </span>
          </div>
          <div className="space-y-3 text-slate-300">
            <div>
              <span className="text-slate-400 font-bold">Initial Known Facts:</span>
              <p className="text-slate-300">Target host api.target.corp returns 429 on rapid burst.</p>
            </div>
            <div>
              <span className="text-slate-400 font-bold">Primary Finding:</span>
              <p className="text-emerald-400 font-bold">
                CONFIRMED: JWT signature verification is disabled when alg=none, granting unauthorized admin privilege.
              </p>
            </div>
            <div>
              <span className="text-slate-400 font-bold">Efficiency & Dead-End Telemetry:</span>
              <p className="text-slate-300">
                1 Dead-end track terminated early saving 66.7% wasted actions and reducing time-to-discovery by 56.3%.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
