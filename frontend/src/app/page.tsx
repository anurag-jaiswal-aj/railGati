export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center px-6 py-16">
      <div className="text-center max-w-2xl">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Rail<span className="text-blue-600 dark:text-blue-400">Gati</span>
        </h1>
        <p className="mt-4 text-lg text-foreground/70">
          Intelligent Railway Discovery, Planning &amp; Analytics
        </p>
        <div className="mt-8 rounded-lg border border-foreground/10 bg-foreground/[0.02] p-6 text-sm text-foreground/60">
          <p>
            <strong className="text-foreground/80">v0.1.0</strong> —
            Engineering foundation established.
          </p>
          <p className="mt-2">
            Railway search, journey planning, and analytics are coming in future
            versions.
          </p>
        </div>
      </div>
    </main>
  );
}
