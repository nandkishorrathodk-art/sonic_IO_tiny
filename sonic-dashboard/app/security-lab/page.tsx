"use client";

import { useState, useEffect, useCallback } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Crosshair,
  ListChecks,
  Play,
  RefreshCw,
  AlertCircle,
  Lock,
  Server,
  Activity,
} from "lucide-react";
import { api } from "../../lib/api";
import { PageShell, PageHeader, StateBlock } from "../../components/common/PageShell";

interface SecurityTest {
  test_id: string;
  category: string;
  name: string;
  severity: string;
  last_verdict?: string;
}

interface Finding {
  test_id: string;
  verdict: string;
  detail?: string;
  timestamp?: string;
}

interface AttackSurfaceEntry {
  name: string;
  endpoint: string;
  protocol: string;
  auth_required: string;
  tenant_check: string;
  risk: string;
}

interface ReleaseGate {
  status: string;
  last_audit?: string;
  active_failures?: Finding[];
}

const RISK_STYLE: Record<string, string> = {
  CRITICAL: "text-danger border-danger/40 bg-danger/10",
  HIGH: "text-warning border-warning/40 bg-warning/10",
  MEDIUM: "text-secondary-300 border-secondary-500/40 bg-secondary-500/10",
  LOW: "text-muted border-ink-600 bg-ink-800",
};

const VERDICT_STYLE: Record<string, string> = {
  PASS: "text-success border-success/40 bg-success/10",
  FAIL: "text-danger border-danger/40 bg-danger/10",
  SKIP: "text-warning border-warning/40 bg-warning/10",
};

export default function SecurityLabPage() {
  const [tests, setTests] = useState<SecurityTest[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [gate, setGate] = useState<ReleaseGate | null>(null);
  const [surface, setSurface] = useState<AttackSurfaceEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [auditing, setAuditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reproducing, setReproducing] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [testsData, findingsData, gateData, surfaceData] = await Promise.all([
        api.getSecurityTests(),
        api.getSecurityFindings(),
        api.getReleaseGate(),
        api.getAttackSurface(),
      ]);
      setTests(testsData.tests || []);
      setFindings(findingsData.findings || []);
      setGate(gateData);
      setSurface(surfaceData.attack_surface || []);
    } catch (err: any) {
      setError(err.message || "Failed to load security lab data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const runAudit = async () => {
    setAuditing(true);
    setError(null);
    try {
      const data = await api.runSecurityAudit();
      setFindings(data.findings || []);
      const [gateData] = await Promise.all([api.getReleaseGate(), api.getSecurityTests()]);
      setGate(gateData);
    } catch (err: any) {
      setError(err.message || "Security audit failed.");
    } finally {
      setAuditing(false);
    }
  };

  const reproduce = async (testId: string) => {
    setReproducing(testId);
    try {
      await api.reproduceSecurityTest(testId);
      await fetchAll();
    } catch (err: any) {
      setError(err.message || `Reproducing ${testId} failed.`);
    } finally {
      setReproducing(null);
    }
  };

  const gateColor =
    gate?.status === "RELEASE_CANDIDATE_CERTIFIED"
      ? "success"
      : gate?.status?.startsWith("FAIL")
        ? "danger"
        : "warning";

  return (
    <PageShell>
      <PageHeader
        accent="primary"
        icon={<ShieldCheck className="w-6 h-6 text-primary-400" />}
        title="SELF-SECURITY TESTING LAB"
        badge={gate ? gate.status : "…"}
        subtitle="Adversarial acceptance suite & Release Gate certification"
        actions={
          <button
            onClick={runAudit}
            disabled={auditing}
            className="btn-primary inline-flex items-center gap-2 text-xs font-mono"
          >
            {auditing ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            {auditing ? "AUDITING…" : "RUN AUDIT"}
          </button>
        }
      />

      {error && (
        <div className="p-4 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs font-mono flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      <StateBlock loading={loading} loadingText="Loading security catalog…" error={null}>
        {/* Release Gate summary */}
        {gate && (
          <div
            className={`glass-card rounded-2xl p-5 border ${
              gateColor === "success"
                ? "border-success/40"
                : gateColor === "danger"
                  ? "border-danger/40"
                  : "border-warning/40"
            }`}
          >
            <div className="flex items-center gap-3">
              {gateColor === "success" ? (
                <ShieldCheck className="w-8 h-8 text-success" />
              ) : (
                <ShieldAlert className="w-8 h-8 text-warning" />
              )}
              <div>
                <div className="text-sm font-bold text-white font-mono">{gate.status}</div>
                <div className="text-xs text-muted font-mono">
                  Last audit: {gate.last_audit || "never"} · Active failures:{" "}
                  {gate.active_failures?.length || 0}
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Test catalog */}
          <div className="glass-card rounded-2xl p-5 space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-white font-mono uppercase tracking-wider">
              <ListChecks className="w-4 h-4 text-secondary-400" />
              Adversarial Test Catalog
              <span className="chip bg-ink-800 text-muted-bright border border-ink-600 ml-auto">
                {tests.length} tests
              </span>
            </div>
            <div className="space-y-2 max-h-[28rem] overflow-y-auto pr-1">
              {tests.map((t) => {
                const v = (t.last_verdict || "—") as string;
                return (
                  <div
                    key={t.test_id}
                    className="flex items-center gap-3 rounded-lg bg-ink-850/60 border border-ink-700 p-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-bold text-white font-mono">
                        {t.test_id}
                        <span className="text-muted-dim ml-2">/ {t.category}</span>
                      </div>
                      <div className="text-xs text-muted truncate">{t.name}</div>
                    </div>
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                        RISK_STYLE[t.severity] || RISK_STYLE.LOW
                      }`}
                    >
                      {t.severity}
                    </span>
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                        VERDICT_STYLE[v] || "text-muted border-ink-600 bg-ink-800"
                      }`}
                    >
                      {v}
                    </span>
                    <button
                      onClick={() => reproduce(t.test_id)}
                      disabled={reproducing === t.test_id}
                      className="text-muted hover:text-secondary-300 disabled:opacity-40"
                      title={`Reproduce ${t.test_id}`}
                    >
                      <RefreshCw
                        className={`w-3.5 h-3.5 ${reproducing === t.test_id ? "animate-spin" : ""}`}
                      />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Attack surface */}
          <div className="glass-card rounded-2xl p-5 space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-white font-mono uppercase tracking-wider">
              <Crosshair className="w-4 h-4 text-danger" />
              Attack Surface Inventory
              <span className="chip bg-ink-800 text-muted-bright border border-ink-600 ml-auto">
                {surface.length} surfaces
              </span>
            </div>
            <div className="space-y-2 max-h-[28rem] overflow-y-auto pr-1">
              {surface.map((s, i) => (
                <div
                  key={`${s.endpoint}-${i}`}
                  className="rounded-lg bg-ink-850/60 border border-ink-700 p-3 space-y-1"
                >
                  <div className="flex items-center gap-2">
                    {s.name === "Public Health" ? (
                      <Activity className="w-3.5 h-3.5 text-muted" />
                    ) : s.name === "Auth" ? (
                      <Lock className="w-3.5 h-3.5 text-warning" />
                    ) : (
                      <Server className="w-3.5 h-3.5 text-secondary-400" />
                    )}
                    <span className="text-xs font-bold text-white font-mono">{s.name}</span>
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded border ml-auto ${
                        RISK_STYLE[s.risk] || RISK_STYLE.LOW
                      }`}
                    >
                      {s.risk}
                    </span>
                  </div>
                  <div className="text-[11px] text-cyan-300 font-mono truncate">{s.endpoint}</div>
                  <div className="text-[10px] text-muted-dim font-mono">
                    {s.protocol} · auth: {s.auth_required} · tenant: {s.tenant_check}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Findings */}
        {findings.length > 0 && (
          <div className="glass-card rounded-2xl p-5 space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-white font-mono uppercase tracking-wider">
              <ShieldAlert className="w-4 h-4 text-danger" />
              Audit Findings
              <span className="chip bg-ink-800 text-muted-bright border border-ink-600 ml-auto">
                {findings.length} recorded
              </span>
            </div>
            <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
              {findings.map((f, i) => (
                <div
                  key={`${f.test_id}-${i}`}
                  className="flex items-center gap-3 rounded-lg bg-ink-850/60 border border-ink-700 p-3"
                >
                  <span className="text-xs font-mono text-dim shrink-0">{f.test_id}</span>
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                      VERDICT_STYLE[f.verdict] || ""
                    }`}
                  >
                    {f.verdict}
                  </span>
                  <span className="text-xs text-muted truncate">{f.detail}</span>
                  {f.timestamp && (
                    <span className="text-[10px] text-muted-dim font-mono ml-auto shrink-0">
                      {f.timestamp.slice(0, 19)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </StateBlock>
    </PageShell>
  );
}
