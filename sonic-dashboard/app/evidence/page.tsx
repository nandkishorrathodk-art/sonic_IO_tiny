"use client";

import { useState, useEffect } from "react";
import { 
  FileCheck2, 
  Download, 
  Copy, 
  Check, 
  ExternalLink, 
  ShieldCheck, 
  Terminal, 
  Search,
  Code2,
  ShieldAlert,
  Loader2,
  Lock,
  GitCommit,
  CheckCircle2,
  AlertTriangle,
  Flame,
  Fingerprint,
  RefreshCw,
  Scale,
} from "lucide-react";

interface EvidenceItem {
  id: string;
  artifact_type: string;
  source_agent: string;
  tool_name: string;
  sha256: string;
  raw_content: string;
  created_at: string;
}

interface VerificationLineage {
  verifier_id: string;
  verifier_type: string;
  status: string;
  reproducible: boolean;
  notes: string;
}

interface Finding {
  id: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  confidence_score: number;
  confidence_band: "low" | "moderate" | "high" | "very_high";
  vulnerability_class: string;
  target: string;
  endpoint: string;
  lifecycle_state: string;
  poc: string;
  created_by_agent: string;
  verified_by_agents: string[];
  evidence_items: EvidenceItem[];
  verification_history: VerificationLineage[];
  manifest_hash: string;
  remediation: string;
  is_reportable: boolean;
}

export default function EvidenceBoard() {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<"trust_chain" | "reproduction" | "evidence_raw" | "manifest">("trust_chain");

  const [findings, setFindings] = useState<Finding[]>([
    {
      id: "find-jwt-none-01",
      title: "Authentication Bypass via Unsigned JWT (alg=None)",
      severity: "critical",
      confidence_score: 0.94,
      confidence_band: "very_high",
      vulnerability_class: "Broken Authentication",
      target: "https://api.target.internal",
      endpoint: "/api/v2/tokens/renew",
      lifecycle_state: "verified",
      poc: "curl -X POST https://api.target.internal/api/v2/tokens/renew -H 'Authorization: Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiJhZG1pbiIsImlzcyI6ImF1dGgifQ.'",
      created_by_agent: "recon-dynamic-agent-01",
      verified_by_agents: ["independent-verifier-02", "adversarial-reviewer-01"],
      evidence_items: [
        {
          id: "evi-01",
          artifact_type: "HTTP_REQUEST",
          source_agent: "recon-dynamic-agent-01",
          tool_name: "httpx",
          sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
          raw_content: "POST /api/v2/tokens/renew HTTP/1.1\nHost: api.target.internal\nAuthorization: Bearer eyJhbGciOiJub25lIn0...",
          created_at: "2026-08-28T07:15:00Z",
        },
        {
          id: "evi-02",
          artifact_type: "HTTP_RESPONSE",
          source_agent: "recon-dynamic-agent-01",
          tool_name: "httpx",
          sha256: "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",
          raw_content: "HTTP/1.1 200 OK\nContent-Type: application/json\n\n{\"status\":\"success\",\"role\":\"superadmin\",\"token\":\"eyJhbGci...\"}",
          created_at: "2026-08-28T07:15:01Z",
        },
        {
          id: "evi-03",
          artifact_type: "TOOL_OUTPUT",
          source_agent: "independent-verifier-02",
          tool_name: "daytona_sandbox_poc",
          sha256: "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
          raw_content: "Isolated sandbox execution confirmed HTTP 200 with privileged session grant.",
          created_at: "2026-08-28T07:16:30Z",
        },
      ],
      verification_history: [
        {
          verifier_id: "independent-verifier-02",
          verifier_type: "independent",
          status: "verified",
          reproducible: true,
          notes: "Independent replay in Daytona sandbox produced identical superadmin token.",
        },
        {
          verifier_id: "adversarial-reviewer-01",
          verifier_type: "adversarial",
          status: "verified",
          reproducible: true,
          notes: "Challenged alternative hypothesis (guest session renewal). Disproved: returned claims contain elevated admin scopes.",
        },
      ],
      manifest_hash: "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
      remediation: "Reject any JWT where the algorithm header is 'none' or missing. Enforce strict RS256 signature validation with JWKS.",
      is_reportable: true,
    },
  ]);

  const f = findings[selectedIdx] || findings[0];

  const handleCopyPoC = () => {
    if (f?.poc) {
      navigator.clipboard.writeText(f.poc);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header & Global Status */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#0F131F]/90 border border-slate-800/80 p-5 rounded-2xl glow-blue">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-emerald-600 via-cyan-500 to-blue-600 p-0.5 shadow-lg shadow-emerald-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-[#0C0E16] rounded-[10px] flex items-center justify-center">
              <ShieldCheck className="w-6 h-6 text-emerald-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-wide">EVIDENCE & TRUST ENGINE</h2>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-emerald-950 text-emerald-300 border border-emerald-800/60 rounded-full font-semibold">
                PHASE 7 VERIFIED
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              Independent adversarial verification, cryptographic chain-of-custody, and multi-factor trust scoring.
            </p>
          </div>
        </div>

        <button className="px-4 py-2 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 rounded-xl text-xs font-semibold flex items-center gap-2 transition glow-emerald">
          <Download className="w-4 h-4 text-emerald-400" />
          <span>Export Evidence Package (.zip)</span>
        </button>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Col: Findings List */}
        <div className="space-y-3 lg:col-span-1">
          <span className="text-xs font-mono text-slate-400 font-bold uppercase tracking-wider">
            Verified Findings ({findings.length})
          </span>
          <div className="space-y-2">
            {findings.map((item, idx) => (
              <div
                key={item.id}
                onClick={() => setSelectedIdx(idx)}
                className={`p-4 rounded-xl border transition cursor-pointer ${
                  selectedIdx === idx
                    ? "bg-[#141A29] border-cyan-500/60 shadow-lg shadow-cyan-950/40"
                    : "bg-[#0F131F]/80 border-slate-800 hover:border-slate-700"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-950/80 text-red-300 font-bold uppercase border border-red-800/40">
                    {item.severity}
                  </span>
                  <span className="text-[10px] font-mono text-emerald-400 font-bold">
                    {(item.confidence_score * 100).toFixed(0)}% CONFIDENCE
                  </span>
                </div>
                <h4 className="text-xs font-bold text-white mt-2 line-clamp-1">{item.title}</h4>
                <p className="text-[11px] text-slate-400 font-mono mt-1">{item.endpoint || item.target}</p>
                <div className="flex items-center gap-2 mt-3 pt-2 border-t border-slate-800/60 text-[10px] text-slate-500 font-mono">
                  <Fingerprint className="w-3 h-3 text-cyan-400" />
                  <span>SHA-256 Verified Custody</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Col: Finding Details & Trust Engine View */}
        <div className="lg:col-span-2 space-y-6">
          {f && (
            <div className="bg-[#0F131F]/90 border border-slate-800/80 rounded-2xl p-6 space-y-6">
              {/* Finding Title & Top Summary */}
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 text-[10px] font-mono bg-red-950 text-red-300 rounded font-bold uppercase border border-red-800/60">
                      {f.severity} SEVERITY
                    </span>
                    <span className="px-2 py-0.5 text-[10px] font-mono bg-emerald-950 text-emerald-300 rounded font-bold uppercase border border-emerald-800/60">
                      {f.confidence_band.toUpperCase()} CONFIDENCE ({(f.confidence_score * 100).toFixed(1)}%)
                    </span>
                    <span className="px-2 py-0.5 text-[10px] font-mono bg-blue-950 text-blue-300 rounded font-bold uppercase border border-blue-800/60">
                      {f.lifecycle_state.toUpperCase()}
                    </span>
                  </div>
                  <h3 className="text-base font-bold text-white mt-1">{f.title}</h3>
                  <p className="text-xs text-slate-400 font-mono">{f.target} {f.endpoint}</p>
                </div>
              </div>

              {/* "WHY IS THIS FINDING TRUSTED?" Panel */}
              <div className="bg-gradient-to-br from-[#0D1527] to-[#0A0E18] border border-cyan-500/30 p-4 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-cyan-400 font-mono font-bold text-xs">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    <span>WHY IS THIS FINDING TRUSTED?</span>
                  </div>
                  <span className="text-[10px] font-mono text-slate-400">Strict Provenance Engine</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                  <div className="p-2.5 bg-slate-900/60 border border-slate-800/60 rounded-lg">
                    <span className="text-[10px] font-mono text-slate-400 uppercase">Independent Verifiers:</span>
                    <p className="text-emerald-400 font-bold mt-0.5">{f.verified_by_agents.length} Independent Agents</p>
                  </div>
                  <div className="p-2.5 bg-slate-900/60 border border-slate-800/60 rounded-lg">
                    <span className="text-[10px] font-mono text-slate-400 uppercase">Controlled Reproduction:</span>
                    <p className="text-emerald-400 font-bold mt-0.5">100% Sandbox Replay</p>
                  </div>
                  <div className="p-2.5 bg-slate-900/60 border border-slate-800/60 rounded-lg">
                    <span className="text-[10px] font-mono text-slate-400 uppercase">Adversarial Review:</span>
                    <p className="text-purple-400 font-bold mt-0.5">Counter-Hypothesis Disproved</p>
                  </div>
                </div>
              </div>

              {/* Navigation Tabs */}
              <div className="flex items-center gap-2 border-b border-slate-800 pb-2 text-xs font-semibold font-mono">
                <button
                  onClick={() => setActiveTab("trust_chain")}
                  className={`px-3 py-1.5 rounded-lg transition ${activeTab === "trust_chain" ? "bg-cyan-950 text-cyan-400 border border-cyan-800/60" : "text-slate-400 hover:text-white"}`}
                >
                  Verification Lineage
                </button>
                <button
                  onClick={() => setActiveTab("reproduction")}
                  className={`px-3 py-1.5 rounded-lg transition ${activeTab === "reproduction" ? "bg-cyan-950 text-cyan-400 border border-cyan-800/60" : "text-slate-400 hover:text-white"}`}
                >
                  Reproducible PoC
                </button>
                <button
                  onClick={() => setActiveTab("evidence_raw")}
                  className={`px-3 py-1.5 rounded-lg transition ${activeTab === "evidence_raw" ? "bg-cyan-950 text-cyan-400 border border-cyan-800/60" : "text-slate-400 hover:text-white"}`}
                >
                  Attached Evidence ({f.evidence_items.length})
                </button>
                <button
                  onClick={() => setActiveTab("manifest")}
                  className={`px-3 py-1.5 rounded-lg transition ${activeTab === "manifest" ? "bg-cyan-950 text-cyan-400 border border-cyan-800/60" : "text-slate-400 hover:text-white"}`}
                >
                  SHA-256 Manifest
                </button>
              </div>

              {/* Tab 1: Verification Lineage */}
              {activeTab === "trust_chain" && (
                <div className="space-y-3">
                  {f.verification_history.map((v, i) => (
                    <div key={i} className="p-3.5 bg-slate-900/60 border border-slate-800/80 rounded-xl space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          <span className="font-bold text-white font-mono">{v.verifier_id}</span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 uppercase">
                            {v.verifier_type}
                          </span>
                        </div>
                        <span className="text-[10px] font-mono text-emerald-400 font-bold">REPRODUCIBLE: TRUE</span>
                      </div>
                      <p className="text-xs text-slate-300 pl-6">{v.notes}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Tab 2: Reproduction PoC */}
              {activeTab === "reproduction" && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-slate-400 font-bold uppercase">Sandbox Replay Command</span>
                    <button
                      onClick={handleCopyPoC}
                      className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded text-xs flex items-center gap-1.5"
                    >
                      {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copied ? "Copied" : "Copy Command"}</span>
                    </button>
                  </div>
                  <pre className="p-4 bg-[#0A0D14] border border-slate-800 rounded-xl text-xs font-mono text-emerald-400 overflow-x-auto">
                    {f.poc}
                  </pre>
                </div>
              )}

              {/* Tab 3: Evidence Raw */}
              {activeTab === "evidence_raw" && (
                <div className="space-y-3">
                  {f.evidence_items.map((it) => (
                    <div key={it.id} className="p-3.5 bg-slate-900/60 border border-slate-800/80 rounded-xl space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-cyan-400 font-bold">{it.id}</span>
                          <span className="font-mono text-[10px] px-1.5 py-0.5 bg-slate-800 rounded text-slate-300">
                            {it.artifact_type}
                          </span>
                          <span className="font-mono text-[10px] text-slate-500">by {it.source_agent}</span>
                        </div>
                        <span className="text-[10px] font-mono text-slate-400">{it.created_at}</span>
                      </div>
                      <pre className="p-2.5 bg-[#090C14] border border-slate-800/60 rounded text-[11px] font-mono text-slate-300 overflow-x-auto">
                        {it.raw_content}
                      </pre>
                      <div className="text-[10px] font-mono text-slate-500 flex items-center gap-1">
                        <Lock className="w-3 h-3 text-emerald-400" />
                        <span>SHA-256: {it.sha256}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Tab 4: Manifest */}
              {activeTab === "manifest" && (
                <div className="space-y-3">
                  <div className="p-3 bg-emerald-950/20 border border-emerald-800/40 rounded-xl text-xs space-y-1">
                    <span className="font-mono font-bold text-emerald-400 uppercase text-[10px]">
                      TOP-LEVEL CHAIN-OF-CUSTODY MANIFEST HASH
                    </span>
                    <p className="font-mono text-slate-200 text-xs break-all">{f.manifest_hash}</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
