"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";
import { formatMoney, type Period } from "./model";

type Snapshot = {
  id: string;
  period_id: string;
  comparison_period_id: string;
  status: "DRAFT" | "REVIEW_REQUESTED" | "APPROVED" | "REJECTED" | "SUPERSEDED";
  version: number;
  source_digest: string;
  mapping_changed?: boolean;
  statements?: Record<string, {
    line_code: string;
    label: string;
    current_amount: string;
    prior_amount: string;
    presentation_amount: string;
    variance: string;
  }[]>;
};

type Readiness = { status: "READY" | "BLOCKED"; reasons: string[]; unsupported_statements?: string[] };
type Sources = { current: { journal_id: string; journal_no: string; amount: string }[]; prior: { journal_id: string; journal_no: string; amount: string }[] };
const message = (error: unknown) => error instanceof ApiError ? error.message : "비교 재무제표를 불러오지 못했습니다.";

export function ComparativeWorkspace({ company }: { company: Company }) {
  const [periods, setPeriods] = useState<Period[]>([]);
  const [currentId, setCurrentId] = useState("");
  const [priorId, setPriorId] = useState("");
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [selected, setSelected] = useState<Snapshot | null>(null);
  const [sourceRows, setSourceRows] = useState<Sources | null>(null);
  const [fromCode, setFromCode] = useState("REVENUE");
  const [toCode, setToCode] = useState("NON_OPERATING_INCOME");
  const [reclassAmount, setReclassAmount] = useState("");
  const [reclassReason, setReclassReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const retry = useRef<{ fingerprint: string; key: string } | null>(null);
  const scope = { "X-Company-ID": company.id };

  useEffect(() => {
    let active = true;
    setPeriods([]); setCurrentId(""); setPriorId(""); setReadiness(null); setSnapshots([]); setSelected(null); setSourceRows(null); setError("");
    authenticatedRequest<Period[]>("/closing/periods", { headers: scope })
      .then(rows => { if (!active) return; const closed = rows.filter(row => row.status === "CLOSED"); setPeriods(closed); setCurrentId(closed.at(-1)?.id ?? ""); })
      .catch(reason => { if (active) setError(message(reason)); });
    return () => { active = false; };
  }, [company.id]);

  useEffect(() => {
    setPriorId(""); setReadiness(null); setSnapshots([]); setSelected(null); setSourceRows(null); setError("");
    const candidates = periods.filter(row => row.id !== currentId && row.end_date < (periods.find(item => item.id === currentId)?.end_date ?? ""));
    setPriorId(candidates.at(-1)?.id ?? "");
  }, [currentId, periods]);

  useEffect(() => {
    let active = true;
    setReadiness(null); setSnapshots([]); setSelected(null); setSourceRows(null);
    if (!currentId || !priorId) return () => { active = false; };
    const query = new URLSearchParams({ period_id: currentId, comparison_period_id: priorId });
    Promise.all([
      authenticatedRequest<Readiness>(`/financial-statements/comparatives/readiness?${query}`, { headers: scope }),
      authenticatedRequest<Snapshot[]>(`/financial-statements/comparatives?period_id=${encodeURIComponent(currentId)}`, { headers: scope }),
    ]).then(([state, history]) => { if (!active) return; setReadiness(state); setSnapshots(history.filter(row => row.comparison_period_id === priorId)); })
      .catch(reason => { if (active) setError(message(reason)); });
    return () => { active = false; };
  }, [company.id, currentId, priorId]);

  async function refresh(snapshotId?: string) {
    if (!snapshotId) { setSelected(null); return; }
    try { setSelected(await authenticatedRequest<Snapshot>(`/financial-statements/comparatives/${snapshotId}`, { headers: scope })); }
    catch (reason) { setError(message(reason)); }
  }

  async function command(path: string, body: object) {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      const updated = await authenticatedRequest<Snapshot>(`/financial-statements/comparatives/${selected.id}/${path}`, {
        method: "POST", headers: scope, body: JSON.stringify(body),
      });
      setSnapshots(rows => [updated, ...rows.filter(row => row.id !== updated.id)]);
      await refresh(updated.id);
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  async function generate() {
    if (!currentId || !priorId) return;
    const fingerprint = JSON.stringify([currentId, priorId]);
    if (retry.current?.fingerprint !== fingerprint) {
      retry.current = { fingerprint, key: crypto.randomUUID() };
    }
    setBusy(true); setError("");
    try {
      const created = await authenticatedRequest<Snapshot>("/financial-statements/comparatives", {
        method: "POST", headers: { ...scope, "Idempotency-Key": retry.current.key }, body: JSON.stringify({ period_id: currentId, comparison_period_id: priorId }),
      });
      retry.current = null;
      setSnapshots(rows => [created, ...rows.filter(row => row.id !== created.id)]);
      await refresh(created.id);
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  async function showSources(kind: string, lineCode: string) {
    if (!selected) return;
    try {
      const query = new URLSearchParams({ statement_type: kind, line_code: lineCode });
      setSourceRows(await authenticatedRequest<Sources>(`/financial-statements/comparatives/${selected.id}/sources?${query}`, { headers: scope }));
    } catch (reason) { setError(message(reason)); }
  }

  async function submitReclassification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    await command("reclassifications", {
      statement_type: "INCOME_STATEMENT", from_line_code: fromCode, to_line_code: toCode,
      amount: reclassAmount, reason: reclassReason, expected_version: selected.version,
    });
    setReclassAmount(""); setReclassReason("");
  }

  const current = periods.find(row => row.id === currentId);
  const previous = periods.find(row => row.id === priorId);
  return <section className="panel">
    <h2>비교 재무제표</h2>
    <p>동일 분류 체계로 검증할 수 있는 재무상태표와 손익계산서만 비교합니다. 현금흐름표·자본변동표·주석 비교는 아직 지원하지 않습니다.</p>
    <div className="form-row">
      <label>당기 <select aria-label="비교 당기" value={currentId} onChange={event => setCurrentId(event.target.value)}>{periods.map(row => <option key={row.id} value={row.id}>{row.start_date} ~ {row.end_date}</option>)}</select></label>
      <label>전기 <select aria-label="비교 전기" value={priorId} onChange={event => setPriorId(event.target.value)}>{periods.filter(row => row.id !== currentId && row.end_date < (current?.end_date ?? "")).map(row => <option key={row.id} value={row.id}>{row.start_date} ~ {row.end_date}</option>)}</select></label>
    </div>
    {readiness && <p role="status">준비 상태: {readiness.status}{readiness.reasons.length ? ` · ${readiness.reasons.join(", ")}` : ""}</p>}
    {readiness?.status === "READY" && company.permissions.includes("financial_statement.generate") && <button disabled={busy} onClick={() => void generate()}>비교 Snapshot 생성</button>}
    {snapshots.length > 0 && <label>비교 버전 <select aria-label="비교 버전" value={selected?.id ?? ""} onChange={event => void refresh(event.target.value)}><option value="">선택</option>{snapshots.map(row => <option key={row.id} value={row.id}>{row.status} · v{row.version}</option>)}</select></label>}
    {selected && <>
      <p>상태 {selected.status} · 원천 {selected.source_digest.slice(0, 12)}…</p>
      {selected.mapping_changed && <p>전기와 당기 계정 표시 매핑이 다릅니다. 아래 금액을 원본과 대조하고 필요한 표시 재분류 근거를 기록하세요.</p>}
      {Object.entries(selected.statements ?? {}).map(([kind, lines]) => <div key={kind}>
        <h3>{kind === "BALANCE_SHEET" ? "재무상태표" : "손익계산서"}</h3>
        <table><thead><tr><th>항목</th><th>당기</th><th>전기 원본</th><th>전기 표시</th><th>증감</th><th>원천</th></tr></thead><tbody>{lines.map(line => <tr key={line.line_code}><th>{line.label}</th><td>{formatMoney(line.current_amount)}</td><td>{formatMoney(line.prior_amount)}</td><td>{formatMoney(line.presentation_amount)}</td><td>{formatMoney(line.variance)}</td><td><button onClick={() => void showSources(kind, line.line_code)}>전표 출처</button></td></tr>)}</tbody></table>
      </div>)}
      {selected.status === "DRAFT" && company.permissions.includes("financial_statement.generate") && <form onSubmit={event => void submitReclassification(event)}>
        <h3>손익계산서 전기 표시 재분류</h3>
        <label>기존 항목<select value={fromCode} onChange={event => setFromCode(event.target.value)}><option value="REVENUE">매출액</option><option value="NON_OPERATING_INCOME">영업외수익</option><option value="COGS">매출원가</option><option value="OPERATING_EXPENSE">영업비용</option><option value="NON_OPERATING_EXPENSE">영업외비용</option><option value="TAX_EXPENSE">법인세비용</option></select></label>
        <label>변경 항목<select value={toCode} onChange={event => setToCode(event.target.value)}>{(fromCode === "REVENUE" || fromCode === "NON_OPERATING_INCOME" ? ["REVENUE", "NON_OPERATING_INCOME"] : ["COGS", "OPERATING_EXPENSE", "NON_OPERATING_EXPENSE", "TAX_EXPENSE"]).filter(code => code !== fromCode).map(code => <option key={code} value={code}>{code}</option>)}</select></label>
        <label>금액<input inputMode="decimal" value={reclassAmount} onChange={event => setReclassAmount(event.target.value)} /></label>
        <label>재분류 근거<input value={reclassReason} onChange={event => setReclassReason(event.target.value)} /></label>
        <button disabled={busy || !reclassAmount || !reclassReason}>전기 표시 재분류</button>
      </form>}
      {sourceRows && <section aria-label="비교 재무제표 원천"><h3>전표 원천</h3>{(["current", "prior"] as const).map(periodKey => <div key={periodKey}><h4>{periodKey === "current" ? "당기" : "전기"}</h4>{sourceRows[periodKey].map((source, index) => <p key={`${source.journal_id}:${index}`}><Link href="/journals">{source.journal_no || source.journal_id}</Link> · {formatMoney(source.amount)}</p>)}</div>)}</section>}
      {selected.status === "DRAFT" && company.permissions.includes("financial_statement.generate") && <button disabled={busy} onClick={() => void command("request-review", { expected_version: selected.version })}>검토 요청</button>}
      {selected.status === "REVIEW_REQUESTED" && company.permissions.includes("financial_statement.approve") && <>
        <button disabled={busy} onClick={() => void command("approve", { expected_version: selected.version })}>독립 승인</button>
        <button disabled={busy} onClick={() => void command("reject", { expected_version: selected.version, reason: "수정 필요" })}>반려</button>
      </>}
      {selected.status === "APPROVED" && <Link href="/reports">승인된 비교 보고서 내보내기</Link>}
    </>}
    {error && <p role="alert" className="error">{error}</p>}
    {current && previous && <p>당기 {current.close_version}차 마감 · 전기 {previous.close_version}차 마감 · 내부 검증용</p>}
  </section>;
}
