"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";
import { financialStatementAskHref } from "@/features/ai-team/context";
import { formatMoney, type Account, type Period, type Source, type Statement, type StatementSet } from "./model";

type Kind = "BALANCE_SHEET" | "INCOME_STATEMENT";
const failure = (error: unknown) => error instanceof ApiError ? error.message : "재무제표를 불러오지 못했습니다.";
const mappingOptions: Record<string, [string, string][]> = {
  ASSET: [["ASSET_ACCOUNTS", "자산"]],
  LIABILITY: [["LIABILITY_ACCOUNTS", "부채"]],
  EQUITY: [["EQUITY_ACCOUNTS", "자본"]],
  REVENUE: [["REVENUE", "매출액"], ["NON_OPERATING_INCOME", "영업외수익"]],
  EXPENSE: [["COGS", "매출원가"], ["OPERATING_EXPENSE", "영업비용"], ["NON_OPERATING_EXPENSE", "영업외비용"], ["TAX_EXPENSE", "법인세비용"]],
};

export function FinancialStatements({ company }: { company: Company }) {
  const [periods, setPeriods] = useState<Period[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState("");
  const [periodId, setPeriodId] = useState("");
  const [sets, setSets] = useState<StatementSet[]>([]);
  const [setId, setSetId] = useState("");
  const [kind, setKind] = useState<Kind>("BALANCE_SHEET");
  const [statement, setStatement] = useState<Statement | null>(null);
  const [sourceCode, setSourceCode] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const retry = useRef<{ period: string; key: string } | null>(null);
  const scope = { "X-Company-ID": company.id };
  const selected = periods.find(period => period.id === periodId);
  const activeSet = sets.find(value => value.id === setId);

  useEffect(() => {
    let active = true;
    Promise.all([
      authenticatedRequest<Period[]>("/closing/periods", { headers: { "X-Company-ID": company.id } }),
      company.permissions.includes("financial_statement.generate")
        ? authenticatedRequest<Account[]>("/accounts", { headers: { "X-Company-ID": company.id } })
        : Promise.resolve([]),
    ])
      .then(([values, available]) => { if (active) { const closed = values.filter(value => value.status === "CLOSED"); setPeriods(closed); setPeriodId(closed[0]?.id ?? ""); const custom = available.filter(value => value.posting_allowed && value.template_account_id === null); setAccounts(custom); setAccountId(custom[0]?.id ?? ""); } })
      .catch(reason => { if (active) setError(failure(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company.id, company.permissions]);

  useEffect(() => {
    let active = true;
    setSetId(""); setStatement(null); setSources([]); setSourceCode("");
    if (!periodId) return () => { active = false; };
    authenticatedRequest<StatementSet[]>(`/financial-statements/sets?period_id=${encodeURIComponent(periodId)}`, { headers: { "X-Company-ID": company.id } })
      .then(values => { if (active) { setSets(values); setSetId(values[0]?.id ?? ""); } })
      .catch(reason => { if (active) setError(failure(reason)); });
    return () => { active = false; };
  }, [company.id, periodId, notice]);

  useEffect(() => {
    let active = true;
    setStatement(null); setSources([]); setSourceCode("");
    if (!setId) return () => { active = false; };
    authenticatedRequest<Statement>(`/financial-statements/sets/${setId}/${kind}`, { headers: { "X-Company-ID": company.id } })
      .then(value => { if (active) setStatement(value); })
      .catch(reason => { if (active) setError(failure(reason)); });
    return () => { active = false; };
  }, [company.id, setId, kind]);

  async function generate() {
    if (!periodId || !company.permissions.includes("financial_statement.generate")) return;
    if (retry.current?.period !== periodId) retry.current = { period: periodId, key: crypto.randomUUID() };
    setBusy(true); setError(""); setNotice("");
    try {
      const value = await authenticatedRequest<StatementSet>("/financial-statements/generate", {
        method: "POST", headers: { ...scope, "Idempotency-Key": retry.current.key },
        body: JSON.stringify({ period_id: periodId }),
      });
      retry.current = null; setSetId(value.id); setNotice("장부 기준과 계정 매핑을 검증하고 BS/IS 스냅샷을 생성했습니다.");
    } catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }

  async function drilldown(code: string) {
    if (!setId) return;
    setError(""); setSourceCode(code); setSources([]);
    try {
      const query = new URLSearchParams({ statement_type: kind, line_code: code });
      setSources(await authenticatedRequest<Source[]>(`/financial-statements/sets/${setId}/drilldown?${query}`, { headers: scope }));
    } catch (reason) { setError(failure(reason)); }
  }

  async function mapAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!periodId || !accountId) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(""); setNotice("");
    try {
      await authenticatedRequest("/financial-statements/mappings", {
        method: "POST", headers: scope,
        body: JSON.stringify({ period_id: periodId, account_id: accountId, line_code: form.get("line_code") }),
      });
      setNotice("회사 계정의 재무제표 표시 항목을 연결했습니다. BS/IS를 다시 생성해 주세요.");
    } catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }

  const selectedAccount = accounts.find(account => account.id === accountId);

  if (loading) return <p role="status" className="loading-message">마감된 회계기간을 확인하고 있습니다…</p>;
  return <div className="workspace-stack">
    <section className="panel">
      <h2>마감된 기간</h2>
      <p>재무제표는 확정된 전표와 월마감 시산표의 표현 스냅샷입니다. 생성해도 장부는 바뀌지 않습니다.</p>
      {periods.length === 0 ? <p>마감된 회계기간이 없습니다. <Link href="/closing">월마감 확인</Link></p> : <>
        <label>회계기간 <select aria-label="재무제표 회계기간" value={periodId} onChange={event => { setPeriodId(event.target.value); setNotice(""); }}>
          {periods.map(value => <option key={value.id} value={value.id}>{value.start_date} ~ {value.end_date} · 마감 {value.close_version}</option>)}
        </select></label>
        {selected && company.permissions.includes("financial_statement.generate") && <button disabled={busy} onClick={() => void generate()}>{busy ? "생성 중…" : "BS/IS 생성"}</button>}
      </>}
      {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}
    </section>
    {periodId && accounts.length > 0 && company.permissions.includes("financial_statement.generate") && <section className="panel"><details><summary>회사 추가 계정 표시 항목 연결</summary>
      <p>확정 전표에 사용한 회사 전용 계정이 매핑되지 않았다면 재무제표 생성이 차단됩니다. 해당 계정을 정확한 표시 항목에 연결하세요.</p>
      <form onSubmit={event => void mapAccount(event)}><label>계정 <select value={accountId} onChange={event => setAccountId(event.target.value)}>{accounts.map(account => <option key={account.id} value={account.id}>{account.account_code} {account.account_name}</option>)}</select></label>
        <label>표시 항목 <select name="line_code" key={accountId}>{(mappingOptions[selectedAccount?.account_type ?? ""] ?? []).map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
        <button disabled={busy || !selectedAccount}>계정 연결</button></form>
    </details></section>}
    {sets.length > 0 && <section className="panel"><h2>스냅샷 이력</h2><label>생성 결과 <select value={setId} onChange={event => setSetId(event.target.value)}>{sets.map(value => <option key={value.id} value={value.id}>마감 버전 {value.close_version} · Taxonomy v{value.taxonomy_version} · {value.generated_at.slice(0, 10)}</option>)}</select></label>
      {activeSet && <p>상태 {activeSet.status} · 원천 마감 {activeSet.closing_run_id} · 시산표 digest {activeSet.trial_balance_digest.slice(0, 12)}…</p>}</section>}
    {statement && <section className="panel"><h2>재무제표</h2><div className="section-navigation" role="tablist" aria-label="재무제표 종류">
      <button role="tab" aria-selected={kind === "BALANCE_SHEET"} onClick={() => setKind("BALANCE_SHEET")}>재무상태표</button>
      <button role="tab" aria-selected={kind === "INCOME_STATEMENT"} onClick={() => setKind("INCOME_STATEMENT")}>손익계산서</button>
      </div><p>생성 상태 {statement.status} · 스냅샷 {statement.snapshot_digest.slice(0, 12)}…</p>
      <table><thead><tr><th scope="col">항목</th><th scope="col">금액</th><th scope="col">출처와 질문</th></tr></thead><tbody>{statement.lines.map(line => <tr key={line.id}><th scope="row">{line.label}{line.subtotal_type === "TOTAL" ? " · 합계" : ""}</th><td>{formatMoney(line.current_amount)}</td><td><button onClick={() => void drilldown(line.line_code)}>계정·전표 보기</button> <Link href={financialStatementAskHref(periodId, kind, line.line_code)} aria-label={`${line.label} AI에게 묻기`}>AI에게 묻기</Link></td></tr>)}</tbody></table>
    </section>}
    {sourceCode && <section className="panel"><h2>{statement?.lines.find(line => line.line_code === sourceCode)?.label} 원장 출처</h2>
      {sources.length === 0 ? <p>이 항목에 연결된 확정 전표가 없습니다.</p> : <table><thead><tr><th scope="col">계정</th><th scope="col">전표</th><th scope="col">기준일</th><th scope="col">기여 금액</th></tr></thead><tbody>{sources.map(source => <tr key={source.journal_line_id}><th scope="row">{source.account_code} {source.account_name}</th><td>{source.journal_no || source.journal_id}<br /><Link href="/journals">전표 목록</Link></td><td>{source.entry_date}</td><td>{formatMoney(source.amount)}</td></tr>)}</tbody></table>}
    </section>}
  </div>;
}
