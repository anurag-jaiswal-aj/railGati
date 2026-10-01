import Link from "next/link";

interface HubCentralityItem {
  station_code: string;
  station_name: string;
  out_degree: number;
  in_degree: number;
  total_topological_degree: number;
  outbound_service_occurrence_volume: number;
  inbound_service_occurrence_volume: number;
  combined_occurrence_volume: number;
}

interface HubCentralityResponse {
  timetable_snapshot_id: number;
  hubs: HubCentralityItem[];
}

interface EdgeVolumeItem {
  from_station_code: string;
  from_station_name: string;
  to_station_code: string;
  to_station_name: string;
  service_occurrence_volume: number;
}

interface EdgeVolumeResponse {
  timetable_snapshot_id: number;
  edges: EdgeVolumeItem[];
}

interface TerminusItem {
  station_code: string;
  station_name: string;
  originating_count: number;
  terminating_count: number;
  total_terminus_volume: number;
}

interface TerminusResponse {
  timetable_snapshot_id: number;
  termini: TerminusItem[];
}

async function getNetworkData() {
  const fetchOptions = { next: { revalidate: 300 } };
  const baseUrl = "http://127.0.0.1:8000/api/v1";

  const [hubsRes, edgesRes, terminiRes] = await Promise.all([
    fetch(`${baseUrl}/network/hubs`, fetchOptions).catch(() => null),
    fetch(`${baseUrl}/network/edges/volume`, fetchOptions).catch(() => null),
    fetch(`${baseUrl}/network/termini`, fetchOptions).catch(() => null)
  ]);

  const hubs: HubCentralityResponse | null = hubsRes && hubsRes.ok ? await hubsRes.json() : null;
  const edges: EdgeVolumeResponse | null = edgesRes && edgesRes.ok ? await edgesRes.json() : null;
  const termini: TerminusResponse | null = terminiRes && terminiRes.ok ? await terminiRes.json() : null;

  return { hubs, edges, termini };
}

export default async function NetworkPage() {
  const { hubs, edges, termini } = await getNetworkData();

  if (!hubs && !edges && !termini) {
    return (
      <main className="flex flex-1 flex-col items-center px-4 py-12 justify-center">
        <h1 className="text-2xl font-bold mb-4">Network Discovery Unavailable</h1>
        <p className="text-foreground/70 mb-8">Failed to connect to the backend services.</p>
        <Link href="/" className="text-blue-600 hover:underline">Back to Search</Link>
      </main>
    );
  }

  return (
    <main className="flex flex-1 flex-col items-center px-4 py-12 md:py-16">
      <div className="w-full max-w-5xl mb-4">
        <Link href="/" className="text-sm font-medium text-blue-600 hover:underline flex items-center gap-1 w-fit">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m15 18-6-6 6-6"/>
          </svg>
          Back to Search
        </Link>
      </div>

      <div className="w-full max-w-5xl text-center mb-8">
        <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-foreground mb-4">
          Network Discovery
        </h1>
        <p className="text-lg text-foreground/70 max-w-2xl mx-auto">
          Explore the structure of RailGati&apos;s historical railway timetable network.
        </p>
      </div>

      {/* Historical Disclaimer */}
      <div className="w-full max-w-5xl mb-12 p-4 rounded-xl border border-yellow-500/30 bg-yellow-500/10 text-yellow-800 dark:text-yellow-400 text-sm flex items-start gap-3 shadow-sm mx-auto">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 mt-0.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        <p>
          RailGati uses a historical timetable dataset for this view. Scheduled service counts and network relationships are not live railway status.
        </p>
      </div>

      <div className="w-full max-w-5xl grid grid-cols-1 gap-12">
        {/* Major Timetable Hubs */}
        <section>
          <div className="mb-6">
            <h2 className="text-2xl font-bold text-foreground">Major Timetable Hubs</h2>
            <p className="text-sm text-foreground/60 mt-1">
              Top stations ranked by the number of distinct stations directly reachable from them in the historical timetable. This represents scheduled connectivity, not passenger demand.
            </p>
          </div>
          <div className="bg-card rounded-2xl border border-foreground/10 overflow-hidden shadow-sm">
            {!hubs ? (
              <div className="px-6 py-8 text-center text-foreground/50">Unavailable</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-foreground/[0.03] border-b border-foreground/10">
                    <tr>
                      <th className="px-6 py-4 font-semibold text-foreground/60">Rank</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60">Station</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60 text-right">Scheduled Degree (Connections)</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60 text-right">Scheduled Volume</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-foreground/5">
                    {hubs.hubs.slice(0, 10).map((hub, idx) => (
                      <tr key={hub.station_code} className="hover:bg-foreground/[0.02] transition-colors">
                        <td className="px-6 py-4 text-foreground/50 font-mono">#{idx + 1}</td>
                        <td className="px-6 py-4">
                          <Link href={`/stations/${hub.station_code.toLowerCase()}`} className="font-medium text-blue-600 hover:underline">
                            {hub.station_name} <span className="text-foreground/50 text-xs font-normal">({hub.station_code})</span>
                          </Link>
                        </td>
                        <td className="px-6 py-4 text-right font-mono text-foreground/80">{hub.total_topological_degree}</td>
                        <td className="px-6 py-4 text-right font-mono text-foreground/80">{hub.combined_occurrence_volume}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        {/* Highest-Volume Scheduled Connections */}
        <section>
          <div className="mb-6">
            <h2 className="text-2xl font-bold text-foreground">Highest-Volume Scheduled Connections</h2>
            <p className="text-sm text-foreground/60 mt-1">
              Station-to-station segments with the highest recorded scheduled train volume in the historical timetable.
            </p>
          </div>
          <div className="bg-card rounded-2xl border border-foreground/10 overflow-hidden shadow-sm">
            {!edges ? (
              <div className="px-6 py-8 text-center text-foreground/50">Unavailable</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-foreground/[0.03] border-b border-foreground/10">
                    <tr>
                      <th className="px-6 py-4 font-semibold text-foreground/60">Rank</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60">From Station</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60">To Station</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60 text-right">Scheduled Train Volume</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-foreground/5">
                    {edges.edges.slice(0, 10).map((edge, idx) => (
                      <tr key={`${edge.from_station_code}-${edge.to_station_code}`} className="hover:bg-foreground/[0.02] transition-colors">
                        <td className="px-6 py-4 text-foreground/50 font-mono">#{idx + 1}</td>
                        <td className="px-6 py-4">
                          <Link href={`/stations/${edge.from_station_code.toLowerCase()}`} className="font-medium text-blue-600 hover:underline">
                            {edge.from_station_name} <span className="text-foreground/50 text-xs font-normal">({edge.from_station_code})</span>
                          </Link>
                        </td>
                        <td className="px-6 py-4">
                          <Link href={`/stations/${edge.to_station_code.toLowerCase()}`} className="font-medium text-blue-600 hover:underline">
                            {edge.to_station_name} <span className="text-foreground/50 text-xs font-normal">({edge.to_station_code})</span>
                          </Link>
                        </td>
                        <td className="px-6 py-4 text-right font-mono text-foreground/80">{edge.service_occurrence_volume}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        {/* Major Scheduled Termini */}
        <section>
          <div className="mb-6">
            <h2 className="text-2xl font-bold text-foreground">Major Scheduled Termini</h2>
            <p className="text-sm text-foreground/60 mt-1">
              Top stations where the most scheduled services either originate or terminate in the historical timetable.
            </p>
          </div>
          <div className="bg-card rounded-2xl border border-foreground/10 overflow-hidden shadow-sm">
            {!termini ? (
              <div className="px-6 py-8 text-center text-foreground/50">Unavailable</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-foreground/[0.03] border-b border-foreground/10">
                    <tr>
                      <th className="px-6 py-4 font-semibold text-foreground/60">Rank</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60">Station</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60 text-right">Originating Services</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60 text-right">Terminating Services</th>
                      <th className="px-6 py-4 font-semibold text-foreground/60 text-right">Total Terminal Occurrences</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-foreground/5">
                    {termini.termini.slice(0, 10).map((term, idx) => (
                      <tr key={term.station_code} className="hover:bg-foreground/[0.02] transition-colors">
                        <td className="px-6 py-4 text-foreground/50 font-mono">#{idx + 1}</td>
                        <td className="px-6 py-4">
                          <Link href={`/stations/${term.station_code.toLowerCase()}`} className="font-medium text-blue-600 hover:underline">
                            {term.station_name} <span className="text-foreground/50 text-xs font-normal">({term.station_code})</span>
                          </Link>
                        </td>
                        <td className="px-6 py-4 text-right font-mono text-foreground/80">{term.originating_count}</td>
                        <td className="px-6 py-4 text-right font-mono text-foreground/80">{term.terminating_count}</td>
                        <td className="px-6 py-4 text-right font-mono text-foreground/80">{term.total_terminus_volume}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

      </div>
    </main>
  );
}
