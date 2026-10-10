"use client";
import { useEffect, useState } from "react";
import { authenticatedRequest } from "@/features/auth/session";

type Account = { id: string; account_code: string; account_name: string; account_type: string; posting_allowed: boolean };
const labels: Record<string, string> = { ASSET: "자산", LIABILITY: "부채", EQUITY: "자본", REVENUE: "수익", EXPENSE: "비용" };

export function AccountCatalog({ companyId }: { companyId: string }) {
  const [accounts, setAccounts] = useState<Account[]>();
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    authenticatedRequest<Account[]>("/accounts", { headers: { "X-Company-ID": companyId } })
      .then(value => { if (active) setAccounts(value); })
      .catch(error => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [companyId]);
  return <section aria-label="서버 계정과목 목록">
    <p className="catalog-notice">계정과목은 서버에서 준비합니다. 직접 추가하거나 Excel로 새 계정을 만들 필요 없이, 전표 작성 시 목록에서 선택하세요.</p>
    <label>계정코드·계정명 검색<input value={search} onChange={event => setSearch(event.target.value)} placeholder="예: 보통예금" /></label>
    {error && <p role="alert">{error}</p>}
    {!accounts && !error && <p role="status">계정과목을 확인하고 있습니다…</p>}
    {accounts && <div className="table-scroll"><table><thead><tr><th>계정코드</th><th>계정과목</th><th>구분</th><th>전표 입력</th></tr></thead><tbody>{accounts.filter(row => `${row.account_code} ${row.account_name}`.includes(search.trim())).map(row => <tr key={row.id}><td>{row.account_code}</td><td>{row.account_name}</td><td>{labels[row.account_type] ?? "확인 필요"}</td><td>{row.posting_allowed ? "사용 가능" : "분류 계정"}</td></tr>)}</tbody></table>{accounts.length === 0 && <p>계정과목 준비 상태를 운영 담당자에게 확인해 주세요.</p>}</div>}
  </section>;
}
