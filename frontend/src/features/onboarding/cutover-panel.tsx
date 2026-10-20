"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import type { CutoverStatus } from "./model";
import { canPromoteCutover, cutoverPhase } from "./cutover-flow";

const journalLabels: Record<string, string> = {
  DRAFT: "초안", PROPOSED: "제출됨", REVIEW_REQUIRED: "승인 대기",
  APPROVED: "승인됨", POSTED: "장부 반영 완료",
};

export function CutoverPanel({ company }: { company: Company }) {
  const [status, setStatus] = useState<CutoverStatus>();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const headers = { "X-Company-ID": company.id };

  async function refresh() {
    const result = await authenticatedRequest<CutoverStatus>("/opening-balances/cutover-status", { headers });
    setStatus(result);
    return result;
  }

  useEffect(() => {
    let active = true;
    authenticatedRequest<CutoverStatus>("/opening-balances/cutover-status", { headers: { "X-Company-ID": company.id } })
      .then(result => { if (active) setStatus(result); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : "기초자료 상태를 불러오지 못했습니다."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company.id]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "처리하지 못했습니다. 다시 시도해 주세요."); }
    finally { setBusy(false); }
  }

  const canPropose = company.permissions.includes("journal.propose");
  const canPromote = status ? canPromoteCutover(status, company.permissions) : false;
  const posted = status?.journal_status === "POSTED";
  const complete = !!status && ["NO_OPENING", "COMPLETE"].includes(cutoverPhase(status));

  return <section className="panel setup-complete" aria-label="기초자료 이관">
    <span className="eyebrow">회계 준비 완료</span><h2>기초자료 이관</h2>
    {loading && <p role="status">기초자료 진행 상태를 확인하고 있습니다…</p>}
    {error && <p role="alert" className="error">{error} <button disabled={busy} onClick={() => void run(refresh)}>다시 확인</button></p>}
    {notice && <p role="status">{notice}</p>}
    {status && <>
      {status.no_opening_balance ? <p>기초자료 이관 필요 없음 · 신규 회사의 회계 준비가 완료됐습니다.</p> : <>
        <ol className="cutover-progress">
          <li>기초자료 검증 완료</li>
          <li>Opening Journal {status.journal_id ? "작성 완료" : "작성 필요"}</li>
          <li>전표 제출·독립 승인·장부 반영 {posted ? "완료" : journalLabels[status.journal_status ?? ""] ?? "대기 중"}</li>
          {status.ar_ap_source_present && <>
            <li>채권·채무 미결 항목 대조 {posted ? status.ar_ap_preview_ready ? "준비 완료" : "확인 필요" : "장부 반영 대기"}</li>
            <li>채권·채무 반영 {status.ar_ap_promoted ? "완료" : "대기 중"}</li>
          </>}
          <li>Cutover {complete ? "완료" : "진행 중"}</li>
        </ol>
        {!status.journal_id && status.opening_required && (canPropose ?
          <button disabled={busy} onClick={() => void run(async () => {
            await authenticatedRequest("/opening-balances/imports", {
              method: "POST", headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
              body: JSON.stringify({ expected_version: status.session_version }),
            });
            setNotice("기초잔액 전표를 만들었습니다. 전표 화면에서 제출한 뒤 별도 사용자가 승인·장부 반영해 주세요.");
          })}>기초잔액 전표 만들기</button> :
          <p>전표 작성 권한이 없습니다. 회사 관리자에게 요청해 주세요.</p>)}
        {status.journal_id && <p>전표 상태: {journalLabels[status.journal_status ?? ""] ?? status.journal_status} · <Link href={`/journals#journal-${status.journal_id}`}>전표 확인하기</Link></p>}
        {status.journal_id && !posted && <p className="muted">전표 화면에서 제출하고, 작성자와 다른 사용자가 승인한 뒤 장부에 반영해야 합니다.</p>}
        {posted && status.ar_ap_source_present && !status.ar_ap_promoted && <>
          <h3>채권·채무 사전 대조</h3>
          <p>{status.ar_ap_preview_ready ? "반영할 준비가 됐습니다." : "원천을 확인해 주세요."}</p>
          {status.ar_ap_totals.length > 0 && <ul>{status.ar_ap_totals.map(total => <li key={`${total.role}:${total.account_code}:${total.counterparty_code}`}>
            {total.role === "AR" ? "매출채권" : "매입채무"} · {total.counterparty_code} · 기초잔액 {total.opening_amount} / 미결 항목 {total.item_amount}
          </li>)}</ul>}
          {status.ar_ap_issues.length > 0 && <ul>{status.ar_ap_issues.map((issue, index) => <li key={index} className="error">{issue.section} {issue.row_key}: {issue.message}</li>)}</ul>}
          {status.ar_ap_preview_ready && status.ar_ap_source_digest && (canPromote ?
            <button disabled={busy} onClick={() => void run(async () => {
              const result = await authenticatedRequest<{ receivables: unknown[]; payables: unknown[] }>("/opening-balances/ar-ap-promotion", {
                method: "POST", headers,
                body: JSON.stringify({ expected_version: status.session_version, expected_digest: status.ar_ap_source_digest }),
              });
              setNotice(`미결 항목을 반영했습니다. 매출채권 ${result.receivables.length}건, 매입채무 ${result.payables.length}건입니다.`);
            })}>기초 채권·채무 반영</button> :
            <p>채권·채무 반영 권한이 없습니다. 담당자에게 요청해 주세요.</p>)}
        </>}
        {status.ar_ap_promoted && <p>반영 완료 · 매출채권 {status.receivable_count}건 · 매입채무 {status.payable_count}건</p>}
      </>}
      {complete && <p role="status">Cutover 완료</p>}
      <div className="workspace-buttons"><button disabled={busy} onClick={() => void run(refresh)}>상태 새로고침</button><Link href="/receivables">채권 확인</Link><Link href="/payables">채무 확인</Link><Link href="/accounting">회계 설정</Link></div>
    </>}
  </section>;
}
