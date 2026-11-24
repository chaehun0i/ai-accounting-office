import assert from "node:assert/strict";
import test from "node:test";
import { setSourceCurrent, setIssueLabels } from "../src/features/reporting/statement-set-model.ts";
import { equityReviewActions } from "../src/features/reporting/equity-review-model.ts";
import { RequestScope } from "../src/features/reporting/request-scope.ts";

test("전체 세트는 READY와 동일 digest를 모두 충족해야 현재 승인 대상으로 표시한다", () => {
  assert.equal(setSourceCurrent("READY", "frozen", "frozen"), true);
  assert.equal(setSourceCurrent("BLOCKED", "frozen", "frozen"), false);
  assert.equal(setSourceCurrent("READY", "new revision", "frozen"), false);
  assert.equal(setSourceCurrent(undefined, null, "frozen"), false);
  assert.match(setIssueLabels.PROFIT_TRANSFER_IS_MISMATCH, /우회/);
  assert.deepEqual(equityReviewActions("REVIEW_REQUESTED", true, ["financial_statement.approve"]), []);
});

test("세트 회사·기간 전환과 새로고침은 이전 조회·생성 응답을 무효화한다", () => {
  const scope = new RequestScope();
  const previous = scope.start("read");
  const generation = scope.start("generate");
  scope.invalidate();
  const current = scope.start("read");
  assert.equal(previous(), false);
  assert.equal(generation(), false);
  assert.equal(current(), true);
});
