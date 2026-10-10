import assert from "node:assert/strict";
import test from "node:test";
import { workspaceSummary } from "../src/features/onboarding/workspace-summary.ts";

test("입력 진행률은 서버 입력 분모를 사용하고 고정 계정과목을 제외합니다", () => {
  assert.deepEqual(workspaceSummary([
    { code: "Company", complete: 2, total: 4, status: "IN_PROGRESS" },
    { code: "COA", complete: 100, total: 100, status: "COMPLETE" },
    { code: "Opening_Balances", complete: 1, total: 2, status: "WARNING" },
  ]), { complete: 3, total: 6, percent: 50, warnings: 1, inProgress: 1, empty: 0 });
});

test("입력 대상이 없어도 완료를 추정하거나 0으로 나누지 않습니다", () => {
  assert.equal(workspaceSummary([]).percent, 0);
});
