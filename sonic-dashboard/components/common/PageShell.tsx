import React from "react";

interface PageHeaderProps {
  icon: React.ReactNode;
  title: string;
  badge?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  accent?: "primary" | "secondary" | "accent" | "success";
}

const ACCENT_WRAP: Record<string, string> = {
  primary: "from-primary-600 to-primary-700 shadow-glow",
  secondary: "from-secondary-600 to-secondary-700 shadow-glow-cyan",
  accent: "from-accent-600 to-accent-700 shadow-glow-violet",
  success: "from-emerald-600 to-emerald-700",
};

export function PageHeader({ icon, title, badge, subtitle, actions, accent = "primary" }: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between glass-card rounded-2xl p-5 animate-fade-in-up">
      <div className="flex items-center gap-4 min-w-0">
        <div
          className={`grid place-items-center w-12 h-12 rounded-xl bg-gradient-to-tr ${ACCENT_WRAP[accent]} text-white shrink-0`}
        >
          <div className="bg-ink-950/40 w-full h-full rounded-[10px] grid place-items-center">
            {icon}
          </div>
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-lg font-bold text-white tracking-wide truncate">{title}</h2>
            {badge && (
              <span className="chip bg-ink-800 text-muted-bright border border-ink-600">
                {badge}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="text-xs text-muted mt-1 font-mono truncate">{subtitle}</p>
          )}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

interface PageShellProps {
  children: React.ReactNode;
  maxWidth?: string;
}

export function PageShell({ children, maxWidth = "max-w-7xl" }: PageShellProps) {
  return (
    <div className={`min-h-screen bg-ink-950 bg-grid-glow ${maxWidth} mx-auto p-6 space-y-6`}>
      {children}
    </div>
  );
}

interface StateBlockProps {
  error?: string | null;
  loading?: boolean;
  empty?: boolean;
  emptyIcon?: React.ReactNode;
  emptyTitle?: string;
  emptyText?: string;
  spinnerColor?: string;
  loadingText?: string;
  children?: React.ReactNode;
}

export function StateBlock({
  error,
  loading,
  empty,
  emptyIcon,
  emptyTitle,
  emptyText,
  spinnerColor = "text-primary-400",
  loadingText = "Loading…",
  children,
}: StateBlockProps) {
  if (error) {
    return (
      <div className="p-4 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs font-mono">
        <strong className="mr-1">Backend Error:</strong> {error}
      </div>
    );
  }
  if (loading) {
    return (
      <div className="py-20 text-center space-y-3 animate-fade-in-up">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-ink-850 border border-ink-700">
          <span className={`block w-6 h-6 rounded-full border-2 border-ink-600 border-t-transparent ${spinnerColor} animate-devin-spin`} />
        </div>
        <span className="text-xs text-muted font-mono">{loadingText}</span>
      </div>
    );
  }
  if (empty) {
    return (
      <div className="glass-card rounded-2xl p-12 text-center space-y-3 animate-fade-in-up">
        <div className="grid place-items-center w-16 h-16 mx-auto rounded-2xl bg-ink-800 border border-ink-700 text-muted-dim">
          {emptyIcon}
        </div>
        {emptyTitle && <h3 className="text-sm font-bold text-white">{emptyTitle}</h3>}
        {emptyText && (
          <p className="text-xs text-muted max-w-md mx-auto">{emptyText}</p>
        )}
      </div>
    );
  }
  return <>{children}</>;
}
