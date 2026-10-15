"use client";

import type { Company } from "@/features/companies/selection-state";
import { isFinal, runMessage } from "./model";
import { useAccountingQuery } from "./use-accounting-query";

export function AccountingQueryWorkspace({ company }: { company: Company }) {
  const {
    periods, periodId, question, run, loading, busy, error, showSource,
    setPeriodId, setQuestion, setShowSource, clearResult, submit, reloadPeriods,
  } = useAccountingQuery(company.id);
  const selected = periods.find(period => period.id === periodId);

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
      {!loading && periods.length === 0 && error && <button type="button" onClick={reloadPeriods}>회계기간 다시 불러오기</button>}
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
