import Link from "next/link";
import { notFound } from "next/navigation";

interface TrainDetail {
  train_number: string;
  name: string;
  type: string | null;
  return_train_number: string | null;
  provenance: {
    snapshot_id: number;
    source_name: string;
    retrieved_at: string;
  };
}

interface TrainStopResponse {
  stop_sequence: number;
  station_code: string;
  station_name: string;
  arrival_time: string | null;
  departure_time: string | null;
  source_day: number | null;
}

interface TrainRouteProfileResponse {
  train_number: string;
  timetable_snapshot_id: number;
  origin_station_code: string;
  destination_station_code: string;
  total_stops: number;
  total_duration_minutes: number | null;
  total_dwell_minutes: number | null;
  dwell_percentage: number | null;
}

async function getTrainData(train_number: string) {
  const fetchOptions = { next: { revalidate: 60 } };
  
  const [detailRes, routeRes, profileRes] = await Promise.all([
    fetch(`http://127.0.0.1:8000/api/v1/trains/${train_number}`, fetchOptions),
    fetch(`http://127.0.0.1:8000/api/v1/trains/${train_number}/route`, fetchOptions),
    fetch(`http://127.0.0.1:8000/api/v1/network/trains/${train_number}/profile`, fetchOptions)
  ]);

  if (!detailRes.ok) {
    if (detailRes.status === 404) return null;
    throw new Error("Unable to load train information. Please try again.");
  }

  if (!routeRes.ok || !profileRes.ok) {
    throw new Error("Unable to load train information. Please try again.");
  }

  const detail: TrainDetail = await detailRes.json();
  const route: TrainStopResponse[] = await routeRes.json();
  const profile: TrainRouteProfileResponse = await profileRes.json();

  return { detail, route, profile };
}

export default async function TrainPage({ params }: { params: { train_number: string } }) {
  const resolvedParams = await params;
  const trainData = await getTrainData(resolvedParams.train_number);
  
  if (!trainData) {
    notFound();
  }

  const { detail, route, profile } = trainData;

  const formatTime = (timeStr: string | null) => {
    if (!timeStr) return "—";
    return timeStr.slice(0, 5); // HH:MM
  };

  const formatDuration = (mins: number | null) => {
    if (mins === null) return "—";
    const h = Math.floor(mins / 60);
    const m = Math.round(mins % 60);
    return `${h}h ${m}m`;
  };

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

      <div className="w-full max-w-4xl overflow-hidden rounded-2xl border border-foreground/10 bg-card shadow-lg mb-8">
        {/* Header */}
        <div className="bg-foreground/[0.02] border-b border-foreground/10 px-8 py-10 flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
          <div>
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              <span className="rounded-md bg-blue-100 dark:bg-blue-900/40 px-3 py-1 text-sm font-bold tracking-widest text-blue-800 dark:text-blue-300">
                {detail.train_number}
              </span>
              {detail.type && (
                <span className="rounded-md bg-foreground/10 px-3 py-1 text-sm font-medium text-foreground/80">
                  {detail.type}
                </span>
              )}
              {detail.return_train_number && (
                <span className="text-sm font-medium text-foreground/60 flex items-center gap-1">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                  Return: {detail.return_train_number}
                </span>
              )}
            </div>
            <h1 className="text-4xl md:text-5xl font-extrabold text-foreground tracking-tight">
              {detail.name}
            </h1>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-yellow-500/30 bg-yellow-500/10 px-3 py-1 text-xs font-semibold text-yellow-700 dark:text-yellow-500">
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            Historical Timetable Profile
          </div>
        </div>

        {/* Profile Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-foreground/10">
          <div className="bg-card px-8 py-6 col-span-2 md:col-span-4 flex justify-between items-center">
             <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">Route</h3>
                <p className="text-xl font-bold text-foreground">
                  <Link href={`/stations/${profile.origin_station_code.toLowerCase()}`} className="text-blue-600 hover:underline">{profile.origin_station_code}</Link> 
                  <span className="mx-2 text-foreground/40">→</span> 
                  <Link href={`/stations/${profile.destination_station_code.toLowerCase()}`} className="text-blue-600 hover:underline">{profile.destination_station_code}</Link>
                </p>
             </div>
          </div>
          <div className="bg-card px-8 py-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">Total Stops</h3>
            <p className="text-2xl font-medium text-foreground">{profile.total_stops}</p>
          </div>
          <div className="bg-card px-8 py-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">Scheduled Duration</h3>
            <p className="text-2xl font-medium text-foreground font-mono">{formatDuration(profile.total_duration_minutes)}</p>
          </div>
          <div className="bg-card px-8 py-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">Scheduled Dwell</h3>
            <p className="text-2xl font-medium text-foreground font-mono">{formatDuration(profile.total_dwell_minutes)}</p>
          </div>
          <div className="bg-card px-8 py-6">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/50 mb-1">Dwell %</h3>
            <p className="text-2xl font-medium text-foreground font-mono">{profile.dwell_percentage ? `${profile.dwell_percentage.toFixed(1)}%` : "—"}</p>
          </div>
        </div>
      </div>

      <div className="w-full max-w-4xl">
        <h2 className="text-2xl font-bold text-foreground mb-6">Historical Timetable Route</h2>
        <div className="bg-card rounded-2xl border border-foreground/10 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="bg-foreground/[0.03] border-b border-foreground/10">
                <tr>
                  <th className="px-6 py-4 font-semibold text-foreground/60 w-16">#</th>
                  <th className="px-6 py-4 font-semibold text-foreground/60">Station</th>
                  <th className="px-6 py-4 font-semibold text-foreground/60 text-right">Arrival</th>
                  <th className="px-6 py-4 font-semibold text-foreground/60 text-right">Departure</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-foreground/5">
                {route.map((stop) => (
                  <tr key={stop.stop_sequence} className="hover:bg-foreground/[0.02] transition-colors">
                    <td className="px-6 py-4 text-foreground/50 font-mono">{stop.stop_sequence}</td>
                    <td className="px-6 py-4">
                      <div className="font-medium text-foreground">{stop.station_name}</div>
                      <Link href={`/stations/${stop.station_code.toLowerCase()}`} className="text-xs text-blue-600 hover:underline">
                        {stop.station_code}
                      </Link>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="font-mono text-foreground">{formatTime(stop.arrival_time)}</div>
                    </td>
                    <td className="px-6 py-4 text-right relative">
                      <div className="font-mono text-foreground">{formatTime(stop.departure_time)}</div>
                      {stop.source_day && stop.source_day > 0 ? (
                        <div className="absolute right-6 -bottom-1 text-[10px] font-bold text-blue-600 bg-blue-100 dark:bg-blue-900/40 px-1.5 rounded">
                          +{stop.source_day} day
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </main>
  );
}
