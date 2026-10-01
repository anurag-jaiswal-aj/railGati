"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";

interface JourneyLeg {
  train_number: string;
  train_name: string;
  train_type: string | null;
  origin_station: string;
  destination_station: string;
  departure_time: string | null;
  arrival_time: string | null;
  source_day_offset: number | null;
  duration_minutes: number | null;
}

interface JourneyOption {
  journey_id: string;
  type: "DIRECT" | "ONE_TRANSFER";
  legs: JourneyLeg[];
  total_duration_minutes: number | null;
  timing_confidence: "HIGH" | "MISSING_DATA";
  number_of_stops: number;
  transfer_station: string | null;
  layover_minutes: number | null;
}

interface JourneyCompareResponse {
  source: string;
  destination: string;
  timetable_snapshot_id: number;
  max_transfers: number;
  journeys: JourneyOption[];
}

function JourneysContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  
  const source = searchParams.get("source");
  const destination = searchParams.get("destination");

  const [maxTransfers, setMaxTransfers] = useState<0 | 1>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<JourneyCompareResponse | null>(null);

  useEffect(() => {
    if (!source || !destination) {
      return;
    }

    const fetchJourneys = async () => {
      setLoading(true);
      setError(null);
      
      try {
        const res = await fetch(`http://127.0.0.1:8000/api/v1/journeys/compare?source=${source}&destination=${destination}&max_transfers=${maxTransfers}`);
        
        if (!res.ok) {
          if (res.status === 400 || res.status === 404 || res.status === 422) {
            const errData = await res.json();
            throw new Error(errData.detail || "One or both stations could not be found.");
          }
          throw new Error("Unable to load journey results. Please try again.");
        }
        
        const jsonData = await res.json();
        setData(jsonData);
      } catch (err: unknown) {
        if (err instanceof Error) {
          setError(err.message || "Unable to load journey results. Please try again.");
        } else {
          setError("Unable to load journey results. Please try again.");
        }
      } finally {
        setLoading(false);
      }
    };

    fetchJourneys();
  }, [source, destination, maxTransfers]);

  if (!source || !destination) {
    return (
      <main className="flex flex-1 flex-col items-center px-4 py-12">
        <div className="w-full max-w-4xl text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Incomplete Search</h2>
          <p className="text-foreground/70 mb-8">Please provide both an origin and destination station.</p>
          <button onClick={() => router.push("/")} className="rounded-full bg-blue-600 px-6 py-2 text-white font-semibold hover:bg-blue-700 transition">
            Back to Search
          </button>
        </div>
      </main>
    );
  }

  const formatTime = (timeStr: string | null) => {
    if (!timeStr) return "--:--";
    return timeStr.slice(0, 5); // Assuming HH:MM:SS
  };

  const formatDuration = (mins: number | null) => {
    if (mins === null) return "--";
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return `${h}h ${m}m`;
  };

  const renderLeg = (leg: JourneyLeg) => (
    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center py-3">
      <div className="flex-1">
        <div className="font-bold text-lg text-foreground">
          {leg.train_name} <span className="text-foreground/50 text-sm font-normal">({leg.train_number})</span>
        </div>
        <div className="text-sm text-foreground/70">
          Type: {leg.train_type || "N/A"}
        </div>
      </div>
      <div className="flex flex-1 items-center justify-between sm:justify-end gap-6 w-full sm:w-auto mt-3 sm:mt-0">
        <div className="text-center">
          <div className="font-bold text-lg text-foreground">{formatTime(leg.departure_time)}</div>
          <div className="text-xs text-foreground/50">{leg.origin_station}</div>
        </div>
        <div className="flex flex-col items-center px-4">
          <div className="text-xs text-foreground/50 mb-1">{formatDuration(leg.duration_minutes)}</div>
          <div className="h-px w-16 sm:w-24 bg-foreground/20 relative">
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-blue-500"></div>
          </div>
        </div>
        <div className="text-center">
          <div className="font-bold text-lg text-foreground">
            {formatTime(leg.arrival_time)}
            {leg.source_day_offset ? <span className="text-xs text-blue-600 ml-1">+{leg.source_day_offset} day</span> : null}
          </div>
          <div className="text-xs text-foreground/50">{leg.destination_station}</div>
        </div>
      </div>
    </div>
  );

  const directJourneys = data?.journeys.filter(j => j.type === "DIRECT") || [];
  const transferJourneys = data?.journeys.filter(j => j.type === "ONE_TRANSFER") || [];

  return (
    <main className="flex flex-1 flex-col items-center px-4 py-8">
      <div className="w-full max-w-4xl mb-6 flex flex-col sm:flex-row justify-between items-start sm:items-end gap-4">
        <div>
          <button onClick={() => router.push("/")} className="text-sm font-medium text-blue-600 hover:underline flex items-center gap-1 w-fit mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="m15 18-6-6 6-6"/>
            </svg>
            Back to Search
          </button>
          <h1 className="text-3xl font-extrabold text-foreground tracking-tight">
            {source} → {destination}
          </h1>
          <p className="text-sm text-foreground/60 mt-1">
            Historical timetable data — results represent scheduled routes in the available timetable snapshot.
          </p>
        </div>
        <div className="flex bg-foreground/5 p-1 rounded-lg">
          <button
            onClick={() => setMaxTransfers(0)}
            className={`px-4 py-1.5 text-sm font-semibold rounded-md transition ${maxTransfers === 0 ? "bg-card shadow text-foreground" : "text-foreground/60 hover:text-foreground"}`}
          >
            Direct
          </button>
          <button
            onClick={() => setMaxTransfers(1)}
            className={`px-4 py-1.5 text-sm font-semibold rounded-md transition ${maxTransfers === 1 ? "bg-card shadow text-foreground" : "text-foreground/60 hover:text-foreground"}`}
          >
            1 Transfer
          </button>
        </div>
      </div>

      <div className="w-full max-w-4xl">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-foreground/10 border-t-blue-600 mb-4" />
            <p className="text-foreground/60">Searching historical timetable...</p>
          </div>
        ) : error ? (
          <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-8 text-center">
            <h3 className="text-lg font-semibold text-red-600 mb-2">Search Failed</h3>
            <p className="text-foreground/70">{error}</p>
          </div>
        ) : data?.journeys.length === 0 ? (
          <div className="rounded-xl border border-foreground/10 bg-card p-8 text-center shadow-sm">
            <h3 className="text-lg font-semibold text-foreground mb-2">No Routes Found</h3>
            <p className="text-foreground/70">No historical timetable journeys found for this station pair.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {maxTransfers === 0 && directJourneys.length === 0 && (
              <div className="rounded-xl border border-foreground/10 bg-card p-8 text-center shadow-sm">
                <p className="text-foreground/70">No direct historical timetable journeys found. Try enabling 1 Transfer.</p>
              </div>
            )}
            
            {maxTransfers === 0 && directJourneys.map(journey => (
              <div key={journey.journey_id} className="rounded-2xl border border-foreground/10 bg-card p-6 shadow-sm">
                {renderLeg(journey.legs[0])}
                <div className="mt-4 pt-4 border-t border-foreground/10 flex justify-between text-xs text-foreground/50">
                  <span>Total Duration: {formatDuration(journey.total_duration_minutes)}</span>
                  <span>{journey.number_of_stops} stops</span>
                  {journey.timing_confidence === "MISSING_DATA" && <span className="text-yellow-600">Timing Missing Data</span>}
                </div>
              </div>
            ))}

            {maxTransfers === 1 && transferJourneys.length === 0 && directJourneys.length === 0 && (
              <div className="rounded-xl border border-foreground/10 bg-card p-8 text-center shadow-sm">
                <p className="text-foreground/70">No historical timetable journeys found for this station pair.</p>
              </div>
            )}

            {maxTransfers === 1 && transferJourneys.map(journey => (
              <div key={journey.journey_id} className="rounded-2xl border border-foreground/10 bg-card p-6 shadow-sm">
                <div className="flex flex-col gap-2">
                  {renderLeg(journey.legs[0])}
                  
                  <div className="flex items-center gap-4 my-2 opacity-80">
                    <div className="h-px flex-1 bg-dashed bg-foreground/20"></div>
                    <div className="text-xs font-semibold text-foreground/60 px-3 py-1 rounded-full bg-foreground/5 flex items-center gap-2">
                      <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"/><path d="m15 9 6-6"/></svg>
                      Transfer at {journey.transfer_station} (Wait: {formatDuration(journey.layover_minutes)})
                    </div>
                    <div className="h-px flex-1 bg-dashed bg-foreground/20"></div>
                  </div>

                  {renderLeg(journey.legs[1])}
                </div>
                
                <div className="mt-4 pt-4 border-t border-foreground/10 flex justify-between text-xs text-foreground/50">
                  <span>Total Duration: {formatDuration(journey.total_duration_minutes)}</span>
                  <span>{journey.number_of_stops} total stops</span>
                  {journey.timing_confidence === "MISSING_DATA" && <span className="text-yellow-600">Timing Missing Data</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

export default function JourneysPage() {
  return (
    <Suspense fallback={
      <main className="flex flex-1 flex-col items-center justify-center px-4 py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-foreground/10 border-t-blue-600 mb-4" />
        <p className="text-foreground/60">Loading...</p>
      </main>
    }>
      <JourneysContent />
    </Suspense>
  );
}
