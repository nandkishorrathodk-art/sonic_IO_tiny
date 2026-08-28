'use client';

import React, { useState } from 'react';
import {
  Monitor,
  Terminal,
  FolderTree,
  Cpu,
  Package,
  Layers,
  ShieldCheck,
  Camera,
  Play,
  Square,
  RefreshCw,
  GitBranch,
  FileCode,
  HardDrive,
  Activity,
  Maximize2,
  Server,
  Zap,
} from 'lucide-react';

export default function ComputerWorkspacePage() {
  const [activeTab, setActiveTab] = useState<'desktop' | 'terminal' | 'filesystem' | 'apps' | 'processes' | 'services' | 'audit'>('desktop');

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#0F131F]/90 border border-slate-800/80 p-5 rounded-2xl glow-blue">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-500 p-0.5 shadow-lg shadow-blue-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-[#0C0E16] rounded-[10px] flex items-center justify-center">
              <Monitor className="w-6 h-6 text-blue-400 animate-pulse" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-wide">AUTONOMOUS COMPUTER & WORKSPACE</h2>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-blue-950 text-blue-300 border border-blue-800/60 rounded-full font-semibold">
                PHASE 13
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              Persistent engineering computer: Desktop GUI, Terminal, Filesystem, code-server IDE, Browser, Services, and Git.
            </p>
          </div>
        </div>

        {/* Status & Quick Action Buttons */}
        <div className="flex items-center gap-3 font-mono text-xs">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-950/60 border border-emerald-800/60 text-emerald-300 font-bold">
            <Activity className="w-4 h-4 text-emerald-400" />
            <span>KALI LINUX WORKSPACE: READY</span>
          </div>
          <button className="px-3.5 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/40 rounded-xl font-semibold flex items-center gap-2 transition glow-blue">
            <Camera className="w-3.5 h-3.5 text-blue-400" />
            <span>Screenshot</span>
          </button>
        </div>
      </div>

      {/* Top Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 font-mono text-xs">
        <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
          <span className="text-slate-400">Active Window</span>
          <div className="text-xl font-bold text-cyan-400 mt-1">code-server (IDE)</div>
          <p className="text-[10px] text-slate-500 mt-1">Focus: auth_controller.py</p>
        </div>
        <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
          <span className="text-slate-400">Running Processes</span>
          <div className="text-xl font-bold text-emerald-400 mt-1">5 Active</div>
          <p className="text-[10px] text-slate-500 mt-1">Xvfb, code-server, Chromium, Shell</p>
        </div>
        <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
          <span className="text-slate-400">CPU & RAM Load</span>
          <div className="text-xl font-bold text-purple-400 mt-1">14.2% | 1.5 GB</div>
          <p className="text-[10px] text-slate-500 mt-1">4 Cores / 8.0 GB Total</p>
        </div>
        <div className="bg-[#0F131F]/80 border border-slate-800/80 p-4 rounded-xl">
          <span className="text-slate-400">Execution Security</span>
          <div className="text-xl font-bold text-emerald-400 mt-1">FAIL-CLOSED</div>
          <p className="text-[10px] text-slate-500 mt-1">Zero host machine fallback</p>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2 text-xs font-semibold font-mono">
        <button
          onClick={() => setActiveTab('desktop')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'desktop' ? 'bg-blue-950 text-blue-300 border border-blue-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Desktop View
        </button>
        <button
          onClick={() => setActiveTab('terminal')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'terminal' ? 'bg-blue-950 text-blue-300 border border-blue-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Terminal Console
        </button>
        <button
          onClick={() => setActiveTab('filesystem')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'filesystem' ? 'bg-blue-950 text-blue-300 border border-blue-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Filesystem & Git
        </button>
        <button
          onClick={() => setActiveTab('apps')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'apps' ? 'bg-blue-950 text-blue-300 border border-blue-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Applications
        </button>
        <button
          onClick={() => setActiveTab('processes')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'processes' ? 'bg-blue-950 text-blue-300 border border-blue-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Processes
        </button>
        <button
          onClick={() => setActiveTab('services')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'services' ? 'bg-blue-950 text-blue-300 border border-blue-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Services
        </button>
        <button
          onClick={() => setActiveTab('audit')}
          className={`px-4 py-2 rounded-lg transition ${activeTab === 'audit' ? 'bg-blue-950 text-blue-300 border border-blue-800/60' : 'text-slate-400 hover:text-white'}`}
        >
          Audit Stream
        </button>
      </div>

      {/* Tab 1: Desktop View */}
      {activeTab === 'desktop' && (
        <div className="space-y-4 font-mono text-xs">
          <div className="bg-[#0A0D14] border border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
            {/* Desktop Window Header */}
            <div className="bg-[#121622] px-4 py-2.5 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-red-500/80" />
                <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
                <div className="w-3 h-3 rounded-full bg-green-500/80" />
                <span className="text-slate-400 text-xs ml-2 font-bold">SONIC Computer Display — Xvfb (:99 1920x1080)</span>
              </div>
              <div className="flex items-center gap-3 text-slate-400">
                <span className="text-[11px] text-cyan-400">60 FPS | 24-bit RGB</span>
                <Maximize2 className="w-4 h-4 cursor-pointer hover:text-white" />
              </div>
            </div>

            {/* Virtual Screen Content Mockup */}
            <div className="p-8 min-h-[400px] flex flex-col items-center justify-center bg-[#07090E] border-slate-900 space-y-4">
              <div className="p-6 bg-[#0E121D] border border-slate-800 rounded-xl max-w-lg w-full space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-white font-bold flex items-center gap-2">
                    <FileCode className="w-4 h-4 text-blue-400" />
                    <span>code-server — [auth_controller.py]</span>
                  </span>
                  <span className="text-emerald-400 text-[10px] font-bold">DEBUGGER ACTIVE</span>
                </div>
                <pre className="text-slate-300 text-[11px] font-mono leading-relaxed bg-[#06080C] p-3 rounded-lg border border-slate-800/60">
                  {`def verify_token(token: str) -> bool:
    # SONIC Candidate Fix: Validate algorithm explicitly
    header = jwt.get_unverified_header(token)
    if header.get("alg") == "none":
        raise SecurityException("Algorithm 'none' prohibited")
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])`}
                </pre>
                <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                  <span>Git: branch <strong className="text-cyan-400">fix-auth-bypass</strong></span>
                  <span className="text-emerald-400">✓ Unit Tests Passed (14/14)</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Terminal Console */}
      {activeTab === 'terminal' && (
        <div className="bg-[#0A0D14] border border-slate-800 rounded-xl p-4 font-mono text-xs space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="text-white font-bold flex items-center gap-2">
              <Terminal className="w-4 h-4 text-emerald-400" />
              <span>Interactive PTY Shell (Non-Root Sandbox)</span>
            </span>
            <span className="text-slate-500">PTY /dev/pts/1</span>
          </div>
          <div className="space-y-1 text-slate-300">
            <p className="text-slate-500"># Containerized sandbox environment initialized</p>
            <p><span className="text-emerald-400 font-bold">sonic@kali-workspace:~$</span> uname -a</p>
            <p className="text-slate-400">Linux sonic-kali-linux 6.6.0-kali-amd64 #1 SMP PREEMPT_DYNAMIC x86_64 GNU/Linux</p>
            <p><span className="text-emerald-400 font-bold">sonic@kali-workspace:~$</span> git status</p>
            <p className="text-slate-400">On branch fix-auth-bypass<br />nothing to commit, working tree clean</p>
          </div>
        </div>
      )}

      {/* Tab 3: Filesystem & Git */}
      {activeTab === 'filesystem' && (
        <div className="space-y-3 font-mono text-xs">
          <div className="bg-[#0F131F]/90 border border-slate-800/80 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="text-white font-bold flex items-center gap-2">
                <FolderTree className="w-4 h-4 text-cyan-400" />
                <span>Workspace Directory: /home/sonic/workspace</span>
              </span>
              <span className="text-slate-400">Git: <strong className="text-cyan-400">main (Clean)</strong></span>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-slate-300 hover:bg-slate-800/40 p-1.5 rounded">
                <span>📁 src/auth/</span>
                <span className="text-slate-500">Directory</span>
              </div>
              <div className="flex items-center justify-between text-slate-300 hover:bg-slate-800/40 p-1.5 rounded">
                <span>📄 auth_controller.py</span>
                <span className="text-yellow-400">3.4 KB</span>
              </div>
              <div className="flex items-center justify-between text-slate-300 hover:bg-slate-800/40 p-1.5 rounded">
                <span>📄 test_auth.py</span>
                <span className="text-yellow-400">2.1 KB</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Applications */}
      {activeTab === 'apps' && (
        <div className="space-y-3 font-mono text-xs">
          <div className="bg-[#0F131F]/90 border border-slate-800/80 rounded-xl p-4 space-y-3">
            <div className="text-white font-bold flex items-center gap-2 border-b border-slate-800 pb-2">
              <Package className="w-4 h-4 text-purple-400" />
              <span>Installed Applications & Packages</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <div className="p-3 bg-[#0A0D14] border border-slate-800 rounded-lg">
                <span className="text-white font-bold">code-server (IDE)</span>
                <p className="text-emerald-400 text-[10px]">RUNNING (Port 8080)</p>
              </div>
              <div className="p-3 bg-[#0A0D14] border border-slate-800 rounded-lg">
                <span className="text-white font-bold">chromium (Browser)</span>
                <p className="text-emerald-400 text-[10px]">RUNNING (Playwright)</p>
              </div>
              <div className="p-3 bg-[#0A0D14] border border-slate-800 rounded-lg">
                <span className="text-white font-bold">nuclei v3.2</span>
                <p className="text-cyan-400 text-[10px]">INSTALLED</p>
              </div>
              <div className="p-3 bg-[#0A0D14] border border-slate-800 rounded-lg">
                <span className="text-white font-bold">nmap 7.94</span>
                <p className="text-cyan-400 text-[10px]">INSTALLED</p>
              </div>
              <div className="p-3 bg-[#0A0D14] border border-slate-800 rounded-lg">
                <span className="text-white font-bold">git 2.43</span>
                <p className="text-cyan-400 text-[10px]">INSTALLED</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 5: Processes */}
      {activeTab === 'processes' && (
        <div className="bg-[#0F131F]/90 border border-slate-800 rounded-xl p-4 font-mono text-xs space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2 text-slate-400 uppercase text-[10px]">
            <span>PID</span>
            <span>Process Name</span>
            <span>CPU %</span>
            <span>Memory MB</span>
          </div>
          <div className="flex items-center justify-between text-white">
            <span>1</span>
            <span>systemd/init</span>
            <span className="text-cyan-400">0.1%</span>
            <span className="text-emerald-400">12.5 MB</span>
          </div>
          <div className="flex items-center justify-between text-white">
            <span>10</span>
            <span>Xvfb (:99)</span>
            <span className="text-cyan-400">0.5%</span>
            <span className="text-emerald-400">45.0 MB</span>
          </div>
          <div className="flex items-center justify-between text-white">
            <span>102</span>
            <span>code-server</span>
            <span className="text-cyan-400">1.8%</span>
            <span className="text-emerald-400">120.4 MB</span>
          </div>
          <div className="flex items-center justify-between text-white">
            <span>105</span>
            <span>chromium</span>
            <span className="text-cyan-400">2.4%</span>
            <span className="text-emerald-400">240.0 MB</span>
          </div>
        </div>
      )}

      {/* Tab 6: Services */}
      {activeTab === 'services' && (
        <div className="bg-[#0F131F]/90 border border-slate-800 rounded-xl p-4 font-mono text-xs space-y-3">
          <div className="text-white font-bold flex items-center gap-2 border-b border-slate-800 pb-2">
            <Server className="w-4 h-4 text-cyan-400" />
            <span>Managed Computer Services</span>
          </div>
          <div className="space-y-2">
            <div className="p-3 bg-[#0A0D14] border border-slate-800 rounded-lg flex items-center justify-between">
              <div>
                <span className="text-white font-bold">xvfb (Display Server)</span>
                <p className="text-slate-500 text-[10px]">Virtual Framebuffer on Port 99</p>
              </div>
              <span className="px-2 py-1 bg-emerald-950 text-emerald-300 border border-emerald-800/60 rounded text-[10px] font-bold">RUNNING</span>
            </div>
            <div className="p-3 bg-[#0A0D14] border border-slate-800 rounded-lg flex items-center justify-between">
              <div>
                <span className="text-white font-bold">code-server (IDE Web Service)</span>
                <p className="text-slate-500 text-[10px]">Development Environment on Port 8080</p>
              </div>
              <span className="px-2 py-1 bg-emerald-950 text-emerald-300 border border-emerald-800/60 rounded text-[10px] font-bold">RUNNING</span>
            </div>
          </div>
        </div>
      )}

      {/* Tab 7: Audit Stream */}
      {activeTab === 'audit' && (
        <div className="bg-[#0F131F]/90 border border-slate-800 rounded-xl p-4 font-mono text-xs space-y-2">
          <div className="text-white font-bold flex items-center gap-2 border-b border-slate-800 pb-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Immutable Computer Audit Events</span>
          </div>
          <div className="space-y-1.5 text-slate-300">
            <p className="text-[11px]"><span className="text-slate-500">[2026-08-28 15:00:00]</span> <strong className="text-cyan-400">CREATE_COMPUTER</strong> ws-main-01 (DockerProvider) — <span className="text-emerald-400">SUCCESS</span></p>
            <p className="text-[11px]"><span className="text-slate-500">[2026-08-28 15:00:05]</span> <strong className="text-cyan-400">LAUNCH_APP</strong> code-server — <span className="text-emerald-400">SUCCESS</span></p>
            <p className="text-[11px]"><span className="text-slate-500">[2026-08-28 15:00:12]</span> <strong className="text-cyan-400">WRITE_FILE</strong> /home/sonic/workspace/auth_controller.py — <span className="text-emerald-400">SUCCESS</span></p>
            <p className="text-[11px]"><span className="text-slate-500">[2026-08-28 15:00:18]</span> <strong className="text-cyan-400">EXECUTE_TERMINAL</strong> pytest test_auth.py — <span className="text-emerald-400">EXIT_0</span></p>
            <p className="text-[11px]"><span className="text-slate-500">[2026-08-28 15:00:24]</span> <strong className="text-cyan-400">GIT_COMMIT</strong> "fix(auth): enforce algorithm validation" — <span className="text-emerald-400">SUCCESS</span></p>
          </div>
        </div>
      )}
    </div>
  );
}
