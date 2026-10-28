import assert from "node:assert/strict";
import test from "node:test";
import { cashGenerationPayload, cashIssueLabel, cashLineLabel, type CashBridge, type CashPreflight } from "../src/features/reporting/cash-flow-model.ts";
import type { Period, StatementSet } from "../src/features/reporting/model.ts";

const period: Period = { id: "period", start_date: "2026-01-01", end_date: "2026-01-31", status: "CLOSED", close_version: 2 };
const set: StatementSet = { id: "set", period_id: "period", closing_run_id: "run", close_version: 2, taxonomy_version: 1, status: "GENERATED", trial_balance_digest: "source", generated_at: "2026-02-01" };
const preflight: CashPreflight = { period_id: "period", close_version: 2, source_digest: "source", mapping_digest: "direct", opening_cash: "10", closing_cash: "15", net_cash_movement: "5", net_operating: "5", net_investing: "0", net_financing: "0", exchange_effect: "0", classified_journal_count: 1, issues: [], ready: true };
const bridge: CashBridge = { period_id: "period", statement_set_id: "set", close_version: 2, source_digest: "source", mapping_digest: "mapping", policy_code: "TAX_INTEREST_OPERATING", policy_version: 1, net_profit: "5", net_operating: "5", direct_net_operating: "5", reconciliation_difference: "0.0000", issues: [], status: "READY" };

test("현금흐름표 생성은 화면의 CLOSED 기간과 현재 BS/IS 및 대사 원천에 고정된다", () => {
  assert.deepEqual(cashGenerationPayload(period, set, preflight, bridge), { period_id: "period", statement_set_id: "set", close_version: 2, source_digest: "source", mapping_digest: "mapping" });
  assert.equal(cashGenerationPayload({ ...period, status: "OPEN" }, set, preflight, bridge), null);
  assert.equal(cashGenerationPayload(period, { ...set, close_version: 1 }, preflight, bridge), null);
  assert.equal(cashGenerationPayload(period, set, preflight, { ...bridge, statement_set_id: "old" }), null);
  assert.equal(cashGenerationPayload(period, set, preflight, { ...bridge, reconciliation_difference: "0.01" }), null);
  assert.equal(cashGenerationPayload(period, set, { ...preflight, issues: [{ code: "CASH_FLOW_UNCLASSIFIED" }] }, bridge), null);
});

test("차단 코드와 동결 항목은 사용자에게 구분된 이름으로 보인다", () => {
  assert.match(cashIssueLabel("INDIRECT_STATEMENT_SOURCE_STALE"), /BS\/IS/);
  assert.equal(cashLineLabel("NET_OPERATING"), "영업활동 현금흐름");
});
