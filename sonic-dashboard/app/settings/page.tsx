"use client";

import { useState, useEffect } from "react";
import { Settings, Shield, Cpu, Lock, Save, Check, Loader2, RefreshCw } from "lucide-react";
import { api } from "../../lib/api";

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
      setError(`Failed to save settings: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto font-sans">
      <div className="pb-4 border-b border-slate-800 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-slate-400" />
            <h2 className="text-xl font-bold text-white tracking-tight">Scope & System Configuration</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Manage Immutable Safety Rules, Scope Allowlist, and LLM Provider Endpoints.
          </p>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white font-bold text-xs rounded-lg flex items-center gap-2 transition duration-150"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : saved ? <Check className="w-3.5 h-3.5 text-white" /> : <Save className="w-3.5 h-3.5" />}
          <span>{saving ? "SAVING..." : saved ? "SAVED LIVE!" : "SAVE CONFIGURATION"}</span>
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-red-950/40 border border-red-800 text-red-300 text-xs font-mono">
          {error}
        </div>
      )}

      {/* Custom LLM Provider Section */}
      <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">LLM Provider Configuration</h3>
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
              placeholder="gpt-4o, claude-3-5-sonnet"
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
        </div>

        <div>
          <label className="text-slate-400 block mb-1 text-xs font-mono">Permitted Targets (Comma separated)</label>
          <input
            type="text"
            value={allowedDomains}
            onChange={(e) => setAllowedDomains(e.target.value)}
            className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-emerald-500"
          />
        </div>
      </div>
    </div>
  );
}
