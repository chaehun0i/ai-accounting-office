"use client";

import type { Company } from "@/features/companies/selection-state";
import type { AskContext } from "./context";
import { canReviewTeam, isFinal, runMessage, runStatusLabel, teamStepLabel } from "./model";
import { useAccountingQuery } from "./use-accounting-query";

export function AccountingQueryWorkspace({ company, context }: { company: Company; context: AskContext | null }) {
  const {
    periods, periodId, question, run, steps, mode, loading, busy, error, contextNotice, showSource,
    setPeriodId, setQuestion, setMode, setShowSource, clearResult, submit, reloadPeriods,
  } = useAccountingQuery(company.id, context);
  const selected = periods.find(period => period.id === periodId);
  const teamAllowed = canReviewTeam(company.permissions);

  return <div className="workspace-stack ai-query-workspace">
    <section className="panel ai-query-panel" aria-labelledby="ai-query-heading">
      <div className="ai-query-heading">
        <div>
          <span className="eyebrow">AI 회계팀 · 기간별 질의</span>
          <h2 id="ai-query-heading">장부와 마감 결과에 질문하기</h2>
          {context?.kind === "closing" && <p className="ai-query-context">월마감 화면에서 이어서 질문 · 내용을 확인하고 직접 실행해 주세요.</p>}
          {context?.kind === "financial_statement" && <p className="ai-query-context">재무제표에서 이어서 질문 · {context.statementType === "BALANCE_SHEET" ? "재무상태표" : context.statementType === "CASH_FLOW" ? "현금흐름표" : "손익계산서"} · {context.lineLabel} · 내용을 확인하고 직접 실행해 주세요.</p>}
          <p className="muted">질문하거나 Closing·AR·AP 담당 역할이 같은 기간을 검토하게 할 수 있습니다. 숫자와 근거는 회계 자료에서 가져옵니다.</p>
        </div>
        <span className="ai-query-company">{company.company_name}</span>
      </div>
      {contextNotice && <p role="status">{contextNotice}</p>}
      {loading ? <p role="status">회계기간을 불러오고 있습니다…</p> : periods.length === 0 && !error
        ? <p className="ai-query-empty">조회할 회계기간이 없습니다.</p>
        : periods.length > 0 && <form className="ai-query-form" onSubmit={submit}>
          <fieldset>
            <legend>검토 방식</legend>
            <label><input type="radio" name="ai-mode" checked={mode === "question"} onChange={() => { setMode("question"); clearResult(); }} disabled={busy} /> 기간별 질문</label>
            <label><input type="radio" name="ai-mode" checked={mode === "team"} onChange={() => { setMode("team"); clearResult(); }} disabled={busy || !teamAllowed} /> AI 회계팀 공동 검토</label>
          </fieldset>
          {!teamAllowed && <p className="muted">공동 검토에는 기간·채권·채무 조회 권한이 모두 필요합니다. 기간별 질문은 계속 사용할 수 있습니다.</p>}
          <div>
            <label htmlFor="ai-period">기준 회계기간</label>
            <select id="ai-period" value={periodId} onChange={event => { setPeriodId(event.target.value); clearResult(); }} disabled={busy}>
              {periods.map(period => <option key={period.id} value={period.id}>{period.fiscal_year}년 {period.period_no}기 · {period.start_date}~{period.end_date} · {period.status}</option>)}
            </select>
          </div>
          {mode === "question" && <div>
            <label htmlFor="ai-question">질문</label>
            <textarea id="ai-question" value={question} maxLength={500} rows={4} onChange={event => { setQuestion(event.target.value); clearResult(); }} placeholder="예: 이 기간 마감 가능한가?" disabled={busy} />
          </div>}
          <div className="ai-query-actions">
            <small>{mode === "team" ? "Closing·AR·AP 대사를 읽고 Controller가 차이와 출처를 검증합니다. 장부를 변경하지 않습니다." : "마감 가능 여부 · 손익 · 자산 총액 등을 물어보세요."}</small>
            <button className="button-accent" type="submit" disabled={busy || !periodId || (mode === "question" && !question.trim())}>{busy ? "자료 확인 중…" : run && !isFinal(run.status) ? "계속 확인" : mode === "team" ? "공동 검토 실행" : "질문하기"}</button>
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
      {run.controller_verdict === "REVIEW" && <p role="alert">사람 검토 필요 · 아래 차단 항목과 채권·채무 차이를 확인하고 해당 업무 화면에서 정정해 주세요. 이 검토는 장부를 수정하지 않습니다.</p>}
      {run.graph_name === "accounting_team_period_review" && steps.length > 0 && <div>
        <h3>역할별 검토 이력</h3>
        <ol>{steps.map(step => <li key={step.step_no}>{teamStepLabel[step.node_name] ?? step.node_name} · {step.status === "SUCCEEDED" ? "완료" : step.status === "FAILED" ? "실패" : "진행 중"}</li>)}</ol>
      </div>}
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
