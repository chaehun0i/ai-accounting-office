import assert from "node:assert/strict";
import test from "node:test";
import { isCurrentDisclosureRequest, type DisclosureRequestScope } from "../src/features/reporting/disclosure-model.ts";

const scope: DisclosureRequestScope = { companyId: "company-a", periodId: "period-a", generation: 4 };

test("주석 비동기 응답은 현재 회사·기간·요청 세대에만 반영한다", () => {
  assert.equal(isCurrentDisclosureRequest(scope, { ...scope }), true);
  assert.equal(isCurrentDisclosureRequest(scope, { ...scope, companyId: "company-b" }), false);
  assert.equal(isCurrentDisclosureRequest(scope, { ...scope, periodId: "period-b" }), false);
  assert.equal(isCurrentDisclosureRequest(scope, { ...scope, generation: 5 }), false);
});
