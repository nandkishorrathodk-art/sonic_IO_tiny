"use client";

import { useState, useEffect } from "react";
import { Settings, Shield, Cpu, Save, Check, Lock } from "lucide-react";
import { api } from "../../lib/api";
import { getUserSession } from "../../lib/auth";

export default function SettingsPage() {
  const [llmBaseUrl, setLlmBaseUrl] = useState("https://api.openai.com/v1");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmModel, setLlmModel] = useState("gpt-4o");
  const [daytonaUrl, setDaytonaUrl] = useState("http://localhost:3986");
  const [burpUrl, setBurpUrl] = useState("http://localhost:1337");
  const [allowedDomains, setAllowedDomains] = useState("*.example.com, localhost, 127.0.0.1");

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [apiKeySet, setApiKeySet] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [userRole, setUserRole] = useState<string | null>(null);

  const isAdmin = userRole === "admin" || userRole === "administrator";

  const loadSettings = async () => {
    try {
      const data = await api.getSettings();
      if (data) {
        if (data.llm_base_url) setLlmBaseUrl(data.llm_base_url);
        if (data.llm_model) setLlmModel(data.llm_model);
        if (data.daytona_url) setDaytonaUrl(data.daytona_url);
        if (data.burp_url) setBurpUrl(data.burp_url);
        if (data.allowed_domains) setAllowedDomains(data.allowed_domains.join(", "));
        setApiKeySet(data.llm_api_key_set || false);
      }
    } catch (err: any) {
      setError(err.message);
    }
  };

  useEffect(() => {
    setUserRole(getUserSession()?.role ?? null);
    loadSettings();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    setError(null);

    const domains = allowedDomains.split(",").map((d) => d.trim()).filter(Boolean);

    try {
      await api.updateSettings({
        llm_base_url: llmBaseUrl,
        llm_api_key: llmApiKey || undefined,
        llm_model: llmModel,
        daytona_url: daytonaUrl,
        burp_url: burpUrl,
        allowed_domains: domains,
      });

      setSaved(true);
      if (llmApiKey) setApiKeySet(true);
      setLlmApiKey("");
      setTimeout(() => setSaved(false), 3000);
    } catch (err: any) {
      const msg = err?.message || "";
      if (msg.includes("403") || msg.toLowerCase().includes("admin") || msg.toLowerCase().includes("forbidden")) {
        setError("Administrator access is required to change live settings. Your current role is read-only. Sign in with an admin account to save changes.");
      } else {
        setError(`Failed to save settings: ${msg}`);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-ink-950 bg-grid-glow max-w-4xl mx-auto p-6 space-y-6 font-sans">
      <div className="pb-4 border-b border-ink-800 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-muted" />
            <h2 className="text-xl font-bold text-white tracking-tight">Scope & System Configuration</h2>
          </div>
          <p className="text-xs text-muted mt-1 font-mono">
            Manage Immutable Safety Rules, Scope Allowlist, and LLM Provider Endpoints.
          </p>
        </div>
        <button onClick={handleSave} disabled={saving || !isAdmin} className="btn-primary !py-2 text-xs disabled:opacity-50" title={isAdmin ? "" : "Admin role required to save"}>
          {saving ? <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" /> : saved ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
          <span>{saving ? "SAVING…" : saved ? "SAVED LIVE!" : isAdmin ? "SAVE CONFIGURATION" : "ADMIN ONLY"}</span>
        </button>
      </div>

      {!isAdmin && userRole !== null && (
        <div className="p-3 rounded-lg bg-warning/10 border border-warning/30 text-warning text-xs font-mono flex items-center gap-2">
          <Lock className="w-3.5 h-3.5 shrink-0" />
          <span>
            Read-only view — your role (<strong className="uppercase">{userRole}</strong>) cannot modify live settings.
            Configuration changes require an administrator account.
          </span>
        </div>
      )}

      {error && (
        <div className="p-3 rounded-lg bg-danger/10 border border-danger/30 text-danger text-xs font-mono">{error}</div>
      )}

      {/* LLM provider */}
      <div className="glass-card rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-accent-400" />
            <h3 className="text-sm font-bold text-muted-bright uppercase tracking-wider">LLM Provider Configuration</h3>
          </div>
          <span className={`chip border ${apiKeySet ? "border-success/40 bg-success/10 text-success" : "border-accent-500/40 bg-accent-600/10 text-accent-400"}`}>
            {apiKeySet ? "● API KEY ACTIVE" : "Universal OpenAI / Anthropic / Local"}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
          <div>
            <label className="text-muted block mb-1">Provider Base URL</label>
            <input type="text" value={llmBaseUrl} onChange={(e) => setLlmBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" className="input-field !text-xs" />
          </div>
          <div>
            <label className="text-muted block mb-1">
              API Key {apiKeySet && <span className="text-success font-bold">(Configured)</span>}
            </label>
            <input type="password" value={llmApiKey} onChange={(e) => setLlmApiKey(e.target.value)} placeholder={apiKeySet ? "••••••••••••••••" : "sk-..."} className="input-field !text-xs" />
          </div>
          <div>
            <label className="text-muted block mb-1">Default Model</label>
            <input type="text" value={llmModel} onChange={(e) => setLlmModel(e.target.value)} placeholder="gpt-4o, claude-3-5-sonnet" className="input-field !text-xs" />
          </div>
        </div>
      </div>

      {/* Integration endpoints (now wired to real state) */}
      <div className="glass-card rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Settings className="w-4 h-4 text-secondary-400" />
          <h3 className="text-sm font-bold text-muted-bright uppercase tracking-wider">Integration Endpoints</h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
          <div>
            <label className="text-muted block mb-1">Workstation Compute URL</label>
            <input type="text" value={daytonaUrl} onChange={(e) => setDaytonaUrl(e.target.value)} className="input-field !text-xs" />
          </div>
          <div>
            <label className="text-muted block mb-1">Burp Suite API URL</label>
            <input type="text" value={burpUrl} onChange={(e) => setBurpUrl(e.target.value)} className="input-field !text-xs" />
          </div>
        </div>
      </div>

      {/* Scope allowlist */}
      <div className="glass-card rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-success" />
          <h3 className="text-sm font-bold text-muted-bright uppercase tracking-wider">Target Scope Allowlist</h3>
        </div>
        <div>
          <label className="text-muted block mb-1 text-xs font-mono">Permitted Targets (Comma separated)</label>
          <input type="text" value={allowedDomains} onChange={(e) => setAllowedDomains(e.target.value)} className="input-field !text-xs" />
        </div>
      </div>
    </div>
  );
}
