import assert from "node:assert/strict";
import test from "node:test";
import { canVisit, officeRoutes } from "../src/features/navigation/routes.ts";

test("업무마다 독립 경로를 제공하고 회사 선택은 권한 없이 열 수 있습니다", () => {
  assert.equal(new Set(officeRoutes.map(route => route.href)).size, 11);
  assert.ok(canVisit("/companies", []));
  assert.ok(canVisit("/", []));
  assert.equal(canVisit("/unknown", []), false);
});

test("메뉴와 직접 URL 진입은 같은 서버 permission 계약을 사용합니다", () => {
  assert.equal(canVisit("/journals", []), false);
  assert.ok(canVisit("/journals", ["journal.read"]));
  assert.equal(canVisit("/transactions", ["journal.read"]), false);
  assert.ok(canVisit("/ledger", ["ledger.read"]));
  assert.ok(canVisit("/trial-balance", ["ledger.read"]));
  assert.equal(canVisit("/imports", ["account.read"]), false);
});
