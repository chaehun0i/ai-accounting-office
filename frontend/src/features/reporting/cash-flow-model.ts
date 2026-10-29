import type { Period, StatementSet } from "./model.ts";

export type CashIssue = { code: string; account_id?: string | null; journal_id?: string | null };
export type CashPreflight = {
  period_id: string; close_version: number; source_digest: string; mapping_digest: string;
  opening_cash: string; closing_cash: string; net_cash_movement: string;
  net_operating: string; net_investing: string; net_financing: string; exchange_effect: string;
  classified_journal_count: number; issues: CashIssue[]; ready: boolean;
};
export type CashBridge = {
  period_id: string; statement_set_id: string | null; close_version: number;
  source_digest: string; mapping_digest: string; policy_code: string; policy_version: number;
  net_profit: string | null; net_operating: string | null; direct_net_operating: string;
  reconciliation_difference: string | null; issues: CashIssue[]; status: string;
};
export type CashStatement = {
  id: string; period_id: string; statement_set_id: string; close_version: number;
  source_digest: string; mapping_digest: string; direct_mapping_digest: string; snapshot_digest: string;
  policy_code: string; policy_version: number; method: string; status: string;
  opening_cash: string; closing_cash: string; net_profit: string; net_operating: string;
  net_investing: string; net_financing: string; exchange_effect: string; generated_at: string;
};
export type CashPolicy = {
  id: string; effective_from: string; effective_to: string | null;
  version: number; status: "LATEST" | "SUPERSEDED";
  interest_paid: "OPERATING" | "FINANCING";
  interest_received: "OPERATING" | "INVESTING";
  income_tax_paid: "OPERATING" | "INVESTING" | "FINANCING";
};
export type NonCashDisclosure = {
  id: string; journal_id: string; debit_line_id: string; credit_line_id: string;
  evidence_id: string; source_type: string; amount: string; version: number;
};
export type DisposalSource = {
  id: string; journal_id: string; cash_line_id: string; asset_line_id: string;
  gain_line_id: string; evidence_id: string; proceeds: string; gain_amount: string; version: number;
};
export type CashLine = { id: string; line_code: string; amount: string; source_type: string; source_id: string | null; display_order: number };
type JournalSource = { journal_id: string; journal_line_id: string; entry_date: string; signed_debit_amount: string; is_opening: boolean };
export type CashDrilldown = {
  statement_id: string; lines: CashLine[];
  events: { id: string; journal_id: string; cash_line_id: string; cash_account_id: string; counterpart_line_id: string; counterpart_account_id: string; activity_type: string; line_code: string; cash_inflow: string; cash_outflow: string; classification_id: string; classification_version: number; evidence_id: string | null; allocation_id: string | null; allocation_version: number | null }[];
  adjustments: { id: string; rule_id: string; rule_version: number; account_id: string; adjustment_code: string; opening_balance: string; closing_balance: string; amount: string }[];
  adjustment_sources: (JournalSource & { adjustment_id: string })[];
  cash_balance_sources: (JournalSource & { scope_id: string; scope_version: number; account_id: string })[];
  journals: { journal_id: string; transaction_id: string | null; evidence_ids: string[] }[];
};

/** The server owns reconciliation. The client also binds generation to the visible close and BS/IS. */
export function cashGenerationPayload(period: Period | undefined, set: StatementSet | undefined, preflight: CashPreflight | null, bridge: CashBridge | null) {
  if (!period || period.status !== "CLOSED" || !set || !preflight || !bridge
    || set.period_id !== period.id || set.close_version !== period.close_version || set.status !== "GENERATED"
    || preflight.period_id !== period.id || bridge.period_id !== period.id
    || preflight.close_version !== period.close_version || bridge.close_version !== period.close_version
    || bridge.statement_set_id !== set.id || preflight.source_digest !== bridge.source_digest
    || set.trial_balance_digest !== bridge.source_digest || !bridge.mapping_digest || !bridge.source_digest
    || !preflight.ready || preflight.issues.length > 0 || bridge.status !== "READY" || bridge.issues.length > 0
    || bridge.net_profit === null || bridge.net_operating === null
    || bridge.reconciliation_difference === null || !/^-?0(?:\.0+)?$/.test(bridge.reconciliation_difference)) return null;
  return {
    period_id: period.id, statement_set_id: set.id, close_version: period.close_version,
    source_digest: bridge.source_digest, mapping_digest: bridge.mapping_digest,
  };
}

const issues: Record<string, string> = {
  CASH_SCOPE_MISSING: "현금·현금성자산 범위를 설정해 주세요.",
  CASH_SCOPE_NOT_FULL_PERIOD: "현금 범위가 선택 기간 전체에 적용되어야 합니다.",
  CASH_FLOW_UNCLASSIFIED: "현금 거래의 영업·투자·재무 활동 분류를 확인해 주세요.",
  CASH_FLOW_COMPLEX_JOURNAL: "복합 전표의 현금 배분과 증빙을 확인해 주세요.",
  CASH_FLOW_ALLOCATION_INVALID: "현금 배분 금액과 증빙 연결을 확인해 주세요.",
  CASH_FLOW_ALLOCATION_INCOMPLETE: "현금 거래 배분을 완료해 주세요.",
  CASH_FLOW_RECONCILIATION_MISMATCH: "현금 증감과 활동별 합계가 일치하지 않습니다.",
  CASH_FLOW_POLICY_SPLITS_PERIOD: "이자·세금 분류 정책이 기간 중에 바뀌었습니다. 적용일을 기간 경계로 맞춰 주세요.",
  CASH_FLOW_POLICY_MISMATCH: "이자·세금 현금 거래 분류가 회사 정책과 다릅니다.",
  CASH_FLOW_DISPOSAL_CLASSIFICATION: "처분대금 현금 유입을 투자활동 처분 항목으로 분류해 주세요.",
  INDIRECT_DISPOSAL_SOURCE_INVALID: "처분손익 전표·처분대금·증빙 원천을 확인해 주세요.",
  INDIRECT_RULE_MISSING: "사용 계정의 간접법 조정 규칙을 설정해 주세요.",
  INDIRECT_RULE_DUPLICATED: "중복된 간접법 조정 규칙을 확인해 주세요.",
  INDIRECT_RULE_NOT_FULL_PERIOD: "간접법 규칙이 기간 전체에 적용되어야 합니다.",
  INDIRECT_POLICY_UNSUPPORTED: "지원하는 간접법 정책과 버전을 확인해 주세요.",
  INDIRECT_SOURCE_UNSUPPORTED: "지원하지 않는 조정 원천이 있어 생성할 수 없습니다.",
  INDIRECT_RULE_ACCOUNT_INVALID: "조정 규칙과 계정 유형의 연결을 확인해 주세요.",
  INDIRECT_NONCASH_RELATION_UNSUPPORTED: "비현금 조정의 상대 계정 관계를 확인해 주세요.",
  INDIRECT_WORKING_CAPITAL_SOURCE_UNSUPPORTED: "운전자본 변동의 원천을 확인해 주세요.",
  INDIRECT_DIRECT_POLICY_MISMATCH: "현금 활동 분류와 간접법 정책을 맞춰 주세요.",
  INDIRECT_STATEMENT_SOURCE_MISSING: "현재 마감 기준의 BS/IS를 먼저 생성해 주세요.",
  INDIRECT_STATEMENT_SOURCE_STALE: "BS/IS 원천이 변경되었습니다. BS/IS를 다시 생성해 주세요.",
  INDIRECT_OPERATING_RECONCILIATION_MISMATCH: "간접법 영업현금흐름과 현금 거래 합계의 차이를 확인해 주세요.",
};
export function cashIssueLabel(code: string) { return issues[code] ?? "사전 점검에서 차단 항목이 발견되었습니다. 담당자에게 코드를 전달해 주세요."; }
const lines: Record<string, string> = {
  OPENING_CASH: "기초 현금 및 현금성자산", CLOSING_CASH: "기말 현금 및 현금성자산",
  NET_PROFIT: "당기순이익", NET_OPERATING: "영업활동 현금흐름", NET_INVESTING: "투자활동 현금흐름",
  NET_FINANCING: "재무활동 현금흐름", EXCHANGE_EFFECT: "환율 변동 효과", NET_CASH_MOVEMENT: "현금 순증감",
  NONCASH_PAIR: "비현금 조정", WORKING_CAPITAL: "운전자본 조정",
  DISPOSAL_GAIN: "처분손익 조정",
};
export function cashLineLabel(code: string) { return lines[code] ?? code; }
