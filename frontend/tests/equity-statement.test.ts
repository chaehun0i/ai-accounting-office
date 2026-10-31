import assert from "node:assert/strict";
import test from "node:test";
import { equityCell, equityIssueLabels, equityMovements, type EquitySnapshot } from "../src/features/reporting/equity-model.ts";

test("자본변동표 셀은 스냅샷 금액을 그대로 사용한다", () => {
  const snapshot = { lines: [
    { id: "line-1", component_id: "capital", movement_type: "OPENING", amount: "123456789012345.1234", display_order: 1 },
    { id: "line-2", component_id: "capital", movement_type: "CLOSING", amount: "123456789012345.1234", display_order: 6 },
  ] } as EquitySnapshot;
  assert.equal(equityCell(snapshot, "capital", "OPENING")?.amount, "123456789012345.1234");
  assert.equal(equityCell(snapshot, "capital", "OWNER_TRANSACTIONS"), undefined);
  assert.equal(equityMovements[0][0], "OPENING");
  assert.equal(equityMovements.at(-1)?.[0], "CLOSING");
});

test("차단 사유는 완료 상태 대신 명시적으로 표시된다", () => {
  assert.match(equityIssueLabels.EQUITY_ROLLFORWARD_MISMATCH, /BS 자본총계/);
  assert.match(equityIssueLabels.DIVIDEND_CF_SOURCE_MISMATCH, /CF/);
  assert.match(equityIssueLabels.PROFIT_TRANSFER_IS_MISMATCH, /IS/);
  assert.match(equityIssueLabels.PRIOR_EQUITY_SNAPSHOT_STALE, /마감 원천/);
});
