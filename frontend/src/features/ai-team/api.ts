import { authenticatedRequest } from "@/features/auth/session";
import type { Period, QueryRun, QueryStep } from "./model";
import { queryRequest } from "./model";

export function listPeriods(companyId: string) {
  return authenticatedRequest<Period[]>("/closing/periods", { headers: { "X-Company-ID": companyId } });
}

export function askBookkeeper(companyId: string, periodId: string, question: string, key: string) {
  return authenticatedRequest<QueryRun>("/agent/queries/bookkeeper", queryRequest(companyId, periodId, question, key));
}

export function reviewPeriod(companyId: string, periodId: string, key: string) {
  return authenticatedRequest<QueryRun>("/agent/queries/accounting-team", {
    method: "POST",
    headers: { "X-Company-ID": companyId, "Idempotency-Key": key },
    body: JSON.stringify({ period_id: periodId }),
  });
}

export function getQuerySteps(companyId: string, runId: string) {
  return authenticatedRequest<QueryStep[]>(`/agent/runs/${runId}/steps`, { headers: { "X-Company-ID": companyId } });
}

export function getQueryRun(companyId: string, runId: string) {
  return authenticatedRequest<QueryRun>(`/agent/runs/${runId}`, { headers: { "X-Company-ID": companyId } });
}
