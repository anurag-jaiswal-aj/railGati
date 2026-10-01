"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="flex flex-1 flex-col items-center justify-center px-4 py-12 md:py-24">
      <div className="w-full max-w-md rounded-2xl border border-foreground/10 bg-card p-8 text-center shadow-lg">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/20 text-red-600">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <h2 className="mb-2 text-xl font-bold text-foreground">
          Unable to load train information
        </h2>
        <p className="mb-8 text-foreground/70">
          We encountered an unexpected problem while fetching the historical timetable data for this train.
        </p>
        <div className="flex flex-col gap-3">
          <button
            onClick={() => reset()}
            className="w-full rounded-full bg-blue-600 px-6 py-3 font-semibold text-white transition hover:bg-blue-700"
          >
            Try again
          </button>
          <Link
            href="/"
            className="w-full rounded-full border border-foreground/20 px-6 py-3 font-semibold text-foreground transition hover:bg-foreground/5"
          >
            Back to Search
          </Link>
        </div>
      </div>
    </main>
  );
}
