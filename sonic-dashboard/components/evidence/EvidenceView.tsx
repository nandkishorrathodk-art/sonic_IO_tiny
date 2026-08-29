import React, { useState, useEffect } from "react";
import { FileCheck2, ShieldCheck, RefreshCw, Loader2, AlertCircle } from "lucide-react";
import { api } from "../../lib/api";

export function EvidenceView() {
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
      setError(err.message || "Failed to load evidence from backend.");
      setFindings([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvidence();
  }, []);

  return (
    <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-[#30363D] pb-3">
        <div className="flex items-center gap-2">
          <FileCheck2 className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-bold text-white">Verified Findings & Cryptographic Evidence</span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
            SHA-256 Custody Chain
          </span>
        </div>
        <button
          onClick={fetchEvidence}
          className="px-2.5 py-1 bg-[#21262D] hover:bg-[#30363D] text-[#C9D1D9] hover:text-white rounded text-xs flex items-center gap-1.5 transition"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      {error ? (
        <div className="p-4 rounded-lg bg-red-950/40 border border-red-800/60 text-red-300 text-xs font-mono">
          <strong>Backend Error:</strong> {error}
        </div>
      ) : loading ? (
        <div className="my-auto text-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-emerald-400 mx-auto mb-2" />
          <span className="text-xs text-[#8B949E] font-mono">Querying Evidence Engine...</span>
        </div>
      ) : findings.length === 0 ? (
        <div className="my-auto text-center py-12 space-y-2">
          <AlertCircle className="w-8 h-8 text-[#484F58] mx-auto" />
          <h4 className="text-xs font-bold text-white">No Verified Findings Yet</h4>
          <p className="text-[11px] text-[#8B949E] max-w-sm mx-auto">
            Findings verified by independent and adversarial agents will be listed here with cryptographic proof.
          </p>
        </div>
      ) : (
        <div className="space-y-3 overflow-y-auto">
          {findings.map((f, i) => (
            <div key={f.id || i} className="p-3 rounded-lg border border-[#30363D] bg-[#0D1117] space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-white">{f.title || f.name}</span>
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-red-950 text-red-400 border border-red-800">
                  {f.severity || "CRITICAL"}
                </span>
              </div>
              <p className="text-[11px] text-[#8B949E] font-mono">{f.endpoint || f.target}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
