"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Mail,
  Building,
  UserCheck,
  ArrowRight,
  Lock,
  AlertCircle,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { setAuthToken } from "../../lib/auth";
import { API_BASE } from "../../lib/api";
import { BrandMark } from "../../components/common/BrandMark";

const ROLES = [
  { id: "operator", label: "Operator" },
  { id: "admin", label: "Admin" },
  { id: "auditor", label: "Auditor" },
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [role, setRole] = useState("operator");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, name, role, tenant_id: tenantId }),
      });

      if (!res.ok) throw new Error(`Login failed with status ${res.status}`);

      const data = await res.json();
      if (data?.access_token) {
        setAuthToken(data.access_token, {
          email: data.user?.email || email,
          name: data.user?.name || name,
          role: data.user?.role || "operator",
          tenant_id: data.user?.tenant_id || tenantId,
        });
        router.push("/");
      } else {
        throw new Error("No access token returned.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to authenticate session.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-ink-950 text-slate-200 flex flex-col justify-between font-sans relative overflow-hidden">
      {/* Ambient glows */}
      <div className="fixed inset-0 bg-grid-glow pointer-events-none" />
      <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] bg-primary-600/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[600px] h-[600px] bg-secondary-600/10 rounded-full blur-[140px] pointer-events-none" />

      {/* Top nav */}
      <header className="h-16 border-b border-ink-800/80 backdrop-blur-md bg-ink-950/60 px-6 flex items-center justify-between z-10">
        <BrandMark withWordmark href="/landing" />
        <div className="flex items-center gap-3 text-xs font-mono">
          <Link href="/landing" className="btn-ghost">Overview</Link>
          <Link href="/" className="btn-secondary !px-4 !py-2 text-xs">
            <span>Direct Workstation</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </header>

      {/* Login card */}
      <main className="flex-1 flex items-center justify-center p-6 z-10">
        <div className="w-full max-w-md glass-card rounded-2xl p-8 shadow-2xl space-y-6 relative animate-fade-in-up">
          <div className="space-y-2 text-center">
            <div className="inline-flex items-center gap-1.5 chip bg-primary-600/10 text-primary-400 border border-primary-500/40">
              <Lock className="w-3 h-3" />
              <span>TENANT-ISOLATED ACCESS</span>
            </div>
            <h1 className="text-xl font-bold tracking-tight text-white">
              Autonomous Workstation Login
            </h1>
            <p className="text-xs text-muted font-mono">
              Authenticate tenant identity to load isolated missions &amp; Docker sandbox.
            </p>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs font-mono flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-4 text-xs font-mono">
            <div className="space-y-1.5">
              <label className="text-muted-bright font-medium flex items-center gap-1.5">
                <Mail className="w-3.5 h-3.5 text-primary-400" />
                <span>Operator Email</span>
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="engineer@company.com"
                className="input-field"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-muted-bright font-medium flex items-center gap-1.5">
                <Building className="w-3.5 h-3.5 text-accent-400" />
                <span>Tenant Workspace Partition</span>
              </label>
              <input
                type="text"
                required
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                placeholder="tenant-alpha"
                className="input-field"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-muted-bright font-medium flex items-center gap-1.5">
                <UserCheck className="w-3.5 h-3.5 text-success" />
                <span>Security Clearance Role</span>
              </label>
              <div className="grid grid-cols-3 gap-2">
                {ROLES.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => setRole(r.id)}
                    className={`py-2 px-3 rounded-lg border text-center font-semibold text-[11px] capitalize transition ${
                      role === r.id
                        ? "bg-primary-600 text-white border-primary-500 shadow-glow"
                        : "bg-ink-950 text-muted border-ink-700 hover:text-slate-200 hover:border-ink-600"
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>

            <button type="submit" disabled={loading} className="btn-primary w-full !py-3 text-xs tracking-wide">
              {loading ? (
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <span>AUTHENTICATE &amp; ENTER WORKSTATION</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <div className="flex items-center justify-center gap-1.5 text-[10px] font-mono text-muted-dim">
            <ShieldCheck className="w-3 h-3 text-success" />
            <span>Fail-Closed Host Security Guard Active</span>
          </div>
        </div>
      </main>

      <footer className="h-12 border-t border-ink-800/80 px-6 flex items-center justify-between text-[11px] font-mono text-muted-dim z-10">
        <div>SONIC-REDA Autonomy Core v1.3.0</div>
        <Link href="/landing" className="hover:text-slate-300 transition">Back to overview</Link>
      </footer>
    </div>
  );
}
