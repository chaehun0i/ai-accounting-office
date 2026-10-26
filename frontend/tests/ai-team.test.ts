import assert from "node:assert/strict";
import test from "node:test";
import { canReviewTeam, isFinal, queryPayload, queryRequest, runMessage, runStatusLabel, teamStepLabel, type QueryRun } from "../src/features/ai-team/model.ts";

const base: QueryRun = {
  id: "run", period_id: "period", question_text: "손익이 얼마야?",
  status: "COMPLETED", answer_text: "당기순이익은 100.0000입니다.",
  answer_amount: "100.0000", answer_resource_id: "statement",
  answer_source_digest: "digest", controller_verdict: "PASS", error_code: null,
  graph_name: "bookkeeper",
};

test("기간 UUID와 질문을 분리해 제출하고 Decimal 문자열을 보존한다", () => {
  assert.deepEqual(queryPayload("period", "  손익이 얼마야?  "), { period_id: "period", question: "손익이 얼마야?" });
  const request = queryRequest("company", "period", "  손익이 얼마야?  ", "retry-key");
  assert.deepEqual(request.headers, { "X-Company-ID": "company", "Idempotency-Key": "retry-key" });
  assert.deepEqual(JSON.parse(String(request.body)), { period_id: "period", question: "손익이 얼마야?" });
  assert.equal(base.answer_amount, "100.0000");
  assert.equal(runMessage(base), base.answer_text);
});

test("공동 검토 역할 단계는 실제 서버 node_name으로 표시한다", () => {
  assert.match(teamStepLabel.closing_agent, /Closing Agent/);
  assert.match(teamStepLabel.ar_agent, /AR Agent/);
  assert.match(teamStepLabel.ap_agent, /AP Agent/);
  assert.match(teamStepLabel.controller_agent, /Controller/);
});

test("공동 검토는 기간·채권·채무 권한을 모두 요구한다", () => {
  assert.equal(canReviewTeam(["period.read", "receivable.read", "payable.read"]), true);
  assert.equal(canReviewTeam(["period.read", "receivable.read"]), false);
  assert.match(runMessage({ ...base, status: "BLOCKED", error_code: "TEAM_SOURCE_CONFLICT" }), /원천이 변경/);
});

test("검증 차단과 실행 실패는 정상 답변과 구별한다", () => {
  assert.equal(isFinal("PENDING"), false);
  assert.equal(isFinal("RUNNING"), false);
  assert.equal(isFinal("COMPLETED"), true);
  assert.match(runMessage({ ...base, status: "BLOCKED", answer_text: null }), /검증 단계/);
  assert.match(runMessage({ ...base, status: "FAILED", error_code: "INTERNAL", answer_text: null }), /다시 시도/);
  assert.equal(runStatusLabel("COMPLETED"), "조회 완료");
  assert.equal(runStatusLabel("BLOCKED"), "검증 차단");
});
