export default function NotFound() {
  return (
    <main className="min-h-screen bg-[#0D0F12] text-[#E6EDF3] flex items-center justify-center p-8">
      <div className="text-center font-mono">
        <h1 className="text-xl font-semibold">Page not found</h1>
        <p className="text-sm text-slate-400 mt-2">The requested Sonic workspace route does not exist.</p>
      </div>
    </main>
  );
}
