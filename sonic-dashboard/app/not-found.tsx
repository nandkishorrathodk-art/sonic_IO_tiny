import Link from "next/link";

export default function NotFound() {
  return (
    <main className="min-h-screen bg-ink-950 bg-grid-glow flex items-center justify-center p-8">
      <div className="text-center font-mono space-y-4 animate-fade-in-up">
        <div className="text-7xl font-black text-gradient">404</div>
        <h1 className="text-xl font-semibold text-white">Page not found</h1>
        <p className="text-sm text-muted max-w-md mx-auto">
          The route you requested does not exist in the SONIC-REDA workstation.
        </p>
        <Link href="/" className="btn-primary !px-6 !py-2.5 text-xs inline-flex">
          Return to Workstation
        </Link>
      </div>
    </main>
  );
}
