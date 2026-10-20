import assert from "node:assert/strict";
import test from "node:test";
import { setupSteps, savedStep, stepForSection, missingStepValues } from "../src/features/onboarding/setup-steps.ts";

test("회사별 초기 설정은 기초 채권·채무를 포함하며 잘못된 저장 위치는 첫 단계로 복구합니다", () => {
  assert.equal(setupSteps.length, 7);
  assert.equal(savedStep("Accounting_Settings"), 1);
  assert.equal(stepForSection("AR_Opening"), 4);
  assert.equal(stepForSection("AP_Opening"), 5);
  assert.equal(savedStep("invalid"), 0);
  assert.equal(savedStep(null), 0);
  assert.equal(stepForSection("Fixed_Assets"), 6);
});
test("필수 규칙은 서버 필드 정의와 법인 여부를 사용합니다", () => {
  const workspace = { cells: [{ field_code: "Company.taxpayer_type", row_key: "singleton", value: "CORPORATION" }], fields: [{ field_code: "Company.corporation_number", section_code: "Company", label: "법인등록번호", active: true, input_mode: "TEXT", required_rule_code: "CORPORATION" }] };
  assert.deepEqual(missingStepValues(workspace, "Company", {}), ["법인등록번호"]);
  assert.deepEqual(missingStepValues(workspace, "Company", { "Company.taxpayer_type::singleton": "INDIVIDUAL" }), []);
  assert.deepEqual(missingStepValues(workspace, "Company", { "Company.corporation_number::singleton": "1234567890123" }), []);
});
test("기초잔액은 명시적 없음 확인을 요구하고 선택 거래처는 생략할 수 있습니다", () => {
  const workspace = { cells: [], fields: [] };
  assert.equal(missingStepValues(workspace, "Opening_Balances", {}).length, 1);
  assert.deepEqual(missingStepValues(workspace, "Opening_Balances", { "Company.no_opening_balance::singleton": true }), []);
  assert.deepEqual(missingStepValues(workspace, "Counterparties", {}), []);
  assert.deepEqual(missingStepValues(workspace, "AR_Opening", {}), []);
  assert.deepEqual(missingStepValues(workspace, "AP_Opening", {}), []);
});

test("채권 입력 행이 생기면 카탈로그 필수값을 확인합니다", () => {
  const workspace = { cells: [{ field_code: "AR_Opening.reference_code", row_key: "CP|INV-1", value: "INV-1" }], fields: [
    { field_code: "AR_Opening.reference_code", section_code: "AR_Opening", label: "원천 참조", active: true, input_mode: "TEXT", required_rule_code: "ALWAYS" },
    { field_code: "AR_Opening.original_amount", section_code: "AR_Opening", label: "원금", active: true, input_mode: "NUMBER", required_rule_code: "ALWAYS" },
  ] };
  assert.deepEqual(missingStepValues(workspace, "AR_Opening", {}), ["원금"]);
  assert.deepEqual(missingStepValues(workspace, "AR_Opening", { "AR_Opening.original_amount::CP|INV-1": "100" }), []);
});

test("자동 계산값은 기초잔액 입력 행으로 세지 않습니다", () => {
  const workspace = { cells: [{ field_code: "Opening_Balances.debit_total", row_key: "derived", value: "0" }], fields: [{ field_code: "Opening_Balances.debit_total", section_code: "Opening_Balances", label: "차변 합계", active: true, input_mode: "DERIVED_READONLY", required_rule_code: "NEVER" }, { field_code: "Opening_Balances.account_code", section_code: "Opening_Balances", label: "계정코드", active: true, input_mode: "TEXT", required_rule_code: "ALWAYS" }] };
  assert.equal(missingStepValues(workspace, "Opening_Balances", {}).length, 1);
  assert.deepEqual(missingStepValues(workspace, "Opening_Balances", { "Company.no_opening_balance::singleton": true }), []);
});
