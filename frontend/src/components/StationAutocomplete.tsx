"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { getClientApiUrl } from "@/lib/api";

interface Station {
  code: string;
  name: string;
  state: string | null;
  zone: string | null;
}

interface StationAutocompleteProps {
  id: string;
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  onSelectStation: (code: string) => void;
}

export function StationAutocomplete({
  id,
  label,
  placeholder,
  value,
  onChange,
  onSelectStation,
}: StationAutocompleteProps) {
  const [results, setResults] = useState<Station[]>([]);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    const fetchStations = async () => {
      if (!value.trim()) {
        setResults([]);
        return;
      }
      
      setLoading(true);
      setError(null);
      
      try {
        const baseUrl = getClientApiUrl();
        const res = await fetch(`${baseUrl}/api/v1/stations/search?q=${encodeURIComponent(value)}&size=5`);
        if (!res.ok) {
          throw new Error("Failed to search stations");
        }
        const data = await res.json();
        setResults(data.items || []);
        setIsOpen(true);
      } catch (err) {
        console.error(err);
        setError("Error loading stations");
      } finally {
        setLoading(false);
      }
    };

    const debounce = setTimeout(fetchStations, 300);
    return () => clearTimeout(debounce);
  }, [value]);

  return (
    <div className="relative w-full" ref={wrapperRef}>
      <label htmlFor={id} className="block text-sm font-medium text-foreground/80 mb-1">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type="text"
          className="w-full rounded-md border border-foreground/20 bg-background px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => {
            if (value && results.length > 0) setIsOpen(true);
          }}
          autoComplete="off"
        />
        {loading && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          </div>
        )}
      </div>

      {isOpen && (value.trim().length > 0) && (
        <div className="absolute z-10 mt-1 w-full rounded-md border border-foreground/10 bg-background py-1 shadow-lg max-h-60 overflow-auto">
          {error ? (
            <div className="px-4 py-2 text-sm text-red-500">{error}</div>
          ) : results.length === 0 && !loading ? (
            <div className="px-4 py-2 text-sm text-foreground/50">No stations found</div>
          ) : (
            <ul role="listbox">
              {results.map((station) => (
                <li
                  key={station.code}
                  className="cursor-pointer px-4 py-2 hover:bg-foreground/5 transition-colors group flex items-center justify-between"
                  onClick={() => {
                    onChange(station.name);
                    onSelectStation(station.code);
                    setIsOpen(false);
                  }}
                  role="option"
                  aria-selected="false"
                >
                  <div>
                    <span className="block font-medium text-foreground">{station.name}</span>
                    <span className="block text-xs text-foreground/60">{station.state || "Unknown State"} • {station.zone || "N/A"}</span>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className="rounded bg-blue-100 dark:bg-blue-900/30 px-1.5 py-0.5 text-xs font-semibold text-blue-800 dark:text-blue-300">
                      {station.code}
                    </span>
                    <Link
                      href={`/stations/${station.code.toLowerCase()}`}
                      className="text-xs text-blue-600 hover:underline opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => e.stopPropagation()}
                    >
                      Details
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
