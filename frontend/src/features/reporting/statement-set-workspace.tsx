"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";
import type { Period } from "./model";
import { EquityReview } from "./equity-review";
import { setIssueLabels, setSourceCurrent } from "./statement-set-model";
import { RequestScope } from "./request-scope";

type Revision = { id: string; snapshot_digest: string; generated_at: string;
  balance_id: string; income_id: string; cash_id: string; equity_id: string; notes_id: string };
type Readiness = { status: string; issues: string[]; source_digest: string | null };

export function StatementSetWorkspace({ company, period }: { company: Company; period: Period }) {
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<{ rows: string[][]; narratives: string[][] } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const requests = useRef(new RequestScope());
  const retry = useRef<string | null>(null);
  useEffect(() => {
    const scope = requests.current;
    const current = scope.start("read");
    setLoading(true); setError("");
    const headers = { "X-Company-ID": company.id };
    Promise.all([
      authenticatedRequest<Readiness>(`/financial-statement-sets/readiness?period_id=${period.id}`, { headers }),
      authenticatedRequest<Revision[]>(`/financial-statement-sets?period_id=${period.id}`, { headers }),
    ]).then(([state, rows]) => {
      if (!current()) return;
      setReadiness(state); setRevisions(rows);
      setSelected(id => rows.some(row => row.id === id) ? id : rows[0]?.id ?? "");
    }).catch(reason => { if (current()) setError(reason instanceof ApiError ? reason.message : "세트 원천을 조회하지 못했습니다."); })
      .finally(() => { if (current()) setLoading(false); });
    return () => scope.invalidate();
  }, [company.id, period.id, refresh]);
  useEffect(() => {
    let active = true;
    setDetail(null);
    if (!selected) return () => { active = false; };
    authenticatedRequest<{ rows: string[][]; narratives: string[][] }>(`/financial-statement-sets/${selected}`, { headers: { "X-Company-ID": company.id } })
      .then(value => { if (active) setDetail(value); })
      .catch(reason => { if (active) setError(reason instanceof ApiError ? reason.message : "고정된 세트 내용을 조회하지 못했습니다."); });
    return () => { active = false; };
  }, [company.id, selected]);
  async function generate() {
    if (busy || readiness?.status !== "READY") return;
    const current = requests.current.start("generate");
    retry.current ??= crypto.randomUUID();
    setBusy(true); setError("");
    try {
      const row = await authenticatedRequest<Revision>("/financial-statement-sets/generate", {
        method: "POST", headers: { "X-Company-ID": company.id, "Idempotency-Key": retry.current },
        body: JSON.stringify({ period_id: period.id }),
      });
      if (current()) { retry.current = null; setSelected(row.id); setRefresh(value => value + 1); }
    } catch (reason) { if (current()) setError(reason instanceof ApiError ? reason.message : "세트 구성에 실패했습니다."); }
    finally { if (current()) setBusy(false); }
  }
  const revision = revisions.find(row => row.id === selected);
  return <section className="panel" aria-label="재무제표 세트 승인">
    <h2>재무제표 세트 승인</h2>
    <p>BS·IS·CF·SCE·승인된 주석을 정확한 원천으로 묶어 독립 승인합니다. 개별 제표 승인과 구분되는 내부 검증용 승인입니다.</p>
    {error && <p role="alert">{error}</p>}
    <button disabled={busy || loading} onClick={() => setRefresh(value => value + 1)}>원천 다시 확인</button>
    {loading ? <p role="status">세트 구성과 대사 확인 중…</p> : <>
      <p role="status">구성 상태: {readiness?.status ?? "조회 실패"}</p>
      <ul>{readiness?.issues.map(issue => <li key={issue}>{setIssueLabels[issue] ?? "해당 제표의 원천·대사 상태를 확인하세요."} <code>{issue}</code></li>)}</ul>
      {company.permissions.includes("financial_statement.generate") && <button disabled={busy || readiness?.status !== "READY"} onClick={() => void generate()}>현재 revision으로 세트 고정</button>}
      {revisions.length > 0 && <label>세트 이력 <select value={selected} onChange={event => setSelected(event.target.value)}>
        {revisions.map(row => <option key={row.id} value={row.id}>{row.generated_at} · {row.snapshot_digest.slice(0, 12)}</option>)}
      </select></label>}
      {revision && <>
        <p>{setSourceCurrent(readiness?.status, readiness?.source_digest, revision.snapshot_digest) ? "현재 원천 일치" : "과거 원천 · 새 승인/Export 전 현재성을 확인하세요"}</p>
        <dl>{(["balance_id", "income_id", "cash_id", "equity_id", "notes_id"] as const).map(key => <div key={key}><dt>{{balance_id:"재무상태표",income_id:"손익계산서",cash_id:"현금흐름표",equity_id:"자본변동표",notes_id:"승인 주석"}[key]}</dt><dd>{revision[key]}</dd></div>)}</dl>
        {detail && <details><summary>고정된 제표 금액과 승인 주석</summary>
          <table><thead><tr><th>제표</th><th>항목</th><th>금액·내용</th><th>원천 ID</th></tr></thead>
            <tbody>{detail.rows.map((row, index) => <tr key={index}>{row.map((value, column) => <td key={column}>{value}</td>)}</tr>)}</tbody></table>
          {detail.narratives.map((row, index) => <p key={index}>{row[1]}</p>)}
        </details>}
        <p>원천 금액·전표·증빙은 이 화면의 각 제표 및 주석 원천 조회에서 확인하세요.</p>
        <EquityReview key={`${company.id}:${revision.id}`} company={company} snapshotId={revision.id} basePath="/financial-statement-sets" title="재무제표 세트" />
        <Link href="/reports">Report Center에서 승인 재무제표 세트 내보내기</Link>
      </>}
    </>}
  </section>;
}
