import test from "node:test";
import assert from "node:assert/strict";
import {lineTotals,units,money,journalStatus,availableJournalActions} from "../src/features/accounting/journal-model.ts";
const line=(d:string,c:string)=>({account_id:"account",debit_amount:d,credit_amount:c,memo:""});
test("분개 추가와 삭제 후 정확한 합계와 최소 분개 수를 검증합니다",()=>{const lines=[line("0.1","0"),line("0","0.1")];assert.equal(lineTotals(lines).balanced,true);lines.push(line("0.2","0"));assert.equal(lineTotals(lines).difference,"0.2000");assert.equal(lineTotals(lines.slice(0,1)).valid,false)});
test("금액은 부동소수점 변환 없이 소수점 네 자리로 보존합니다",()=>{assert.equal(money(units("999999999999999.1234")),"999999999999999.1234");assert.throws(()=>units("1.00001"));assert.throws(()=>units("-1"));assert.equal(lineTotals([line("1","1"),line("1","0")]).valid,false)});
test("내부 전표 상태를 한국어 회계 안내로 표시합니다",()=>{assert.equal(journalStatus.REVIEW_REQUIRED,"승인 대기");assert.equal(journalStatus.POSTED,"장부 반영 완료")});

test("상태와 권한에 맞는 제출 승인 반려 확정 동작만 제공합니다",()=>{assert.equal(availableJournalActions("DRAFT",["journal.submit"])[0][0],"submit");assert.deepEqual(availableJournalActions("REVIEW_REQUIRED",["journal.approve"]).map(a=>a[0]),["approve","reject"]);assert.equal(availableJournalActions("APPROVED",["journal.post"])[0][0],"post");assert.equal(availableJournalActions("POSTED",["journal.post"]).length,0);assert.equal(availableJournalActions("REVIEW_REQUIRED",[]).length,0)});
