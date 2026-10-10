import assert from "node:assert/strict";
import test from "node:test";
import { cellKey, conflictKey, isEditable, isVisible, mergeKey, type Field } from "../src/features/onboarding/model.ts";

test("온보딩 금액과 업무 키는 JavaScript 숫자 변환 없이 보존합니다", () => {
  assert.equal(mergeKey(["as_of_date", "account_code", "counterparty_code"], { as_of_date: "2025-01-01", account_code: "00100" }), "2025-01-01|00100|");
  assert.equal(cellKey("COA.account_code", "00100"), "COA.account_code::00100");
  assert.equal(conflictKey({ field_code: "COA.account_name", row_key: "00100", value: "현금", source_type: "MANUAL", status: "VALID", version: 1 }), "COA.account_name:00100");
});
test("파생값과 비활성 필드는 직접 수정하지 않습니다", () => {
  const field = { active: true, input_mode: "TEXT" } as Field;
  assert.equal(isEditable(field), true);
  assert.equal(isEditable({ ...field, input_mode: "DERIVED_READONLY" }), false);
  assert.equal(isEditable({ ...field, active: false }), false);
});

test("법인번호는 법인 회사에만 표시합니다", () => {
  const field = { active: true, required_rule_code: "CORPORATION" } as Field;
  assert.equal(isVisible(field, "CORPORATION"), true);
  assert.equal(isVisible(field, "INDIVIDUAL"), false);
});
