import { money, units } from "../accounting/journal-model.ts";

export type Obligation = {
  id: string; counterparty_name: string; origin_date: string; due_date: string;
  original_amount: string; outstanding_amount: string; status: string; version: number;
  origin_journal_id: string; source_transaction_id: string | null; import_id: string | null;
  evidence_ids: string[];
};
export type Settlement = {
  id: string; journal_entry_id: string; settlement_date: string; total_amount: string;
  status: string; version: number; unapplied_amount: string;
  allocations: { target_id: string; allocated_amount: string; expected_version: number }[];
};
export const financeStatus: Record<string, string> = {
  OPEN: "미결제", PARTIAL: "일부 결제", SETTLED: "결제 완료", WRITEOFF: "상각",
  CANCELLED: "취소", DRAFT: "배분 작성 중", CONFIRMED: "배분 확정", UNAPPLIED: "미배분액 있음",
};
export function allocationSummary(total: string, amounts: string[]) {
  const allocated = amounts.reduce((sum, amount) => sum + units(amount || "0"), 0n);
  const unapplied = units(total) - allocated;
  return { allocated: money(allocated), unapplied: money(unapplied), valid: unapplied >= 0n };
}
export function collected(value: Obligation) {
  return money(units(value.original_amount) - units(value.outstanding_amount));
}
export function agingLabel(due: string, asOf: string) {
  const days = Math.floor((Date.parse(asOf) - Date.parse(due)) / 86400000);
  return days <= 0 ? "기한 전" : days <= 30 ? "1~30일 경과" : days <= 60 ? "31~60일 경과" : days <= 90 ? "61~90일 경과" : "90일 초과";
}
