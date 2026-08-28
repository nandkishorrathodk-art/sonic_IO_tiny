import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SONIC WORKSTATION — Autonomous AI Engineer & Computer Workspace",
  description: "Next-Generation Autonomous AI Developer & Security Researcher Workstation",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#0A0C10] text-slate-100 min-h-screen flex flex-col antialiased font-sans selection:bg-blue-600 selection:text-white overflow-hidden">
        {children}
      </body>
    </html>
  );
}
