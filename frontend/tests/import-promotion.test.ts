import assert from "node:assert/strict";
import test from "node:test";
import { canPromote, promotionCommand } from "../src/features/imports/promotion.ts";
const receipt = { id: "receipt-1", source_digest: "a".repeat(64), confirmed_version: 3, status: "CONFIRMED" };
test("거래 생성은 파일 확인과 거래 생성 권한을 모두 요구합니다", () => {
  assert.equal(canPromote(receipt, ["import.confirm"]), false);
  assert.equal(canPromote(receipt, ["transaction.create"]), false);
  assert.equal(canPromote(receipt, ["import.confirm", "transaction.create"]), true);
  assert.equal(canPromote({ ...receipt, status: "COMPLETED" }, ["import.confirm", "transaction.create"]), false);
});
test("거래 생성 요청은 서버가 확인한 영수증과 원천 다이제스트 및 버전에 묶입니다", () => {
  assert.deepEqual(promotionCommand(receipt), { expected_version: 3, receipt_id: "receipt-1", source_digest: "a".repeat(64) });
  assert.equal(promotionCommand({ ...receipt, confirmed_version: 4 }).expected_version, 4);
});
