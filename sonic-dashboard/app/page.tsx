"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  FileText,
  Monitor,
  PanelRightClose,
  Share2,
  FileCheck2,
  Dna,
  Compass,
} from "lucide-react";
import { api } from "../lib/api";
import {
  WorkstationState,
  SystemStatus,
  WorkstationTab,
  CommandResult,
  SessionItem,
  normalizeSessionList,
  sanitizeCurrentAction,
} from "../types/workstation";

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

const TABS: { id: WorkstationTab; label: string; icon: React.ReactNode }[] = [
  { id: "desktop", label: "Computer", icon: <Monitor className="w-3.5 h-3.5 text-success" /> },
  { id: "code", label: "Code", icon: <FileText className="w-3.5 h-3.5 text-secondary-400" /> },
  { id: "changes", label: "Changes", icon: <FileText className="w-3.5 h-3.5 text-warning" /> },
  { id: "research", label: "Research", icon: <Share2 className="w-3.5 h-3.5 text-accent-400" /> },
  { id: "evidence", label: "Evidence", icon: <FileCheck2 className="w-3.5 h-3.5 text-success" /> },
  { id: "evolution", label: "Evolution", icon: <Dna className="w-3.5 h-3.5 text-primary-400" /> },
  { id: "mission", label: "Mission", icon: <Compass className="w-3.5 h-3.5 text-primary-400" /> },
];

export default function SonicDevinWorkstation() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [activeTab, setActiveTab] = useState<WorkstationTab>("desktop");
  const [connectionStatus, setConnectionStatus] = useState<SystemStatus>("CONNECTING");
  const [sessionId, setSessionId] = useState("fresh");
  const [workstationState, setWorkstationState] = useState<WorkstationState | null>(null);
  const [activeFile, setActiveFile] = useState("");
  const [fileContent, setFileContent] = useState<string[]>([]);
  const [gitDiff, setGitDiff] = useState("");
  const [commandLogs, setCommandLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [sessionList, setSessionList] = useState<SessionItem[]>([]);
  const abortPollRef = useRef<boolean>(false);
  const activePromptSessionRef = useRef<string | null>(null);

  const fetchWorkstationData = async (targetSession = sessionId) => {
    try {
      const state = await api.getWorkstationState(targetSession);
      setWorkstationState(state);
      setConnectionStatus("LIVE");
      setErrorMessage(null);

      // If backend reports state is not RUNNING, stop loading spinner
      if (state && state.status !== "RUNNING") {
        setLoading(false);
      }

      try {
        const rawSessions = await api.listSessions();
        setSessionList(normalizeSessionList(rawSessions));
      } catch {
        // keep current list safely on error
      }
    } catch (err: any) {
      setConnectionStatus("OFFLINE");
      setErrorMessage(err.message || "Failed to reach backend control plane.");
    }
  };

  const handleNewSession = async () => {
    abortPollRef.current = true;
    setLoading(false);
    const newSessionId = `mission-${Math.random().toString(36).substring(2, 7)}`;
    setSessionId(newSessionId);
    setActiveFile("");
    setFileContent([]);
    setGitDiff("");
    setCommandLogs([]);
    await fetchWorkstationData(newSessionId);
  };


  const handleDeleteSession = async (delSessionId: string) => {
    try {
      await api.deleteSession(delSessionId);
      if (sessionId === delSessionId) {
        setSessionId("fresh");
        await fetchWorkstationData("fresh");
      } else {
        await fetchWorkstationData(sessionId);
      }
    } catch {
      // ignore
    }
  };

  const fetchFile = async (path: string) => {
    if (!path) {
      setActiveFile("");
      setFileContent([]);
      return;
    }
    setActiveFile(path);
    try {
      const data = await api.getFileContent(path, sessionId);
      if (data?.lines) setFileContent(data.lines);
      else if (data?.content) setFileContent(data.content.split("\n"));
    } catch {
      setFileContent(["# Error reading file from filesystem."]);
    }
  };

  const fetchDiff = async () => {
    try {
      const data = await api.getGitDiff(sessionId);
      if (data?.diff) setGitDiff(data.diff);
    } catch {
      setGitDiff("");
    }
  };

  useEffect(() => {
    fetchWorkstationData(sessionId);
    fetchDiff();
    const interval = setInterval(() => fetchWorkstationData(sessionId), 5000);
    return () => clearInterval(interval);
  }, [sessionId]);

  const handleSendPrompt = async (prompt: string, mode: "Normal" | "Autonomous" | "Pair-Program") => {
    const currentTargetSession = sessionId;
    activePromptSessionRef.current = currentTargetSession;
    abortPollRef.current = false;
    setLoading(true);

    try {
      const res = await api.sendPrompt(prompt, currentTargetSession, mode.toLowerCase());
      if (mode === "Autonomous") setActiveTab("mission");

      // If user interrupted or navigated away during prompt send, abort immediately
      if (abortPollRef.current || activePromptSessionRef.current !== currentTargetSession) {
        setLoading(false);
        return;
      }

      if (res?.state) {
        setWorkstationState(res.state);
        // If state is already non-running (IDLE, BLOCKED, PAUSED, COMPLETED), stop loading
        if (res.state.status && res.state.status !== "RUNNING") {
          setLoading(false);
          await fetchDiff();
          return;
        }
      }

      // Safeguard: Poll with timeout (max 300 attempts = 5 minutes max wait)
      const MAX_ATTEMPTS = 300;
      let finished = false;

      for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
        if (abortPollRef.current || activePromptSessionRef.current !== currentTargetSession) {
          break;
        }

        await new Promise((resolve) => setTimeout(resolve, 1000));

        if (abortPollRef.current || activePromptSessionRef.current !== currentTargetSession) {
          break;
        }

        try {
          const nextState = await api.getWorkstationState(currentTargetSession);
          if (abortPollRef.current || activePromptSessionRef.current !== currentTargetSession) {
            break;
          }

          setWorkstationState(nextState);

          // 1. If backend status transitioned to non-RUNNING (IDLE, PAUSED, BLOCKED, COMPLETED)
          if (nextState?.status && nextState.status !== "RUNNING") {
            finished = true;
            break;
          }

          // 2. If the worklog feed contains a completed response from SONIC
          const logs = nextState?.worklog || [];
          const lastLog = logs.length > 0 ? logs[logs.length - 1] : null;
          if (lastLog && (lastLog.type === "response" || lastLog.title === "SONIC Response")) {
            finished = true;
            break;
          }
        } catch {
          // Retry on transient network blip
        }
      }

      // Timeout safeguard: if 45s passed without completion, perform final state check and release loader
      if (!finished && !abortPollRef.current) {
        try {
          const finalState = await api.getWorkstationState(currentTargetSession);
          if (activePromptSessionRef.current === currentTargetSession) {
            setWorkstationState(finalState);
          }
        } catch {
          // ignore
        }
      }

      await fetchDiff();
      try {
        const rawSessions = await api.listSessions();
        setSessionList(normalizeSessionList(rawSessions));
      } catch {}
    } catch (err: any) {
      alert(`Execution error: ${err.message}`);
    } finally {
      if (activePromptSessionRef.current === currentTargetSession) {
        setLoading(false);
      }
    }
  };

  const handleRunCommand = async (cmd: string): Promise<CommandResult | null> => {
    setCommandLogs((prev) => [...prev, `sonic@sandbox-01:~$ ${cmd}`]);
    try {
      const res = await api.executeCommand(cmd, sessionId);
      if (res?.output) setCommandLogs((prev) => [...prev, res.output.trim()]);
      await fetchWorkstationData(sessionId);
      return res;
    } catch (err: any) {
      setCommandLogs((prev) => [...prev, `[FAIL-CLOSED REJECTED]: ${err.message}`]);
      return null;
    }
  };

  const handleSaveFile = async (content: string) => {
    try {
      await api.saveFileContent(activeFile, content, sessionId);
      await fetchFile(activeFile);
      await fetchDiff();
    } catch (err: any) {
      alert(`Failed to save file: ${err.message}`);
    }
  };

  const handleInterrupt = async () => {
    // Immediate cancellation safeguard: abort polling loop and clear spinner
    abortPollRef.current = true;
    setLoading(false);
    try {
      await api.interruptSession(sessionId);
      await fetchWorkstationData(sessionId);
    } catch (err: any) {
      console.error("Failed to interrupt session:", err);
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-ink-950 text-slate-200 overflow-hidden font-sans">
      {connectionStatus === "OFFLINE" && (
        <OfflineBanner onRetry={() => fetchWorkstationData(sessionId)} message={errorMessage || undefined} />
      )}

      <div className="flex flex-1 min-h-0 overflow-hidden">
        <WorkstationSidebar
          sidebarOpen={sidebarOpen}
          setSidebarOpen={setSidebarOpen}
          sessions={sessionList}
          currentSessionId={sessionId}
          onSelectSession={(id) => {
            abortPollRef.current = true;
            setLoading(false);
            setSessionId(id);
            setActiveFile("");
            setFileContent([]);
            setGitDiff("");
            setCommandLogs([]);
            fetchWorkstationData(id);
          }}
          onNewSession={handleNewSession}
          onDeleteSession={handleDeleteSession}
        />

        <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden bg-ink-950">
          <WorkstationHeader
            sidebarOpen={sidebarOpen}
            setSidebarOpen={setSidebarOpen}
            sessionName={workstationState?.mission_name || "New conversation"}
            gitBranch={workstationState?.git_branch || ""}
            latestCommit={workstationState?.latest_commit}
            connectionStatus={connectionStatus}
          />

          <div className="flex-1 grid grid-cols-12 overflow-hidden">
            <div className={`${rightPanelOpen ? "col-span-6" : "col-span-12"} border-r border-ink-800 flex flex-col h-full bg-ink-900 overflow-hidden`}>
              <WorklogFeed
                worklog={workstationState?.worklog || []}
                currentAction={sanitizeCurrentAction(
                  workstationState?.current_action,
                  workstationState?.status,
                  loading
                )}
                status={workstationState?.status}
                loading={loading}
                onSendPrompt={handleSendPrompt}
                onInterrupt={handleInterrupt}
                onSelectFile={fetchFile}
                sessionName={workstationState?.mission_name || ""}
                gitBranch={workstationState?.git_branch || ""}
                rightPanelOpen={rightPanelOpen}
                onToggleRightPanel={() => setRightPanelOpen((open) => !open)}
                sessionId={sessionId}
                onRefreshState={() => fetchWorkstationData(sessionId)}
              />
            </div>


            {rightPanelOpen && (
              <div className="col-span-6 flex flex-col h-full bg-ink-950 overflow-hidden">
                <div className="h-10 border-b border-ink-800 bg-ink-900 px-3 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1 min-w-0 overflow-x-auto">
                    {TABS.map((tab) => (
                      <button
                        key={tab.id}
                        onClick={() => {
                          setActiveTab(tab.id);
                          if (tab.id === "changes") fetchDiff();
                        }}
                        className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 transition whitespace-nowrap ${
                          activeTab === tab.id
                            ? "bg-ink-800 text-white font-semibold"
                            : "text-muted hover:text-white"
                        }`}
                      >
                        {tab.icon}
                        <span>{tab.label}</span>
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={() => setRightPanelOpen(false)}
                    className="p-1 rounded text-muted hover:text-white hover:bg-ink-800 transition shrink-0"
                    title="Hide Computer panel"
                    aria-label="Hide Computer panel"
                  >
                    <PanelRightClose className="w-4 h-4" />
                  </button>
                </div>

                <div className="flex-1 overflow-hidden p-3 flex flex-col">
                  {activeTab === "desktop" && (
                    <ComputerSurface
                      desktopState={workstationState?.desktop}
                      onRunCommand={handleRunCommand}
                      commandLogs={commandLogs}
                      onInterrupt={handleInterrupt}
                      sessionId={sessionId}
                    />
                  )}
                  {activeTab === "code" && (
                    <CodeViewer activeFile={activeFile} fileContent={fileContent} gitDiff={gitDiff} viewMode="code" onSaveFile={handleSaveFile} />
                  )}
                  {activeTab === "changes" && (
                    <CodeViewer activeFile={activeFile} fileContent={fileContent} gitDiff={gitDiff} viewMode="changes" onRefreshDiff={fetchDiff} />
                  )}
                  {activeTab === "research" && <ResearchView />}
                  {activeTab === "evidence" && <EvidenceView sessionId={sessionId} />}
                  {activeTab === "evolution" && <EvolutionView sessionId={sessionId} />}
                  {activeTab === "mission" && <MissionView workstationState={workstationState} sessionId={sessionId} />}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
