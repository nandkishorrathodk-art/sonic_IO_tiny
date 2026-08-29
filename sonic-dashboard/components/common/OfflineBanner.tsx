import React from "react";
import { WifiOff, AlertCircle, RefreshCw } from "lucide-react";

interface OfflineBannerProps {
  onRetry?: () => void;
  message?: string;
}

export function OfflineBanner({ onRetry, message }: OfflineBannerProps) {
  return (
    <div className="bg-red-950/90 border-b border-red-800/80 px-4 py-2 flex items-center justify-between text-xs text-red-200 font-mono z-40">
      <div className="flex items-center gap-2">
        <WifiOff className="w-4 h-4 text-red-400 flex-shrink-0" />
        <span className="font-bold">BACKEND DISCONNECTED:</span>
        <span className="text-red-300">
          {message || "FastAPI Control Plane is offline or unreachable. No synthetic data is being generated (Fail-Closed)."}
        </span>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-2.5 py-1 bg-red-900/80 hover:bg-red-800 border border-red-700 text-white rounded font-bold flex items-center gap-1.5 transition text-[11px]"
        >
          <RefreshCw className="w-3 h-3" />
          <span>Retry Connection</span>
        </button>
      )}
    </div>
  );
}
