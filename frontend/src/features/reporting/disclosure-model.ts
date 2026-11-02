export type DisclosureRequestScope = {
  companyId: string;
  periodId: string;
  generation: number;
};

export function isCurrentDisclosureRequest(
  request: DisclosureRequestScope,
  current: DisclosureRequestScope,
): boolean {
  return request.companyId === current.companyId
    && request.periodId === current.periodId
    && request.generation === current.generation;
}
