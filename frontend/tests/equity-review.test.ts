import assert from "node:assert/strict";
import test from "node:test";
import { equityReviewActions } from "../src/features/reporting/equity-review-model.ts";

test("SCE 승인 UI는 권한·상태·원천 현재성에 맞는 작업만 제공한다", () => {
  const writer = ["financial_statement.generate"];
  const reviewer = ["financial_statement.approve"];
  assert.deepEqual(equityReviewActions("NOT_REQUESTED", false, writer), ["request-review"]);
  assert.deepEqual(equityReviewActions("REJECTED", false, writer), ["request-review"]);
  assert.deepEqual(equityReviewActions("REVIEW_REQUESTED", false, writer), []);
  assert.deepEqual(equityReviewActions("REVIEW_REQUESTED", false, reviewer), ["approve", "reject"]);
  assert.deepEqual(equityReviewActions("REVIEW_REQUESTED", true, reviewer), []);
  assert.deepEqual(equityReviewActions("APPROVED", false, [...writer, ...reviewer]), []);
  assert.deepEqual(equityReviewActions("NOT_REQUESTED", false, ["financial_statement.read"]), []);
});
