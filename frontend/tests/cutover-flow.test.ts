import assert from "node:assert/strict";
import test from "node:test";
import { canPromoteCutover, cutoverPhase } from "../src/features/onboarding/cutover-flow.ts";
import type { CutoverStatus } from "../src/features/onboarding/model.ts";

const base: CutoverStatus = {
  session_version: 8, onboarding_status: "COMPLETED", opening_required: true,
  no_opening_balance: false, journal_id: null, journal_status: null,
  ar_ap_source_present: true, ar_ap_preview_ready: false, ar_ap_source_digest: null,
  ar_ap_issues: [], ar_ap_totals: [], ar_ap_promoted: false,
  receivable_count: 0, payable_count: 0,
};

test("신규 회사와 Opening·승인·대조·승격 단계를 서버 상태로 구분합니다", () => {
  assert.equal(cutoverPhase({ ...base, no_opening_balance: true, opening_required: false }), "NO_OPENING");
  assert.equal(cutoverPhase(base), "CREATE_JOURNAL");
  assert.equal(cutoverPhase({ ...base, journal_id: "J", journal_status: "REVIEW_REQUIRED" }), "POST_JOURNAL");
  assert.equal(cutoverPhase({ ...base, journal_id: "J", journal_status: "POSTED" }), "PREVIEW_BLOCKED");
  assert.equal(cutoverPhase({ ...base, journal_id: "J", journal_status: "POSTED", ar_ap_preview_ready: true }), "PROMOTE");
  assert.equal(cutoverPhase({ ...base, journal_id: "J", journal_status: "POSTED", ar_ap_promoted: true }), "COMPLETE");
  assert.equal(cutoverPhase({ ...base, journal_id: "J", journal_status: "POSTED", ar_ap_source_present: false }), "COMPLETE");
});

test("기초 채권·채무 승격에는 역할별 기존 권한이 모두 필요합니다", () => {
  const status = { ...base, ar_ap_totals: [{ role: "AR", account_code: "AR", counterparty_code: "C", opening_amount: "100", item_amount: "100" }, { role: "AP", account_code: "AP", counterparty_code: "S", opening_amount: "50", item_amount: "50" }] };
  assert.equal(canPromoteCutover(status, ["journal.propose", "collection.record"]), false);
  assert.equal(canPromoteCutover(status, ["collection.record", "payment.record"]), false);
  assert.equal(canPromoteCutover(status, ["journal.propose", "collection.record", "payment.record"]), true);
});
