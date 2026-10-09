"use client";

import { useEffect, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import { ApiError } from "@/shared/api";
import type { Company } from "@/features/companies/selection-state";

type Settings = {
  functional_currency_code: string; fiscal_year_start_month: number;
  journal_number_prefix: string; allow_manual_journal: boolean; version: number;
};
type Account = { id: string; account_code: string; account_name: string; posting_allowed: boolean };
type Period = { id: string; start_date: string; end_date: string; status: "OPEN" | "CLOSED" };
type Template = { id: string; name: string; version: number };

export function AccountingMaster({ company }: { company: Company }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [periods, setPeriods] = useState<Period[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const canRead = company.permissions.includes("account.read");
  const canManage = company.permissions.includes("company.accounting_settings.update");
  const headers = { "X-Company-ID": company.id };

  useEffect(() => {
    let current = true;
    setLoading(true); setError("");
    if (!canRead) { setLoading(false); return; }
    const scoped = <T,>(path: string) => authenticatedRequest<T>(path, { headers: { "X-Company-ID": company.id } });
    Promise.all([
      scoped<Settings>("/accounting/settings").catch(error => {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }),
      scoped<Account[]>("/accounts"), scoped<Period[]>("/accounting/periods"),
      scoped<Template[]>("/account-templates"),
    ]).then(([value, list, dates, available]) => {
      if (!current) return;
      setSettings(value); setAccounts(list); setPeriods(dates); setTemplates(available);
    }).catch(error => { if (current) setError(error.message); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [company.id, canRead, retry]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const fields = new FormData(event.currentTarget);
    try {
      if (settings) {
        await authenticatedRequest("/accounting/settings", { method: "PATCH", headers,
          body: JSON.stringify({ expected_version: settings.version,
            journal_number_prefix: fields.get("prefix"), allow_manual_journal: fields.has("manual") }) });
      } else {
        await authenticatedRequest("/accounting/initialize", { method: "POST", headers,
          body: JSON.stringify({ fiscal_year: Number(fields.get("year")), template_id: fields.get("template"),
            fiscal_year_start_month: Number(fields.get("month")), functional_currency_code: "KRW" }) });
      }
      setRetry(value => value + 1);
    } catch (error) { setError(error instanceof Error ? error.message : "회계 정보를 저장하지 못했습니다."); }
    finally { setBusy(false); }
  }

  if (!canRead) return <section className="panel"><h2>회계 기준 정보</h2><p>회계 기준 정보를 조회하려면 회사 관리자에게 권한을 요청해 주세요.</p></section>;
  if (loading) return <p role="status">회계 기준 정보를 확인하고 있습니다…</p>;
  return <section className="panel">
    <h2>회계 기준 정보</h2>
    {error && <div role="alert"><p className="error">{error}</p><button onClick={() => setRetry(value => value + 1)}>다시 확인</button></div>}
    {settings ? <>
      <p>회계 기준 통화 {settings.functional_currency_code} · 회계연도 시작 {settings.fiscal_year_start_month}월</p>
      {canManage && <form onSubmit={submit} key={settings.version}>
        <label>전표번호 접두어<input name="prefix" defaultValue={settings.journal_number_prefix} pattern="[A-Z][A-Z0-9]{0,9}" maxLength={10} required /></label>
        <label><input name="manual" type="checkbox" defaultChecked={settings.allow_manual_journal} /> 수기 전표 허용</label>
        <button disabled={busy}>{busy ? "저장 중…" : "회계 설정 저장"}</button>
      </form>}
      <h3>계정과목 ({accounts.length}개)</h3>
      <table><thead><tr><th>코드</th><th>계정과목</th><th>전기 가능</th></tr></thead><tbody>
        {accounts.map(account => <tr key={account.id}><td>{account.account_code}</td><td>{account.account_name}</td><td>{account.posting_allowed ? "가능" : "분류용"}</td></tr>)}
      </tbody></table>
      <h3>회계기간</h3><ul>{periods.map(period => <li key={period.id}>{period.start_date} ~ {period.end_date} · {period.status === "OPEN" ? "열림" : "마감"}</li>)}</ul>
    </> : <>
      <p>아직 회계 기준 정보가 없습니다. 회사의 회계연도를 확인한 뒤 초기 설정을 진행해 주세요.</p>
      {canManage && templates.length > 0 ? <form onSubmit={submit}>
        <label>계정과목 기본안<select name="template">{templates.map(template => <option key={template.id} value={template.id}>{template.name} (버전 {template.version})</option>)}</select></label>
        <label>회계연도 시작 연도<input name="year" type="number" min={2026} max={9998} defaultValue={new Date().getFullYear()} required /></label>
        <label>회계연도 시작 월<select name="month">{Array.from({ length: 12 }, (_, i) => <option key={i} value={i + 1}>{i + 1}월</option>)}</select></label>
        <p className="muted">초기 설정 후 회계 기준 통화와 회계연도 시작 월은 이 화면에서 변경할 수 없습니다.</p>
        <button disabled={busy}>{busy ? "설정 중…" : "회계 기준 정보 만들기"}</button>
      </form> : <p>{canManage ? "사용 가능한 계정과목 기본안이 없습니다. 운영 담당자에게 문의해 주세요." : "회사 관리자가 회계 초기 설정을 진행할 수 있습니다."}</p>}
    </>}
  </section>;
}
