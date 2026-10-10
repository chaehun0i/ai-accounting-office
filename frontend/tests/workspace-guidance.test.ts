import assert from "node:assert/strict";
import test from "node:test";
import { workspaceGuidance, sectionStatus } from "../src/features/onboarding/workspace-guidance.ts";

test("입력률과 관계없이 서버가 준비 완료를 판단합니다", () => {
  assert.match(workspaceGuidance("IN_PROGRESS", false, true).title, /확인/);
  assert.match(workspaceGuidance("READY_TO_COMPLETE", false, true).title, /준비가 되었습니다/);
  assert.match(workspaceGuidance("READY_TO_COMPLETE", true, true).title, /저장/);
});
test("조회 권한만 있는 사용자에게 입력을 요구하지 않습니다", () => {
  assert.match(workspaceGuidance("IN_PROGRESS", false, false).title, /확인할 수/);
  assert.match(workspaceGuidance("COMPLETED", false, false).title, /마쳤습니다/);
});
test("입력 대상이 없는 영역을 미입력으로 단정하지 않습니다", () => {
  assert.equal(sectionStatus({ code: "Accounting_Settings", status: "EMPTY", total: 0 }), "내용 확인");
  assert.equal(sectionStatus({ code: "COA", status: "EMPTY", total: 0 }), "준비된 계정목록");
  assert.equal(sectionStatus({ code: "Opening_Balances", status: "WARNING", total: 0 }), "확인 필요");
});
