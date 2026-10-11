import assert from "node:assert/strict";
import test from "node:test";
import { allocationSummary, agingLabel, financeStatus } from "../src/features/finance/model.ts";
import { canVisit } from "../src/features/navigation/routes.ts";

test("복수 배분과 미배분액은 정수 소수점 단위로 계산합니다", () => {
  assert.deepEqual(allocationSummary("6000000", ["4000000", "2000000"]), {
    allocated: "6000000.0000", unapplied: "0.0000", valid: true,
  });
  assert.equal(allocationSummary("1.0000", ["0.1", "0.2"]).unapplied, "0.7000");
  assert.equal(allocationSummary("100", ["101"]).valid, false);
  assert.throws(() => allocationSummary("100", ["잘못된 입력"]));
});

test("기한과 업무 상태를 사용자용 한국어로 표시합니다", () => {
  assert.equal(agingLabel("2026-01-01", "2026-01-31"), "1~30일 경과");
  assert.equal(agingLabel("2026-01-01", "2026-02-01"), "31~60일 경과");
  assert.equal(agingLabel("2026-01-31", "2026-01-31"), "기한 전");
  assert.equal(financeStatus.PARTIAL, "일부 결제");
  assert.equal(financeStatus.UNAPPLIED, "미배분액 있음");
});

test("채권과 채무 메뉴는 각각 서버 권한에 연결됩니다", () => {
  assert.equal(canVisit("/receivables", []), false);
  assert.equal(canVisit("/payables", ["receivable.read"]), false);
  assert.equal(canVisit("/receivables", ["receivable.read"]), true);
  assert.equal(canVisit("/payables", ["payable.read"]), true);
});
