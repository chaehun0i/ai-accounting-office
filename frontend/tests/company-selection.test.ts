import assert from "node:assert/strict";
import test from "node:test";
import { SelectionGate, filterCompanies } from "../src/features/companies/selection-state.ts";

test("회사 전환 뒤 도착한 이전 응답과 사용자 변경 전 응답을 버립니다", () => {
  const gate = new SelectionGate();
  const first = gate.next();
  const second = gate.next();
  assert.equal(gate.accepts(first), false);
  assert.equal(gate.accepts(second), true);
  gate.next();
  assert.equal(gate.accepts(second), false);
});
test("회사명 검색은 UUID와 권한을 바꾸지 않습니다", () => {
  const company = { id: "company-uuid", company_name: "한빛 Office", role_code: "VIEWER", permissions: ["company.read"], version: 1, business_number: "1234567890", address: "서울" };
  assert.deepEqual(filterCompanies([company], " OFFICE "), [company]);
  assert.deepEqual(filterCompanies([company], "없는 회사"), []);
});
