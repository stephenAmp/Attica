import { useQuery } from "@tanstack/react-query";
import { compareReleases } from "../../api/releases";
import type { ReleaseFilters } from "./types";

export function useReleaseComparison(
  tenantId: string,
  filters: ReleaseFilters,
) {
  const valid = Boolean(tenantId) && Object.values(filters).every(Boolean) && filters.baseline_release !== filters.candidate_release && Date.parse(filters.start_time) < Date.parse(filters.end_time);

  return useQuery({
    queryKey: ["release-comparison", tenantId, filters],
    queryFn: ({ signal }) => compareReleases(tenantId, filters, signal),
    enabled: valid,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}