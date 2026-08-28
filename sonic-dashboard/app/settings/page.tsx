"use client";

import { useState, useEffect } from "react";
import { Settings, Shield, Cpu, Lock, Save, Check, Loader2, RefreshCw } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

  useEffect(() => {
    async function loadSettings() {
      try {
        const res = await fetch(`${API_BASE}/live/settings`);
        if (res.ok) {
          const data = await res.json();
          if (data.llm_base_url) setLlmBaseUrl(data.llm_base_url);
          if (data.llm_model) setLlmModel(data.llm_model);
          if (data.daytona_url) setDaytonaUrl(data.daytona_url);
          if (data.burp_url) setBurpUrl(data.burp_url);
          if (data.allowed_domains) setAllowedDomains(data.allowed_domains.join(", "));
          setApiKeySet(data.llm_api_key_set || false);
        }
      } catch {
        // Keep defaults
      }
    }
    loadSettings();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);

    const domains = allowedDomains.split(",").map(d => d.trim()).filter(Boolean);

    try {
      const res = await fetch(`${API_BASE}/live/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          llm_base_url: llmBaseUrl,
          llm_api_key: llmApiKey || undefined,
          llm_model: llmModel,
          daytona_url: daytonaUrl,
          burp_url: burpUrl,
          allowed_domains: domains,
        }),
      });

      if (res.ok) {
        setSaved(true);
        if (llmApiKey) setApiKeySet(true);
        setLlmApiKey(""); // Clear sensitive input after saving
        setTimeout(() => setSaved(false), 3000);
      }
    } catch {
      alert("Failed to connect to backend API to save settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="pb-4 border-b border-slate-800 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-slate-400" />
            <h2 className="text-xl font-bold text-white tracking-tight">Scope & System Configuration</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">Manage Immutable Safety Rules, Scope Allowlist, and Custom LLM Provider Endpoints.</p>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white font-bold text-xs rounded-lg flex items-center gap-2 transition duration-150 glow-red"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : saved ? <Check className="w-3.5 h-3.5 text-white" /> : <Save className="w-3.5 h-3.5" />}
          <span>{saving ? "SAVING..." : saved ? "SAVED LIVE!" : "SAVE CONFIGURATION"}</span>
        </button>
      </div>

      {/* Custom LLM Provider Section */}
      <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">Custom LLM Provider</h3>
          </div>
          <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold ${
            apiKeySet ? "bg-emerald-950 text-emerald-400 border border-emerald-800" : "bg-purple-950 text-purple-400 border border-purple-800"
          }`}>
            {apiKeySet ? "● API KEY ACTIVE" : "Universal OpenAI / Anthropic / Local Ollama"}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
          <div>
            <label className="text-slate-400 block mb-1">Provider Base URL</label>
            <input
              type="text"
              value={llmBaseUrl}
              onChange={(e) => setLlmBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div>
            <label className="text-slate-400 block mb-1">
              API Key {apiKeySet && <span className="text-emerald-400 font-bold">(Configured)</span>}
            </label>
            <input
              type="password"
              value={llmApiKey}
              onChange={(e) => setLlmApiKey(e.target.value)}
              placeholder={apiKeySet ? "••••••••••••••••••••" : "sk-..."}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div>
            <label className="text-slate-400 block mb-1">Default Model</label>
            <input
              type="text"
              value={llmModel}
              onChange={(e) => setLlmModel(e.target.value)}
              placeholder="gpt-4o, claude-3-5-sonnet, grok-3"
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-cyan-500"
            />
          </div>
        </div>
      </div>

      {/* Scope Allowlist Section */}
      <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">Target Scope Allowlist</h3>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono font-bold">Immutable Safety</span>
        </div>

        <div className="text-xs font-mono space-y-2">
          <label className="text-slate-400 block">Allowed Domains / IP Ranges (Comma separated)</label>
          <input
            type="text"
            value={allowedDomains}
            onChange={(e) => setAllowedDomains(e.target.value)}
            className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-cyan-500"
          />
          <p className="text-[11px] text-slate-500">
            Any action targeted outside these domains will be automatically blocked with verdict <code className="text-red-400">BLOCKED_OUT_OF_SCOPE</code>.
          </p>
        </div>
      </div>

      {/* Daytona Virtual Computer Section */}
      <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">Daytona Virtual Computer Fleet</h3>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800 font-mono font-bold">Sandbox Controller</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
          <div>
            <label className="text-slate-400 block mb-1">Daytona API Server</label>
            <input
              type="text"
              value={daytonaUrl}
              onChange={(e) => setDaytonaUrl(e.target.value)}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div>
            <label className="text-slate-400 block mb-1">Burp Suite REST API Endpoint</label>
            <input
              type="text"
              value={burpUrl}
              onChange={(e) => setBurpUrl(e.target.value)}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-cyan-500"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
