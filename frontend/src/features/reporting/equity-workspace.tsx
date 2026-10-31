"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";
import { formatMoney, type Account, type Period, type StatementSet } from "./model";
import {
  equityCell, equityIssueLabels, equityMovements,
  type DividendDeclaration, type DividendPayment, type EquityComponent, type EquityEvent,
  type EquityMapping, type EquityReadiness, type EquitySnapshot, type EquitySource,
} from "./equity-model";

const fail = (reason: unknown) => reason instanceof ApiError ? reason.message : "자본변동 원천을 불러오지 못했습니다.";
const componentTypes = [
  ["CONTRIBUTED_CAPITAL", "납입자본"], ["RETAINED_EARNINGS", "이익잉여금"],
  ["TREASURY_STOCK", "자기주식"], ["OTHER_EQUITY", "기타자본"],
  ["OCI_COMPONENT", "기타포괄손익"],
] as const;
const eventTypes = [
  "CAPITAL_CONTRIBUTION", "CAPITAL_REDUCTION", "DIVIDEND",
  "TREASURY_STOCK_ACQUIRE", "TREASURY_STOCK_DISPOSE", "PROFIT_TRANSFER",
  "OCI_TRANSFER", "OTHER_ADJUSTMENT",
] as const;

export function EquityWorkspace({ company, period, statementSet }: {
  company: Company; period: Period; statementSet: StatementSet | undefined;
}) {
  const [components, setComponents] = useState<EquityComponent[]>([]);
  const [mappings, setMappings] = useState<EquityMapping[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [events, setEvents] = useState<EquityEvent[]>([]);
  const [declarations, setDeclarations] = useState<DividendDeclaration[]>([]);
  const [payments, setPayments] = useState<Record<string, DividendPayment[]>>({});
  const [readiness, setReadiness] = useState<EquityReadiness | null>(null);
  const [history, setHistory] = useState<EquitySnapshot[]>([]);
  const [snapshotId, setSnapshotId] = useState("");
  const [snapshot, setSnapshot] = useState<EquitySnapshot | null>(null);
  const [sourceLine, setSourceLine] = useState<EquitySnapshot["lines"][number] | null>(null);
  const [sources, setSources] = useState<EquitySource[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const retry = useRef<{ source: string; key: string } | null>(null);
  const scope = `${company.id}:${period.id}`;
  const scopeRef = useRef(scope);
  scopeRef.current = scope;
  const selectedSnapshotRef = useRef(snapshotId);
  selectedSnapshotRef.current = snapshotId;
  const canGenerate = company.permissions.includes("financial_statement.generate");
  const headers = { "X-Company-ID": company.id };

  useEffect(() => {
    let active = true;
    setLoading(true); setBusy(false); setError(""); setNotice("");
    setComponents([]); setMappings([]); setAccounts([]); setEvents([]);
    setDeclarations([]); setPayments({}); setReadiness(null); setHistory([]);
    setSnapshot(null); setSnapshotId(""); setSources([]); setSourceLine(null);
    retry.current = null;
    Promise.all([
      authenticatedRequest<EquityComponent[]>("/equity/components", { headers: { "X-Company-ID": company.id } }),
      authenticatedRequest<EquityMapping[]>("/equity/mappings", { headers: { "X-Company-ID": company.id } }),
      authenticatedRequest<EquityEvent[]>(`/equity/events?period_id=${encodeURIComponent(period.id)}`, { headers: { "X-Company-ID": company.id } }),
      authenticatedRequest<DividendDeclaration[]>("/equity/dividends", { headers: { "X-Company-ID": company.id } }),
      authenticatedRequest<EquityReadiness>(`/equity/reconciliation?period_id=${encodeURIComponent(period.id)}`, { headers: { "X-Company-ID": company.id } }),
      authenticatedRequest<EquitySnapshot[]>(`/equity/statements?period_id=${encodeURIComponent(period.id)}`, { headers: { "X-Company-ID": company.id } }),
      canGenerate ? authenticatedRequest<Account[]>("/accounts", { headers: { "X-Company-ID": company.id } }) : Promise.resolve([]),
    ]).then(([componentRows, mappingRows, eventRows, dividendRows, status, snapshots, available]) => {
      if (!active) return;
      setComponents(componentRows); setMappings(mappingRows); setEvents(eventRows);
      setDeclarations(dividendRows); setReadiness(status); setHistory(snapshots);
      void Promise.all(dividendRows.map(async item => [item.id, await authenticatedRequest<DividendPayment[]>(
        `/equity/dividends/${item.id}/payments`, { headers: { "X-Company-ID": company.id } },
      )] as const)).then(rows => { if (active) setPayments(Object.fromEntries(rows)); })
        .catch(reason => { if (active) setError(fail(reason)); });
      setAccounts(available.filter(account => account.account_type === "EQUITY" && account.posting_allowed));
      setSnapshotId(snapshots[0]?.id ?? "");
    }).catch(reason => { if (active) setError(fail(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company.id, canGenerate, period.id, revision]);

  useEffect(() => {
    let active = true;
    setSnapshot(null); setSources([]); setSourceLine(null);
    if (!snapshotId) return () => { active = false; };
    authenticatedRequest<EquitySnapshot>(`/equity/statements/${snapshotId}`, { headers: { "X-Company-ID": company.id } })
      .then(value => { if (active && value.period_id === period.id) setSnapshot(value); })
      .catch(reason => { if (active) setError(fail(reason)); });
    return () => { active = false; };
  }, [company.id, period.id, snapshotId]);

  async function post(path: string, payload: object, message: string, key?: string) {
    const requestScope = scope;
    setBusy(true); setError(""); setNotice("");
    try {
      await authenticatedRequest(path, {
        method: "POST", headers: { ...headers, ...(key ? { "Idempotency-Key": key } : {}) },
        body: JSON.stringify(payload),
      });
      if (scopeRef.current === requestScope) {
        setNotice(message); setRevision(value => value + 1);
      }
    } catch (reason) { if (scopeRef.current === requestScope) setError(fail(reason)); }
    finally { if (scopeRef.current === requestScope) setBusy(false); }
  }

  function createComponent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void post("/equity/components", {
      component_code: form.get("component_code"), name: form.get("name"),
      component_type: form.get("component_type"), display_order: Number(form.get("display_order")),
    }, "자본 구성요소를 등록했습니다.");
  }

  function mapAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void post("/equity/mappings", {
      component_id: form.get("component_id"), account_id: form.get("account_id"),
      effective_from: period.start_date,
    }, "자본 계정을 구성요소에 연결했습니다.");
  }

  function classify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void post("/equity/events", {
      journal_line_id: form.get("journal_line_id"), event_type: form.get("event_type"),
    }, "POSTED 전표의 자본변동 원천을 분류했습니다.");
  }

  function declare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void post("/equity/dividends", {
      resolution_date: form.get("resolution_date"),
      payable_date: form.get("payable_date") || null,
      total_amount: form.get("total_amount"),
      source_journal_id: form.get("source_journal_id") || null,
    }, "배당결의를 기록했습니다. 실제 지급은 별도 CF 원천으로 연결합니다.");
  }

  function recordPayment(event: FormEvent<HTMLFormElement>, declarationId: string) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void post(`/equity/dividends/${declarationId}/payments`, {
      cash_flow_event_id: form.get("cash_flow_event_id"),
    }, "POSTED 지급 전표와 CF 재무활동 원천을 연결했습니다.");
  }

  async function generate() {
    if (!readiness?.source_digest || readiness.status !== "READY") return;
    if (retry.current?.source !== readiness.source_digest) {
      retry.current = { source: readiness.source_digest, key: crypto.randomUUID() };
    }
    await post("/equity/statements/generate", { period_id: period.id },
               "자본변동표 스냅샷을 생성했습니다.", retry.current.key);
  }

  async function drilldown(line: EquitySnapshot["lines"][number]) {
    if (!snapshot) return;
    const requestScope = scope;
    const statementId = snapshot.id;
    setSourceLine(line); setSources([]); setError("");
    try {
      const rows = await authenticatedRequest<EquitySource[]>(
        `/equity/statements/${statementId}/lines/${line.id}/sources`, { headers },
      );
      if (scopeRef.current === requestScope && selectedSnapshotRef.current === statementId) {
        setSources(rows);
      }
    } catch (reason) { if (scopeRef.current === requestScope) setError(fail(reason)); }
  }

  const currentSnapshot = snapshot?.snapshot_digest === readiness?.source_digest;
  const orderedComponents = [...components].sort((a, b) => a.display_order - b.display_order);
  const active = orderedComponents.filter(component => snapshot?.lines.some(line => line.component_id === component.id));

  return <section className="panel" aria-labelledby="equity-heading">
    <h2 id="equity-heading">자본변동표</h2>
    <p>CLOSED 기간 · 구성요소별 Roll-forward · 내부 검증용. 법정 승인·감사 완료 상태는 아닙니다.</p>
    {loading ? <p role="status">자본변동 원천과 대사를 확인하고 있습니다…</p> : <>
      {!statementSet && <p>현재 BS/IS 스냅샷을 먼저 생성해 주세요.</p>}
      {readiness && <div>
        <p role="status">대사 상태: <strong>{readiness.status}</strong></p>
        {readiness.issues.length > 0 && <ul>{readiness.issues.map(issue =>
          <li key={issue}>{equityIssueLabels[issue] ?? issue} <code>{issue}</code></li>)}</ul>}
        <p>BS 기말자본 {readiness.balance_sheet_equity === null ? "검증 전" : formatMoney(readiness.balance_sheet_equity)} · IS 당기순이익 {readiness.income_statement_profit === null ? "검증 전" : formatMoney(readiness.income_statement_profit)} · SCE 기말합계 {readiness.rollforward_equity === null ? "검증 전" : formatMoney(readiness.rollforward_equity)}</p>
      </div>}
      {canGenerate && <button disabled={busy || readiness?.status !== "READY" || !statementSet}
        onClick={() => void generate()}>자본변동표 생성</button>}
      {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}
      {canGenerate && <details><summary>자본 구성요소·계정 설정</summary>
        <ul>{orderedComponents.map(component => <li key={component.id}>{component.component_code} · {component.name} · v{component.version}</li>)}</ul>
        <form onSubmit={createComponent}><h3>구성요소 등록</h3>
          <label>코드 <input name="component_code" required pattern="[A-Z][A-Z0-9_]+" /></label>
          <label>이름 <input name="name" required /></label>
          <label>유형 <select name="component_type">{componentTypes.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
          <label>표시 순서 <input name="display_order" type="number" min="1" defaultValue={orderedComponents.length + 1} /></label>
          <button disabled={busy}>등록</button>
        </form>
        {orderedComponents.length > 0 && accounts.length > 0 && <form onSubmit={mapAccount}><h3>자본 계정 연결</h3>
          <label>구성요소 <select name="component_id">{orderedComponents.map(component => <option key={component.id} value={component.id}>{component.name}</option>)}</select></label>
          <label>계정 <select name="account_id">{accounts.map(account => <option key={account.id} value={account.id}>{account.account_code} {account.account_name}</option>)}</select></label>
          <button disabled={busy}>연결</button>
        </form>}
        <p>기준일 {period.start_date} · 연결 {mappings.filter(mapping => mapping.status === "ACTIVE").length}건</p>
      </details>}
      {canGenerate && <details><summary>자본변동 전표와 배당결의</summary>
        <p>전표 등록·승인·POSTED 처리는 <Link href="/journals">전표 화면</Link>에서 완료한 뒤 자본 라인 ID를 분류합니다.</p>
        <form onSubmit={classify}><label>POSTED 전표 라인 ID <input name="journal_line_id" required /></label>
          <label>변동 유형 <select name="event_type">{eventTypes.map(type => <option key={type}>{type}</option>)}</select></label>
          <button disabled={busy}>원천 분류</button></form>
        <h3>검증된 변동 이벤트</h3>{events.length === 0 ? <p>등록된 기간 변동이 없습니다.</p> :
          <ul>{events.map(item => <li key={item.id}>{item.event_date} · {item.event_type} · {formatMoney(item.amount)} · 전표 {item.source_journal_id}</li>)}</ul>}
        <form onSubmit={declare}><h3>배당결의</h3>
          <label>결의일 <input name="resolution_date" type="date" defaultValue={period.start_date} required /></label>
          <label>지급 예정일 <input name="payable_date" type="date" /></label>
          <label>금액 <input name="total_amount" type="number" step="0.0001" min="0.0001" required /></label>
          <label>POSTED 결의 전표 ID <input name="source_journal_id" /></label>
          <button disabled={busy}>결의 기록</button>
        </form>
        {declarations.map(item => <div key={item.id}><p>결의 {item.resolution_date} · {formatMoney(item.total_amount)} · {item.status} · 지급 예정 {item.payable_date ?? "미정"} · 현금 지급은 별도</p>
          {(payments[item.id] ?? []).map(payment => <p key={payment.id}>실제 지급 {payment.payment_date} · {formatMoney(payment.amount)} · 전표 {payment.journal_id} · CF 원천 {payment.cash_flow_event_id}</p>)}
          {item.status === "APPROVED" && <form onSubmit={event => recordPayment(event, item.id)}><label>CF 재무활동 현금유출 이벤트 ID <input name="cash_flow_event_id" required /></label><button disabled={busy}>실제 지급 연결</button></form>}
        </div>)}
      </details>}
      {history.length > 0 && <div><label>자본변동표 이력 <select value={snapshotId} onChange={event => setSnapshotId(event.target.value)}>
        {history.map(item => <option key={item.id} value={item.id}>마감 v{item.close_version} · {item.generated_at.slice(0, 10)} · {item.snapshot_digest.slice(0, 12)}</option>)}</select></label></div>}
      {snapshot && <div><p>{currentSnapshot ? "현재 원천 대사 완료" : "과거 스냅샷 · 현재 원천과 다름"} · {snapshot.status} · digest {snapshot.snapshot_digest.slice(0, 12)}…</p>
        <div className="table-scroll"><table><caption>구성요소별 자본변동표</caption><thead><tr><th scope="col">변동 유형</th>{active.map(component => <th scope="col" key={component.id}>{component.name}</th>)}</tr></thead>
          <tbody>{equityMovements.map(([movement, label]) => <tr key={movement}><th scope="row">{label}</th>{active.map(component => {
            const line = equityCell(snapshot, component.id, movement);
            return <td key={component.id}>{line ? <><span>{formatMoney(line.amount)}</span> <button onClick={() => void drilldown(line)} aria-label={`${label} ${component.name} 원천 보기`}>원천</button></> : "—"}</td>;
          })}</tr>)}</tbody></table></div>
        <Link href="/reports">Report Center에서 PDF·XLSX·CSV 내보내기</Link>
      </div>}
      {sourceLine && <div><h3>{sourceLine.movement_type} 원천</h3>{sources.length === 0 ? <p>연결된 전표가 없습니다.</p> :
        <table><thead><tr><th scope="col">원천</th><th scope="col">금액</th><th scope="col">증빙</th></tr></thead><tbody>{sources.map((item, index) =>
          <tr key={`${item.journal_line_id ?? item.income_statement_id}:${index}`}><td>{item.journal_id ? <>{item.entry_date} · {item.account_code} {item.account_name} · {item.journal_no ?? item.journal_id} <Link href="/journals">전표 보기</Link></> : <>IS 스냅샷 {item.income_statement_id} <Link href="/financial-statements">손익계산서 보기</Link></>}</td><td>{formatMoney(item.amount)}</td><td>{item.evidence_ids.join(", ") || "—"}</td></tr>)}</tbody></table>}</div>}
    </>}
  </section>;
}
