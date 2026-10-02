"use client";

import { useEffect, useState } from "react";

/** Current time in ms, refreshed every minute so "overdue" labels stay accurate. */
export function useNow(intervalMs = 60_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
