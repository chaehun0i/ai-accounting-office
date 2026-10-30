export type EquityComponent = {
  id: string; component_code: string; name: string;
  component_type: string; status: string; display_order: number; version: number;
};
export type EquityMapping = {
  id: string; component_id: string; account_id: string;
  effective_from: string; effective_to: string | null; status: string; version: number;
};
export type EquityEvent = {
  id: string; component_id: string; event_date: string; event_type: string;
  amount: string; source_journal_id: string; source_journal_line_id: string; status: string;
};
export type DividendDeclaration = {
  id: string; resolution_date: string; payable_date: string | null;
  total_amount: string; status: string; source_journal_id: string | null;
};
export type DividendPayment = {
  id: string; declaration_id: string; cash_flow_event_id: string;
  journal_id: string; payment_date: string; amount: string;
};
export type EquityReadiness = {
  period_id: string; status: "READY" | "BLOCKED"; issues: string[];
  balance_sheet_equity: string | null; income_statement_profit: string | null;
  rollforward_equity: string | null; source_digest: string | null;
};
export type EquityLine = {
  id: string; component_id: string; movement_type: string;
  amount: string; display_order: number;
};
export type EquitySnapshot = {
  id: string; company_id: string; period_id: string; statement_set_id: string;
  close_version: number; snapshot_digest: string; status: "RECONCILED";
  balance_sheet_digest: string; income_statement_digest: string;
  generated_at: string; lines: EquityLine[];
};
export type EquitySource = {
  journal_id: string | null; journal_line_id: string | null;
  journal_no: string | null; entry_date: string | null;
  account_code: string | null; account_name: string | null;
  evidence_ids: string[]; income_statement_id: string | null; amount: string;
};

export const equityMovements = [
  ["OPENING", "기초자본"],
  ["OWNER_TRANSACTIONS", "소유주 거래"],
  ["PROFIT_OR_LOSS", "당기손익"],
  ["OTHER_COMPREHENSIVE_INCOME", "기타포괄손익"],
  ["OTHER_ADJUSTMENTS", "기타 조정"],
  ["CLOSING", "기말자본"],
] as const;

export const equityIssueLabels: Record<string, string> = {
  BS_IS_SNAPSHOT_MISSING: "현재 CLOSED 기간의 BS/IS 스냅샷을 먼저 생성해 주세요.",
  EQUITY_COMPONENT_MISSING: "자본 구성요소를 등록해 주세요.",
  RETAINED_EARNINGS_COMPONENT_REQUIRED: "이익잉여금 구성요소를 정확히 하나 등록해 주세요.",
  EQUITY_MAPPING_INCOMPLETE: "사용된 자본 계정의 구성요소 연결이 누락됐습니다.",
  DUPLICATE_EQUITY_MAPPING: "동일 계정에 중복된 구성요소 연결이 있습니다.",
  INACTIVE_EQUITY_COMPONENT: "비활성 구성요소에 연결된 계정을 확인해 주세요.",
  UNCLASSIFIED_EQUITY_SOURCE: "POSTED 자본변동 전표 라인을 분류해 주세요.",
  OPENING_EQUITY_UNVERIFIED: "Opening 전표 또는 전기 BS로 기초자본을 검증해 주세요.",
  PRIOR_EQUITY_SNAPSHOT_MISSING: "직전 CLOSED 기간의 BS 스냅샷이 필요합니다.",
  PRIOR_EQUITY_MISMATCH: "기초자본과 직전 BS 기말자본이 다릅니다.",
  EQUITY_ROLLFORWARD_MISMATCH: "구성요소 기말합계와 BS 자본총계가 다릅니다.",
  DIVIDEND_CF_SOURCE_MISMATCH: "실제 배당지급과 CF 재무활동 원천이 일치하지 않습니다.",
};

export function equityCell(snapshot: EquitySnapshot, componentId: string, movement: string): EquityLine | undefined {
  return snapshot.lines.find(line => line.component_id === componentId && line.movement_type === movement);
}
