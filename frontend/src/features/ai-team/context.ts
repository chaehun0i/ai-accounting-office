import type { Period } from "./model";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type ClosingAskContext = { kind: "closing"; periodId: string | null };

export const CLOSING_QUESTION = "이 기간의 월마감 준비 상태와 마감을 막는 항목을 알려줘.";

export function closingAskHref(periodId: string) {
  return `/ai-team?${new URLSearchParams({ period_id: periodId, context: "closing" })}`;
}

export function parseAskContext(params: Pick<URLSearchParams, "get" | "getAll">): ClosingAskContext | null {
  if (params.get("context") !== "closing" || params.getAll("context").length !== 1) return null;
  const values = params.getAll("period_id");
  return { kind: "closing", periodId: values.length === 1 && UUID.test(values[0]) ? values[0].toLowerCase() : null };
}

export function selectContextPeriod(periods: Period[], context: ClosingAskContext | null) {
  if (!context) return { periodId: periods[0]?.id ?? "", notice: "" };
  const found = periods.find(period => period.id.toLowerCase() === context.periodId);
  return {
    periodId: found?.id ?? periods[0]?.id ?? "",
    notice: !found && periods.length > 0
      ? "전달된 회계기간을 사용할 수 없어 현재 회사의 기간을 선택했습니다."
      : "",
  };
}
