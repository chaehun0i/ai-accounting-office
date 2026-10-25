import assert from "node:assert/strict";
import test from "node:test";
import { matchesClosedPeriod, type Period, type ResolvedReportPeriod } from "../src/features/reporting/model.ts";
import { canVisit } from "../src/features/navigation/routes.ts";

const period: Period = {
  id: "period-1", start_date: "2026-01-01", end_date: "2026-01-31",
  status: "CLOSED", close_version: 1,
};
const resolved: ResolvedReportPeriod = {
  period_preset: "CUSTOM", period_mode: "AS_OF", timezone: "Asia/Seoul",
  date_from: null, date_to: null, as_of: "2026-01-31", partial: false,
};

test("서버가 해석한 AS_OF/RANGE만 선택한 CLOSED 기간과 연결합니다", () => {
  assert.equal(matchesClosedPeriod(period, resolved), true);
  assert.equal(matchesClosedPeriod(period, { ...resolved, as_of: "2026-01-30" }), false);
  assert.equal(matchesClosedPeriod(period, {
    ...resolved, period_mode: "RANGE", as_of: null,
    date_from: "2026-01-01", date_to: "2026-01-31",
  }), true);
  assert.equal(matchesClosedPeriod({ ...period, status: "OPEN" }, resolved), false);
});

test("Report Center 경로는 보고서 조회 권한에 연결됩니다", () => {
  assert.equal(canVisit("/reports", ["report.read"]), true);
  assert.equal(canVisit("/reports", ["financial_statement.read"]), false);
});
