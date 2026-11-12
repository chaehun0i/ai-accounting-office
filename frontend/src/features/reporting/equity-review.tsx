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

export function EquityReview({ company, snapshotId }: { company: Company; snapshotId: string }) {
  const [review, setReview] = useState<Review | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const requests = useRef(new RequestScope());
  const retry = useRef<{ fingerprint: string; key: string } | null>(null);
  const path = `/equity/statements/${snapshotId}/review`;
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

  const actions = review ? equityReviewActions(review.status, review.source_stale, company.permissions) : [];
  return <section aria-label="자본변동표 독립 검토">
    <h4>자본변동표 독립 검토</h4>
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
      <ul>{review.events.map(event => <li key={event.id}>{labels[event.status]} · {event.reason} · {event.created_at} · 검토자 {event.actor_id}</li>)}</ul>
    </>}
    <button disabled={busy} onClick={() => { setError(""); setRefresh(value => value + 1); }}>검토 상태 새로고침</button>
  </section>;
}
