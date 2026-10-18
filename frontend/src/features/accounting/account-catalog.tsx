"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import { ApiError } from "@/shared/api";

type Account = {
  id: string; account_code: string; account_name: string; account_type: string;
  posting_allowed: boolean; template_account_id: string | null;
  control_account_type: string | null; status: "ACTIVE" | "INACTIVE"; version: number;
};
type Action = "edit" | "deactivate";
const labels: Record<string, string> = { ASSET: "자산", LIABILITY: "부채", EQUITY: "자본", REVENUE: "수익", EXPENSE: "비용" };
const roles: Record<string, string> = {
  AR: "매출채권", AP: "매입채무", TAX_INPUT: "매입 부가세", TAX_OUTPUT: "매출 부가세",
  BANK_CASH: "현금·예금", CARD_CLEARING: "카드 미수", CARD_PAYABLE: "카드 미지급",
};

export function AccountCatalog({ companyId, canCreate = false, canUpdate = false, canDeactivate = false }: {
  companyId: string; canCreate?: boolean; canUpdate?: boolean; canDeactivate?: boolean;
}) {
  const [accounts, setAccounts] = useState<Account[]>();
  const [search, setSearch] = useState("");
  const [accountType, setAccountType] = useState("");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [action, setAction] = useState<{ id: string; kind: Action } | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState("");
  const load = useCallback(async () => authenticatedRequest<Account[]>("/accounts", { headers: { "X-Company-ID": companyId } }), [companyId]);
  useEffect(() => {
    let active = true;
    setAccounts(undefined); setError(""); setSaved(""); setEditing(false); setAction(null);
    load().then(value => { if (active) setAccounts(value); })
      .catch(failure => { if (active) setError(failure instanceof Error ? failure.message : "계정과목을 불러오지 못했습니다."); });
    return () => { active = false; };
  }, [load]);
  async function refresh() {
    setError("");
    try { setAccounts(await load()); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "계정과목을 다시 불러오지 못했습니다."); }
  }
  async function createAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setSaved("");
    const form = event.currentTarget;
    const fields = new FormData(form);
    try {
      const value = await authenticatedRequest<Account>("/accounts", {
        method: "POST", headers: { "X-Company-ID": companyId },
        body: JSON.stringify({ account_code: fields.get("code"), account_name: fields.get("name"),
          account_type: fields.get("type"), is_contra: fields.has("contra"),
          parent_account_id: fields.get("parent") || null }),
      });
      setAccounts(current => [...(current ?? []), value].sort((a, b) => a.account_code.localeCompare(b.account_code)));
      form.reset(); setEditing(false); setSaved("우리 회사 계정과목을 추가했습니다.");
    } catch (failure) { setError(failure instanceof Error ? failure.message : "추가하지 못했습니다. 다시 확인해 주세요."); }
    finally { setBusy(false); }
  }
  async function submitAction(event: FormEvent<HTMLFormElement>, account: Account, kind: Action) {
    event.preventDefault(); setBusy(true); setError(""); setSaved("");
    const fields = new FormData(event.currentTarget);
    const path = kind === "edit" ? `/accounts/${account.id}` : `/accounts/${account.id}/deactivate`;
    const body = kind === "edit"
      ? { expected_version: account.version, account_code: String(fields.get("code") ?? "").trim(), account_name: String(fields.get("name") ?? "").trim() }
      : { expected_version: account.version, reason: String(fields.get("reason") ?? "").trim() };
    try {
      const value = await authenticatedRequest<Account>(path, {
        method: kind === "edit" ? "PATCH" : "POST", headers: { "X-Company-ID": companyId }, body: JSON.stringify(body),
      });
      setAccounts(current => current?.map(row => row.id === value.id ? value : row).sort((a, b) => a.account_code.localeCompare(b.account_code)));
      setAction(null);
      setSaved(kind === "edit" ? "계정과목을 수정했습니다." : "계정과목을 비활성화했습니다.");
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 409) {
        setAction(null); await refresh(); setError("다른 변경 사항이 먼저 저장되었습니다. 최신 계정과목을 확인하고 다시 시도해 주세요.");
      } else setError(failure instanceof Error ? failure.message : "변경 사항을 저장하지 못했습니다.");
    } finally { setBusy(false); }
  }
  const visible = accounts?.filter(row => (!accountType || row.account_type === accountType) && `${row.account_code} ${row.account_name}`.includes(search.trim()));
  return <section aria-label="서버 계정과목 목록">
    <p className="catalog-notice">전표 작성에 사용할 계정과목입니다. 계정명이나 코드를 검색해 확인하세요.</p>
    {canCreate && <button onClick={() => { setEditing(!editing); setAction(null); setSaved(""); }}>우리 회사 계정과목 추가</button>}
    {editing && <form onSubmit={createAccount} aria-label="회사 계정과목 추가">
      <p>추가한 계정은 현재 회사에서만 사용할 수 있습니다.</p>
      <label>계정코드<input name="code" required maxLength={20} pattern="[A-Z0-9][A-Z0-9_-]*" placeholder="예: CUSTOM_001" /></label>
      <label>계정명<input name="name" required maxLength={200} placeholder="예: 온라인 판매수수료" /></label>
      <label>계정 구분<select name="type" aria-label="계정 구분">{Object.entries(labels).map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
      <label>상위 계정<select name="parent" aria-label="상위 계정"><option value="">별도 계정으로 추가</option>{accounts?.filter(a => !a.posting_allowed && a.status === "ACTIVE").map(a => <option key={a.id} value={a.id}>{a.account_name}</option>)}</select></label>
      <label><input name="contra" type="checkbox" />차감 계정으로 사용 (감가상각누계액 등)</label>
      <button disabled={busy} type="submit">{busy ? "저장 중…" : "추가"}</button><button type="button" disabled={busy} onClick={() => setEditing(false)}>취소</button>
    </form>}
    {saved && <p role="status">{saved}</p>}
    <label>계정코드·계정명 검색<input value={search} onChange={event => setSearch(event.target.value)} placeholder="예: 보통예금" /></label>
    <label>계정 구분<select value={accountType} onChange={event => setAccountType(event.target.value)}><option value="">전체 계정</option>{Object.entries(labels).map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
    {accounts && <p className="muted">전체 {accounts.length}개 · 현재 {visible?.length}개 표시</p>}
    {error && <p role="alert">{error} <button type="button" onClick={refresh}>목록 새로고침</button></p>}
    {!accounts && !error && <p role="status">계정과목을 확인하고 있습니다…</p>}
    {accounts && <div className="table-scroll"><table><thead><tr><th>계정코드</th><th>계정과목</th><th>구분</th><th>전표 입력</th><th>관리 역할</th><th>상태</th><th>관리</th></tr></thead><tbody>{visible?.map(row => <tr key={row.id}>
      <td>{row.account_code}</td><td>{row.account_name}</td><td>{labels[row.account_type] ?? "확인 필요"}</td>
      <td>{row.posting_allowed ? "사용 가능" : "분류 계정"}</td><td>{row.control_account_type ? roles[row.control_account_type] ?? row.control_account_type : "—"}</td>
      <td>{row.status === "ACTIVE" ? "사용 중" : "비활성"}</td>
      <td>{row.status === "ACTIVE" && <>{canUpdate && !row.template_account_id && <button disabled={busy} onClick={() => { setAction({ id: row.id, kind: "edit" }); setEditing(false); }}>수정</button>}{canDeactivate && !row.template_account_id && <button disabled={busy} onClick={() => { setAction({ id: row.id, kind: "deactivate" }); setEditing(false); }}>비활성화</button>}</>}</td>
    </tr>)}</tbody></table>{accounts.length > 0 && visible?.length === 0 && <p role="status">검색 결과가 없습니다. 계정명이나 코드를 다시 확인해 주세요.</p>}{accounts.length === 0 && <p>계정과목 준비 상태를 운영 담당자에게 확인해 주세요.</p>}</div>}
    {action && accounts?.filter(row => row.id === action.id).map(row => <form key={`${row.id}-${action.kind}`} onSubmit={event => submitAction(event, row, action.kind)} aria-label={`${row.account_name} ${action.kind === "edit" ? "수정" : "비활성화"}`}>
      <h3>{row.account_name} · {action.kind === "edit" ? "수정" : "비활성화"}</h3>
      {action.kind === "edit" ? <><label>계정코드<input name="code" defaultValue={row.account_code} required maxLength={20} pattern="[A-Z0-9][A-Z0-9_-]*" /></label><label>계정명<input name="name" defaultValue={row.account_name} required maxLength={200} /></label></> : <>
        <label>변경 사유<input name="reason" required maxLength={500} /></label>
      </>}
      <button type="submit" disabled={busy}>{busy ? "저장 중…" : action.kind === "deactivate" ? "비활성화 확인" : "저장"}</button><button type="button" disabled={busy} onClick={() => setAction(null)}>취소</button>
    </form>)}
  </section>;
}
