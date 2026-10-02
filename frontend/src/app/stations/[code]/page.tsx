import Link from "next/link";
import { notFound } from "next/navigation";
import { getServerApiUrl } from "@/lib/api";

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

interface TrainSearchItem {
  train_number: string;
  name: string;
  type: string | null;
  return_train_number: string | null;
}

interface PaginatedTrains {
  items: TrainSearchItem[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

interface StationTransferFreeReachResponse {
  station_code: string;
  station_name: string | null;
  topological_outbound_degree: number;
  transfer_free_outbound_reach: number;
  reachability_span_ratio: number;
}

interface OutboundEdgeItem {
  next_station_code: string;
  next_station_name: string | null;
  train_volume: number;
  min_duration_minutes: number;
  max_duration_minutes: number;
  avg_duration_minutes: number;
}

interface OutboundEdgeTransitResponse {
  station_code: string;
  station_name: string | null;
  timetable_snapshot_id: number;
  outbound_edges: OutboundEdgeItem[];
}

async function getStationData(code: string) {
  const fetchOptions = { next: { revalidate: 60 } };
  const baseUrl = getServerApiUrl() + "/api/v1";

  const [stationRes, trainsRes, reachRes, outboundRes] = await Promise.all([
    fetch(`${baseUrl}/stations/${code}`, fetchOptions),
    fetch(`${baseUrl}/stations/${code}/trains`, fetchOptions).catch(() => null),
    fetch(`${baseUrl}/network/stations/${code}/transfer-free-reach`, fetchOptions).catch(() => null),
    fetch(`${baseUrl}/network/stations/${code}/outbound-edges/transit`, fetchOptions).catch(() => null)
  ]);

  if (!stationRes.ok) {
    if (stationRes.status === 404) return null;
    throw new Error("Failed to fetch station");
  }

  const station: StationDetail = await stationRes.json();
  const trains: PaginatedTrains | null = trainsRes && trainsRes.ok ? await trainsRes.json() : null;
  const reach: StationTransferFreeReachResponse | null = reachRes && reachRes.ok ? await reachRes.json() : null;
  const outbound: OutboundEdgeTransitResponse | null = outboundRes && outboundRes.ok ? await outboundRes.json() : null;

  return { station, trains, reach, outbound };
}

export default async function StationPage({ params }: { params: { code: string } }) {
  const resolvedParams = await params;
  const data = await getStationData(resolvedParams.code);
  
  if (!data) {
    notFound();
  }

  const { station, trains, reach, outbound } = data;

  const formatDuration = (mins: number) => {
    const h = Math.floor(mins / 60);
    const m = Math.round(mins % 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  };

  return (
    <main className="flex flex-1 flex-col items-center px-4 py-12">
      <div className="w-full max-w-4xl mb-4">
        <Link href="/" className="text-sm font-medium text-blue-600 hover:underline flex items-center gap-1 w-fit">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m15 18-6-6 6-6"/>
          </svg>
          Back to Search
        </Link>
      </div>

      {/* Historical Disclaimer */}
      <div className="w-full max-w-4xl mb-8 p-4 rounded-xl border border-yellow-500/30 bg-yellow-500/10 text-yellow-800 dark:text-yellow-400 text-sm flex items-start gap-3">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 mt-0.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        <p>
          RailGati uses a historical timetable dataset for this view. Scheduled service counts and network relationships are not live railway status.
        </p>
      </div>

      <div className="w-full max-w-4xl overflow-hidden rounded-2xl border border-foreground/10 bg-card shadow-lg mb-8">
        {/* Header */}
        <div className="bg-foreground/[0.02] border-b border-foreground/10 px-8 py-10 flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
          <div>
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              <span className="rounded-md bg-blue-100 dark:bg-blue-900/40 px-3 py-1 text-sm font-bold tracking-widest text-blue-800 dark:text-blue-300">
                {station.code}
              </span>
              <span className="text-sm font-medium text-foreground/50">Canonical ID: {station.id}</span>
            </div>
            <h1 className="text-4xl md:text-5xl font-extrabold text-foreground tracking-tight">
              {station.name}
            </h1>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-semibold text-blue-700 dark:text-blue-400">
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v20"/><path d="m17 5-5-3-5 3"/><path d="m17 19-5 3-5-3"/><path d="M2 12h20"/><path d="m5 7-3 5 3 5"/><path d="m19 7 3 5-3 5"/></svg>
            Historical Timetable Intelligence
          </div>
        </div>

        {/* Details Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-foreground/10">
          <div className="bg-card px-6 py-5">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">State</h3>
            <p className="text-base font-medium text-foreground">{station.state || "—"}</p>
          </div>
          <div className="bg-card px-6 py-5">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">Railway Zone</h3>
            <p className="text-base font-medium text-foreground">{station.zone || "—"}</p>
          </div>
          <div className="bg-card px-6 py-5">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">Latitude</h3>
            <p className="text-base font-medium text-foreground font-mono">
              {station.latitude !== null ? station.latitude.toFixed(6) : "—"}
            </p>
          </div>
          <div className="bg-card px-6 py-5">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">Longitude</h3>
            <p className="text-base font-medium text-foreground font-mono">
              {station.longitude !== null ? station.longitude.toFixed(6) : "—"}
            </p>
          </div>
        </div>
      </div>

      <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
        {/* Network Summary Cards */}
        <div className="rounded-2xl border border-foreground/10 bg-card overflow-hidden shadow-sm flex flex-col justify-center px-8 py-8">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground/50 mb-4">Timetable Reach</h2>
          <div className="text-4xl font-extrabold text-foreground mb-2">
            {reach ? reach.transfer_free_outbound_reach : "—"}
          </div>
          <p className="text-sm text-foreground/60 mb-6 flex-1">
            Distinct stations reachable without a transfer in the historical timetable.
          </p>
          <Link
            href={`/stations/${station.code.toLowerCase()}/reachability`}
            className="inline-flex w-fit items-center gap-2 rounded-full border border-blue-500/30 bg-blue-500/10 px-4 py-2 text-sm font-semibold text-blue-700 transition hover:bg-blue-500/20 dark:text-blue-400"
          >
            Explore Network Reachability
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
          </Link>
        </div>

        <div className="rounded-2xl border border-foreground/10 bg-card overflow-hidden shadow-sm flex flex-col justify-center px-8 py-8">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground/50 mb-4">Direct Outbound Connections</h2>
          <div className="text-4xl font-extrabold text-foreground mb-2">
            {outbound ? outbound.outbound_edges.length : "—"}
          </div>
          <p className="text-sm text-foreground/60">
            Distinct stations immediately downstream on scheduled train routes.
          </p>
        </div>
      </div>

      <div className="w-full max-w-4xl grid grid-cols-1 gap-8">
        {/* Direct Outbound Connections */}
        <div>
          <h2 className="text-2xl font-bold text-foreground mb-4">Direct Outbound Connections</h2>
          <div className="bg-card rounded-2xl border border-foreground/10 overflow-hidden shadow-sm">
            {!outbound ? (
              <div className="px-6 py-8 text-center text-foreground/50">Unavailable</div>
            ) : outbound.outbound_edges.length === 0 ? (
              <div className="px-6 py-8 text-center text-foreground/50">No scheduled outbound connections.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-foreground/[0.03] border-b border-foreground/10">
                    <tr>
                      <th className="px-6 py-4 font-semibold text-foreground/60">Next Station</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60 text-right">Scheduled Services</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60 text-right">Avg. Scheduled Travel Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-foreground/5">
                    {outbound.outbound_edges.map((edge) => (
                      <tr key={edge.next_station_code} className="hover:bg-foreground/[0.02] transition-colors">
                        <td className="px-6 py-4">
                          <Link href={`/stations/${edge.next_station_code.toLowerCase()}`} className="font-medium text-blue-600 hover:underline">
                            {edge.next_station_name || edge.next_station_code} <span className="text-foreground/50 text-xs font-normal">({edge.next_station_code})</span>
                          </Link>
                        </td>
                        <td className="px-6 py-4 text-right font-mono text-foreground/80">{edge.train_volume}</td>
                        <td className="px-6 py-4 text-right font-mono text-foreground/80">{formatDuration(edge.avg_duration_minutes)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Scheduled Trains */}
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-foreground mb-4">Scheduled Services</h2>
          <div className="bg-card rounded-2xl border border-foreground/10 overflow-hidden shadow-sm">
            {!trains ? (
              <div className="px-6 py-8 text-center text-foreground/50">Unavailable</div>
            ) : trains.items.length === 0 ? (
              <div className="px-6 py-8 text-center text-foreground/50">No scheduled trains call at this station.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-foreground/[0.03] border-b border-foreground/10">
                    <tr>
                      <th className="px-6 py-4 font-semibold text-foreground/60">Train Number</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60">Train Name</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60">Type</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-foreground/5">
                    {trains.items.map((train) => (
                      <tr key={train.train_number} className="hover:bg-foreground/[0.02] transition-colors">
                        <td className="px-6 py-4 font-mono text-foreground/80">
                          <Link href={`/trains/${train.train_number}`} className="text-blue-600 hover:underline font-bold">
                            {train.train_number}
                          </Link>
                        </td>
                        <td className="px-6 py-4 font-medium text-foreground">{train.name}</td>
                        <td className="px-6 py-4 text-foreground/70">{train.type || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {trains && trains.total > trains.size && (
              <div className="px-6 py-4 bg-foreground/[0.02] border-t border-foreground/10 text-center text-xs text-foreground/50">
                Showing first {trains.items.length} scheduled services of {trains.total}.
              </div>
            )}
          </div>
        </div>
      </div>

    </main>
  );
}
