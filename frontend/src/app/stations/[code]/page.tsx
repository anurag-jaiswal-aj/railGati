import Link from "next/link";
import { notFound } from "next/navigation";

interface StationDetail {
  id: number;
  code: string;
  name: string;
  state: string | null;
  zone: string | null;
  latitude: number | null;
  longitude: number | null;
  provenance: {
    snapshot_id: number;
    source_name: string;
    retrieved_at: string;
  };
}

async function getStation(code: string): Promise<StationDetail | null> {
  const res = await fetch(`http://127.0.0.1:8000/api/v1/stations/${code}`, {
    // Next.js fetch caching
    next: { revalidate: 60 }
  });
  
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error("Failed to fetch station");
  }
  
  return res.json();
}

export default async function StationPage({ params }: { params: { code: string } }) {
  // Await the params in Next.js 15
  const resolvedParams = await params;
  const station = await getStation(resolvedParams.code);
  
  if (!station) {
    notFound();
  }

  return (
    <main className="flex flex-1 flex-col items-center px-4 py-12">
      <div className="w-full max-w-4xl mb-8">
        <Link href="/" className="text-sm font-medium text-blue-600 hover:underline flex items-center gap-1 w-fit">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m15 18-6-6 6-6"/>
          </svg>
          Back to Search
        </Link>
      </div>

      <div className="w-full max-w-4xl overflow-hidden rounded-2xl border border-foreground/10 bg-card shadow-lg">
        {/* Header */}
        <div className="bg-foreground/[0.02] border-b border-foreground/10 px-8 py-10 flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="rounded-md bg-blue-100 dark:bg-blue-900/40 px-3 py-1 text-sm font-bold tracking-widest text-blue-800 dark:text-blue-300">
                {station.code}
              </span>
              <span className="text-sm font-medium text-foreground/50">Canonical ID: {station.id}</span>
            </div>
            <h1 className="text-4xl md:text-5xl font-extrabold text-foreground tracking-tight">
              {station.name}
            </h1>
          </div>
        </div>

        {/* Details Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-foreground/10">
          <div className="bg-card px-8 py-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">State</h3>
            <p className="text-lg font-medium text-foreground">{station.state || "Not Available"}</p>
          </div>
          
          <div className="bg-card px-8 py-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">Railway Zone</h3>
            <p className="text-lg font-medium text-foreground">{station.zone || "Not Available"}</p>
          </div>

          <div className="bg-card px-8 py-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">Latitude</h3>
            <p className="text-lg font-medium text-foreground font-mono">
              {station.latitude !== null ? station.latitude.toFixed(6) : "Not Available"}
            </p>
          </div>

          <div className="bg-card px-8 py-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">Longitude</h3>
            <p className="text-lg font-medium text-foreground font-mono">
              {station.longitude !== null ? station.longitude.toFixed(6) : "Not Available"}
            </p>
          </div>
        </div>

        {/* Provenance Footer */}
        <div className="bg-foreground/[0.02] border-t border-foreground/10 px-8 py-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 text-xs text-foreground/50">
          <div className="flex items-center gap-1.5">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            <span>Source: <strong>{station.provenance.source_name}</strong></span>
          </div>
          <div className="flex items-center gap-4">
            <span>Snapshot ID: {station.provenance.snapshot_id}</span>
            <span>Retrieved: {new Date(station.provenance.retrieved_at).toLocaleDateString()}</span>
          </div>
        </div>
      </div>
    </main>
  );
}
