"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { localDate } from "@/shared/calendar";
import { OfficeDialog } from "@/shared/ui/dialog";
import { allocationSummary, agingLabel, collected, financeStatus, type Obligation, type Settlement } from "./model";

type Journal = { id: string; journal_no: string; description: string; entry_date: string; status: string };
type Aging = { total_outstanding: string; overdue: string; due_7d: string; due_30d: string };
type Reconciliation = { status: string; subledger_amount: string; gl_amount: string; difference: string; rows: { account_id: string; account_name: string; status: string; difference: string }[] };

export function FinanceWorkspace({ company, kind }: { company: Company; kind: "AR" | "AP" }) {
  const targetPath = kind === "AR" ? "receivables" : "payables";
  const settlementPath = kind === "AR" ? "collections" : "payments";
  const title = kind === "AR" ? "채권" : "채무";
  const action = kind === "AR" ? "수금" : "지급";
  const canRecord = company.permissions.includes(kind === "AR" ? "collection.record" : "payment.record");
  const [asOf, setAsOf] = useState(localDate);
  const [rows, setRows] = useState<Obligation[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [journals, setJournals] = useState<Journal[]>([]);
  const [aging, setAging] = useState<Aging | null>(null);
  const [reconciliation, setReconciliation] = useState<Reconciliation | null>(null);
  const [selected, setSelected] = useState<Obligation | null>(null);
  const [editing, setEditing] = useState<Settlement | null>(null);
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [dialog, setDialog] = useState<"source" | "settlement" | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const requestKey = useRef<{ fingerprint: string; key: string } | null>(null);
  const headers = { "X-Company-ID": company.id };

  useEffect(() => {
    let active = true;
    const scope = { headers: { "X-Company-ID": company.id } };
    Promise.all([
      authenticatedRequest<Obligation[]>(`/${targetPath}?as_of=${asOf}`, scope),
      authenticatedRequest<Settlement[]>(`/${settlementPath}`, scope),
      authenticatedRequest<Aging>(`/${targetPath}/aging?as_of=${asOf}`, scope),
      authenticatedRequest<Reconciliation>(`/${targetPath}/reconciliation?as_of=${asOf}`, scope),
      company.permissions.includes("journal.read") ? authenticatedRequest<Journal[]>(`/journals?date_from=${asOf.slice(0, 4)}-01-01&date_to=${asOf.slice(0, 4)}-12-31`, scope) : Promise.resolve([]),
    ]).then(([values, records, summary, matched, sources]) => {
      if (!active) return;
      setRows(values); setSettlements(records); setAging(summary); setReconciliation(matched);
      setJournals(sources.filter(journal => journal.status === "POSTED")); setError("");
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "내용을 불러오지 못했습니다."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company.id, company.permissions, targetPath, settlementPath, asOf, revision]);

  async function command<T>(path: string, body: object): Promise<T> {
    const fingerprint = JSON.stringify([path, body]);
    if (requestKey.current?.fingerprint !== fingerprint) requestKey.current = { fingerprint, key: crypto.randomUUID() };
    return authenticatedRequest<T>(path, { method: "POST", headers: { ...headers, "Idempotency-Key": requestKey.current.key }, body: JSON.stringify(body) });
  }

  async function run(task: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await task(); requestKey.current = null; setRevision(value => value + 1); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "저장하지 못했습니다. 최신 내용을 다시 확인해 주세요."); }
    finally { setBusy(false); }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    void run(async () => {
      if (dialog === "source") {
        await command(`/${targetPath}/from-journals`, { journal_id: form.get("journal"), due_date: form.get("due") });
        setNotice(`${title}을 등록했습니다.`);
      } else {
        const journal = journals.find(value => value.id === form.get("journal"));
        await command(`/${settlementPath}`, { journal_id: form.get("journal"), settlement_date: journal?.entry_date, total_amount: form.get("amount"), reference_no: form.get("reference") });
        setNotice(`${action} 기록을 만들었습니다. 대상별 금액을 배분한 뒤 확정해 주세요.`);
      }
      setDialog(null);
    });
  }

  function startAllocation(value: Settlement) {
    setEditing(value); setAmounts(Object.fromEntries(value.allocations.map(line => [line.target_id, line.allocated_amount])));
  }

  function saveAllocation() {
    if (!editing) return;
    void run(async () => {
      const allocations = rows.filter(row => amounts[row.id] && amounts[row.id] !== "0").map(row => ({ target_id: row.id, expected_version: row.version, allocated_amount: amounts[row.id] }));
      const result = await command<Settlement>(`/${settlementPath}/${editing.id}/allocations`, { expected_version: editing.version, allocations });
      setEditing(result); setAmounts(Object.fromEntries(result.allocations.map(line => [line.target_id, line.allocated_amount]))); setNotice("배분 내역을 저장했습니다. 확인 후 확정해 주세요.");
    });
  }

  function confirm() {
    if (!editing) return;
    void run(async () => {
      await command(`/${settlementPath}/${editing.id}/confirm`, { expected_version: editing.version });
      setEditing(null); setSelected(null); setNotice("배분을 확정했습니다. 잔액과 원장 대사 결과를 확인해 주세요.");
    });
  }

  let allocation = null;
  try { if (editing) allocation = allocationSummary(editing.total_amount, Object.values(amounts)); } catch { /* 잘못된 금액은 저장 전에 안내합니다. */ }
  const dirty = editing && JSON.stringify(Object.entries(amounts).filter(([, value]) => value && value !== "0").sort()) !== JSON.stringify(editing.allocations.map(line => [line.target_id, line.allocated_amount]).sort());

  return <section className="panel" aria-busy={loading || busy}>
    <div className="section-heading"><div><h2>{title} 관리</h2><p>장부에 반영된 전표를 기준으로 {action} 내역과 남은 금액을 확인합니다.</p></div>
      {canRecord && <div className="button-row"><button onClick={() => setDialog("source")} disabled={busy}>{title} 등록</button><button onClick={() => setDialog("settlement")} disabled={busy}>{action} 등록</button></div>}</div>
    <label>조회 기준일<input type="date" value={asOf} onChange={event => { setAsOf(event.target.value); setSelected(null); setLoading(true); }} /></label>
    {error && <div role="alert"><p>{error}</p><button onClick={() => { setLoading(true); setRevision(value => value + 1); }}>최신 내용 다시 불러오기</button></div>}
    {notice && <p role="status">{notice}</p>}
    {loading ? <p role="status">잔액을 불러오는 중입니다…</p> : <>
      {aging && <div className="summary-grid"><p>남은 금액 <strong>{aging.total_outstanding}원</strong></p><p>기한 경과 <strong>{aging.overdue}원</strong></p><p>7일 내 기한 <strong>{aging.due_7d}원</strong></p><p>30일 내 기한 <strong>{aging.due_30d}원</strong></p></div>}
      {rows.length === 0 ? <p>조회 기준일에 등록된 {title}이 없습니다. 확정 전표의 거래처와 계정을 확인한 뒤 등록해 주세요.</p> : <div className="table-scroll"><table><caption>{title} 잔액 · {asOf} 기준</caption><thead><tr><th>거래처</th><th>발생일</th><th>기한</th><th>발생액</th><th>{action}액</th><th>남은 금액</th><th>기한 경과</th><th>상태</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td><button onClick={() => setSelected(row)}>{row.counterparty_name}</button></td><td>{row.origin_date}</td><td>{row.due_date}</td><td>{row.original_amount}</td><td>{collected(row)}</td><td>{row.outstanding_amount}</td><td>{row.status === "SETTLED" ? "—" : agingLabel(row.due_date, asOf)}</td><td>{financeStatus[row.status]}</td></tr>)}</tbody></table></div>}
      <h3>원장과 잔액 대사</h3>{reconciliation && <><p role="status">{reconciliation.status === "MATCHED" ? "보조부와 원장 잔액이 일치합니다." : "잔액에 차이가 있습니다. 미등록 발생 전표 또는 미확정 배분을 확인해 주세요."}</p><p>보조부 {reconciliation.subledger_amount}원 · 원장 {reconciliation.gl_amount}원 · 차이 {reconciliation.difference}원</p><ul>{reconciliation.rows.map(row => <li key={row.account_id}>{row.account_name}: {row.status === "MATCHED" ? "일치" : `차이 ${row.difference}원`}</li>)}</ul></>}
      <h3>{action} 기록</h3><p>실제 은행 이체 기능이 아닙니다. 이미 확정한 회계 전표에 배분 근거를 연결합니다.</p>
      {!canRecord && <p>현재 권한으로는 조회만 가능합니다. 등록이 필요하면 회사 관리자에게 권한을 요청해 주세요.</p>}
      {settlements.length === 0 ? <p>등록된 {action} 기록이 없습니다.</p> : <ul>{settlements.map(value => <li key={value.id}>{value.settlement_date} · {value.total_amount}원 · {financeStatus[value.status]} · 미배분 {value.unapplied_amount}원 {canRecord && value.status === "DRAFT" && <button onClick={() => startAllocation(value)}>배분 검토</button>}</li>)}</ul>}
    </>}
    <OfficeDialog open={dialog !== null} onClose={() => setDialog(null)} busy={busy} title={dialog === "source" ? `${title} 등록` : `${action} 등록`} description="승인과 장부 반영이 끝난 전표를 선택해 주세요.">
      {error && <p role="alert">{error}</p>}
      <form onSubmit={submit}><label>확정 전표<select name="journal" required><option value="">전표 선택</option>{journals.map(journal => <option key={journal.id} value={journal.id}>{journal.journal_no} · {journal.entry_date} · {journal.description}</option>)}</select></label>
        {dialog === "source" ? <label>결제 기한<input name="due" type="date" required /></label> : <><label>{action}액<input name="amount" inputMode="decimal" pattern="[0-9]+([.][0-9]{1,4})?" required /></label><label>확인용 참조번호<input name="reference" maxLength={100} /></label></>}
        <button disabled={busy || journals.length === 0}>{busy ? "저장 중…" : "등록"}</button></form>
      {journals.length === 0 && <p>조회 기준연도의 확정 전표가 없습니다. 전표 메뉴에서 작성·승인·장부 반영을 먼저 진행해 주세요.</p>}
    </OfficeDialog>
    <OfficeDialog open={editing !== null} onClose={() => setEditing(null)} busy={busy} title={`${action} 배분`} description="대상별 금액을 입력하고 저장한 뒤 확정합니다. 초과 배분은 허용되지 않습니다.">
      {error && <p role="alert">{error}</p>}
      {editing && <><p>총액 {editing.total_amount}원 · 배분 {allocation?.allocated ?? "금액 확인 필요"}원 · 미배분 {allocation?.unapplied ?? "—"}원</p>
        {rows.filter(row => row.status !== "SETTLED").map(row => <label key={row.id}>{row.counterparty_name} · 남은 {row.outstanding_amount}원<input aria-label={`${row.counterparty_name} 배분액`} value={amounts[row.id] ?? ""} onChange={event => setAmounts(values => ({ ...values, [row.id]: event.target.value }))} inputMode="decimal" /></label>)}
        <button onClick={saveAllocation} disabled={busy || !allocation?.valid || !dirty}>배분 저장</button><button onClick={confirm} disabled={busy || !!dirty}>배분 확정</button><p>미배분액은 잔액으로 보존됩니다. 확정 후에는 이 기록의 배분을 수정할 수 없습니다.</p></>}
    </OfficeDialog>
    <OfficeDialog open={selected !== null} onClose={() => setSelected(null)} title={`${title} 상세`} description="발생 전표와 배분 내역을 통해 출처를 확인합니다.">
      {selected && <><h3>{selected.counterparty_name}</h3><p>남은 금액 {selected.outstanding_amount}원</p><Link href={`/journals?journal=${selected.origin_journal_id}`}>발생 전표 확인</Link><p>거래 출처: {selected.source_transaction_id ?? "직접 작성한 전표"}</p><p>파일 접수 출처: {selected.import_id ?? "파일 접수 출처 없음"}</p><p>연결 증빙 {selected.evidence_ids.length}건</p><ul>{settlements.filter(value => value.allocations.some(line => line.target_id === selected.id)).map(value => <li key={value.id}>{value.settlement_date} · {financeStatus[value.status]} · {value.allocations.find(line => line.target_id === selected.id)?.allocated_amount}원</li>)}</ul></>}
    </OfficeDialog>
  </section>;
}
