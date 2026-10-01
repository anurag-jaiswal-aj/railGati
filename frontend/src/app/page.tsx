"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { StationAutocomplete } from "@/components/StationAutocomplete";

export default function Home() {
  const router = useRouter();
  const [fromQuery, setFromQuery] = useState("");
  const [toQuery, setToQuery] = useState("");
  const [fromStation, setFromStation] = useState<string | null>(null);
  const [toStation, setToStation] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  const handleSearch = () => {
    setSearchError(null);
    if (!fromStation || !toStation) return;
    
    if (fromStation === toStation) {
      setSearchError("Origin and destination must be different stations.");
      return;
    }

    router.push(`/journeys?source=${fromStation}&destination=${toStation}`);
  };

  const handleFromChange = (station: string | null) => {
    setFromStation(station);
    setSearchError(null);
  };

  const handleToChange = (station: string | null) => {
    setToStation(station);
    setSearchError(null);
  };

  return (
    <main className="flex flex-1 flex-col items-center px-4 py-12 md:py-24">
      <div className="w-full max-w-4xl text-center mb-12">
        <h1 className="text-4xl font-extrabold tracking-tight sm:text-6xl text-foreground">
          Rail<span className="text-blue-600 dark:text-blue-500">Gati</span>
        </h1>
        <p className="mt-6 text-xl text-foreground/70">
          Intelligent Railway Discovery & Exploration
        </p>
      </div>

      <div className="w-full max-w-3xl rounded-2xl border border-foreground/10 bg-card p-6 shadow-xl dark:bg-card/50 backdrop-blur-sm">
        <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-4 items-end">
          <StationAutocomplete
            id="from-station"
            label="From"
            placeholder="Search departure station..."
            value={fromQuery}
            onChange={setFromQuery}
            onSelectStation={handleFromChange}
          />
          
          <div className="hidden md:flex h-12 w-12 items-center justify-center rounded-full bg-foreground/5 text-foreground/40 mb-1">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14" />
              <path d="m12 5 7 7-7 7" />
            </svg>
          </div>

          <StationAutocomplete
            id="to-station"
            label="To"
            placeholder="Search arrival station..."
            value={toQuery}
            onChange={setToQuery}
            onSelectStation={handleToChange}
          />
        </div>

        <div className="mt-8 flex flex-col items-center gap-4">
          {searchError && (
            <div
              role="alert"
              className="rounded-md border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-600 dark:text-red-400 flex items-center gap-2"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              {searchError}
            </div>
          )}
          <button
            onClick={handleSearch}
            disabled={!fromStation || !toStation}
            className="rounded-full bg-blue-600 px-8 py-3 font-semibold text-white transition-all hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-background flex items-center gap-2"
          >
            Search Trains
          </button>
        </div>
      </div>
      <div className="mt-8">
        <Link href="/network" className="text-blue-600 hover:underline font-medium text-sm flex items-center gap-1">
          Explore Network Discovery
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
        </Link>
      </div>
    </main>
  );
}
