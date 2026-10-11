import { authenticatedRequest } from "@/features/auth/session";
import type { Dimension, DimensionValue, DimensionGroup } from "./dimension-model";

export async function loadDimensionGroups(companyId: string): Promise<DimensionGroup[]> {
  const headers = { "X-Company-ID": companyId };
  const dimensions = await authenticatedRequest<Dimension[]>("/accounting/dimensions", { headers });
  return Promise.all(dimensions.map(async d => ({ ...d, values: await authenticatedRequest<DimensionValue[]>(`/accounting/dimensions/${d.id}/values`, { headers }) })));
}

