"use client";

import { useState } from "react";
import { StationAutocomplete } from "@/components/StationAutocomplete";

export default function Home() {
  const [fromQuery, setFromQuery] = useState("");
  const [toQuery, setToQuery] = useState("");
  const [fromStation, setFromStation] = useState<string | null>(null);
  const [toStation, setToStation] = useState<string | null>(null);

  const [searchState, setSearchState] = useState<"idle" | "loading" | "empty">("idle");
  const [emptyMessage, setEmptyMessage] = useState("");

  const handleSearch = async () => {
    if (!fromStation || !toStation) return;
    
    setSearchState("loading");
    try {
      const res = await fetch(`http://localhost:8000/api/v1/trains/between?source=${fromStation}&destination=${toStation}`);
      if (res.status === 501) {
        const data = await res.json();
        setEmptyMessage(data.message);
        setSearchState("empty");
      } else {
        // Fallback for unexpected status
        setSearchState("empty");
        setEmptyMessage("Train search is currently unavailable.");
      }
    } catch {
      setSearchState("empty");
      setEmptyMessage("Failed to connect to the server.");
    }
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
            onSelectStation={setFromStation}
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
            onSelectStation={setToStation}
          />
        </div>

        <div className="mt-8 flex justify-center">
          <button
            onClick={handleSearch}
            disabled={!fromStation || !toStation || searchState === "loading"}
            className="rounded-full bg-blue-600 px-8 py-3 font-semibold text-white transition-all hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-background flex items-center gap-2"
          >
            {searchState === "loading" ? (
              <>
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Searching...
              </>
            ) : (
              "Search Trains"
            )}
          </button>
        </div>
      </div>

      {searchState === "empty" && (
        <div className="mt-12 w-full max-w-3xl rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-8 text-center animate-in fade-in slide-in-from-bottom-4">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-yellow-500/10 text-yellow-600">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-foreground mb-2">Train Discovery Unavailable</h3>
          <p className="text-foreground/70 max-w-lg mx-auto leading-relaxed">
            {emptyMessage}
          </p>
        </div>
      )}
    </main>
  );
}
