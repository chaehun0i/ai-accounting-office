import assert from "node:assert/strict";
import test from "node:test";
import {
  CLOSING_QUESTION, closingAskHref, parseAskContext, selectContextPeriod,
} from "../src/features/ai-team/context.ts";
import { queryRequest, type Period } from "../src/features/ai-team/model.ts";

const closingPeriod = "11111111-1111-1111-1111-111111111111";
const otherPeriod = "22222222-2222-2222-2222-222222222222";
const periods: Period[] = [{
  id: closingPeriod, start_date: "2026-09-01", end_date: "2026-09-30",
  fiscal_year: 2026, period_no: 9, status: "CLOSING",
}];

test("월마감 화면은 현재 기간만 URL에 전달하고 지원하는 문맥만 받는다", () => {
  const href = closingAskHref(closingPeriod);
  assert.equal(href, `/ai-team?period_id=${closingPeriod}&context=closing`);
  assert.deepEqual(parseAskContext(new URLSearchParams(href.split("?")[1])), {
    kind: "closing", periodId: closingPeriod,
  });
  assert.equal(parseAskContext(new URLSearchParams("context=invoice&period_id=" + closingPeriod)), null);
  assert.equal(parseAskContext(new URLSearchParams("context=closing&context=closing")), null);
});

test("현재 회사의 기간만 선택하고 잘못된 문맥 기간은 일반 안내로 대체한다", () => {
  const valid = parseAskContext(new URLSearchParams(`context=closing&period_id=${closingPeriod}`));
  assert.deepEqual(selectContextPeriod(periods, valid), { periodId: closingPeriod, notice: "" });

  for (const requested of [otherPeriod, "not-a-uuid", "", `${closingPeriod}&period_id=${otherPeriod}`]) {
    const context = parseAskContext(new URLSearchParams(`context=closing&period_id=${requested}`));
    const result = selectContextPeriod(periods, context);
    assert.equal(result.periodId, closingPeriod);
    assert.match(result.notice, /현재 회사의 기간/);
    assert.doesNotMatch(result.notice, /11111111|22222222/);
  }
  assert.deepEqual(selectContextPeriod(periods, null), { periodId: closingPeriod, notice: "" });
});

test("문맥은 수정 가능한 질문 초안이며 실제 제출 계약은 기존 API를 유지한다", () => {
  assert.match(CLOSING_QUESTION, /월마감 준비 상태/);
  const request = queryRequest("current-company", closingPeriod, ` ${CLOSING_QUESTION} `, "submit-key");
  assert.deepEqual(request.headers, { "X-Company-ID": "current-company", "Idempotency-Key": "submit-key" });
  assert.deepEqual(JSON.parse(String(request.body)), { period_id: closingPeriod, question: CLOSING_QUESTION });
});
