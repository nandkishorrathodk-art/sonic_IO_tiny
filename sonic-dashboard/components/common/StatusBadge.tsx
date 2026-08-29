import React from "react";
import { Wifi, WifiOff, RefreshCw, AlertTriangle, ShieldCheck } from "lucide-react";
import { SystemStatus } from "../../types/workstation";

interface StatusBadgeProps {
  status: SystemStatus;
  label?: string;
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  switch (status) {
    case "LIVE":
      return (
        <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800/80">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>{label || "LIVE"}</span>
        </span>
      );
    case "CONNECTING":
      return (
        <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-blue-950/80 text-blue-400 border border-blue-800/80">
          <RefreshCw className="w-2.5 h-2.5 animate-spin" />
          <span>{label || "CONNECTING"}</span>
        </span>
      );
    case "OFFLINE":
    case "DISCONNECTED":
      return (
        <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-red-950/80 text-red-400 border border-red-800/80">
          <WifiOff className="w-2.5 h-2.5" />
          <span>{label || status}</span>
        </span>
      );
    case "ERROR":
      return (
        <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-amber-950/80 text-amber-400 border border-amber-800/80">
          <AlertTriangle className="w-2.5 h-2.5" />
          <span>{label || "FAIL-CLOSED"}</span>
        </span>
      );
  }
}
