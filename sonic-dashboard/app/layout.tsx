import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "SONIC — Virtual Workstation",
    template: "%s · SONIC",
  },
  description:
    "A general-purpose virtual workstation and isolated sandbox environment.",
  applicationName: "SONIC",
  authors: [{ name: "SONIC" }],
  keywords: ["virtual workstation", "sandbox", "computer", "terminal"],
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
