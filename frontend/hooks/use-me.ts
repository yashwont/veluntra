"use client";

import { useQuery } from "@tanstack/react-query";

import { getMe } from "@/services/auth";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: getMe, staleTime: 5 * 60_000 });
}
