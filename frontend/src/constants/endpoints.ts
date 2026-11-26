export const Endpoints = {
  releases: {
    urlPath: "/tenants/:tenantId/releases",
    compare: (tenantId: string) => `/tenants/${tenantId}/releases/compare`,
  },

  traces: {
    list: (tenantId: string) => `/tenants/${tenantId}/traces`,
    detail: (tenantId: string, traceId: string) =>`/tenants/${tenantId}/traces/${traceId}`,
  },
} as const;