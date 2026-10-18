import type { Period } from "./model";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type ClosingAskContext = { kind: "closing"; periodId: string | null };
export type FinancialStatementType = "BALANCE_SHEET" | "INCOME_STATEMENT";
export type FinancialStatementAskContext = {
  kind: "financial_statement";
  periodId: string | null;
  statementType: FinancialStatementType;
  lineCode: string;
  lineLabel: string;
};
export type AskContext = ClosingAskContext | FinancialStatementAskContext;

const REPORT_LINES: Record<FinancialStatementType, Record<string, string>> = {
  BALANCE_SHEET: {
    ASSETS: "자산총계", ASSET_ACCOUNTS: "자산", LIABILITIES: "부채총계",
    LIABILITY_ACCOUNTS: "부채", EQUITY: "자본총계", EQUITY_ACCOUNTS: "자본",
    UNTRANSFERRED_PROFIT: "미대체 누적손익", LIABILITIES_EQUITY: "부채와 자본총계",
  },
  INCOME_STATEMENT: {
    REVENUE: "매출액", COGS: "매출원가", GROSS_PROFIT: "매출총이익",
    OPERATING_EXPENSE: "영업비용", OPERATING_PROFIT: "영업이익",
    NON_OPERATING_INCOME: "영업외수익", NON_OPERATING_EXPENSE: "영업외비용",
    PROFIT_BEFORE_TAX: "법인세차감전이익", TAX_EXPENSE: "법인세비용", NET_PROFIT: "당기순이익",
  },
};

export const CLOSING_QUESTION = "이 기간의 월마감 준비 상태와 마감을 막는 항목을 알려줘.";

export function closingAskHref(periodId: string) {
  return `/ai-team?${new URLSearchParams({ period_id: periodId, context: "closing" })}`;
}

export function financialStatementAskHref(periodId: string, statementType: FinancialStatementType, lineCode: string) {
  return `/ai-team?${new URLSearchParams({
    period_id: periodId, context: "financial_statement", statement_type: statementType, line_code: lineCode,
  })}`;
}

export function questionDraft(context: AskContext | null) {
  if (!context) return "";
  if (context.kind === "closing") return CLOSING_QUESTION;
  const statement = context.statementType === "BALANCE_SHEET" ? "재무상태표" : "손익계산서";
  return `이 기간 ${statement}의 ${context.lineLabel} (${context.lineCode}) 항목 금액과 연결 계정을 설명해줘.`;
}

export function askContextKey(companyId: string, context: AskContext | null) {
  if (!context) return `${companyId}:global`;
  if (context.kind === "closing") return `${companyId}:closing:${context.periodId ?? "invalid"}`;
  return `${companyId}:financial_statement:${context.periodId ?? "invalid"}:${context.statementType}:${context.lineCode}`;
}

export function parseAskContext(params: Pick<URLSearchParams, "get" | "getAll">): AskContext | null {
  const kinds = params.getAll("context");
  if (kinds.length !== 1) return null;
  const values = params.getAll("period_id");
  const periodId = values.length === 1 && UUID.test(values[0]) ? values[0].toLowerCase() : null;
  if (kinds[0] === "closing") return { kind: "closing", periodId };
  if (kinds[0] !== "financial_statement") return null;
  const types = params.getAll("statement_type");
  const codes = params.getAll("line_code");
  if (types.length !== 1 || codes.length !== 1) return null;
  const statementType = types[0];
  if (statementType !== "BALANCE_SHEET" && statementType !== "INCOME_STATEMENT") return null;
  const lineCode = codes[0];
  if (!Object.hasOwn(REPORT_LINES[statementType], lineCode)) return null;
  const lineLabel = REPORT_LINES[statementType][lineCode];
  return lineLabel ? { kind: "financial_statement", periodId, statementType, lineCode, lineLabel } : null;
}

export function selectContextPeriod(periods: Period[], context: AskContext | null) {
  if (!context) return { periodId: periods[0]?.id ?? "", notice: "" };
  const found = periods.find(period => period.id.toLowerCase() === context.periodId);
  return {
    periodId: found?.id ?? periods[0]?.id ?? "",
    notice: !found && periods.length > 0
      ? "전달된 회계기간을 사용할 수 없어 현재 회사의 기간을 선택했습니다."
      : "",
  };
}
