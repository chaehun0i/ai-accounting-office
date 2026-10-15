import assert from "node:assert/strict";
import test from "node:test";
import { formatAnswerAmount, isFinal, queryPayload, queryRequest, runMessage, type QueryRun } from "../src/features/ai-team/model.ts";

const base: QueryRun = {
  id: "run", period_id: "period", question_text: "손익이 얼마야?",
  status: "COMPLETED", answer_text: "당기순이익은 100.0000입니다.",
  answer_amount: "100.0000", answer_resource_id: "statement",
  answer_source_digest: "digest", controller_verdict: "PASS", error_code: null,
};

test("기간 UUID와 질문을 분리해 제출하고 Decimal 문자열을 보존한다", () => {
  assert.deepEqual(queryPayload("period", "  손익이 얼마야?  "), { period_id: "period", question: "손익이 얼마야?" });
  const request = queryRequest("company", "period", "  손익이 얼마야?  ", "retry-key");
  assert.deepEqual(request.headers, { "X-Company-ID": "company", "Idempotency-Key": "retry-key" });
  assert.deepEqual(JSON.parse(String(request.body)), { period_id: "period", question: "손익이 얼마야?" });
  assert.equal(formatAnswerAmount(base.answer_amount), "100.0000");
  assert.equal(formatAnswerAmount(null), null);
  assert.equal(runMessage(base), base.answer_text);
});

test("검증 차단과 실행 실패는 정상 답변과 구별한다", () => {
  assert.equal(isFinal("PENDING"), false);
  assert.equal(isFinal("RUNNING"), false);
  assert.equal(isFinal("COMPLETED"), true);
  assert.match(runMessage({ ...base, status: "BLOCKED", answer_text: null }), /검증 단계/);
  assert.match(runMessage({ ...base, status: "FAILED", error_code: "INTERNAL", answer_text: null }), /다시 시도/);
});
