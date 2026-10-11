import assert from "node:assert/strict";
import test from "node:test";
import { documentActions, documentLabels, documentPaths, documentTotals, type BusinessDocument } from "../src/features/business-documents/model.ts";

test("문서 항목 합계는 정확한 소수점 네 자리로 계산한다", () => {
  assert.deepEqual(documentTotals([{ line_no: 1, description: "용역", supply_amount: "10000000.0001", tax_amount: "1000000.0002" }]), { supply: "10000000.0001", tax: "1000000.0002", total: "11000000.0003" });
  assert.throws(() => documentTotals([{ line_no: 1, description: "오류", supply_amount: "-1", tax_amount: "0" }]));
});
test("승인과 제출은 상태와 권한을 함께 확인한다", () => {
  assert.deepEqual(documentActions({ status: "DRAFT" } as BusinessDocument, ["invoice.review"]), ["submit"]);
  assert.deepEqual(documentActions({ status: "REVIEW_REQUIRED" } as BusinessDocument, ["invoice.approve"]), ["approve"]);
  assert.deepEqual(documentActions({ status: "APPROVED" } as BusinessDocument, ["invoice.approve"]), []);
  assert.deepEqual(documentActions({ status: "REVIEW_REQUIRED" } as BusinessDocument, []), []);
});
test("정정문서는 Invoice와 별도 경로와 한국어 안내를 사용한다", () => {
  assert.equal(documentPaths.CREDIT_NOTE, "/credit-notes");
  assert.equal(documentLabels.DEBIT_NOTE, "증액 정정문서");
});
