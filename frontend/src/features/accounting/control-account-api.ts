import { authenticatedRequest } from "@/features/auth/session";

export const roles = ["AR", "AP", "TAX_INPUT", "TAX_OUTPUT", "BANK_CASH", "CARD_CLEARING", "CARD_PAYABLE"] as const;
export type Role = typeof roles[number];
export const roleNames: Record<Role, string> = { AR: "매출채권", AP: "매입채무", TAX_INPUT: "매입 부가세", TAX_OUTPUT: "매출 부가세", BANK_CASH: "현금·예금", CARD_CLEARING: "카드 미수", CARD_PAYABLE: "카드 미지급" };
export type Mapping = { role: Role; account_id: string | null; version: number };
export type Impact = { digest: string; blocking: boolean; facts: { code: string; subject: string; count: number; blocking: boolean }[] };
export type ChangeRequest = { id: string; role: Role; current_account_id: string | null; target_account_id: string; impact_digest: string; status: string; requester_id: string; approver_id: string | null; version: number; created_at: string; executed_at: string | null };
export type ChangeEvent = { id: string; event_type: string; actor_id: string; occurred_at: string; before_account_id: string | null; after_account_id: string | null };
const base = "/control-account-roles";
const scoped = (companyId: string) => ({ "X-Company-ID": companyId });
export const controlApi = {
  mappings: (companyId: string) => authenticatedRequest<Mapping[]>(base, { headers: scoped(companyId) }),
  requests: (companyId: string) => authenticatedRequest<ChangeRequest[]>(`${base}/requests`, { headers: scoped(companyId) }),
  impact: (companyId: string, id: string) => authenticatedRequest<Impact>(`${base}/requests/${id}/impact`, { headers: scoped(companyId) }),
  events: (companyId: string, id: string) => authenticatedRequest<ChangeEvent[]>(`${base}/requests/${id}/events`, { headers: scoped(companyId) }),
  preview: (companyId: string, role: Role, accountId: string, mappingVersion: number, accountVersion: number) => authenticatedRequest<Impact>(`${base}/impact`, {
    method: "POST", headers: scoped(companyId),
    body: JSON.stringify({ role, target_account_id: accountId, expected_mapping_version: mappingVersion, expected_target_account_version: accountVersion }),
  }),
  create: (companyId: string, role: Role, accountId: string, mappingVersion: number, accountVersion: number) => authenticatedRequest<ChangeRequest>(`${base}/requests`, {
    method: "POST", headers: { ...scoped(companyId), "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ role, target_account_id: accountId, expected_mapping_version: mappingVersion, expected_target_account_version: accountVersion }),
  }),
  command: (companyId: string, request: ChangeRequest, action: "approve" | "reject" | "execute", reason: string, idempotencyKey?: string) => authenticatedRequest<ChangeRequest>(`${base}/requests/${request.id}/${action}`, {
    method: "POST", headers: { ...scoped(companyId), ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}) },
    body: JSON.stringify({ expected_version: request.version, reason }),
  }),
};
