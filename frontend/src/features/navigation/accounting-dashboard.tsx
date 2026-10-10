"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, CalendarDays, ClipboardCheck, Files, BookOpen } from "lucide-react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { localDate } from "@/shared/calendar";
import { journalStatus } from "@/features/accounting/journal-model";

type Period = { id: string; fiscal_year: number; period_no: number; start_date: string; end_date: string; status: string };
type Entry = { id: string; entry_date: string; description: string; journal_no: string | null; status: string };

export function AccountingDashboard({ company }: { company: Company }) {
  const [periods, setPeriods] = useState<Period[]>();
  const [periodId, setPeriodId] = useState("");
  const [entries, setEntries] = useState<Entry[]>();
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const period = periods?.find(value => value.id === periodId);
  const canReadPeriods = company.permissions.includes("period.read");
  const canReadJournals = company.permissions.includes("journal.read");
  useEffect(() => {
    if (!canReadPeriods) return;
    let active = true;
    authenticatedRequest<Period[]>("/accounting/periods", { headers: { "X-Company-ID": company.id } })
      .then(value => {
        if (!active) return;
        setPeriods(value);
        const today = localDate();
        setPeriodId(value.find(row => row.start_date <= today && row.end_date >= today)?.id ?? value.at(-1)?.id ?? "");
        setError("");
      }).catch(error => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [company.id, canReadPeriods, retry]);
  useEffect(() => {
    if (!period || !canReadJournals) return;
    let active = true;
    authenticatedRequest<Entry[]>(`/journals?date_from=${period.start_date}&date_to=${period.end_date}`, { headers: { "X-Company-ID": company.id } })
      .then(value => { if (active) { setEntries(value); setError(""); } })
      .catch(error => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [company.id, period, canReadJournals, retry]);
  const pending = entries?.filter(row => ["PROPOSED", "REVIEW_REQUIRED"].includes(row.status));
  const approved = entries?.filter(row => row.status === "APPROVED");
  return <>
    <section className="panel accounting-project">
      <div className="section-toolbar"><div><span className="eyebrow">회사 회계 워크스페이스</span><h2>{company.company_name}</h2><p>회계기간별 기록과 검토할 업무를 한곳에서 확인하세요.</p></div><span className="status-chip">실제 장부 기준</span></div>
      <div className="accounting-period-picker"><CalendarDays aria-hidden="true" size={20} />{canReadPeriods ? <label>업무 회계기간<select value={periodId} onChange={event => { setPeriodId(event.target.value); setEntries(undefined); }}><option value="">회계기간 선택</option>{periods?.map(row => <option key={row.id} value={row.id}>{row.fiscal_year} 회계연도 · {row.period_no}기 ({row.start_date} ~ {row.end_date})</option>)}</select></label> : <p>회계기간 조회 권한이 필요합니다.</p>}{period && <span className="status-chip">{period.status === "OPEN" ? "기록 가능" : "마감된 기간"}</span>}</div>
      {!periods && canReadPeriods && !error && <p role="status">회계기간을 확인하고 있습니다…</p>}
      {periods?.length === 0 && <p>아직 회계연도가 설정되지 않았습니다. <Link href="/accounting">회계 설정 확인</Link></p>}
      {error && <div role="alert"><p className="error">{error}</p><button onClick={() => setRetry(value => value + 1)}>다시 확인</button></div>}
      <div className="workspace-stats"><div><Files size={20} aria-hidden="true" /><span>작성 중 전표</span><strong>{entries?.filter(row => row.status === "DRAFT").length ?? "—"}</strong></div><div><ClipboardCheck size={20} aria-hidden="true" /><span>검토할 전표</span><strong>{pending?.length ?? "—"}</strong></div><div><BookOpen size={20} aria-hidden="true" /><span>장부 반영 대기</span><strong>{approved?.length ?? "—"}</strong></div><div><span>장부 반영 완료</span><strong>{entries?.filter(row => row.status === "POSTED").length ?? "—"}</strong></div></div>
      <small className="muted">선택한 기간의 전표 조회 결과(최대 500건) 기준입니다. 조회하지 못한 값은 —로 표시합니다.</small>
    </section>
    <div className="accounting-home-grid"><section className="panel"><div className="section-toolbar"><h2>회계 업무 흐름</h2></div><ol className="task-timeline">{[
      ["회계 준비", "회사정보와 기초잔액을 확인합니다.", "/onboarding", "onboarding.read"],
      ["거래·증빙 정리", "거래를 기록하고 원본 출처를 확인합니다.", "/transactions", "transaction.read"],
      ["전표 작성·승인", "분개를 제출하고 별도 검토자의 승인을 받습니다.", "/journals", "journal.read"],
      ["장부 확인", "반영된 기록을 원장과 시산표에서 확인합니다.", "/trial-balance", "ledger.read"],
    ].map(([label, description, href, permission]) => <li key={href}><span><strong>{label}</strong><small>{description}</small></span>{company.permissions.includes(permission) ? <Link href={href} aria-label={`${label} 열기`}><ArrowRight size={19} /></Link> : <small>담당자 권한 필요</small>}</li>)}</ol></section>
      <section className="panel"><div className="section-toolbar"><h2>최근 회계 기록</h2>{canReadJournals && <Link href="/journals">전체 보기</Link>}</div>{!canReadJournals ? <p>전표 조회 권한이 필요합니다.</p> : !period ? <p>회계기간을 선택해 주세요.</p> : !entries ? <p role="status">회계 기록을 확인하고 있습니다…</p> : entries.length === 0 ? <div className="workspace-empty"><BookOpen size={32} aria-hidden="true" /><h3>아직 기록된 전표가 없습니다</h3><p>거래를 확인한 뒤 전표를 작성해 주세요. 승인·장부 반영 전에는 장부에 포함되지 않습니다.</p></div> : <div className="table-scroll"><table><thead><tr><th>일자·전표</th><th>적요</th><th>상태</th></tr></thead><tbody>{[...entries].sort((a, b) => b.entry_date.localeCompare(a.entry_date) || a.id.localeCompare(b.id)).slice(0, 6).map(row => <tr key={row.id}><td><Link href={`/journals#journal-${row.id}`}>{row.entry_date}<small>{row.journal_no ?? "초안"}</small></Link></td><td>{row.description}</td><td><span className="status-chip">{journalStatus[row.status] ?? "확인 필요"}</span></td></tr>)}</tbody></table></div>}</section></div>
  </>;
}
