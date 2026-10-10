"use client";
import { useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import { useCompany } from "../company-provider";
import type { Company } from "../selection-state";

export function CompanyProfile({ company }: { company: Company }) {
  const context = useCompany();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const values = new FormData(event.currentTarget);
    try {
      await authenticatedRequest(`/companies/${company.id}`, { method: "PATCH", body: JSON.stringify({ expected_version: company.version, company_name: values.get("company_name"), address: values.get("address") }) });
      await context.select(company.id);
    } catch (error) { setError(error instanceof Error ? error.message : "회사정보를 저장하지 못했습니다."); }
    finally { setBusy(false); }
  }
  return <section className="panel"><h2>회사정보</h2><p>초기 설정을 다시 하지 않고 필요한 정보만 수정할 수 있습니다.</p>
    <form onSubmit={save}><fieldset disabled={busy || !company.permissions.includes("company.update")}>
      <label>회사명<input name="company_name" defaultValue={company.company_name} maxLength={200} required /></label>
      <label>주소<input name="address" defaultValue={company.address} maxLength={500} required /></label>
      <p className="muted">사업자등록번호와 사업자 유형은 이 화면에서 변경하지 않습니다.</p>
      <button className="button-accent" disabled={busy}>{busy ? "저장 중…" : "회사정보 저장"}</button>
    </fieldset>{error && <p role="alert">{error}</p>}</form>
    {!company.permissions.includes("company.update") && <p>조회만 가능합니다. 수정은 회사 관리자에게 요청해 주세요.</p>}
  </section>;
}
