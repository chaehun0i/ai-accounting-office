"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";
import { formatMoney, type Period } from "./model";
import type { DividendDeclaration, DividendPayment } from "./equity-model";
import { canLinkPayment, dividendIssues, type DividendSource, type PaymentSources } from "./dividend-model";

export function DividendWorkspace({ company, period, onChanged }: {
  company: Company; period: Period; onChanged: () => void;
}) {
  const [sources, setSources] = useState<DividendSource[]>([]);
  const [declarations, setDeclarations] = useState<DividendDeclaration[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [declarationId, setDeclarationId] = useState("");
  const [paymentSources, setPaymentSources] = useState<PaymentSources | null>(null);
  const [payments, setPayments] = useState<DividendPayment[]>([]);
  const [eventId, setEventId] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const canWrite = company.permissions.includes("financial_statement.generate");
  // Parent keys this workspace by company/period. Cleanup also isolates late responses.
  const [lifetime] = useState(() => ({ active: true }));
  useEffect(() => { lifetime.active = true; return () => { lifetime.active = false; }; }, [lifetime]);
  const failure = (reason: unknown) => reason instanceof ApiError ? reason.message : "배당 원천을 확인하지 못했습니다.";

  useEffect(() => {
    let active = true;
    setLoading(true); setError(""); setSourceId("");
    const headers = { "X-Company-ID": company.id };
    Promise.all([
      authenticatedRequest<DividendSource[]>(`/equity/dividend-sources?period_id=${period.id}`, { headers }),
      authenticatedRequest<DividendDeclaration[]>("/equity/dividends", { headers }),
    ]).then(([sourceRows, rows]) => {
      if (!active) return;
      setSources(sourceRows); setDeclarations(rows);
      setDeclarationId(current => rows.some(row => row.id === current) ? current : rows[0]?.id ?? "");
    }).catch(reason => { if (active) setError(failure(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company.id, period.id, revision]);

  useEffect(() => {
    let active = true;
    setPaymentSources(null); setPayments([]); setEventId("");
    if (!declarationId) return () => { active = false; };
    const headers = { "X-Company-ID": company.id };
    Promise.all([
      authenticatedRequest<PaymentSources>(`/equity/dividends/${declarationId}/payment-sources?period_id=${period.id}`, { headers }),
      authenticatedRequest<DividendPayment[]>(`/equity/dividends/${declarationId}/payments`, { headers }),
    ]).then(([candidates, rows]) => {
      if (!active || candidates.declaration_id !== declarationId || candidates.period_id !== period.id) return;
      setPaymentSources(candidates); setPayments(rows);
    }).catch(reason => { if (active) setError(failure(reason)); });
    return () => { active = false; };
  }, [company.id, period.id, declarationId, revision]);

  async function submit(path: string, payload: object) {
    setBusy(true); setError("");
    try {
      await authenticatedRequest(path, { method: "POST", headers: { "X-Company-ID": company.id }, body: JSON.stringify(payload) });
      if (lifetime.active) { setRevision(value => value + 1); onChanged(); }
    } catch (reason) { if (lifetime.active) setError(failure(reason)); }
    finally { if (lifetime.active) setBusy(false); }
  }
  const source = sources.find(item => item.journal_id === sourceId && item.status === "AVAILABLE");
  function declare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!source || !canWrite) return;
    const form = new FormData(event.currentTarget);
    void submit("/equity/dividends", { source_journal_id: source.journal_id,
      total_amount: source.amount, resolution_date: form.get("resolution_date"), payable_date: form.get("payable_date") || null });
  }
  return <details><summary>배당결의와 실제 지급 원천</summary>
    <p>현재 기간의 승인·POSTED 결의 전표를 선택합니다. 실제 현금유출은 별도 지급기간의 CF 원천으로 연결하며 전표를 자동 생성하지 않습니다.</p>
    {error && <p role="alert">{error}</p>}
    <button disabled={busy || loading} onClick={() => setRevision(value => value + 1)}>원천 새로 확인</button>
    {loading ? <p role="status">배당 원천 확인 중…</p> : <>
      {canWrite && <form onSubmit={declare}>
        <label>결의 전표 <select value={sourceId} onChange={event => setSourceId(event.target.value)} required>
          <option value="">원천 선택</option>{sources.map(item => <option key={item.journal_id} value={item.journal_id} disabled={item.status !== "AVAILABLE"}>
            {item.entry_date} · {item.journal_no ?? item.journal_id} · {formatMoney(item.amount)} {item.status === "LINKED" ? "(등록됨)" : ""}
          </option>)}
        </select></label>
        {source && <p>{source.description} · 원천 금액 {formatMoney(source.amount)} · 증빙 {source.evidence_ids.join(", ") || "없음"}</p>}
        <label>결의일 <input key={sourceId} name="resolution_date" type="date" defaultValue={source?.entry_date ?? period.start_date} max={source?.entry_date} required /></label>
        <label>지급 예정일 <input name="payable_date" type="date" /></label>
        <button disabled={busy || !source}>검증된 결의 등록</button>
      </form>}
      {sources.length === 0 && <p>현재 기간에 연결 가능한 결의 전표가 없습니다. 이익잉여금 계정 매핑과 승인된 전표를 확인하세요. <Link href="/journals">전표 확인</Link></p>}
      <label>지급을 확인할 결의 <select value={declarationId} disabled={busy} onChange={event => { setDeclarationId(event.target.value); setPaymentSources(null); setPayments([]); setEventId(""); }}>
        <option value="">결의 선택</option>{declarations.map(item => <option key={item.id} value={item.id}>{item.resolution_date} · {formatMoney(item.total_amount)} · {item.status}</option>)}
      </select></label>
      {paymentSources && <>
        <p>전체 연결 지급 {formatMoney(paymentSources.paid_amount)} · 결의 잔액 {formatMoney(paymentSources.remaining_amount)} · 지급 원천 조회기간 {period.start_date} ~ {period.end_date}</p>
        <p>후속 기간 지급은 상단 회계기간을 변경하고 같은 결의를 선택하세요.</p>
        {paymentSources.issue && <p role="status">{dividendIssues[paymentSources.issue] ?? paymentSources.issue} <Link href="/financial-statements">CF 확인</Link></p>}
        <ul>{paymentSources.candidates.map(item => <li key={item.event_id}>
          {canWrite && <input type="radio" name="dividend-payment" aria-label={`${item.journal_no ?? item.journal_id} 지급 선택`} checked={eventId === item.event_id}
            disabled={busy || !canLinkPayment(paymentSources, item.event_id)} onChange={() => setEventId(item.event_id)} />}
          {item.entry_date} · {item.journal_no ?? item.journal_id} · {formatMoney(item.amount)} · {item.issue ? dividendIssues[item.issue] ?? item.issue : "연결 가능"} · 증빙 {item.evidence_id ?? "없음"}
        </li>)}</ul>
        {canWrite && <button disabled={busy || !canLinkPayment(paymentSources, eventId)} onClick={() => void submit(`/equity/dividends/${declarationId}/payments`, { cash_flow_event_id: eventId })}>실제 지급 연결</button>}
        <p>CF 원천 {paymentSources.statement_id ?? "없음"} · digest {paymentSources.source_digest ?? "없음"}</p>
      </>}
      <ul>{payments.map(item => <li key={item.id}>연결 지급 {item.payment_date} · {formatMoney(item.amount)} · 전표 {item.journal_id}</li>)}</ul>
      <Link href="/journals">전표·증빙 확인</Link>
    </>}
  </details>;
}
