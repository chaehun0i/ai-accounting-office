"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import { canAskCashFlowLine, financialStatementAskHref } from "@/features/ai-team/context";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";
import { formatMoney, type Period, type StatementSet } from "./model";
import { cashGenerationPayload, cashIssueLabel, cashLineLabel, type CashBridge, type CashDrilldown, type CashLine, type CashPolicy, type CashPreflight, type CashStatement, type DisposalSource, type NonCashDisclosure } from "./cash-flow-model";

const failure = (error: unknown) => error instanceof ApiError ? error.message : "현금흐름표를 불러오지 못했습니다.";

export function CashFlowWorkspace({ company, period, statementSet }: { company: Company; period: Period; statementSet: StatementSet | undefined }) {
  const [preflight, setPreflight] = useState<CashPreflight | null>(null);
  const [bridge, setBridge] = useState<CashBridge | null>(null);
  const [snapshots, setSnapshots] = useState<CashStatement[]>([]);
  const [policies, setPolicies] = useState<CashPolicy[]>([]);
  const [disclosures, setDisclosures] = useState<NonCashDisclosure[]>([]);
  const [disposals, setDisposals] = useState<DisposalSource[]>([]);
  const [frozenDisclosures, setFrozenDisclosures] = useState<NonCashDisclosure[]>([]);
  const [frozenDisposals, setFrozenDisposals] = useState<DisposalSource[]>([]);
  const [policyFrom, setPolicyFrom] = useState(period.start_date);
  const [interestPaid, setInterestPaid] = useState<CashPolicy["interest_paid"]>("OPERATING");
  const [interestReceived, setInterestReceived] = useState<CashPolicy["interest_received"]>("OPERATING");
  const [incomeTaxPaid, setIncomeTaxPaid] = useState<CashPolicy["income_tax_paid"]>("OPERATING");
  const [snapshotId, setSnapshotId] = useState("");
  const [lines, setLines] = useState<CashLine[]>([]);
  const [lineId, setLineId] = useState("");
  const [trace, setTrace] = useState<CashDrilldown | null>(null);
  const [loading, setLoading] = useState(true);
  const [linesLoading, setLinesLoading] = useState(false);
  const [traceLoading, setTraceLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [currentStale, setCurrentStale] = useState(false);
  const [revision, setRevision] = useState(0);
  const mounted = useRef(false);
  const traceRequest = useRef(0);
  const retry = useRef<{ fingerprint: string; key: string } | null>(null);
  const canRead = company.permissions.includes("financial_statement.read");
  const canGenerate = company.permissions.includes("financial_statement.generate");
  const snapshot = snapshots.find(value => value.id === snapshotId);
  const payload = cashGenerationPayload(period, statementSet, preflight, bridge);

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  useEffect(() => {
    let active = true;
    setLoading(true); setError(""); setCurrentStale(false); setPreflight(null); setBridge(null); setSnapshots([]); setSnapshotId("");
    setPolicies([]); setDisclosures([]); setDisposals([]); setFrozenDisclosures([]); setFrozenDisposals([]); setPolicyFrom(period.start_date);
    setLines([]); setLineId(""); setTrace(null); traceRequest.current += 1;
    if (!canRead || period.status !== "CLOSED") { setLoading(false); return () => { active = false; }; }
    const headers = { "X-Company-ID": company.id };
    const query = new URLSearchParams({ period_id: period.id });
    Promise.all([
      authenticatedRequest<CashPreflight>(`/cash-flow/preflight?${query}`, { headers }),
      authenticatedRequest<CashBridge>(`/cash-flow/indirect-bridge?${query}`, { headers }),
      authenticatedRequest<CashPolicy[]>("/cash-flow/policies", { headers }),
      authenticatedRequest<NonCashDisclosure[]>(`/cash-flow/non-cash-disclosures?${query}`, { headers }),
      authenticatedRequest<DisposalSource[]>(`/cash-flow/disposal-sources?${query}`, { headers }),
      authenticatedRequest<CashStatement>(`/cash-flow/statements?${query}`, { headers }).then(value => [value]).catch(reason => {
        if (reason instanceof ApiError && reason.status === 404) return [];
        if (reason instanceof ApiError && reason.status === 409) { if (active) setCurrentStale(true); return []; }
        throw reason;
      }),
    ]).then(([check, reconciliation, policyRows, disclosureRows, disposalRows, values]) => {
      if (!active) return;
      setPreflight(check); setBridge(reconciliation); setSnapshots(values); setSnapshotId(values[0]?.id ?? "");
      setPolicies(policyRows); setDisclosures(disclosureRows); setDisposals(disposalRows);
    }).catch(reason => { if (active) setError(failure(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company.id, period.id, period.status, canRead, revision]);

  useEffect(() => {
    let active = true;
    setLines([]); setLineId(""); setTrace(null); setTraceLoading(false); setFrozenDisclosures([]); setFrozenDisposals([]); traceRequest.current += 1;
    if (!snapshotId || !canRead) { setLinesLoading(false); return () => { active = false; }; }
    setLinesLoading(true);
    Promise.all([
      authenticatedRequest<CashLine[]>(`/cash-flow/${encodeURIComponent(snapshotId)}/lines`, { headers: { "X-Company-ID": company.id } }),
      authenticatedRequest<NonCashDisclosure[]>(`/cash-flow/${encodeURIComponent(snapshotId)}/disclosures`, { headers: { "X-Company-ID": company.id } }),
      authenticatedRequest<DisposalSource[]>(`/cash-flow/${encodeURIComponent(snapshotId)}/disposals`, { headers: { "X-Company-ID": company.id } }),
    ])
      .then(([values, disclosureRows, disposalRows]) => { if (active) { setLines(values); setFrozenDisclosures(disclosureRows); setFrozenDisposals(disposalRows); } })
      .catch(reason => { if (active) setError(failure(reason)); })
      .finally(() => { if (active) setLinesLoading(false); });
    return () => { active = false; };
  }, [company.id, snapshotId, canRead]);

  async function generate() {
    if (!payload || !canGenerate || !canRead || busy || loading) return;
    const fingerprint = JSON.stringify([company.id, payload]);
    if (retry.current?.fingerprint !== fingerprint) retry.current = { fingerprint, key: crypto.randomUUID() };
    setBusy(true); setError(""); setNotice("");
    try {
      const value = await authenticatedRequest<CashStatement>("/cash-flow/generate", {
        method: "POST", headers: { "X-Company-ID": company.id, "Idempotency-Key": retry.current.key },
        body: JSON.stringify(payload),
      });
      if (!mounted.current) return;
      retry.current = null; setSnapshots(values => [value, ...values.filter(item => item.id !== value.id)]); setSnapshotId(value.id);
      setNotice("간접법 대사가 완료된 현금흐름표 스냅샷을 생성했습니다.");
    } catch (reason) { if (mounted.current) setError(`${failure(reason)} 사전 점검을 새로고침해 현재 원천을 확인해 주세요.`); }
    finally { if (mounted.current) setBusy(false); }
  }

  async function savePolicy() {
    if (!canGenerate || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const saved = await authenticatedRequest<CashPolicy>("/cash-flow/policies", {
        method: "POST", headers: { "X-Company-ID": company.id },
        body: JSON.stringify({ effective_from: policyFrom, interest_paid: interestPaid, interest_received: interestReceived, income_tax_paid: incomeTaxPaid }),
      });
      if (mounted.current) { setPolicies(rows => [...rows.filter(row => row.id !== saved.id), saved]); setNotice(`현금흐름 분류 정책 v${saved.version}을 기록했습니다.`); setRevision(value => value + 1); }
    } catch (reason) { if (mounted.current) setError(failure(reason)); }
    finally { if (mounted.current) setBusy(false); }
  }

  async function drilldown(id: string) {
    const request = ++traceRequest.current;
    setLineId(id); setTrace(null); setTraceLoading(true); setError("");
    try {
      const value = await authenticatedRequest<CashDrilldown>(`/cash-flow/${encodeURIComponent(snapshotId)}/drilldown?${new URLSearchParams({ line_id: id })}`, { headers: { "X-Company-ID": company.id } });
      if (mounted.current && request === traceRequest.current) setTrace(value);
    } catch (reason) { if (mounted.current && request === traceRequest.current) setError(failure(reason)); }
    finally { if (mounted.current && request === traceRequest.current) setTraceLoading(false); }
  }

  if (!canRead) return null;
  const blockers = [...(preflight?.issues ?? []), ...(bridge?.issues ?? [])].filter((issue, index, all) => all.findIndex(value => value.code === issue.code && value.account_id === issue.account_id && value.journal_id === issue.journal_id) === index);
  return <section className="panel" aria-labelledby="cash-flow-heading">
    <h2 id="cash-flow-heading">현금흐름표 · 간접법</h2>
    <p>선택한 마감 기간의 BS/IS와 현금 원천을 대사한 표현 스냅샷입니다. 현금 거래는 대사와 출처 확인에 사용됩니다.</p>
    <p>간접법 대사 완료는 보고서 승인 상태를 의미하지 않습니다.</p>
    <details><summary>이자·법인세 현금흐름 정책</summary>
      {policies.length > 0 && <ul>{policies.map(row => <li key={row.id}>v{row.version} · {row.effective_from} ~ {row.effective_to ?? "이후"} · {row.status} · 이자 지급 {row.interest_paid} · 이자 수취 {row.interest_received} · 법인세 납부 {row.income_tax_paid}</li>)}</ul>}
      {policies.length === 0 && <p>별도 회사 정책이 없으면 기존 영업활동 분류를 사용합니다.</p>}
      {canGenerate && <div className="workspace-buttons"><label>적용 시작일<input type="date" value={policyFrom} onChange={event => setPolicyFrom(event.target.value)} /></label>
        <label>이자 지급<select value={interestPaid} onChange={event => setInterestPaid(event.target.value as CashPolicy["interest_paid"])}><option value="OPERATING">영업</option><option value="FINANCING">재무</option></select></label>
        <label>이자 수취<select value={interestReceived} onChange={event => setInterestReceived(event.target.value as CashPolicy["interest_received"])}><option value="OPERATING">영업</option><option value="INVESTING">투자</option></select></label>
        <label>법인세 납부<select value={incomeTaxPaid} onChange={event => setIncomeTaxPaid(event.target.value as CashPolicy["income_tax_paid"])}><option value="OPERATING">영업</option><option value="INVESTING">투자</option><option value="FINANCING">재무</option></select></label>
        <button disabled={busy || !policyFrom} onClick={() => void savePolicy()}>정책 기록</button></div>}
    </details>
    <button disabled={loading || busy} onClick={() => { setNotice(""); setRevision(value => value + 1); }}>사전 점검 새로고침</button>
    {loading ? <p role="status">현금흐름표 생성 조건을 확인하고 있습니다…</p> : <>
      <p role="status">{payload ? "생성 가능 · 현금 및 간접법 대사 완료" : "생성 대기 · 아래 원천과 차단 항목을 확인해 주세요."}</p>
      {!statementSet && <p>선택한 기간의 BS/IS를 먼저 생성해 주세요.</p>}
      {statementSet && bridge?.statement_set_id && bridge.statement_set_id !== statementSet.id && <p>현재 간접법 원천과 선택한 BS/IS가 다릅니다. 현재 마감 기준의 BS/IS 스냅샷을 선택해 주세요.</p>}
      {blockers.length > 0 && <ul aria-label="현금흐름표 생성 차단 항목">{blockers.map((issue, index) => <li key={`${issue.code}-${index}`}>{cashIssueLabel(issue.code)} <small>({issue.code})</small>{issue.account_id && <> · 계정 {issue.account_id}</>}{issue.journal_id && <> · 전표 {issue.journal_id} <Link href="/journals">전표 확인</Link></>}</li>)}</ul>}
      {bridge && <p>당기순이익 {bridge.net_profit === null ? "미확인" : formatMoney(bridge.net_profit)} · 간접법 영업현금흐름 {bridge.net_operating === null ? "미확인" : formatMoney(bridge.net_operating)} · 대사 차이 {bridge.reconciliation_difference === null ? "미확인" : formatMoney(bridge.reconciliation_difference)}</p>}
      {preflight && <p>기초 현금 {formatMoney(preflight.opening_cash)} · 기말 현금 {formatMoney(preflight.closing_cash)} · 순증감 {formatMoney(preflight.net_cash_movement)}</p>}
      {canGenerate ? <button disabled={!payload || busy || loading} onClick={() => void generate()}>{busy ? "현금흐름표 생성 중…" : "간접법 현금흐름표 생성"}</button> : <p>조회 권한으로 확인 중입니다. 생성에는 재무제표 생성 권한이 필요합니다.</p>}
    </>}
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}
    {currentStale && <p role="status">기존 스냅샷의 원천이 변경되었습니다. 사전 점검을 확인하고 현재 마감 기준으로 다시 생성해 주세요.</p>}
    {!loading && !error && snapshots.length === 0 && <p>현재 원천에 유효한 현금흐름표 스냅샷이 없습니다.</p>}
    {snapshots.length > 0 && <><h3>현금흐름표 스냅샷</h3><label>현금흐름표 생성 결과 <select disabled={busy} value={snapshotId} onChange={event => setSnapshotId(event.target.value)}>{snapshots.map(value => <option key={value.id} value={value.id}>마감 {value.close_version} · {value.generated_at.slice(0, 10)} · {value.status}</option>)}</select></label>
      {snapshot && <><p>간접법 · {snapshot.status === "RECONCILED" ? "대사 완료 (RECONCILED)" : snapshot.status} · 마감 버전 {snapshot.close_version}</p><p>정책 {snapshot.policy_code} v{snapshot.policy_version} · 스냅샷 {snapshot.snapshot_digest.slice(0, 12)}…</p></>}
      {linesLoading ? <p role="status">현금흐름표 항목을 불러오고 있습니다…</p> : <table><caption>간접법 현금흐름표 항목</caption><thead><tr><th scope="col">항목</th><th scope="col">금액</th><th scope="col">출처와 질문</th></tr></thead><tbody>{lines.map(line => <tr key={line.id}><th scope="row">{cashLineLabel(line.line_code)}</th><td>{formatMoney(line.amount)}</td><td><button aria-pressed={line.id === lineId} onClick={() => void drilldown(line.id)}>원천·전표 보기</button>{canAskCashFlowLine(line.line_code) && (line.source_type === "TOTAL" || line.source_type === "NET_PROFIT") && <> <Link href={financialStatementAskHref(period.id, "CASH_FLOW", line.line_code)} aria-label={`${cashLineLabel(line.line_code)} AI에게 묻기`}>AI에게 묻기</Link></>}</td></tr>)}</tbody></table>}
      <details><summary>비현금 공시 · {frozenDisclosures.length}건</summary><ul>{frozenDisclosures.map(row => <li key={row.id}>{row.source_type} · {formatMoney(row.amount)} · 전표 {row.journal_id} · 증빙 {row.evidence_id}</li>)}</ul></details>
      <details><summary>자산 처분 원천 · {frozenDisposals.length}건</summary><ul>{frozenDisposals.map(row => <li key={row.id}>처분대금 {formatMoney(row.proceeds)} · 처분손익 조정 {formatMoney(row.gain_amount)} · 전표 {row.journal_id} · 증빙 {row.evidence_id}</li>)}</ul></details>
    </>}
    {(disclosures.length > 0 || disposals.length > 0) && <p>현재 기간 등록 원천: 비현금 {disclosures.length}건 · 처분 {disposals.length}건. 스냅샷을 다시 생성하면 현재 원천이 고정됩니다.</p>}
    {lineId && <div><h3>{cashLineLabel(lines.find(line => line.id === lineId)?.line_code ?? "")} 원천</h3>{traceLoading && <p role="status">동결된 원천과 증빙 연결을 불러오고 있습니다…</p>}{trace && <>
      {trace.adjustments.length > 0 && <table><caption>간접법 조정과 규칙 버전</caption><thead><tr><th scope="col">조정</th><th scope="col">계정</th><th scope="col">금액</th><th scope="col">규칙</th></tr></thead><tbody>{trace.adjustments.map(item => <tr key={item.id}><th scope="row">{cashLineLabel(item.adjustment_code)}</th><td>{item.account_id}</td><td>{formatMoney(item.amount)}</td><td>{item.rule_id} v{item.rule_version}</td></tr>)}</tbody></table>}
      {trace.events.length > 0 && <table><caption>현금 거래 출처 · 대사 근거</caption><thead><tr><th scope="col">전표</th><th scope="col">활동 / 분류 버전</th><th scope="col">유입</th><th scope="col">유출</th><th scope="col">증빙 / 배분 버전</th></tr></thead><tbody>{trace.events.map(item => <tr key={item.id}><th scope="row">{item.journal_id}</th><td>{item.activity_type} · {item.classification_id} v{item.classification_version}</td><td>{formatMoney(item.cash_inflow)}</td><td>{formatMoney(item.cash_outflow)}</td><td>{item.evidence_id ?? "별도 배분 증빙 없음"}{item.allocation_id && <> · {item.allocation_id} v{item.allocation_version}</>}</td></tr>)}</tbody></table>}
      {(trace.adjustment_sources.length > 0 || trace.cash_balance_sources.length > 0) && <table><caption>조정 및 현금 잔액의 원장 출처</caption><thead><tr><th scope="col">구분</th><th scope="col">기준일</th><th scope="col">전표 / 전표 행</th><th scope="col">차변 기준 금액</th></tr></thead><tbody>{[...trace.adjustment_sources, ...trace.cash_balance_sources].map((item, index) => <tr key={`${item.journal_line_id}-${index}`}><th scope="row">{"adjustment_id" in item ? "간접법 조정" : `현금 범위 v${item.scope_version}`}{item.is_opening ? " · 기초" : ""}</th><td>{item.entry_date}</td><td>{item.journal_id}<br />{item.journal_line_id}</td><td>{formatMoney(item.signed_debit_amount)}</td></tr>)}</tbody></table>}
      {trace.journals.length > 0 && <><h4>전표·거래·증빙 연결</h4><ul>{trace.journals.map(item => <li key={item.journal_id}>전표 {item.journal_id} <Link href="/journals">전표 목록</Link>{item.transaction_id && <> · 거래 {item.transaction_id} <Link href="/transactions">거래 목록</Link></>} · 증빙 {item.evidence_ids.join(", ") || "연결 없음"}</li>)}</ul></>}
      {trace.events.length === 0 && trace.adjustments.length === 0 && trace.adjustment_sources.length === 0 && trace.cash_balance_sources.length === 0 && trace.journals.length === 0 && <p>이 합계에 연결된 개별 원천이 없습니다.</p>}
    </>}</div>}
  </section>;
}
