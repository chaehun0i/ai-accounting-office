"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";

type AgentRun = {
  id: string;
  transaction_id: string | null;
  status: "PENDING" | "RUNNING" | "WAITING_FOR_INPUT" | "COMPLETED" | "BLOCKED" | "FAILED";
  pending_action: string | null;
  controller_verdict: string | null;
  result_journal_id: string | null;
  error_code: string | null;
  version: number;
};
type RunStep = {
  id: string;
  step_no: number;
  node_name: string;
  status: string;
  error_code: string | null;
};
type RunEvent = {
  event_seq: number;
  event_type: string;
  stage: string;
  message_code: string | null;
  created_at: string;
};

function ProposalAudit({ companyId, runId, version }: {
  companyId: string; runId: string; version: number;
}) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<{ steps: RunStep[]; events: RunEvent[]; version: number } | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!open) return;
    let active = true;
    const headers = { "X-Company-ID": companyId };
    Promise.all([
      authenticatedRequest<RunStep[]>(`/agent/runs/${runId}/steps`, { headers }),
      authenticatedRequest<RunEvent[]>(`/agent/runs/${runId}/events`, { headers }),
    ]).then(([steps, events]) => {
      if (active) { setHistory({ steps, events, version }); setError(""); }
    }).catch(reason => {
      if (active) setError(reason instanceof ApiError ? reason.message : "실행 이력을 불러오지 못했습니다.");
    });
    return () => { active = false; };
  }, [open, companyId, runId, version, attempt]);

  return <details onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>전표 제안 실행 이력</summary>
    {open && <>
      <p>실행 ID {runId}</p>
      {error ? <><p role="alert">{error}</p>
        <button type="button" onClick={() => { setError(""); setAttempt(value => value + 1); }}>이력 다시 불러오기</button>
      </> : history?.version !== version ? <p role="status">실행 이력 확인 중…</p> : <>
        <h5>처리 단계</h5>
        {history.steps.length ? <ol>{history.steps.map(step => <li key={step.id}>
          {step.node_name} · {step.status}{step.error_code ? ` · ${step.error_code}` : ""}
        </li>)}</ol> : <p>기록된 처리 단계가 없습니다.</p>}
        <h5>감사 이벤트</h5>
        {history.events.length ? <ol>{history.events.map(event => <li key={event.event_seq}>
          <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString("ko-KR")}</time>
          {" · "}{event.event_type} · {event.stage}{event.message_code ? ` · ${event.message_code}` : ""}
        </li>)}</ol> : <p>기록된 감사 이벤트가 없습니다.</p>}
      </>}
    </>}
  </details>;
}

type ProposalLine = {
  account_id: string;
  account_code: string;
  account_name: string;
  debit_amount: string;
  credit_amount: string;
};
type ProposalPreview = {
  run_id: string;
  transaction_id: string;
  run_version: number;
  source_version: number;
  entry_date: string;
  description: string;
  lines: ProposalLine[];
  evidence_count: number;
  controller_verdict: string;
};

export function canUseAgentProposal(permissions: string[]): boolean {
  return ["transaction.read", "account.read", "journal.read", "journal.propose"]
    .every(permission => permissions.includes(permission));
}

export function agentReviewKey(companyId: string, transactionId: string): string {
  return `agent-proposal:${companyId}:${transactionId}`;
}

const message = (error: unknown) => error instanceof ApiError ? error.message : "전표 제안을 처리하지 못했습니다.";

export function AgentReview({ company, transaction }: {
  company: Company;
  transaction: { id: string; version: number; description: string; amount: string };
}) {
  const [run, setRun] = useState<AgentRun | null>(null);
  const [preview, setPreview] = useState<ProposalPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestKey = useRef<string | null>(null);
  const storageKey = agentReviewKey(company.id, transaction.id);
  const headers = { "X-Company-ID": company.id };
  const eligible = canUseAgentProposal(company.permissions);

  async function load(runId: string): Promise<AgentRun> {
    const current = await authenticatedRequest<AgentRun>(`/agent/runs/${runId}`, { headers });
    if (current.transaction_id !== transaction.id) throw new Error("거래와 제안 실행이 일치하지 않습니다.");
    const candidate = current.status === "WAITING_FOR_INPUT" && current.pending_action === "REVIEW_PROPOSAL"
      ? await authenticatedRequest<ProposalPreview>(`/agent/runs/${runId}/proposal`, { headers }) : null;
    setRun(current);
    setPreview(candidate);
    return current;
  }

  useEffect(() => {
    if (!eligible) return;
    const saved = window.sessionStorage.getItem(storageKey);
    if (!saved) return;
    let active = true;
    authenticatedRequest<AgentRun>(`/agent/runs/${saved}`, { headers: { "X-Company-ID": company.id } }).then(async current => {
      if (current.transaction_id !== transaction.id) throw new Error("거래와 제안 실행이 일치하지 않습니다.");
      const candidate = current.status === "WAITING_FOR_INPUT" && current.pending_action === "REVIEW_PROPOSAL"
        ? await authenticatedRequest<ProposalPreview>(`/agent/runs/${saved}/proposal`, { headers: { "X-Company-ID": company.id } }) : null;
      if (active) { setRun(current); setPreview(candidate); }
    }).catch(reason => {
      if (!active) return;
      window.sessionStorage.removeItem(storageKey);
      if (!(reason instanceof ApiError && [403, 404].includes(reason.status))) setError(message(reason));
    });
    return () => { active = false; };
  }, [company.id, eligible, storageKey, transaction.id]);

  useEffect(() => {
    if (!run || !["PENDING", "RUNNING"].includes(run.status)) return;
    const timer = window.setInterval(() => {
      void load(run.id).catch(reason => setError(message(reason)));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [run?.id, run?.status]);

  async function start() {
    setBusy(true); setError("");
    requestKey.current ??= crypto.randomUUID();
    try {
      const created = await authenticatedRequest<AgentRun>("/agent/runs/bookkeeper", {
        method: "POST", headers: { ...headers, "Idempotency-Key": requestKey.current },
        body: JSON.stringify({ transaction_id: transaction.id }),
      });
      window.sessionStorage.setItem(storageKey, created.id);
      requestKey.current = null;
      await load(created.id);
    } catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }

  async function decide(decision: "CONTINUE" | "REJECT") {
    if (!run || !preview || run.status !== "WAITING_FOR_INPUT") return;
    setBusy(true); setError("");
    try {
      const result = await authenticatedRequest<AgentRun>(`/agent/runs/${run.id}/resume`, {
        method: "POST", headers,
        body: JSON.stringify({ expected_version: preview.run_version, decision }),
      });
      setRun(result); setPreview(null);
    } catch (reason) {
      setError(message(reason));
      await load(run.id).catch(() => undefined);
    } finally { setBusy(false); }
  }

  const canRequest = !run || (["BLOCKED", "FAILED", "COMPLETED"].includes(run.status) && !run.result_journal_id);

  return <section className="panel" aria-label="AI 전표 제안">
    <h4>AI 전표 제안</h4>
    <p>선택한 거래의 계정과 금액을 검증해 초안을 제안합니다. 검토 후 진행해도 전표 승인이나 장부 반영은 하지 않습니다.</p>
    {!eligible ? <p>회계 담당자의 거래·계정 조회 및 전표 작성 권한이 필요합니다.</p> : <>
      {canRequest &&
        <button type="button" disabled={busy} onClick={() => void start()}>{busy ? "확인 중…" : run ? "새 제안 요청" : "전표 제안 받기"}</button>}
      {run && <p role="status">{run.status === "WAITING_FOR_INPUT" ? "사람 검토 대기" : run.status === "COMPLETED"
        ? run.result_journal_id ? "전표 초안 작성 완료" : "제안 거절 완료"
        : run.status === "BLOCKED" ? "검증 차단" : run.status === "FAILED" ? "제안 실패" : "제안 확인 중"}
        {run.error_code ? ` · ${run.error_code}` : ""}</p>}
      {preview && run?.status === "WAITING_FOR_INPUT" && <>
        <p>원천 거래: {transaction.description} · {transaction.amount}원 · 원천 버전 {preview.source_version}</p>
        <p>제안일 {preview.entry_date} · 증빙 {preview.evidence_count}건 · 검증 {preview.controller_verdict}</p>
        {transaction.version !== preview.source_version && <p role="alert">거래가 변경됐습니다. 이 제안을 거절한 뒤 최신 거래로 새 제안을 요청하세요.</p>}
        <div className="table-scroll"><table><thead><tr><th>계정</th><th>차변</th><th>대변</th></tr></thead><tbody>
          {preview.lines.map((line, index) => <tr key={`${line.account_id}:${index}`}><th scope="row">{line.account_code} · {line.account_name}</th><td>{line.debit_amount}</td><td>{line.credit_amount}</td></tr>)}
        </tbody></table></div>
        <div className="workspace-buttons">
          <button type="button" disabled={busy} onClick={() => void decide("REJECT")}>제안 거절</button>
          <button type="button" className="button-accent" disabled={busy || transaction.version !== preview.source_version}
            onClick={() => void decide("CONTINUE")}>검토 후 전표 초안 만들기</button>
        </div>
      </>}
      {run && <ProposalAudit key={`${company.id}:${run.id}`} companyId={company.id} runId={run.id} version={run.version} />}
      {run?.result_journal_id && <p><Link href={`/journals#journal-${run.result_journal_id}`}>작성된 전표 초안 확인하기</Link> · 제출·독립 승인·장부 반영은 전표 화면에서 진행합니다.</p>}
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
