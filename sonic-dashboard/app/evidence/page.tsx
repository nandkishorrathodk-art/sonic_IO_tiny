"use client";

import { useState, useEffect } from "react";
import { FileCheck2, RefreshCw, Hash, AlertCircle } from "lucide-react";
import { api } from "../../lib/api";
import { PageShell, PageHeader, StateBlock } from "../../components/common/PageShell";

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
    <PageShell>
      <PageHeader
        accent="success"
        icon={<FileCheck2 className="w-6 h-6 text-success" />}
        title="EVIDENCE & VERIFICATION BOARD"
        badge="SHA-256 PROVEN"
        subtitle="Cryptographic chain-of-custody, independent verifier logs, and deterministic vulnerability artifacts."
        actions={
          <button onClick={fetchEvidence} className="btn-ghost text-success">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh Evidence</span>
          </button>
        }
      />

      <StateBlock
        error={error}
        loading={loading}
        loadingText="Loading Cryptographic Custody Chain…"
        empty={findings.length === 0}
        emptyIcon={<AlertCircle className="w-8 h-8" />}
        emptyTitle="No Verified Findings Persisted"
        emptyText="Discovered vulnerabilities verified by independent and adversarial verifiers will be displayed here with their complete SHA-256 audit manifest."
        spinnerColor="border-t-success"
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {findings.map((f, i) => {
            const hash = f.manifest_hash || f.sha256;
            return (
              <div key={f.id || i} className="glass-card rounded-xl p-5 space-y-3 font-mono text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-white truncate">{f.title || f.name}</span>
                  <span className="chip border border-danger/40 bg-danger/10 text-danger">
                    {f.severity || "UNSPECIFIED"}
                  </span>
                </div>
                <p className="text-[11px] text-muted truncate">{f.target || f.endpoint}</p>
                {hash && (
                  <div className="text-[10px] text-success bg-ink-950 p-2 rounded border border-ink-700 break-all flex items-center gap-1">
                    <Hash className="w-3 h-3 shrink-0" />
                    <span>{hash}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </StateBlock>
    </PageShell>
  );
}
