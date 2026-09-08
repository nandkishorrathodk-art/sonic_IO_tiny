"use client";

import React from "react";
import {
  Search,
  Globe,
  Zap,
  Key,
  Flame,
  Terminal,
  ChevronRight,
  Shield,
  Sparkles,
} from "lucide-react";

interface FollowupChipsProps {
  onSelect: (prompt: string) => void;
  contextText?: string;
}

interface Suggestion {
  icon: React.ReactNode;
  label: string;
  prompt: string;
}

export function FollowupChips({ onSelect, contextText = "" }: FollowupChipsProps) {
  const suggestions = getDynamicSuggestions(contextText);

  return (
    <div className="pt-2 pb-1 space-y-1.5 animate-fade-in-up">
      <div className="flex items-center gap-1.5 text-[10px] uppercase font-mono font-semibold tracking-wider text-muted-dim pl-1">
        <Sparkles className="w-3 h-3 text-secondary-400" />
        <span>Suggested Next Steps</span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {suggestions.map((item, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => onSelect(item.prompt)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-ink-850 hover:bg-ink-800 border border-ink-750 hover:border-secondary-500/50 text-slate-300 hover:text-white transition shadow-sm text-[11px] font-sans group cursor-pointer"
            title={`Run: "${item.prompt}"`}
          >
            <span className="text-secondary-400 group-hover:scale-110 transition-transform">
              {item.icon}
            </span>
            <span className="font-medium">{item.label}</span>
            <ChevronRight className="w-2.5 h-2.5 text-muted-dim group-hover:text-secondary-400 group-hover:translate-x-0.5 transition-all" />
          </button>
        ))}
      </div>
    </div>
  );
}

function getDynamicSuggestions(context: string): Suggestion[] {
  const lower = context.toLowerCase();

  // If port, network, or ip mentioned
  if (lower.includes("port") || lower.includes("ip") || lower.includes("host") || lower.includes("scan")) {
    return [
      {
        icon: <Search className="w-3 h-3" />,
        label: "Deep Nmap Port Scan",
        prompt: "Run an authentic Nmap service scan with version detection on the target host.",
      },
      {
        icon: <Globe className="w-3 h-3" />,
        label: "Crawl Discovered Endpoints",
        prompt: "Crawl web endpoints on open HTTP/HTTPS ports and map attack surface.",
      },
      {
        icon: <Zap className="w-3 h-3" />,
        label: "Intercept in Burp Suite",
        prompt: "Launch Chromium configured to proxy traffic through Burp Suite on 127.0.0.1:8080.",
      },
    ];
  }

  // If jwt, auth, token, or login mentioned
  if (lower.includes("jwt") || lower.includes("auth") || lower.includes("token") || lower.includes("login") || lower.includes("bearer")) {
    return [
      {
        icon: <Key className="w-3 h-3" />,
        label: "Audit JWT Signature & None Alg",
        prompt: "Analyze discovered JWT tokens for signature bypass, 'none' algorithm vulnerabilities, and weak HMAC secrets.",
      },
      {
        icon: <Flame className="w-3 h-3" />,
        label: "Test Auth Bypass & IDOR",
        prompt: "Test authenticated API endpoints for IDOR (Insecure Direct Object Reference) and role escalation.",
      },
      {
        icon: <Zap className="w-3 h-3" />,
        label: "Intercept Request in Burp",
        prompt: "Send auth request to Burp Suite Repeater for tamper testing.",
      },
    ];
  }

  // If web, url, or http mentioned
  if (lower.includes("http") || lower.includes("url") || lower.includes("web") || lower.includes("browser") || lower.includes("api")) {
    return [
      {
        icon: <Globe className="w-3 h-3" />,
        label: "Crawl Web Endpoints",
        prompt: "Crawl the web application routes, forms, and hidden parameters.",
      },
      {
        icon: <Zap className="w-3 h-3" />,
        label: "Route Traffic to Burp Proxy",
        prompt: "Launch Chromium with proxy set to 127.0.0.1:8080 to intercept HTTP/HTTPS requests in Burp Suite.",
      },
      {
        icon: <Shield className="w-3 h-3" />,
        label: "Inspect Security Headers",
        prompt: "Analyze HTTP response security headers (CSP, HSTS, CORS, X-Frame-Options).",
      },
    ];
  }

  // Default security testing suggestions
  return [
    {
      icon: <Search className="w-3 h-3" />,
      label: "Full Attack Surface Recon",
      prompt: "Perform complete attack surface enumeration and discover active services in the sandbox.",
    },
    {
      icon: <Zap className="w-3 h-3" />,
      label: "Launch Burp Suite & Browser",
      prompt: "Open Chromium and launch Burp Suite side-by-side on the graphical desktop.",
    },
    {
      icon: <Terminal className="w-3 h-3" />,
      label: "Check Sandbox Environment",
      prompt: "Inspect sandbox terminal environment, network interfaces, and installed security tools.",
    },
  ];
}
