"use client";

import { useEffect, useRef, useState } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";
import { equityReviewActions } from "./equity-review-model";
import { RequestScope } from "./request-scope";

type Review = {
  status: string; version: number; source_stale: boolean;
  events: { id: string; status: string; reason: string; actor_id: string; created_at: string }[];
};
const labels: Record<string, string> = {
  NOT_REQUESTED: "검토 요청 전", REVIEW_REQUESTED: "독립 검토 대기",
  APPROVED: "내부 검토 승인", REJECTED: "반려",
};

export function EquityReview({ company, snapshotId, basePath = "/equity/statements", title = "자본변동표", exportTarget }: { company: Company; snapshotId: string; basePath?: string; title?: string; exportTarget?: { period_id: string; date_from: string; date_to: string; expected_review_digest: string } }) {
  const [review, setReview] = useState<Review | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const requests = useRef(new RequestScope());
  const retry = useRef<{ fingerprint: string; key: string } | null>(null);
  const path = `${basePath}/${snapshotId}/review`;
  useEffect(() => {
    const scope = requests.current;
    const current = scope.start("read");
    authenticatedRequest<Review>(path, { headers: { "X-Company-ID": company.id } })
      .then(value => { if (current()) setReview(value); })
      .catch(reason => { if (current()) setError(reason instanceof ApiError ? reason.message : "검토 상태를 조회하지 못했습니다."); });
    return () => scope.invalidate();
  }, [company.id, path, refresh]);

  async function act(action: string) {
    if (!review || busy || !reason.trim()) return;
    const current = requests.current.start("mutation");
    const payload = { expected_version: review.version, reason };
    const fingerprint = JSON.stringify([company.id, snapshotId, action, payload]);
    if (retry.current?.fingerprint !== fingerprint) retry.current = { fingerprint, key: crypto.randomUUID() };
    setBusy(true); setError("");
    try {
      await authenticatedRequest(`${path}/${action}`, {
        method: "POST", headers: { "X-Company-ID": company.id, "Idempotency-Key": retry.current.key },
        body: JSON.stringify(payload),
      });
      if (!current()) return;
      retry.current = null; setReason(""); setRefresh(value => value + 1);
    } catch (reason) {
      if (current()) setError(reason instanceof ApiError ? reason.message : "검토 상태 변경에 실패했습니다.");
    } finally { if (current()) setBusy(false); }
  }

  const [format, setFormat] = useState("PDF");
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState("");
  const exportRetry = useRef<{ fingerprint: string; key: string } | null>(null);
  async function exportApproved() {
    if (!exportTarget || review?.status !== "APPROVED" || review.source_stale || !confirmed || busy) return;
    const current = requests.current.start("export");
    const body = JSON.stringify({ ...exportTarget, approved_snapshot_id: snapshotId,
      expected_version: review.version, format, confirmed: true });
    if (exportRetry.current?.fingerprint !== body) exportRetry.current = { fingerprint: body, key: crypto.randomUUID() };
    setBusy(true); setError(""); setResult("");
    try {
      const run = await authenticatedRequest<{id: string; status: string; answer_resource_id: string | null; error_code: string | null}>(
        "/agent/actions/approved-set-export", {
          method: "POST", headers: { "X-Company-ID": company.id, "Idempotency-Key": exportRetry.current.key }, body,
        });
      if (current()) {
        setResult(run.status === "COMPLETED" && run.answer_resource_id
          ? "보고서 생성 완료 · " + run.answer_resource_id : "실행 " + run.status + " · " + (run.error_code ?? run.id));
        if (run.status === "COMPLETED") { setConfirmed(false); exportRetry.current = null; }
      }
    } catch (reason) {
      if (current()) setError(reason instanceof ApiError ? reason.message : "승인 세트 내보내기에 실패했습니다.");
    } finally { if (current()) setBusy(false); }
  }

  const actions = review ? equityReviewActions(review.status, review.source_stale, company.permissions) : [];
  return <section aria-label={`${title} 독립 검토`}>
    <h4>{title} 독립 검토</h4>
    <p>생성자·검토 요청자와 다른 검토자가 승인합니다. 승인은 내부 검증용이며 법정 공시·감사 완료를 뜻하지 않습니다.</p>
    {error && <p role="alert">{error}</p>}
    {!review ? <p role="status">{error ? "검토 상태를 다시 조회해 주세요." : "검토 상태 확인 중…"}</p> : <>
      <p role="status">{labels[review.status] ?? review.status}{review.source_stale && " · 원천 변경: 새 스냅샷을 생성하세요"}</p>
      {!review.source_stale && review.status !== "APPROVED" && <>
        <label>검토 의견<input value={reason} maxLength={1000} onChange={event => setReason(event.target.value)} /></label>
        {actions.includes("request-review") &&
          <button disabled={busy || !reason.trim()} onClick={() => void act("request-review")}>독립 검토 요청</button>}
        {actions.includes("approve") && <>
          <button disabled={busy || !reason.trim()} onClick={() => void act("approve")}>검토 승인</button>
          <button disabled={busy || !reason.trim()} onClick={() => void act("reject")}>반려</button>
        </>}
      </>}
      {review.status === "APPROVED" && !review.source_stale && <p>현재 승인본을 Report Center에서 내보낼 수 있습니다.</p>}
      {exportTarget && review.status === "APPROVED" && !review.source_stale
        && ["period.read", "financial_statement.read", "report.generate", "report.export"].every(permission => company.permissions.includes(permission))
        && <fieldset disabled={busy}><legend>승인 세트 내보내기</legend>
          <p>승인 버전 {review.version} · 원천 digest {exportTarget.expected_review_digest}</p>
          <label>파일 형식 <select value={format} onChange={event => { setFormat(event.target.value); setConfirmed(false); }}>
            <option>PDF</option><option>XLSX</option><option>CSV</option>
          </select></label>
          <label><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /> 이 승인 세트와 파일 형식을 확인했습니다.</label>
          <button disabled={!confirmed} onClick={() => void exportApproved()}>확인한 세트 내보내기</button>
        </fieldset>}
      {result && <p role="status">{result}</p>}
      <ul>{review.events.map(event => <li key={event.id}>{labels[event.status]} · {event.reason} · {event.created_at} · 검토자 {event.actor_id}</li>)}</ul>
    </>}
    <button disabled={busy} onClick={() => { setError(""); setRefresh(value => value + 1); }}>검토 상태 새로고침</button>
  </section>;
}
