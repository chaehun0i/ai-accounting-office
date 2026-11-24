export const setIssueLabels: Record<string, string> = {
  APPROVED_NOTES_REQUIRED: "현재 원천의 주석을 작성하고 독립 승인을 완료하세요.",
  EQUITY_APPROVAL_REQUIRED: "현재 자본변동표의 독립 승인을 완료하세요.",
  PERIOD_NOT_CLOSED: "선택한 기간을 먼저 마감하세요.",
  STATEMENT_SET_MISSING: "현재 마감 버전의 BS/IS를 생성하세요.",
  CASH_FLOW_SOURCE_REQUIRED: "현재 CF 스냅샷을 생성하세요.",
  EQUITY_SOURCE_REQUIRED: "현재 SCE 스냅샷을 생성하세요.",
  CASH_FLOW_SOURCE_STALE: "CF 원천이 변경됐습니다. 원천을 검토한 후 다시 생성하세요.",
  EQUITY_SOURCE_STALE: "SCE 원천이 변경됐습니다. 원천을 검토한 후 다시 생성하세요.",
  REPORT_SOURCE_STALE: "마감 원천이 변경됐습니다. 마감·제표를 다시 확인하세요.",
  PROFIT_TRANSFER_IS_MISMATCH: "물리적 손익마감 전표와 IS 표시 기준이 충돌합니다. 세트 승인으로 우회할 수 없습니다.",
};
export function setSourceCurrent(status: string | undefined, current: string | null | undefined, frozen: string): boolean {
  return status === "READY" && !!current && current === frozen;
}
