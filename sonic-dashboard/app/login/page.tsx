"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Shield,
  Key,
  Mail,
  Building,
  UserCheck,
  Cpu,
  ArrowRight,
  Sparkles,
  Lock,
  Terminal,
  CheckCircle2,
  AlertCircle,
  Globe,
} from "lucide-react";
import Link from "next/link";
import { setAuthToken } from "../../lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [role, setRole] = useState("operator");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

  const handleLogin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          name,
          role,
          tenant_id: tenantId,
        }),
      });

      if (!res.ok) {
        throw new Error(`Login failed with status ${res.status}`);
      }

      const data = await res.json();
      if (data?.access_token) {
        setAuthToken(data.access_token, {
          email,
          name,
          role,
          tenant_id: tenantId,
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
    <div className="min-h-screen bg-[#07090E] text-slate-100 flex flex-col justify-between font-sans relative overflow-hidden">
      {/* Dynamic Background Glows */}
      <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] bg-blue-600/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[600px] h-[600px] bg-emerald-600/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute top-[40%] right-[30%] w-[350px] h-[350px] bg-purple-600/10 rounded-full blur-[100px] pointer-events-none" />

      {/* Top Navigation */}
      <header className="h-16 border-b border-[#1E2436]/60 backdrop-blur-md px-6 flex items-center justify-between z-10">
        <Link href="/landing" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-blue-600 to-cyan-500 p-0.5 shadow-lg shadow-blue-500/20 group-hover:scale-105 transition">
            <div className="w-full h-full bg-[#0C0E16] rounded-[6px] flex items-center justify-center font-mono font-black text-xs text-blue-400">
              S
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-bold tracking-wider text-sm text-white">SONIC-REDA</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-blue-950/80 text-blue-300 border border-blue-800/50">
              AUTH PORTAL
            </span>
          </div>
        </Link>

        <div className="flex items-center gap-3 text-xs font-mono">
          <Link
            href="/landing"
            className="text-slate-400 hover:text-white transition px-3 py-1.5 rounded-lg hover:bg-slate-800/40"
          >
            Overview
          </Link>
          <Link
            href="/"
            className="text-blue-400 hover:text-blue-300 transition px-3 py-1.5 rounded-lg bg-blue-950/50 border border-blue-800/40 flex items-center gap-1.5"
          >
            <span>Direct Workstation</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </header>

      {/* Main Login Card */}
      <main className="flex-1 flex items-center justify-center p-6 z-10">
        <div className="w-full max-w-md bg-[#0F131F]/90 backdrop-blur-xl border border-slate-800/80 rounded-2xl p-8 shadow-2xl space-y-6 relative">
          <div className="space-y-1.5 text-center">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-950 text-blue-300 border border-blue-800/60 text-[11px] font-mono font-semibold mb-2">
              <Lock className="w-3 h-3" />
              <span>TENANT-ISOLATED ACCESS</span>
            </div>
            <h1 className="text-xl font-bold tracking-tight text-white">
              Autonomous Workstation Login
            </h1>
            <p className="text-xs text-slate-400 font-mono">
              Authenticate tenant identity to load isolated missions & Daytona sandbox.
            </p>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-red-950/50 border border-red-800/60 text-red-300 text-xs font-mono flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-4 text-xs font-mono">
            {/* Email Field */}
            <div className="space-y-1.5">
              <label className="text-slate-300 font-medium flex items-center gap-1.5">
                <Mail className="w-3.5 h-3.5 text-blue-400" />
                <span>Operator Email</span>
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="engineer@company.com"
                className="w-full px-3.5 py-2.5 rounded-xl bg-[#090B10] border border-slate-700/80 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition text-xs"
              />
            </div>

            {/* Tenant ID Field */}
            <div className="space-y-1.5">
              <label className="text-slate-300 font-medium flex items-center gap-1.5">
                <Building className="w-3.5 h-3.5 text-purple-400" />
                <span>Tenant Workspace Partition</span>
              </label>
              <input
                type="text"
                required
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                placeholder="tenant-alpha"
                className="w-full px-3.5 py-2.5 rounded-xl bg-[#090B10] border border-slate-700/80 text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 transition text-xs"
              />
            </div>

            {/* Role Selection */}
            <div className="space-y-1.5">
              <label className="text-slate-300 font-medium flex items-center gap-1.5">
                <UserCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span>Security Clearance Role</span>
              </label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: "operator", label: "Operator" },
                  { id: "admin", label: "Admin" },
                  { id: "auditor", label: "Auditor" },
                ].map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => setRole(r.id)}
                    className={`py-2 px-3 rounded-lg border text-center font-semibold text-[11px] capitalize transition ${
                      role === r.id
                        ? "bg-blue-600 text-white border-blue-500 shadow-md shadow-blue-500/20"
                        : "bg-[#090B10] text-slate-400 border-slate-800 hover:text-slate-200 hover:border-slate-700"
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white font-bold text-xs tracking-wide shadow-lg shadow-blue-600/30 transition flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <span>AUTHENTICATE & ENTER WORKSTATION</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

        </div>
      </main>

      {/* Footer */}
      <footer className="h-12 border-t border-[#1E2436]/60 px-6 flex items-center justify-between text-[11px] font-mono text-slate-500 z-10">
        <div>SONIC-REDA Autonomy Core v1.3.0</div>
        <div>Fail-Closed Host Security Guard Active</div>
      </footer>
    </div>
  );
}
