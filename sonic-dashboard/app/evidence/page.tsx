"use client";

import { useState, useEffect } from "react";
import {
  FileCheck2,
  RefreshCw,
  Loader2,
  AlertCircle,
  ShieldCheck,
} from "lucide-react";
import { api } from "../../lib/api";

export default function EvidenceBoard() {
  const [findings, setFindings] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEvidence = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getEvidence();
      setFindings(data.findings || []);
    } catch (err: any) {
      setError(err.message || "Failed to load verified findings from backend.");
      setFindings([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvidence();
  }, []);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto font-sans">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#0F131F]/90 border border-slate-800/80 p-5 rounded-2xl">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-emerald-600 via-cyan-500 to-blue-600 p-0.5 shadow-lg shadow-emerald-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-[#0C0E16] rounded-[10px] flex items-center justify-center">
              <FileCheck2 className="w-6 h-6 text-emerald-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-wide">EVIDENCE & VERIFICATION BOARD</h2>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-emerald-950 text-emerald-300 border border-emerald-800/60 rounded-full font-semibold">
                SHA-256 PROVEN
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              Cryptographic chain-of-custody, independent verifier logs, and deterministic vulnerability artifacts.
            </p>
          </div>
        </div>

        <button
          onClick={fetchEvidence}
          className="px-3.5 py-1.5 bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-800/80 text-emerald-400 text-xs font-mono font-bold rounded-lg flex items-center gap-1.5 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Refresh Evidence</span>
        </button>
      </div>

      {/* Main Board Content */}
      {error ? (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/60 text-red-300 text-xs font-mono">
          <strong>Backend Error:</strong> {error}
        </div>
      ) : loading ? (
        <div className="py-20 text-center space-y-2">
          <Loader2 className="w-8 h-8 animate-spin text-emerald-400 mx-auto" />
          <span className="text-xs text-slate-400 font-mono">Loading Cryptographic Custody Chain...</span>
        </div>
      ) : findings.length === 0 ? (
        <div className="glass-card rounded-2xl p-12 border border-slate-800 text-center space-y-3">
          <AlertCircle className="w-10 h-10 text-slate-600 mx-auto" />
          <h3 className="text-sm font-bold text-white">No Verified Findings Persisted</h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto">
            Discovered vulnerabilities verified by independent and adversarial verifiers will be displayed here with their complete SHA-256 audit manifest.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {findings.map((f, i) => (
            <div key={f.id || i} className="glass-card rounded-xl p-5 border border-slate-800 space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between">
                <span className="font-bold text-white">{f.title || f.name}</span>
                <span className="px-2 py-0.5 rounded bg-red-950 text-red-400 border border-red-800 text-[10px] font-bold">
                  {f.severity || "UNSPECIFIED"}
                </span>
              </div>
              <p className="text-[11px] text-slate-400">{f.target || f.endpoint}</p>
              {f.manifest_hash && (
                <div className="text-[10px] text-emerald-400 bg-[#0A0D14] p-2 rounded border border-slate-800 truncate">
                  SHA-256: {f.manifest_hash}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
