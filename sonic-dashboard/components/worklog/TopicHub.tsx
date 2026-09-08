"use client";

import React from "react";
import {
  Globe,
  Zap,
  Search,
  Key,
  Flame,
  Terminal,
  ArrowRight,
  ShieldAlert,
} from "lucide-react";

interface TopicHubProps {
  onSelectTopic: (prompt: string) => void;
}

export const TOPIC_TAGS = [
  { tag: "#BurpSuite", prompt: "Open Chromium and Burp Suite to intercept traffic on port 8080." },
  { tag: "#PortScan", prompt: "Run a port scan to discover open services on the target." },
  { tag: "#APISecurity", prompt: "Enumerate API endpoints and fuzz for hidden parameters." },
  { tag: "#JWTAudit", prompt: "Analyze JWT tokens for signature bypass or 'none' algorithm." },
  { tag: "#WebRecon", prompt: "Perform web reconnaissance and map attack surface." },
  { tag: "#LinuxShell", prompt: "Check sandbox OS version, open ports, and installed tools." },
];

export function TopicHub({ onSelectTopic }: TopicHubProps) {
  const cards = [
    {
      icon: <Globe className="w-4 h-4 text-cyan-400" />,
      title: "Web Recon & Discovery",
      desc: "Crawl web routes, extract JS bundles, and map reachable endpoints.",
      prompt: "Perform web reconnaissance on the target URL: crawl endpoints, inspect technologies, and check robots.txt.",
      badge: "Recon",
    },
    {
      icon: <Zap className="w-4 h-4 text-warning" />,
      title: "Burp Suite Interception",
      desc: "Configure Chromium proxy & launch Burp Suite side-by-side on desktop.",
      prompt: "Open Chromium and launch Burp Suite side-by-side on the graphical desktop with proxy configured.",
      badge: "Proxy",
    },
    {
      icon: <Search className="w-4 h-4 text-secondary-400" />,
      title: "Network & Port Scanning",
      desc: "Run real Nmap SYN & service scans with version fingerprinting.",
      prompt: "Run an authentic Nmap service scan with version detection on the target host.",
      badge: "Nmap",
    },
    {
      icon: <Key className="w-4 h-4 text-emerald-400" />,
      title: "JWT & Auth Security",
      desc: "Test token integrity, algorithm confusion (none), and secret bruteforce.",
      prompt: "Audit authentication tokens: check for JWT none algorithm, signature bypass, and weak signing keys.",
      badge: "Auth",
    },
    {
      icon: <Flame className="w-4 h-4 text-rose-400" />,
      title: "API Parameter Fuzzing",
      desc: "Fuzz REST & GraphQL parameters with ffuf to identify IDOR or injection.",
      prompt: "Fuzz API endpoints for parameter tampering, IDOR, and unauthorized access.",
      badge: "Fuzzing",
    },
    {
      icon: <Terminal className="w-4 h-4 text-indigo-400" />,
      title: "Sandbox Linux Shell",
      desc: "Execute Linux commands inside the verified Daytona/Docker container.",
      prompt: "Inspect sandbox terminal environment, network interfaces, and installed security tools.",
      badge: "Terminal",
    },
  ];

  return (
    <div className="max-w-2xl mx-auto py-6 px-3 space-y-4 animate-fade-in-up">
      <div className="text-center space-y-1.5 pb-2">
        <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-secondary-600/10 border border-secondary-500/30 text-secondary-400 text-[11px] font-mono font-medium">
          <ShieldAlert className="w-3.5 h-3.5 text-secondary-400" />
          <span>AUTONOMOUS PENETRATION ARCHITECT</span>
        </div>
        <h3 className="text-lg font-bold text-white tracking-tight">
          What objective should SONIC execute?
        </h3>
        <p className="text-xs text-muted max-w-md mx-auto leading-relaxed">
          Select a cybersecurity objective below or type a natural language instruction to operate the graphical workstation.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {cards.map((card, i) => (
          <div
            key={i}
            onClick={() => onSelectTopic(card.prompt)}
            className="p-3 rounded-xl border border-ink-750 bg-ink-850 hover:bg-ink-800/80 hover:border-secondary-500/60 transition shadow-md group cursor-pointer flex flex-col justify-between"
          >
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <div className="w-7 h-7 rounded-lg bg-ink-900 border border-ink-700 flex items-center justify-center group-hover:border-secondary-500/40 transition">
                  {card.icon}
                </div>
                <span className="text-[10px] font-mono text-muted-dim uppercase tracking-wider px-1.5 py-0.5 rounded bg-ink-900 border border-ink-800">
                  {card.badge}
                </span>
              </div>
              <h4 className="text-[12.5px] font-semibold text-slate-100 group-hover:text-secondary-300 transition">
                {card.title}
              </h4>
              <p className="text-[11px] text-muted leading-relaxed">
                {card.desc}
              </p>
            </div>

            <div className="pt-2 flex items-center justify-end text-[10.5px] font-mono text-muted-dim group-hover:text-secondary-400 transition">
              <span className="flex items-center gap-1">
                <span>Start</span>
                <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
