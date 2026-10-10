"use client";
import { useEffect, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
type Transaction = {id:string; transaction_date:string; accounting_date:string; description:string; amount:string; direction:string; version:number; evidence_id:string|null; import_id:string|null};
export function TransactionWorkspace({company}:{company:Company}) {
 const [rows,setRows]=useState<Transaction[]>([]),[selected,setSelected]=useState<Transaction|null>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 const [from,setFrom]=useState("2025-01-01"),[to,setTo]=useState("2025-12-31");
 useEffect(()=>{let active=true; if(!company.permissions.includes("transaction.read"))return;
 authenticatedRequest<Transaction[]>(`/transactions?date_from=${from}&date_to=${to}`,{headers:{"X-Company-ID":company.id}}).then(r=>{if(active)setRows(r)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false};},[company.id,company.permissions,from,to,revision]);
 async function save(event:FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setError("");const form=new FormData(event.currentTarget);
 try{await authenticatedRequest("/transactions",{method:"POST",headers:{"X-Company-ID":company.id},body:JSON.stringify({transaction_date:form.get("date"),accounting_date:form.get("date"),description:form.get("description"),amount:form.get("amount"),direction:form.get("direction"),source_id:crypto.randomUUID()})});setRevision(r=>r+1);}catch(e){setError(e instanceof Error?e.message:"거래를 저장하지 못했습니다.")}finally{setBusy(false)}}
 if(!company.permissions.includes("transaction.read"))return null;
 return <section className="panel"><h2>회계 거래</h2><p>거래를 기록한 뒤 별도의 전표를 작성하고 승인받아 장부에 반영합니다.</p>
 <label>조회 시작일<input type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label><label>조회 종료일<input type="date" value={to} onChange={e=>setTo(e.target.value)}/></label>
 {error&&<p role="alert">{error}</p>}{company.permissions.includes("transaction.create")&&<form onSubmit={save}><label>거래일<input name="date" type="date" required defaultValue={from}/></label><label>내용<input name="description" required maxLength={2000}/></label><label>금액<input name="amount" inputMode="decimal" required pattern="[0-9]+([.][0-9]{1,4})?"/></label><label>자금 방향<select name="direction"><option value="INFLOW">들어온 금액</option><option value="OUTFLOW">나간 금액</option></select></label><button disabled={busy}>{busy?"저장 중…":"거래 저장"}</button></form>}
 {rows.length===0?<p>조회 기간에 등록된 거래가 없습니다.</p>:<ul>{rows.map(r=><li key={r.id}><button onClick={()=>setSelected(r)}>{r.transaction_date} · {r.description} · {r.amount}원</button></li>)}</ul>}
 {selected&&<article><h3>거래 상세</h3><p>{selected.description}</p><p>증빙: {selected.evidence_id??"연결된 증빙 없음"}</p><p>가져오기 출처: {selected.import_id??"직접 입력"}</p><p>거래 식별자: {selected.id}</p></article>}</section>;
}
