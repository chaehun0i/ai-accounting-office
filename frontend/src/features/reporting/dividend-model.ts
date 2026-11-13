export type DividendSource = {
  journal_id: string; journal_no: string | null; entry_date: string;
  description: string; amount: string; approval_id: string; evidence_ids: string[];
  status: "AVAILABLE" | "LINKED";
};
export type PaymentSources = {
  declaration_id: string; period_id: string; paid_amount: string; remaining_amount: string;
  statement_id: string | null; source_digest: string | null; issue: string | null;
  candidates: { event_id: string; journal_id: string; journal_no: string | null;
    entry_date: string; amount: string; evidence_id: string | null;
    status: "AVAILABLE" | "BLOCKED"; issue: string | null }[];
};
export const dividendIssues: Record<string, string> = {
  PERIOD_NOT_CLOSED: "지급기간을 마감한 뒤 CF를 생성해 주세요.",
  CF_SNAPSHOT_MISSING: "선택한 지급기간의 CF 스냅샷을 먼저 생성해 주세요.",
  DECLARATION_NOT_APPROVED: "승인된 결의 전표가 필요합니다.",
  PAYMENT_ALREADY_LINKED: "이미 연결된 지급 원천입니다.",
  PAYMENT_SOURCE_INVALID: "배당 지급으로 검증된 CF 재무활동 원천이 아닙니다.",
  PAYMENT_SOURCE_STALE: "CF 원천이 변경되었습니다. 현재 원천으로 다시 생성해 주세요.",
  PAYMENT_DATE_OR_LINE_INVALID: "결의일·지급일 또는 상대 분개가 일치하지 않습니다.",
  PAYMENT_ACCOUNT_MISMATCH: "결의 전표의 미지급 계정과 지급 상대 계정이 다릅니다.",
  PAYMENT_EXCEEDS_DECLARATION: "결의 잔액을 초과합니다. 원천을 검토해 주세요.",
};
export function canLinkPayment(sources: PaymentSources | null, eventId: string): boolean {
  return !!sources && !sources.issue && sources.candidates.some(
    item => item.event_id === eventId && item.status === "AVAILABLE" && !item.issue,
  );
}
