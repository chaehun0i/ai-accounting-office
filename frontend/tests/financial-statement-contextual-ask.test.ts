import assert from "node:assert/strict";
import test from "node:test";
import {
  askContextKey, financialStatementAskHref, parseAskContext, questionDraft, selectContextPeriod,
} from "../src/features/ai-team/context.ts";
import { queryRequest, type Period } from "../src/features/ai-team/model.ts";

const periodId = "11111111-1111-1111-1111-111111111111";
const otherPeriodId = "22222222-2222-2222-2222-222222222222";
const periods: Period[] = [{
  id: periodId, start_date: "2026-09-01", end_date: "2026-09-30",
  fiscal_year: 2026, period_no: 9, status: "CLOSED",
}];

test("BS/IS/CF 항목 링크는 금액과 회사 정보를 전달하지 않는다", () => {
  for (const [type, code, label] of [["BALANCE_SHEET", "ASSET_ACCOUNTS", "자산"], ["INCOME_STATEMENT", "OPERATING_EXPENSE", "영업비용"], ["CASH_FLOW", "NET_OPERATING", "영업활동 현금흐름"]] as const) {
    const href = financialStatementAskHref(periodId, type, code);
    const url = new URL(href, "https://example.test");
    assert.deepEqual([...url.searchParams.keys()], ["period_id", "context", "statement_type", "line_code"]);
    assert.deepEqual(parseAskContext(url.searchParams), {
      kind: "financial_statement", periodId, statementType: type, lineCode: code,
      lineLabel: label,
    });
    assert.doesNotMatch(href, /company_id|current_amount|source_digest/);
  }
});

test("지원하지 않는 보고서 문맥과 중복 파라미터는 거부한다", () => {
  for (const params of [
    `context=financial_statement&period_id=${periodId}&statement_type=CASH_FLOW&line_code=ASSETS`,
    `context=financial_statement&period_id=${periodId}&statement_type=BALANCE_SHEET&line_code=NET_PROFIT`,
    `context=financial_statement&period_id=${periodId}&statement_type=BALANCE_SHEET&line_code=toString`,
    `context=financial_statement&period_id=${periodId}&statement_type=BALANCE_SHEET&line_code=ASSETS&line_code=EQUITY`,
    `context=unknown&period_id=${periodId}`,
  ]) assert.equal(parseAskContext(new URLSearchParams(params)), null);
});

test("현재 회사에서 확인된 기간만 선택하고 질문 초안에 금액을 넣지 않는다", () => {
  const valid = parseAskContext(new URLSearchParams(financialStatementAskHref(periodId, "INCOME_STATEMENT", "OPERATING_EXPENSE").split("?")[1]));
  assert.deepEqual(selectContextPeriod(periods, valid), { periodId, notice: "" });
  assert.match(questionDraft(valid), /손익계산서의 영업비용 \(OPERATING_EXPENSE\)/);
  assert.doesNotMatch(questionDraft(valid), /1,234|current_amount/);

  for (const requested of [otherPeriodId, "malformed"]) {
    const foreign = parseAskContext(new URLSearchParams(financialStatementAskHref(requested, "BALANCE_SHEET", "ASSETS").split("?")[1]));
    const selection = selectContextPeriod(periods, foreign);
    assert.equal(selection.periodId, periodId);
    assert.match(selection.notice, /현재 회사의 기간/);
    assert.doesNotMatch(selection.notice, /11111111|22222222/);
  }
});

test("문맥 진입은 초안만 만들고 제출 계약은 기존 질의 API를 유지한다", () => {
  const context = parseAskContext(new URLSearchParams(financialStatementAskHref(periodId, "BALANCE_SHEET", "ASSETS").split("?")[1]));
  const request = queryRequest("current-company", periodId, questionDraft(context), "submission-key");
  assert.deepEqual(request.headers, { "X-Company-ID": "current-company", "Idempotency-Key": "submission-key" });
  assert.deepEqual(JSON.parse(String(request.body)), { period_id: periodId, question: questionDraft(context) });
});

test("회사 또는 보고서 항목 변경 시 Workspace 상태 키가 달라진다", () => {
  const assets = parseAskContext(new URLSearchParams(financialStatementAskHref(periodId, "BALANCE_SHEET", "ASSETS").split("?")[1]));
  const equity = parseAskContext(new URLSearchParams(financialStatementAskHref(periodId, "BALANCE_SHEET", "EQUITY").split("?")[1]));
  assert.notEqual(askContextKey("company-a", assets), askContextKey("company-b", assets));
  assert.notEqual(askContextKey("company-a", assets), askContextKey("company-a", equity));
  assert.notEqual(askContextKey("company-a", assets), askContextKey("company-a", null));
});
