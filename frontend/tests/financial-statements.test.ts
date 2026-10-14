import assert from "node:assert/strict";
import test from "node:test";
import { formatMoney } from "../src/features/reporting/model.ts";
import { canVisit } from "../src/features/navigation/routes.ts";

test("재무제표 표시가 Decimal 문자열을 Number로 변환하지 않습니다", () => {
  assert.equal(formatMoney("123456789012345.1234"), "123,456,789,012,345.1234");
  assert.equal(formatMoney("-1000.0000"), "-1,000");
});

test("재무제표 화면은 별도 조회 권한을 요구합니다", () => {
  assert.ok(canVisit("/financial-statements", ["financial_statement.read"]));
  assert.equal(canVisit("/financial-statements", ["ledger.read"]), false);
});
