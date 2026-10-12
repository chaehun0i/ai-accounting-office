"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { DataImport, type Receipt } from "@/features/imports/data-import";
import { displayAmount } from "@/shared/amount";
import { OfficeDialog } from "@/shared/ui/dialog";

type Account = { id: string; alias: string; control_account_id: string };
type Coa = { id: string; account_name: string; account_type: string; posting_allowed: boolean; status: string };
type Statement = { id: string; bank_account_id: string; statement_start: string; statement_end: string; opening_balance: string; closing_balance: string; status: string; version: number };
type Source = { id: string; source_id: string; occurred_at: string; amount: string; direction: string; counterparty_text: string; description: string; source_status: string; reconciliation_status: string; matched_amount: string; version: number };
type Candidate = { source_id: string; target_type: string; target_id: string; target_reference:string; target_date:string; suggested_amount: string; source_version: number; target_version: number; score: number; classification: string; reasons: string[] };
type Match = { id: string; status: string; matched_amount: string; version: number; lines: { source_type: string; source_id: string; target_type: string; target_id: string; amount: string }[] };
type Summary = { statement_balance?: string; source_balance?: string; reconciled_source_balance: string; gl_balance: string; difference_amount: string; unmatched_count: number; partial_count: number; review_count: number; reconciliation_item_count?: number; blocker: boolean };
type Item = { id:string; reason_code:string; amount:string; description:string; status:string; version:number; resolution_note:string|null };
const itemReasons:Record<string,string>={TIMING_ITEM:"시점 차이",MISSING_TRANSACTION:"거래 누락",DUPLICATE_SOURCE:"중복 원천",WRONG_ACCOUNT:"계정 연결 오류",MANUAL_ADJUSTMENT_CANDIDATE:"조정 검토 필요",UNKNOWN:"원인 확인 중"};
const statuses: Record<string,string> = { UNMATCHED:"미대사",MATCHED:"대사 완료",PARTIAL:"부분대사",REVIEW:"검토 필요",DRAFT:"확정 대기",CONFIRMED:"확정",UNMATCHED_MATCH:"해제",IMPORTED:"자료 접수",RECONCILING:"대사 진행",CLOSED:"명세 마감",CAPTURED:"매입 완료",AUTHORIZED:"승인",CANCELLED:"승인 취소",REFUNDED:"환불",REVERSED:"승인 철회" };
const reasons: Record<string,string> = { AMOUNT_EXACT:"금액 일치",PARTIAL_AMOUNT:"부분 금액",DATE_EXACT:"거래일 일치",DATE_NEAR:"거래일 근접",REFERENCE_EXACT:"참조번호 일치",COUNTERPARTY_EXACT:"거래처 일치" };

export function BankWorkspace({ company, kind }: { company: Company; kind:"BANK"|"CARD" }) {
  const [accounts,setAccounts]=useState<Account[]>([]);
  const [coa,setCoa]=useState<Coa[]>([]);
  const [account,setAccount]=useState("");
  const [statements,setStatements]=useState<Statement[]>([]);
  const [statement,setStatement]=useState("");
  const [sources,setSources]=useState<Source[]>([]);
  const [matches,setMatches]=useState<Match[]>([]);
  const [candidates,setCandidates]=useState<Candidate[]>([]);
  const [selected,setSelected]=useState<Record<string,string>>({});
  const [summary,setSummary]=useState<Summary>();
  const [items,setItems]=useState<Item[]>([]);
  const [receipt,setReceipt]=useState<Receipt>();
  const [dialog,setDialog]=useState(false);
  const [cardUsage,setCardUsage]=useState<"CORPORATE"|"MERCHANT">("CORPORATE");
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [revision,setRevision]=useState(0);
  const [asOf,setAsOf]=useState("2026-12-31");
  const requestKey=useRef<{signature:string;key:string}|null>(null);
  const canManage=company.permissions.includes("reconciliation.manage");
  const canMap=company.permissions.includes("control_account.manage");
  const accountPath=kind==="BANK"?"bank-accounts":"card-accounts";
  const headers={"X-Company-ID":company.id};
  const scope=useRef(company.id); scope.current=company.id;

  useEffect(()=>{
    let active=true;
    Promise.all([
      authenticatedRequest<Account[]>(`/${accountPath}`,{headers:{"X-Company-ID":company.id}}),
      authenticatedRequest<Statement[]>("/bank-statements",{headers:{"X-Company-ID":company.id}}),
      authenticatedRequest<Match[]>("/reconciliations",{headers:{"X-Company-ID":company.id}}),
      company.permissions.includes("account.read")?authenticatedRequest<Coa[]>("/accounts",{headers:{"X-Company-ID":company.id}}):Promise.resolve([]),
    ]).then(([values,statements,matches,coa])=>{if(active){setAccounts(values);setStatements(statements);setMatches(matches);setCoa(coa);}})
      .catch(reason=>{if(active)setError(reason instanceof Error?reason.message:"자료를 불러오지 못했습니다.");})
      .finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[company.id,company.permissions,accountPath,revision]);

  useEffect(()=>{
    let active=true;
    const path=kind==="BANK"?(statement?`/bank-statements/${statement}/transactions`:null):(account?`/card-transactions?account_id=${account}`:null);
    if(path)void authenticatedRequest<Source[]>(path,{headers:{"X-Company-ID":company.id}}).then(values=>{if(active)setSources(values);}).catch(reason=>{if(active)setError(reason instanceof Error?reason.message:"원천 자료를 불러오지 못했습니다.");});
    return()=>{active=false;};
  },[company.id,kind,account,statement,revision]);

  async function command<T>(path:string,body:object):Promise<T>{
    const signature=JSON.stringify([company.id,path,body]);
    if(requestKey.current?.signature!==signature)requestKey.current={signature,key:crypto.randomUUID()};
    return authenticatedRequest<T>(path,{method:"POST",headers:{...headers,"Idempotency-Key":requestKey.current.key},body:JSON.stringify(body)});
  }
  async function run(task:()=>Promise<void>){
    const companyId=company.id;setBusy(true);setError("");setNotice("");
    try{await task();if(scope.current===companyId){requestKey.current=null;setRevision(v=>v+1);}}
    catch(reason){if(scope.current===companyId)setError(reason instanceof Error?reason.message:"처리하지 못했습니다. 최신 내용을 확인하고 다시 시도해 주세요.");}
    finally{if(scope.current===companyId)setBusy(false);}
  }
  function changeAccount(value:string){setItems([]);setAccount(value);setStatement("");setSources([]);setCandidates([]);setSelected({});setSummary(undefined);}
  function changeStatement(value:string){setItems([]);setStatement(value);setSources([]);setCandidates([]);setSelected({});setSummary(undefined);}
  async function refreshSummary(){
    const path=kind==="BANK"?`/bank-statements/${statement}/summary`:`/card-accounts/${account}/summary?as_of=${asOf}`;
    setSummary(await authenticatedRequest<Summary>(path,{headers}));
    if(kind==="BANK")setItems(await authenticatedRequest<Item[]>(`/bank-statements/${statement}/items`,{headers}));
  }
  function createAccount(event:FormEvent<HTMLFormElement>){
    event.preventDefault();const form=new FormData(event.currentTarget);
    void run(async()=>{const value=await command<Account>(`/${accountPath}`,{institution_code:form.get("institution"),alias:form.get("alias"),control_account_id:form.get("control"),usage_type:kind==="CARD"?cardUsage:"CORPORATE"});changeAccount(value.id);setDialog(false);setNotice("별칭과 장부 계정 연결을 저장했습니다.");});
  }
  function importSources(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!receipt)return;const form=new FormData(event.currentTarget);
    const body={account_id:account,import_id:receipt.import_id,receipt_id:receipt.id,source_digest:receipt.source_digest,confirmed_version:receipt.confirmed_version};
    void run(async()=>{if(kind==="BANK"){const value=await command<Statement>("/bank-statements/imports",{...body,statement_start:form.get("start"),statement_end:form.get("end"),opening_balance:form.get("opening"),closing_balance:form.get("closing")});changeStatement(value.id);}else await command("/card-transactions/imports",body);setReceipt(undefined);setNotice("원천 자료를 생성했습니다. 후보를 확인한 뒤 대사를 확정해 주세요.");});
  }
  function findCandidates(){
    void run(async()=>{let values:Candidate[];
      if(kind==="BANK")values=await command< Candidate[]>(`/bank-statements/${statement}/match-candidates`,{});
      else values=(await Promise.all(sources.map(source=>command<Candidate[]>(`/card-transactions/${source.id}/match-candidates`,{})))).flat();
      setCandidates(values);setSelected({});setNotice(values.length?"후보는 자동 확정되지 않습니다. 원천과 대상을 검토해 주세요.":"일치하는 후보가 없습니다. 기존 거래·수금·지급 자료를 확인해 주세요.");
    });
  }
  function saveMatch(){void run(async()=>{
    const lines=candidates.flatMap((candidate,index)=>selected[String(index)]?[{source_type:kind,source_id:candidate.source_id,target_type:candidate.target_type,target_id:candidate.target_id,amount:selected[String(index)],source_version:candidate.source_version,target_version:candidate.target_version}]:[]);
    await command("/reconciliations",{lines});setCandidates([]);setSelected({});setNotice("대사 초안을 저장했습니다. 아래에서 검토 후 확정하세요.");
  });}
  const visibleMatches=matches.filter(match=>match.lines.some(line=>sources.some(source=>source.id===line.source_id)));
  if(loading)return <section className="panel" role="status">대사 자료를 불러오고 있습니다…</section>;
  return <section className="panel">
    <h2>{kind==="BANK"?"은행 명세 대사":"카드 원천 대사"}</h2>
    <p>원천 거래와 기존 회계 자료를 연결합니다. 대사 확정은 전표의 승인·장부 반영과 별개입니다.</p>
    <label>{kind==="BANK"?"계좌":"카드"}<select value={account} onChange={event=>changeAccount(event.target.value)} disabled={busy}><option value="">선택하세요</option>{accounts.map(value=><option key={value.id} value={value.id}>{value.alias}</option>)}</select></label>
    {canMap&&<button onClick={()=>setDialog(true)} disabled={busy}>별칭과 장부 계정 연결</button>}
    {!accounts.length&&<p>등록된 별칭이 없습니다. 회사 관리자에게 장부 계정 연결을 요청하세요. 원계좌·카드번호는 입력하지 않습니다.</p>}
    {kind==="BANK"&&account&&<label>명세 기간<select value={statement} onChange={event=>changeStatement(event.target.value)} disabled={busy}><option value="">선택하세요</option>{statements.filter(value=>value.bank_account_id===account).map(value=><option key={value.id} value={value.id}>{value.statement_start} ~ {value.statement_end} · {statuses[value.status]??"검토 필요"}</option>)}</select></label>}
    {account&&canManage&&company.permissions.includes("import.create")&&<details><summary>새 원천 파일 가져오기</summary><DataImport key={`${company.id}:${kind}`} company={company} financialKind={kind} onConfirmed={setReceipt}/></details>}
    {receipt&&<form onSubmit={importSources}><h3>확인 자료 연결</h3>{kind==="BANK"&&<><label>시작일<input name="start" type="date" required/></label><label>종료일<input name="end" type="date" required/></label><label>기초잔액<input name="opening" inputMode="decimal" required defaultValue="0"/></label><label>기말잔액<input name="closing" inputMode="decimal" required/></label></>}<button disabled={busy||!account}>원천 자료 생성</button></form>}
    {(statement||(kind==="CARD"&&account))&&<>
      <h3>원천 거래</h3>{!sources.length?<p>이 기간에 원천 거래가 없습니다.</p>:<table><thead><tr><th>거래일</th><th>원천 참조</th><th>거래처·사용처</th><th>입출금</th><th>금액</th><th>대사 금액</th><th>상태</th></tr></thead><tbody>{sources.map(value=><tr key={value.id}><td>{value.occurred_at.slice(0,10)}</td><td>{value.source_id}</td><td>{value.counterparty_text||value.description}</td><td>{value.direction==="IN"?"입금·환불":"출금·사용"}</td><td>{displayAmount(value.amount)}</td><td>{displayAmount(value.matched_amount)}</td><td>{statuses[value.reconciliation_status]??"검토 필요"}{kind==="CARD"&&` · ${statuses[value.source_status]??"검토 필요"}`}</td></tr>)}</tbody></table>}
      <button disabled={busy||!sources.length} onClick={findCandidates}>대사 후보 확인</button>
      {!!candidates.length&&<><h3>후보 검토</h3><p>한 원천을 여러 대상에, 여러 원천을 한 대상에 연결할 수 있습니다. 남은 금액 검증은 서버에서 수행합니다.</p><table><thead><tr><th>선택</th><th>원천</th><th>대상</th><th>점수·근거</th><th>배분 금액</th></tr></thead><tbody>{candidates.map((candidate,index)=><tr key={`${candidate.source_id}:${candidate.target_type}:${candidate.target_id}`}><td><input type="checkbox" aria-label={`후보 ${index+1} 선택`} checked={selected[String(index)]!==undefined} disabled={busy||!canManage} onChange={event=>setSelected(old=>{const next={...old};if(event.target.checked)next[String(index)]=candidate.suggested_amount;else delete next[String(index)];return next;})}/></td><td>{sources.find(source=>source.id===candidate.source_id)?.source_id}</td><td>{candidate.target_type==="TRANSACTION"?"거래":candidate.target_type==="COLLECTION"?"수금":"지급"} · {candidate.target_reference||candidate.target_id.slice(0,8)} · {candidate.target_date}</td><td>{candidate.score}점 · {candidate.classification==="AUTO_MATCHED"?"우선 검토 후보":"확인 필요"}<br/>{candidate.reasons.map(reason=>reasons[reason]??"조건 비교").join(" · ")}</td><td><input aria-label={`후보 ${index+1} 배분 금액`} inputMode="decimal" value={selected[String(index)]??candidate.suggested_amount} disabled={busy||selected[String(index)]===undefined} onChange={event=>setSelected(old=>({...old,[String(index)]:event.target.value}))}/></td></tr>)}</tbody></table><button disabled={busy||!canManage||!Object.keys(selected).length} onClick={saveMatch}>선택한 배분으로 초안 저장</button></>}
      <h3>대사 이력</h3>{!visibleMatches.length&&<p>아직 저장된 대사가 없습니다.</p>}{visibleMatches.map(match=><div key={match.id}><p>{match.status==="UNMATCHED"?"해제":statuses[match.status]??"검토 필요"} · {displayAmount(match.matched_amount)} · {match.lines.length}개 연결</p>{match.status==="DRAFT"&&canManage&&<button disabled={busy} onClick={()=>void run(async()=>{await command(`/reconciliations/${match.id}/confirm`,{expected_version:match.version});setNotice("대사를 확정했습니다.");})}>검토한 대사 확정</button>}{match.status==="CONFIRMED"&&canManage&&<form onSubmit={event=>{event.preventDefault();const form=new FormData(event.currentTarget);void run(async()=>{await command(`/reconciliations/${match.id}/unmatch`,{expected_version:match.version,reason:form.get("reason")});setNotice("사유를 보존하고 대사를 해제했습니다.");});}}><label>해제 사유<input name="reason" required maxLength={500}/></label><button disabled={busy}>대사 해제</button></form>}</div>)}
      {kind==="CARD"&&<label>조회 기준일<input type="date" value={asOf} onChange={event=>{setAsOf(event.target.value);setSummary(undefined);}}/></label>}
      {company.permissions.includes("ledger.read")&&<button disabled={busy} onClick={()=>void run(refreshSummary)}>장부와 잔액 비교</button>}
      {summary&&<div role="status"><h3>잔액 비교</h3><p>명세·원천 {displayAmount(summary.statement_balance??summary.source_balance??"0")} · 대사 원천 {displayAmount(summary.reconciled_source_balance)} · 장부 {displayAmount(summary.gl_balance)} · 차이 {displayAmount(summary.difference_amount)}</p><p>미대사 {summary.unmatched_count}건 · 부분대사 {summary.partial_count}건 · 검토 {summary.review_count}건 · 미해결 항목 {summary.reconciliation_item_count??0}건</p><p>{summary.blocker?"미해결 차이가 있습니다. 자동으로 장부를 보정하지 않습니다.":"원천과 장부 비교를 통과했습니다."}</p>{kind==="BANK"&&company.permissions.includes("bank_statement.close")&&<button disabled={busy||summary.blocker} onClick={()=>void run(async()=>{const current=statements.find(value=>value.id===statement);if(current)await command(`/bank-statements/${statement}/close`,{expected_version:current.version});setNotice("명세를 마감했습니다.");})}>검토한 명세 마감</button>}</div>}
    </>}
    {kind==="BANK"&&statement&&<section><h3>차이 원인과 검토 이력</h3><p>원인을 기록하거나 해결 처리해도 장부 금액은 바뀌지 않습니다.</p>{items.map(item=><div key={item.id}><p>{itemReasons[item.reason_code]??"확인 필요"} · {displayAmount(item.amount)} · {item.description} · {item.status==="OPEN"?"미해결":"해결 확인"}</p>{item.resolution_note&&<p>해결 근거: {item.resolution_note}</p>}{item.status==="OPEN"&&canManage&&<form onSubmit={event=>{event.preventDefault();const form=new FormData(event.currentTarget);void run(async()=>{await command(`/bank-statements/${statement}/items/${item.id}/resolve`,{expected_version:item.version,resolution_note:form.get("note")});await refreshSummary();});}}><label>해결 근거<input name="note" required maxLength={500}/></label><button disabled={busy}>해결 확인 기록</button></form>}</div>)}{canManage&&<form onSubmit={event=>{event.preventDefault();const form=new FormData(event.currentTarget);void run(async()=>{await command(`/bank-statements/${statement}/items`,{reason_code:form.get("reason"),amount:form.get("amount"),description:form.get("description")});await refreshSummary();});}}><label>원인<select name="reason">{Object.entries(itemReasons).map(([code,label])=><option key={code} value={code}>{label}</option>)}</select></label><label>차이 금액<input name="amount" inputMode="decimal" required/></label><label>검토 내용<input name="description" required maxLength={500}/></label><button disabled={busy}>미해결 원인 기록</button></form>}</section>}
    {!canManage&&<p>조회 모드입니다. 대사 변경 권한은 회사 관리자에게 문의하세요.</p>}
    {busy&&<p role="status">처리 중입니다…</p>}{notice&&<p role="status">{notice}</p>}{error&&<div role="alert" className="error"><p>{error}</p><p>자료가 변경되었거나 충돌하면 최신 후보를 다시 조회하세요. 같은 작업은 안전하게 재시도할 수 있습니다.</p><button disabled={busy} onClick={()=>{setCandidates([]);setSelected({});setRevision(value=>value+1);}}>최신 자료 새로고침</button></div>}
    <OfficeDialog open={dialog} title="별칭과 장부 계정 연결" description="원계좌·카드번호 대신 별칭을 입력합니다." onClose={()=>setDialog(false)}><form onSubmit={createAccount}>{kind==="CARD"&&<label>카드 용도<select value={cardUsage} onChange={event=>setCardUsage(event.target.value as "CORPORATE"|"MERCHANT")}><option value="CORPORATE">법인카드 사용 · 미지급금</option><option value="MERCHANT">카드매출 수납 · 정산채권</option></select></label>}<label>기관 코드<input name="institution" required maxLength={30}/></label><label>별칭<input name="alias" required maxLength={80}/></label><label>장부 통제계정<select name="control" required><option value="">선택하세요</option>{coa.filter(value=>value.posting_allowed&&value.status==="ACTIVE"&&value.account_type===(kind==="BANK"||cardUsage==="MERCHANT"?"ASSET":"LIABILITY")).map(value=><option key={value.id} value={value.id}>{value.account_name}</option>)}</select></label><button disabled={busy}>연결 저장</button></form></OfficeDialog>
  </section>;
}
