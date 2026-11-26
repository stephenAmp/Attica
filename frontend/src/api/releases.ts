import { api } from "./client"
import type {ReleaseComparison, ReleaseFilters} from "../features/releases/types";
import { Endpoints } from "../constants/endpoints";

export async function compareReleases(tenantId: string, filters: ReleaseFilters, signal?: AbortSignal): Promise<ReleaseComparison> {
  const { data } = await api.get<ReleaseComparison>(
    Endpoints.releases.compare(tenantId),
    {
      params: filters,
      signal,
    },
  );

  return data;
}