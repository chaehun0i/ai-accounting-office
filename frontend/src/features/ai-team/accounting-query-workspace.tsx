"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";
import { askBookkeeper, getQueryRun, listPeriods } from "./api";
import { isFinal, runMessage, type Period, type QueryRun } from "./model";

export function AccountingQueryWorkspace({ company }: { company: Company }) {
  const [periods, setPeriods] = useState<Period[]>([]);
  const [periodId, setPeriodId] = useState("");
  const [question, setQuestion] = useState("");
  const [run, setRun] = useState<QueryRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showSource, setShowSource] = useState(false);
  const [periodRevision, setPeriodRevision] = useState(0);
  const retry = useRef<{ signature: string; key: string } | null>(null);
  const requestVersion = useRef(0);
  const active = useRef(true);
  const selected = periods.find(period => period.id === periodId);

  useEffect(() => {
    active.current = true;
    setLoading(true);
    setError("");
    listPeriods(company.id).then(values => {
      if (!active.current) return;
      setPeriods(values);
      setPeriodId(values[0]?.id ?? "");
    }).catch(reason => { if (active.current) setError(errorMessage(reason)); })
      .finally(() => { if (active.current) setLoading(false); });
    return () => { active.current = false; requestVersion.current += 1; };
  }, [company.id, periodRevision]);

  function clearResult() {
    requestVersion.current += 1;
    retry.current = null;
    setRun(null);
    setShowSource(false);
    setError("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = question.trim();
    if (busy || !periodId || !text) return;
    const version = ++requestVersion.current;
    const signature = JSON.stringify([company.id, periodId, text]);
    if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
    const key = retry.current.key;
    setBusy(true);
    setError("");
    setRun(null);
    try {
      let result = await askBookkeeper(company.id, periodId, text, key);
      for (let attempt = 0; !isFinal(result.status) && attempt < 15; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        if (!active.current || requestVersion.current !== version) return;
        result = await getQueryRun(company.id, result.id);
      }
      if (!active.current || requestVersion.current !== version) return;
      setRun(result);
      if (isFinal(result.status)) retry.current = null;
    } catch (reason) {
      if (active.current && requestVersion.current === version) setError(errorMessage(reason));
    } finally {
      if (active.current && requestVersion.current === version) setBusy(false);
    }
  }

  return <div className="workspace-stack">
    <section className="panel">
      <h2>회계 질의</h2>
      <p>선택한 회사의 마감 검사 또는 마감된 기간의 재무제표를 조회합니다. 금액은 장부와 스냅샷의 검증된 값을 표시합니다.</p>
      <p><strong>회사</strong> {company.company_name}</p>
      {loading ? <p role="status">회계기간을 불러오고 있습니다…</p> : periods.length === 0 && !error
        ? <p>조회할 회계기간이 없습니다.</p>
        : periods.length > 0 && <form onSubmit={submit}>
          <label htmlFor="ai-period">회계기간</label>
          <select id="ai-period" value={periodId} onChange={event => { setPeriodId(event.target.value); clearResult(); }} disabled={busy}>
            {periods.map(period => <option key={period.id} value={period.id}>{period.fiscal_year}년 {period.period_no}기 · {period.start_date}~{period.end_date} · {period.status}</option>)}
          </select>
          <label htmlFor="ai-question">질문</label>
          <textarea id="ai-question" value={question} maxLength={500} rows={3} onChange={event => { setQuestion(event.target.value); clearResult(); }} placeholder="예: 이 기간 마감 가능한가?" disabled={busy} />
          <button type="submit" disabled={busy || !periodId || !question.trim()}>{busy ? "자료 확인 중…" : run && !isFinal(run.status) ? "계속 확인" : "질문하기"}</button>
        </form>}
      {error && <p role="alert" className="error">{error}</p>}
      {!loading && periods.length === 0 && error && <button type="button" onClick={() => setPeriodRevision(value => value + 1)}>회계기간 다시 불러오기</button>}
    </section>
    {run && <section className="panel" aria-live="polite">
      <h2>조회 결과</h2>
      <p><strong>실행 상태</strong> {run.status}</p>
      <p>{runMessage(run)}</p>
      {run.status === "COMPLETED" && run.answer_amount !== null && <p><strong>장부 기준 금액</strong> {run.answer_amount}</p>}
      <p><strong>검증 상태</strong> {run.controller_verdict ?? "확인 중"}</p>
      {run.status === "COMPLETED" && <button type="button" onClick={() => setShowSource(value => !value)} aria-expanded={showSource}>답변 근거 {showSource ? "접기" : "펼쳐보기"}</button>}
      {run.status === "COMPLETED" && showSource && <dl>
        <dt>기준 기간</dt><dd>{selected ? `${selected.start_date} ~ ${selected.end_date}` : run.period_id}</dd>
        <dt>검증 결과</dt><dd>{run.controller_verdict ?? "없음"}</dd>
        <dt>자료 참조</dt><dd>{run.answer_resource_id ?? "없음"}</dd>
        <dt>자료 다이제스트</dt><dd>{run.answer_source_digest ?? "없음"}</dd>
      </dl>}
    </section>}
  </div>;
}

function errorMessage(reason: unknown) {
  if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) return "이 회사의 회계 자료를 조회할 권한이 없습니다.";
  if (reason instanceof ApiError && reason.status === 404) return "선택한 회계기간 또는 자료를 찾을 수 없습니다.";
  return reason instanceof ApiError ? reason.message : "질의를 처리하지 못했습니다. 다시 시도해 주세요.";
}
