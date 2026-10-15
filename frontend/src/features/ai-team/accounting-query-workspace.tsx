"use client";

import type { Company } from "@/features/companies/selection-state";
import { isFinal, runMessage, runStatusLabel } from "./model";
import { useAccountingQuery } from "./use-accounting-query";

export function AccountingQueryWorkspace({ company }: { company: Company }) {
  const {
    periods, periodId, question, run, loading, busy, error, showSource,
    setPeriodId, setQuestion, setShowSource, clearResult, submit, reloadPeriods,
  } = useAccountingQuery(company.id);
  const selected = periods.find(period => period.id === periodId);

  return <div className="workspace-stack ai-query-workspace">
    <section className="panel ai-query-panel" aria-labelledby="ai-query-heading">
      <div className="ai-query-heading">
        <div>
          <span className="eyebrow">AI 회계팀 · 기간별 질의</span>
          <h2 id="ai-query-heading">장부와 마감 결과에 질문하기</h2>
          <p className="muted">마감 검사와 확정된 재무제표를 조회합니다. 금액과 검증 근거는 회계 자료에서 가져옵니다.</p>
        </div>
        <span className="ai-query-company">{company.company_name}</span>
      </div>
      {loading ? <p role="status">회계기간을 불러오고 있습니다…</p> : periods.length === 0 && !error
        ? <p className="ai-query-empty">조회할 회계기간이 없습니다.</p>
        : periods.length > 0 && <form className="ai-query-form" onSubmit={submit}>
          <div>
            <label htmlFor="ai-period">기준 회계기간</label>
            <select id="ai-period" value={periodId} onChange={event => { setPeriodId(event.target.value); clearResult(); }} disabled={busy}>
              {periods.map(period => <option key={period.id} value={period.id}>{period.fiscal_year}년 {period.period_no}기 · {period.start_date}~{period.end_date} · {period.status}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="ai-question">질문</label>
            <textarea id="ai-question" value={question} maxLength={500} rows={4} onChange={event => { setQuestion(event.target.value); clearResult(); }} placeholder="예: 이 기간 마감 가능한가?" disabled={busy} />
          </div>
          <div className="ai-query-actions">
            <small>마감 가능 여부 · 손익 · 자산 총액 등을 물어보세요.</small>
            <button className="button-accent" type="submit" disabled={busy || !periodId || !question.trim()}>{busy ? "자료 확인 중…" : run && !isFinal(run.status) ? "계속 확인" : "질문하기"}</button>
          </div>
        </form>}
      {error && <p role="alert" className="error">{error}</p>}
      {!loading && periods.length === 0 && error && <button type="button" onClick={reloadPeriods}>회계기간 다시 불러오기</button>}
    </section>
    {run && <section className="panel ai-query-result" aria-live="polite" aria-labelledby="ai-result-heading">
      <div className="ai-query-result-heading">
        <h2 id="ai-result-heading">조회 결과</h2>
        <span className={`ai-query-status ai-query-status-${run.status.toLowerCase()}`}>{runStatusLabel(run.status)}</span>
      </div>
      <p className="ai-query-answer">{runMessage(run)}</p>
      {run.status === "COMPLETED" && run.answer_amount !== null && <div className="ai-query-amount"><span>장부 기준 금액</span><strong>{run.answer_amount}</strong></div>}
      <div className="ai-query-verdict"><span>검증 상태</span><strong>{run.controller_verdict ?? "확인 중"}</strong></div>
      {run.status === "COMPLETED" && <button className="ai-query-source-toggle" type="button" onClick={() => setShowSource(value => !value)} aria-expanded={showSource}>답변 근거 {showSource ? "접기" : "펼쳐보기"}</button>}
      {run.status === "COMPLETED" && showSource && <dl className="ai-query-source">
        <dt>기준 기간</dt><dd>{selected ? `${selected.start_date} ~ ${selected.end_date}` : run.period_id}</dd>
        <dt>검증 결과</dt><dd>{run.controller_verdict ?? "없음"}</dd>
        <dt>자료 참조</dt><dd>{run.answer_resource_id ?? "없음"}</dd>
        <dt>자료 다이제스트</dt><dd>{run.answer_source_digest ?? "없음"}</dd>
      </dl>}
    </section>}
  </div>;
}
