import test from "node:test";
import assert from "node:assert/strict";
import {currentYearRange,localDate} from "../src/shared/calendar.ts";

test("거래와 전표 입력 기본값은 샘플 연도 대신 현재 달력 날짜를 사용합니다",()=>{
  const now=new Date(2026,9,10);
  assert.deepEqual(currentYearRange(now),{from:"2026-01-01",to:"2026-12-31"});
  assert.equal(localDate(now),"2026-10-10");
});
