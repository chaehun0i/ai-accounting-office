import assert from "node:assert/strict";
import test from "node:test";
import { canLinkPayment, type PaymentSources } from "../src/features/reporting/dividend-model.ts";

test("배당 지급 선택은 검증된 후보만 허용하며 금액 문자열을 계산하지 않는다", () => {
  const sources: PaymentSources = {
    declaration_id: "declaration", period_id: "payment-period", paid_amount: "0.0001",
    remaining_amount: "99999999999999.9999", statement_id: "cf", source_digest: "digest", issue: null,
    candidates: [{ event_id: "cash", journal_id: "posted", journal_no: "J1", entry_date: "2026-03-04",
      amount: "0.0001", evidence_id: null, status: "AVAILABLE", issue: null }],
  };
  assert.equal(canLinkPayment(null, "cash"), false);
  assert.equal(canLinkPayment(sources, "old-response-event"), false);
  assert.equal(canLinkPayment(sources, "cash"), true);
  assert.equal(canLinkPayment({ ...sources, issue: "PERIOD_NOT_CLOSED" }, "cash"), false);
  for (const issue of ["PAYMENT_ALREADY_LINKED", "PAYMENT_EXCEEDS_DECLARATION", "PAYMENT_SOURCE_STALE", "PAYMENT_ACCOUNT_MISMATCH"]) {
    assert.equal(canLinkPayment({ ...sources, candidates: [{ ...sources.candidates[0], issue, status: "BLOCKED" }] }, "cash"), false);
  }
  assert.equal(sources.remaining_amount, "99999999999999.9999");
});
