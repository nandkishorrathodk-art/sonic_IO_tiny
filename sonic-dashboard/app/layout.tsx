import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "SONIC-REDA — Autonomous AI Red Team Workstation",
    template: "%s · SONIC-REDA",
  },
  description:
    "Next-generation autonomous AI red-team agent: full virtual computer control, evidence-backed kill-chains, and self-evolving multi-agent swarm intelligence.",
  applicationName: "SONIC-REDA",
  authors: [{ name: "SONIC-REDA" }],
  keywords: ["autonomous agent", "red team", "security", "AI", "pentest", "evidence"],
};

export const viewport: Viewport = {
  themeColor: "#070910",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-ink-950 text-slate-200 min-h-screen antialiased font-sans selection:bg-primary-500 selection:text-white">
        {children}
      </body>
    </html>
  );
}
