"use client";

import React, { useState, useEffect } from "react";
import {
  FileText,
  Monitor,
  GitPullRequest,
  Share2,
  FileCheck2,
  Dna,
  Compass,
} from "lucide-react";
import { api } from "../lib/api";
import { WorkstationState, SystemStatus, WorkstationTab, CommandResult } from "../types/workstation";
import { OfflineBanner } from "../components/common/OfflineBanner";
import { WorkstationHeader } from "../components/workstation/WorkstationHeader";
import { WorkstationSidebar } from "../components/workstation/WorkstationSidebar";
import { WorklogFeed } from "../components/worklog/WorklogFeed";
import { ComputerSurface } from "../components/computer/ComputerSurface";
import { CodeViewer } from "../components/code/CodeViewer";
import { ResearchView } from "../components/research/ResearchView";
import { EvidenceView } from "../components/evidence/EvidenceView";
import { EvolutionView } from "../components/evolution/EvolutionView";
import { MissionView } from "../components/mission/MissionView";

export default function SonicDevinWorkstation() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeTab, setActiveTab] = useState<WorkstationTab>("desktop");
  const [connectionStatus, setConnectionStatus] = useState<SystemStatus>("CONNECTING");
  const [sessionId, setSessionId] = useState("default");
  const [workstationState, setWorkstationState] = useState<WorkstationState | null>(null);
  const [activeFile, setActiveFile] = useState("sonic-core/sonic/production_gate/scenario_matrix.py");
  const [fileContent, setFileContent] = useState<string[]>([]);
  const [gitDiff, setGitDiff] = useState("");
  const [commandLogs, setCommandLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [sessionList, setSessionList] = useState<Array<{
    session_id: string;
    mission_name: string;
    status: string;
    git_branch: string;
    log_count?: number;
    last_action?: string;
  }>>([{ session_id: "default", mission_name: "Autonomous Mission", status: "IDLE", git_branch: "main" }]);

  const fetchWorkstationData = async (targetSession = sessionId) => {
    try {
      const state = await api.getWorkstationState(targetSession);
      setWorkstationState(state);
      setConnectionStatus("LIVE");
      setErrorMessage(null);

      // Refresh session list
      try {
        const sessions = await api.listSessions();
        if (sessions && sessions.length > 0) {
          setSessionList(sessions);
        }
      } catch {
        // keep current list
      }
    } catch (err: any) {
      setConnectionStatus("OFFLINE");
      setErrorMessage(err.message || "Failed to reach backend control plane.");
    }
  };

  const handleNewSession = async () => {
    const newSessionId = `mission-${Math.random().toString(36).substring(2, 7)}`;
    setSessionId(newSessionId);
    setCommandLogs([]);
    await fetchWorkstationData(newSessionId);
  };

  const handleDeleteSession = async (delSessionId: string) => {
    try {
      await api.deleteSession(delSessionId);
      if (sessionId === delSessionId) {
        setSessionId("default");
        await fetchWorkstationData("default");
      } else {
        await fetchWorkstationData(sessionId);
      }
    } catch {
      // ignore
    }
  };

  const fetchFile = async (path: string) => {
    setActiveFile(path);
    try {
      const data = await api.getFileContent(path);
      if (data?.lines) {
        setFileContent(data.lines);
      } else if (data?.content) {
        setFileContent(data.content.split("\n"));
      }
    } catch (err) {
      setFileContent(["# Error reading file from filesystem."]);
    }
  };

  const fetchDiff = async () => {
    try {
      const data = await api.getGitDiff();
      if (data?.diff) setGitDiff(data.diff);
    } catch {
      setGitDiff("");
    }
  };

  useEffect(() => {
    fetchWorkstationData(sessionId);
    fetchFile(activeFile);
    fetchDiff();

    const interval = setInterval(() => {
      fetchWorkstationData(sessionId);
    }, 5000);
    return () => clearInterval(interval);
  }, [sessionId]);

  const handleSendPrompt = async (prompt: string) => {
    setLoading(true);
    try {
      const res = await api.sendPrompt(prompt, sessionId);
      if (res?.state) {
        setWorkstationState(res.state);
      }
      await fetchDiff();
      try {
        const sessions = await api.listSessions();
        if (sessions) setSessionList(sessions);
      } catch {}
    } catch (err: any) {
      alert(`Execution error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRunCommand = async (cmd: string): Promise<CommandResult | null> => {
    setCommandLogs((prev) => [...prev, `sonic@sandbox-01:~$ ${cmd}`]);
    try {
      const res = await api.executeCommand(cmd, sessionId);
      if (res?.output) {
        setCommandLogs((prev) => [...prev, res.output.trim()]);
      }
      await fetchWorkstationData(sessionId);
      return res;
    } catch (err: any) {
      setCommandLogs((prev) => [...prev, `[FAIL-CLOSED REJECTED]: ${err.message}`]);
      return null;
    }
  };

  const handleSaveFile = async (content: string) => {
    try {
      await api.saveFileContent(activeFile, content);
      await fetchFile(activeFile);
      await fetchDiff();
    } catch (err: any) {
      alert(`Failed to save file: ${err.message}`);
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-[#0D0F12] text-[#E6EDF3] overflow-hidden font-sans select-none">
      {/* Offline Alert Banner */}
      {connectionStatus === "OFFLINE" && (
        <OfflineBanner onRetry={() => fetchWorkstationData(sessionId)} message={errorMessage || undefined} />
      )}

      {/* Main Workspace Frame */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* 1. Left Sidebar */}
        <WorkstationSidebar
          sidebarOpen={sidebarOpen}
          setSidebarOpen={setSidebarOpen}
          sessions={sessionList}
          currentSessionId={sessionId}
          onSelectSession={(id) => {
            setSessionId(id);
            fetchWorkstationData(id);
          }}
          onNewSession={handleNewSession}
          onDeleteSession={handleDeleteSession}
        />

        {/* 2. Main Workstation Body */}
        <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden bg-[#0D0F12]">
          {/* Top Header */}
          <WorkstationHeader
            sidebarOpen={sidebarOpen}
            setSidebarOpen={setSidebarOpen}
            sessionName={workstationState?.mission_name || "Autonomous Mission"}
            gitBranch={workstationState?.git_branch || "main"}
            latestCommit={workstationState?.latest_commit}
            connectionStatus={connectionStatus}
          />

          {/* 2-Column Split Workspace */}
          <div className="flex-1 grid grid-cols-12 overflow-hidden">
            {/* Left Column: Worklog Execution Stream (Col 6) */}
            <div className="col-span-6 border-r border-[#21262D] flex flex-col h-full bg-[#0D0F12] overflow-hidden">
              <WorklogFeed
                worklog={workstationState?.worklog || []}
                currentAction={workstationState?.current_action}
                loading={loading}
                onSendPrompt={handleSendPrompt}
                onSelectFile={fetchFile}
              />
            </div>

            {/* Right Column: Dynamic Tab Surface (Col 6) */}
            <div className="col-span-6 flex flex-col h-full bg-[#0D0F12] overflow-hidden">
              {/* Tab Switcher Bar */}
              <div className="h-10 border-b border-[#21262D] bg-[#12151A] px-3 flex items-center justify-between text-xs">
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setActiveTab("desktop")}
                    className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                      activeTab === "desktop"
                        ? "bg-[#21262D] text-white font-semibold"
                        : "text-[#8B949E] hover:text-white"
                    }`}
                  >
                    <Monitor className="w-3.5 h-3.5 text-[#3FB950]" />
                    <span>Computer</span>
                  </button>

                  <button
                    onClick={() => setActiveTab("code")}
                    className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                      activeTab === "code"
                        ? "bg-[#21262D] text-white font-semibold"
                        : "text-[#8B949E] hover:text-white"
                    }`}
                  >
                    <FileText className="w-3.5 h-3.5 text-[#58A6FF]" />
                    <span>Code</span>
                  </button>

                  <button
                    onClick={() => {
                      setActiveTab("changes");
                      fetchDiff();
                    }}
                    className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                      activeTab === "changes"
                        ? "bg-[#21262D] text-white font-semibold"
                        : "text-[#8B949E] hover:text-white"
                    }`}
                  >
                    <span>Changes</span>
                  </button>

                  <button
                    onClick={() => setActiveTab("research")}
                    className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                      activeTab === "research"
                        ? "bg-[#21262D] text-white font-semibold"
                        : "text-[#8B949E] hover:text-white"
                    }`}
                  >
                    <Share2 className="w-3.5 h-3.5 text-purple-400" />
                    <span>Research</span>
                  </button>

                  <button
                    onClick={() => setActiveTab("evidence")}
                    className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                      activeTab === "evidence"
                        ? "bg-[#21262D] text-white font-semibold"
                        : "text-[#8B949E] hover:text-white"
                    }`}
                  >
                    <FileCheck2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Evidence</span>
                  </button>

                  <button
                    onClick={() => setActiveTab("evolution")}
                    className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                      activeTab === "evolution"
                        ? "bg-[#21262D] text-white font-semibold"
                        : "text-[#8B949E] hover:text-white"
                    }`}
                  >
                    <Dna className="w-3.5 h-3.5 text-pink-400" />
                    <span>Evolution</span>
                  </button>

                  <button
                    onClick={() => setActiveTab("mission")}
                    className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition ${
                      activeTab === "mission"
                        ? "bg-[#21262D] text-white font-semibold"
                        : "text-[#8B949E] hover:text-white"
                    }`}
                  >
                    <Compass className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Mission</span>
                  </button>
                </div>
              </div>

              {/* Tab Surface Body */}
              <div className="flex-1 overflow-hidden p-3 flex flex-col">
                {activeTab === "desktop" && (
                  <ComputerSurface
                    desktopState={workstationState?.desktop}
                    onRunCommand={handleRunCommand}
                    commandLogs={commandLogs}
                  />
                )}

                {activeTab === "code" && (
                  <CodeViewer
                    activeFile={activeFile}
                    fileContent={fileContent}
                    gitDiff={gitDiff}
                    viewMode="code"
                    onSaveFile={handleSaveFile}
                  />
                )}

                {activeTab === "changes" && (
                  <CodeViewer
                    activeFile={activeFile}
                    fileContent={fileContent}
                    gitDiff={gitDiff}
                    viewMode="changes"
                    onRefreshDiff={fetchDiff}
                  />
                )}

                {activeTab === "research" && <ResearchView />}

                {activeTab === "evidence" && <EvidenceView />}

                {activeTab === "evolution" && <EvolutionView />}

                {activeTab === "mission" && <MissionView workstationState={workstationState} />}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
