import React from "react";
import { WifiOff, RefreshCw } from "lucide-react";

interface OfflineBannerProps {
  onRetry?: () => void;
  message?: string;
}

export function OfflineBanner({ onRetry, message }: OfflineBannerProps) {
  return (
    <div className="bg-danger/15 border-b border-danger/40 px-4 py-2 flex items-center justify-between text-xs text-danger font-mono z-40 backdrop-blur-sm">
      <div className="flex items-center gap-2">
        <WifiOff className="w-4 h-4 text-danger flex-shrink-0" />
        <span className="font-bold">BACKEND DISCONNECTED:</span>
        <span className="text-danger/80">
          {message || "FastAPI Control Plane is offline or unreachable. No synthetic data is being generated (Fail-Closed)."}
        </span>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-2.5 py-1 bg-danger/20 hover:bg-danger/30 border border-danger/50 text-white rounded font-bold flex items-center gap-1.5 transition text-[11px]"
        >
          <RefreshCw className="w-3 h-3" />
          <span>Retry Connection</span>
        </button>
      )}
    </div>
  );
}
