"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";
import {
  adjustmentLabels, checkLabels,
  type Account, type Approval, type ClosingRun, type Period, type Trial,
} from "./model";

const adjustmentTypes = Object.keys(adjustmentLabels);

export function ClosingWorkspace({ company }: { company: Company }) {
  const [periods, setPeriods] = useState<Period[]>([]);
  const [periodId, setPeriodId] = useState("");
  const [history, setHistory] = useState<ClosingRun[]>([]);
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<ClosingRun | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [trial, setTrial] = useState<Trial | null>(null);
  const [stage, setStage] = useState<"UNADJUSTED" | "ADJUSTED">("ADJUSTED");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const retry = useRef<{ signature: string; key: string } | null>(null);
  const companyRef = useRef(company.id);
  companyRef.current = company.id;
  const headers = { "X-Company-ID": company.id };
  const selected = periods.find(value => value.id === periodId);
  const blockers = run?.checks?.filter(value => value.severity === "BLOCKER") ?? [];
  const closeApproval = approvals.find(value => value.action_code === "CLOSE" && value.status !== "CONSUMED");
  const reopenApproval = approvals.find(value => value.action_code === "REOPEN" && value.status !== "CONSUMED");
  const canStart = company.permissions.includes("period.start_closing");
  const canClose = company.permissions.includes("period.close");

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      authenticatedRequest<Period[]>("/closing/periods", { headers: { "X-Company-ID": company.id } }),
      company.permissions.includes("account.read")
        ? authenticatedRequest<Account[]>("/accounts", { headers: { "X-Company-ID": company.id } })
        : Promise.resolve([]),
    ]).then(([loaded, available]) => {
      if (!active) return;
      setPeriods(loaded);
      setAccounts(available.filter(value => value.posting_allowed && value.status === "ACTIVE"));
      setPeriodId(previous => loaded.some(value => value.id === previous) ? previous : loaded[0]?.id ?? "");
    }).catch(reason => { if (active) setError(message(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company.id, company.permissions, revision]);

  useEffect(() => {
    let active = true;
    if (!periodId) { setHistory([]); setRunId(""); setRun(null); return; }
    authenticatedRequest<ClosingRun[]>(`/closing/periods/${periodId}/runs`, { headers: { "X-Company-ID": company.id } })
      .then(values => {
        if (!active) return;
        setHistory(values);
        setRunId(previous => values.some(value => value.id === previous) ? previous : values[0]?.id ?? "");
      }).catch(reason => { if (active) setError(message(reason)); });
    return () => { active = false; };
  }, [company.id, periodId, revision]);

  useEffect(() => {
    let active = true;
    if (!runId) { setRun(null); setApprovals([]); setTrial(null); return; }
    Promise.all([
      authenticatedRequest<ClosingRun>(`/closing-runs/${runId}`, { headers: { "X-Company-ID": company.id } }),
      authenticatedRequest<Approval[]>(`/closing-runs/${runId}/approvals`, { headers: { "X-Company-ID": company.id } }),
      authenticatedRequest<Trial>(`/closing-runs/${runId}/trial-balance?stage=${stage}`, { headers: { "X-Company-ID": company.id } }),
    ]).then(([current, decisions, balance]) => {
      if (active) { setRun(current); setApprovals(decisions); setTrial(balance); }
    }).catch(reason => { if (active) setError(message(reason)); });
    return () => { active = false; };
  }, [company.id, runId, stage, revision]);

  async function command<T>(path: string, body: object): Promise<T> {
    const signature = JSON.stringify([company.id, path, body]);
    if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
    return authenticatedRequest<T>(path, {
      method: "POST",
      headers: { ...headers, "Idempotency-Key": retry.current.key },
      body: JSON.stringify(body),
    });
  }

  async function runCommand(task: () => Promise<string>) {
    const scope = company.id;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await task();
      if (companyRef.current === scope) { retry.current = null; setRevision(value => value + 1); setNotice(result); }
    } catch (reason) {
      if (companyRef.current === scope) setError(message(reason));
    } finally {
      if (companyRef.current === scope) setBusy(false);
    }
  }

  function createAdjustment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!run) return;
    const form = new FormData(event.currentTarget);
    const amount = String(form.get("amount") ?? "").trim();
    if (!/^\d+(\.\d{1,4})?$/.test(amount) || /^0+(\.0+)?$/.test(amount)) {
      setError("조정 금액은 0보다 큰 소수 네 자리 이하의 값으로 입력해 주세요."); return;
    }
    const debit = String(form.get("debit"));
    const credit = String(form.get("credit"));
    if (!debit || !credit || debit === credit) { setError("서로 다른 차변·대변 계정을 선택해 주세요."); return; }
    const reverse = form.get("auto_reverse") === "on";
    void runCommand(async () => {
      await command(`/closing-runs/${run.id}/adjustments`, {
        adjustment_type: form.get("type"), entry_date: form.get("entry_date"),
        description: form.get("description"), auto_reverse: reverse,
        scheduled_reversal_date: reverse ? form.get("reversal_date") : null,
        lines: [
          { account_id: debit, debit_amount: amount, credit_amount: "0" },
          { account_id: credit, debit_amount: "0", credit_amount: amount },
        ],
      });
      return "결산조정 전표 초안을 만들었습니다. 전표 화면에서 별도 검토자 승인과 기표를 진행해 주세요.";
    });
  }

  if (loading) return <p role="status" className="loading-message">결산 자료를 불러오고 있습니다…</p>;
  return <div className="workspace-stack">
    <section className="panel">
      <h2>회계기간 선택</h2>
      <p>장부와 대사 자료를 검사한 뒤 별도 검토자의 승인으로 마감합니다. 마감은 전표 기표를 대신하지 않습니다.</p>
      <label>회계기간 <select aria-label="결산 회계기간" value={periodId} onChange={event => { setPeriodId(event.target.value); setRunId(""); setRun(null); }}>
        {periods.map(value => <option key={value.id} value={value.id}>{value.start_date} ~ {value.end_date} · {value.status}</option>)}
      </select></label>
      {periods.length === 0 && <p>회계기간이 없습니다. 회계 설정을 먼저 완료해 주세요.</p>}
      {selected && <p aria-live="polite">현재 상태 <strong>{selected.status}</strong> · 마감 버전 {selected.close_version}</p>}
      {selected?.status === "OPEN" && canStart && <button disabled={busy} onClick={() => void runCommand(async () => {
        const created = await command<ClosingRun>("/closing-runs", { accounting_period_id: selected.id });
        setRunId(created.id); return "마감을 시작했습니다. 차단 항목을 검토해 주세요.";
      })}>마감 시작</button>}
    </section>

    {history.length > 0 && <section className="panel"><h2>결산 실행 이력</h2>
      <label>실행 버전 <select aria-label="결산 실행 버전" value={runId} onChange={event => setRunId(event.target.value)}>
        {history.map(value => <option key={value.id} value={value.id}>#{value.run_version} · {value.status} · {value.created_at.slice(0, 10)}</option>)}
      </select></label>
    </section>}

    {run && <>
      <section className="panel"><h2>검사 결과</h2>
        <p>실행 #{run.run_version} · {run.status} · 차단 {blockers.length}건</p>
        <p>기준 다이제스트 <code>{run.source_digest.slice(0, 16)}…</code></p>
        {run.status !== "COMPLETED" && selected?.status === "CLOSING" && canStart && <button disabled={busy} onClick={() => void runCommand(async () => {
          await command(`/closing-runs/${run.id}/checks`, {}); return "최신 장부와 대사 상태로 검사를 다시 실행했습니다.";
        })}>검사 다시 실행</button>}
        <table><thead><tr><th>검사</th><th>결과</th><th>영향</th><th>참조</th></tr></thead><tbody>
          {run.checks?.map(value => <tr key={value.check_code}><td>{checkLabels[value.check_code] ?? value.check_code}</td>
            <td><strong>{value.severity}</strong></td><td>{value.amount_impact}</td>
            <td>{value.source_type && value.source_id ? `${value.source_type} ${value.source_id}` : "—"}</td></tr>)}
        </tbody></table>
        {blockers.length > 0 && <p role="status">차단 항목을 해결한 뒤 검사를 다시 실행해야 마감 승인을 요청할 수 있습니다.</p>}
        <p><Link href="/transactions">거래 확인</Link> · <Link href="/journals">전표 확인</Link> · <Link href="/bank-reconciliation">은행 대사</Link> · <Link href="/card-reconciliation">카드 대사</Link></p>
      </section>

      <section className="panel"><h2>결산조정</h2>
        <p>조정은 전표 초안으로 생성됩니다. 사람이 승인하고 기표해야 마감 검사에 반영됩니다.</p>
        {(run.adjustments ?? []).length === 0 ? <p>등록된 조정이 없습니다.</p> : <table><thead><tr><th>유형</th><th>상태</th><th>전표</th><th>역분개</th></tr></thead><tbody>
          {run.adjustments?.map(value => <tr key={value.id}><td>{adjustmentLabels[value.adjustment_type] ?? value.adjustment_type}</td><td>{value.status}</td>
            <td><Link href={`/journals#journal-${value.proposed_journal_id}`}>전표 열기</Link></td>
            <td>{value.auto_reverse ? value.reversal_journal_id ? <Link href={`/journals#journal-${value.reversal_journal_id}`}>역분개 초안</Link> :
              <button disabled={busy || !company.permissions.includes("journal.reverse") || selected?.status !== "CLOSED"} onClick={() => void runCommand(async () => {
                await command(`/closing-adjustments/${value.id}/reversal`, { reason: "예약된 결산조정 역분개" });
                return "다음 열린 기간에 역분개 초안을 만들었습니다. 사람 승인 후 기표해 주세요.";
              })}>역분개 초안</button> : "—"}</td></tr>)}
        </tbody></table>}
        {selected?.status === "CLOSING" && run.status === "ACTIVE" && canStart && company.permissions.includes("journal.propose") &&
          <form onSubmit={createAdjustment}>
            <label>조정 유형 <select name="type">{adjustmentTypes.map(type => <option key={type} value={type}>{adjustmentLabels[type]}</option>)}</select></label>
            <label>귀속일 <input name="entry_date" type="date" min={selected.start_date} max={selected.end_date} defaultValue={selected.end_date} required /></label>
            <label>적요 <input name="description" maxLength={2000} required /></label>
            <label>차변 계정 <select name="debit" required><option value="">선택</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.account_code} {account.account_name}</option>)}</select></label>
            <label>대변 계정 <select name="credit" required><option value="">선택</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.account_code} {account.account_name}</option>)}</select></label>
            <label>금액 <input name="amount" inputMode="decimal" placeholder="0.0000" required /></label>
            <label><input name="auto_reverse" type="checkbox" /> 다음 기간 역분개</label>
            <label>역분개 예정일 <input name="reversal_date" type="date" /></label>
            <button disabled={busy || accounts.length < 2}>조정 전표 초안 생성</button>
          </form>}
      </section>

      <section className="panel"><h2>시산표 단계</h2>
        <label>단계 <select aria-label="시산표 단계" value={stage} onChange={event => setStage(event.target.value as "UNADJUSTED" | "ADJUSTED")}><option value="UNADJUSTED">조정 전</option><option value="ADJUSTED">조정 후</option></select></label>
        {trial && <><p>장부 다이제스트 <code>{trial.digest.slice(0, 16)}…</code></p>
          <table><thead><tr><th>계정</th><th>기간 차변</th><th>기간 대변</th><th>기말 차변</th><th>기말 대변</th></tr></thead><tbody>{trial.rows.map(value =>
            <tr key={value.account_id}><td>{value.account_code} {value.account_name}</td><td>{value.period_debit}</td><td>{value.period_credit}</td><td>{value.ending_debit}</td><td>{value.ending_credit}</td></tr>)}</tbody></table></>}
      </section>

      <section className="panel"><h2>사람 승인과 기간마감</h2>
        {(approvals.length === 0) ? <p>승인 요청이 없습니다.</p> : <ul>{approvals.map(value =>
          <li key={value.id}>{value.action_code} · {value.status} · 요청 {value.requested_at.slice(0, 10)} · {value.reason}</li>)}</ul>}
        {selected?.status === "CLOSING" && run.status === "ACTIVE" && canClose &&
          <button disabled={busy || blockers.length > 0} onClick={() => void runCommand(async () => {
            await command(`/closing-runs/${run.id}/submit`, { reason: "결산 검사 완료 및 기간마감 요청" });
            return "마감 승인 요청을 등록했습니다. 다른 검토자가 승인해야 합니다.";
          })}>마감 승인 요청</button>}
        {closeApproval?.status === "PENDING" && canClose &&
          <button disabled={busy} onClick={() => void runCommand(async () => {
            await command(`/closing-approvals/${closeApproval.id}/approve`, { reason: "검사와 근거 확인" });
            return "승인했습니다. 요청자와 다른 검토자의 승인 기록이 남았습니다.";
          })}>마감 승인</button>}
        {closeApproval?.status === "APPROVED" && canClose &&
          <button disabled={busy || blockers.length > 0} onClick={() => void runCommand(async () => {
            await command(`/closing-runs/${run.id}/close`, { approval_id: closeApproval.id });
            return "회계기간을 마감했습니다. 일반 전표 기표가 차단됩니다.";
          })}>기간 마감</button>}
        {selected?.status === "CLOSED" && company.permissions.includes("period.reopen.request") && !reopenApproval &&
          <button disabled={busy} onClick={() => void runCommand(async () => {
            await command(`/closing-runs/${run.id}/reopen-request`, { reason: "정정 작업을 위한 재개 요청" });
            return "재개 승인 요청을 등록했습니다.";
          })}>재개 요청</button>}
        {reopenApproval?.status === "PENDING" && company.permissions.includes("period.reopen.approve") &&
          <button disabled={busy} onClick={() => void runCommand(async () => {
            await command(`/closing-approvals/${reopenApproval.id}/approve`, { reason: "재개 영향 검토" });
            return "재개 요청을 승인했습니다.";
          })}>재개 승인</button>}
        {reopenApproval?.status === "APPROVED" && company.permissions.includes("period.reopen.execute") &&
          <button disabled={busy} onClick={() => void runCommand(async () => {
            await command(`/closing-runs/${run.id}/reopen`, { approval_id: reopenApproval.id, reason: "승인된 정정 작업" });
            return "회계기간을 재개했습니다. 이전 마감 이력은 보존됩니다.";
          })}>기간 재개</button>}
      </section>
    </>}
    {error && <p role="alert" className="error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
  </div>;
}

function message(reason: unknown): string {
  if (reason instanceof ApiError && reason.status === 409) return `${reason.message} 최신 검사를 다시 실행해 주세요.`;
  return reason instanceof Error ? reason.message : "요청을 처리하지 못했습니다. 다시 시도해 주세요.";
}
