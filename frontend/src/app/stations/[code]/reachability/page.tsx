"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getClientApiUrl } from "@/lib/api";

interface StationDetail {
  id: number;
  code: string;
  name: string;
}

interface NetworkReachabilityItem {
  station_code: string;
  station_name: string | null;
  min_hops: number;
}

interface NetworkReachabilityResponse {
  origin: string;
  timetable_snapshot_id: number;
  max_hops: number;
  total: number;
  stations: NetworkReachabilityItem[];
}

export default function ReachabilityPage() {
  const params = useParams();
  const router = useRouter();
  const code = typeof params.code === 'string' ? params.code.toUpperCase() : '';

  const [station, setStation] = useState<StationDetail | null>(null);
  const [stationError, setStationError] = useState<string | null>(null);

  const [depth, setDepth] = useState<number>(3);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<NetworkReachabilityResponse | null>(null);

  useEffect(() => {
    if (!code) return;

    const controller = new AbortController();
    const signal = controller.signal;

    const fetchStation = async () => {
      try {
        const baseUrl = getClientApiUrl();
        const res = await fetch(`${baseUrl}/api/v1/stations/${code}`, { signal });
        if (!res.ok) {
          if (res.status === 404) {
            setStationError(`Origin station '${code}' not found.`);
            return;
          }
          throw new Error("Unable to load station details.");
        }
        const data = await res.json();
        setStation(data);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        setStationError("Unable to load station details.");
      }
    };
    fetchStation();

    return () => {
      controller.abort();
    };
  }, [code]);

  useEffect(() => {
    if (!code || stationError) return;

    const controller = new AbortController();
    const signal = controller.signal;

    const fetchReachability = async () => {
      setLoading(true);
      setError(null);

      try {
        const baseUrl = getClientApiUrl();
        // Request up to 100 results for the frontend view
        const res = await fetch(`${baseUrl}/api/v1/network/stations/${code}/reachable-destinations?max_hops=${depth}&max_results=100`, { signal });

        if (!res.ok) {
          if (res.status === 404 || res.status === 400 || res.status === 422) {
            const errData = await res.json();
            throw new Error(errData.detail || "Unable to load historical network reachability. Please try again.");
          }
          throw new Error("Unable to load historical network reachability. Please try again.");
        }

        const jsonData = await res.json();
        setData(jsonData);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        if (err instanceof Error) {
          setError(err.message || "Unable to load historical network reachability. Please try again.");
        } else {
          setError("Unable to load historical network reachability. Please try again.");
        }
      } finally {
        if (!signal.aborted) {
          setLoading(false);
        }
      }
    };

    fetchReachability();

    return () => {
      controller.abort();
    };
  }, [code, depth, stationError]);

  if (stationError) {
    return (
      <main className="flex flex-1 flex-col items-center px-4 py-12">
        <div className="w-full max-w-4xl text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Station Not Found</h2>
          <p className="text-foreground/70 mb-8">{stationError}</p>
          <button onClick={() => router.push("/")} className="rounded-full bg-blue-600 px-6 py-2 text-white font-semibold hover:bg-blue-700 transition">
            Back to Search
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="flex flex-1 flex-col items-center px-4 py-8">
      <div className="w-full max-w-4xl mb-6">
        <Link href={`/stations/${code.toLowerCase()}`} className="text-sm font-medium text-blue-600 hover:underline flex items-center gap-1 w-fit mb-4">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m15 18-6-6 6-6"/>
          </svg>
          Back to Station Intelligence
        </Link>
        <h1 className="text-3xl font-extrabold text-foreground tracking-tight">
          Historical Network Reachability
        </h1>
        {station && (
          <p className="text-lg font-semibold text-foreground/80 mt-2">
            From {station.name} ({station.code})
          </p>
        )}
        <p className="text-sm text-foreground/60 mt-1">
          Explore stations connected to this origin through the historical railway topology. Results represent structural graph connectivity, not active passenger journeys or transfer viability.
        </p>
      </div>

      {/* Historical Disclaimer */}
      <div className="w-full max-w-4xl mb-8 p-4 rounded-xl border border-yellow-500/30 bg-yellow-500/10 text-yellow-800 dark:text-yellow-400 text-sm flex items-start gap-3">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 mt-0.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        <p>
          RailGati uses a historical timetable dataset for this view. Scheduled service counts and network relationships are not live railway status.
        </p>
      </div>

      <div className="w-full max-w-4xl flex flex-col md:flex-row gap-6 mb-8 items-start md:items-center">
        <div>
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-semibold text-foreground/80">
              Topology Depth (Hops)
            </legend>
            <div className="flex bg-foreground/5 p-1 rounded-lg w-fit">
              {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((val) => (
                <label
                  key={val}
                  className={`cursor-pointer px-3 py-1.5 text-sm font-semibold rounded-md transition focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-1 focus-within:ring-offset-background ${depth === val ? "bg-card shadow text-foreground" : "text-foreground/60 hover:text-foreground"}`}
                >
                  <input
                    type="radio"
                    name="topology-depth"
                    value={val}
                    checked={depth === val}
                    onChange={() => setDepth(val)}
                    className="sr-only"
                  />
                  {val}
                </label>
              ))}
            </div>
          </fieldset>
        </div>
      </div>

      <div className="w-full max-w-4xl">
        {error ? (
          <div role="alert" className="rounded-md border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-600 dark:text-red-400 flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <span>{error}</span>
            </div>
            <button onClick={() => setDepth(depth)} className="self-start text-xs font-semibold underline mt-1">
              Retry
            </button>
          </div>
        ) : loading ? (
          <div className="bg-card rounded-2xl border border-foreground/10 overflow-hidden shadow-sm animate-pulse h-64 flex items-center justify-center">
            <span className="text-foreground/50">Loading topology...</span>
          </div>
        ) : data && data.stations.length === 0 ? (
          <div className="bg-card rounded-2xl border border-foreground/10 overflow-hidden shadow-sm px-6 py-12 text-center">
            <p className="text-foreground/50 text-lg mb-4">No topologically reachable stations found within this depth.</p>
            {depth < 10 && (
              <button onClick={() => setDepth(d => Math.min(10, d + 1))} className="text-blue-600 hover:underline font-medium">
                Try expanding topology depth
              </button>
            )}
          </div>
        ) : data ? (
          <div className="bg-card rounded-2xl border border-foreground/10 overflow-hidden shadow-sm">
            <div className="px-6 py-4 border-b border-foreground/10 bg-foreground/[0.02] flex justify-between items-center">
              <h2 className="text-sm font-semibold text-foreground/80">
                Topologically Reachable Stations
              </h2>
              <span className="text-xs text-foreground/50 font-mono">
                {data.total >= 100 ? "Showing up to 100 reachable stations" : `${data.total} results`}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm whitespace-nowrap">
                <thead className="bg-foreground/[0.03] border-b border-foreground/10">
                  <tr>
                    <th className="px-6 py-4 font-semibold text-foreground/60">Station Name</th>
                    <th className="px-6 py-4 font-semibold text-foreground/60">Station Code</th>
                    <th className="px-6 py-4 font-semibold text-foreground/60 text-right">Minimum Hops</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-foreground/5">
                  {data.stations.map((st) => (
                    <tr key={st.station_code} className="hover:bg-foreground/[0.02] transition-colors">
                      <td className="px-6 py-4 font-medium text-foreground">
                        <Link href={`/stations/${st.station_code.toLowerCase()}`} className="text-blue-600 hover:underline">
                          {st.station_name || "Unknown Name"}
                        </Link>
                      </td>
                      <td className="px-6 py-4 font-mono text-foreground/80">
                        {st.station_code}
                      </td>
                      <td className="px-6 py-4 text-right font-mono text-foreground/80">
                        {st.min_hops}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>
    </main>
  );
}
