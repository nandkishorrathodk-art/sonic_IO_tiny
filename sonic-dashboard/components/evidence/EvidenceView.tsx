import React, { useState, useEffect } from "react";
import { FileCheck2, RefreshCw, Hash } from "lucide-react";
import { api } from "../../lib/api";
import { StateBlock } from "../common/PageShell";

export function EvidenceView({ sessionId = "default" }: { sessionId?: string }) {
  const [findings, setFindings] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEvidence = async () => {
    setLoading(true);
    setError(null);
    try {
      const [globalData, missionData] = await Promise.all([
        api.getEvidence(),
        api.getMissionEvidence(sessionId),
      ]);
      const missionEvidence = (missionData.evidence || []).map((item: any) => ({
        ...item,
        title: `${item.tool} · ${item.status}`,
        target: item.target || "Agent desktop / authorized target",
        severity: item.verified ? "VERIFIED" : "UNVERIFIED",
      }));
      setFindings([...(globalData.findings || []), ...missionEvidence]);
    } catch (err: any) {
      setError(err.message || "Failed to load evidence from backend.");
      setFindings([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvidence();
  }, [sessionId]);

  return (
    <div className="flex-1 panel flex flex-col overflow-hidden p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-ink-700 pb-3">
        <div className="flex items-center gap-2">
          <FileCheck2 className="w-4 h-4 text-success" />
          <span className="text-sm font-bold text-white">Verified Findings & Cryptographic Evidence</span>
          <span className="chip border border-ink-700 bg-ink-850 text-success">
            <Hash className="w-3 h-3" /> SHA-256 Custody
          </span>
        </div>
        <button onClick={fetchEvidence} className="btn-ghost">
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      <StateBlock
        error={error}
        loading={loading}
        loadingText="Querying Evidence Engine…"
        empty={findings.length === 0}
        emptyIcon={<FileCheck2 className="w-7 h-7" />}
        emptyTitle="No Verified Findings Yet"
        emptyText="Findings verified by independent and adversarial agents will be listed here with cryptographic proof."
        spinnerColor="border-t-success"
      >
        <div className="space-y-3 overflow-y-auto">
          {findings.map((f, i) => {
            const hash = f.sha256 || f.manifest_hash;
            return (
              <div key={f.id || i} className="panel p-3 space-y-2 hover:border-ink-600 transition">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold text-white truncate">{f.title || f.name}</span>
                  <span className="chip border border-danger/40 bg-danger/10 text-danger shrink-0">
                    {f.severity || "UNSPECIFIED"}
                  </span>
                </div>
                <p className="text-[11px] text-muted font-mono truncate">{f.endpoint || f.target}</p>
                {hash && (
                  <p className="text-[10px] text-success/80 font-mono break-all flex items-center gap-1">
                    <Hash className="w-3 h-3 shrink-0" />
                    {hash}
                  </p>
                )}
                {f.output && (
                  <pre className="text-[10px] text-muted bg-ink-950 rounded p-2 whitespace-pre-wrap max-h-28 overflow-y-auto border border-ink-700">
                    {f.output}
                  </pre>
                )}
              </div>
            );
          })}
        </div>
      </StateBlock>
    </div>
  );
}
