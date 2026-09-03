import React from "react";
import { Wifi, WifiOff, RefreshCw, AlertTriangle } from "lucide-react";
import { SystemStatus } from "../../types/workstation";

interface StatusBadgeProps {
  status: SystemStatus;
  label?: string;
}

const STYLES: Record<SystemStatus, { cls: string; icon: React.ReactNode }> = {
  LIVE: {
    cls: "bg-success/10 text-success border-success/40",
    icon: <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />,
  },
  CONNECTING: {
    cls: "bg-secondary/10 text-secondary-400 border-secondary/40",
    icon: <RefreshCw className="w-2.5 h-2.5 animate-spin" />,
  },
  OFFLINE: {
    cls: "bg-danger/10 text-danger border-danger/40",
    icon: <WifiOff className="w-2.5 h-2.5" />,
  },
  DISCONNECTED: {
    cls: "bg-danger/10 text-danger border-danger/40",
    icon: <WifiOff className="w-2.5 h-2.5" />,
  },
  ERROR: {
    cls: "bg-warning/10 text-warning border-warning/40",
    icon: <AlertTriangle className="w-2.5 h-2.5" />,
  },
};

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const s = STYLES[status] ?? STYLES.ERROR;
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${s.cls}`}
    >
      {s.icon}
      <span>{label || status}</span>
    </span>
  );
}
