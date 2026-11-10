import assert from "node:assert/strict";
import test from "node:test";
import { RequestScope } from "../src/features/reporting/request-scope.ts";

test("늦은 기간·revision 응답과 이전 명령 완료를 폐기한다", async () => {
  const scope = new RequestScope();
  let resolve!: (value: string) => void;
  const delayed = new Promise<string>(done => { resolve = done; });
  const valid = scope.start("mutation");
  let displayed = "new-period";
  const completion = delayed.then(value => { if (valid()) displayed = value; });
  scope.invalidate();
  resolve("old-period");
  await completion;
  assert.equal(displayed, "new-period");
});

test("빠른 연속 원천 선택은 마지막 요청만 표시한다", () => {
  const scope = new RequestScope();
  const first = scope.start("sources");
  const latest = scope.start("sources");
  const detail = scope.start("detail");
  assert.equal(first(), false);
  assert.equal(latest(), true);
  assert.equal(detail(), true);
  scope.invalidate();
  assert.equal(latest(), false);
  assert.equal(detail(), false);
});
