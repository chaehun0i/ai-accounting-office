"use client";

import { useState, type FormEvent } from "react";
import { OfficeDialog } from "@/shared/ui/dialog";
import { Plus } from "lucide-react";
import { authenticatedRequest } from "@/features/auth/session";
import { useCompany } from "../company-provider";

export function CompanyCreate() {
  const company = useCompany();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      await authenticatedRequest("/companies", { method: "POST", body: JSON.stringify(Object.fromEntries(data)) });
      setOpen(false); company.reload();
    } catch (error) { setError(error instanceof Error ? error.message : "회사 정보를 확인해 주세요."); }
    finally { setBusy(false); }
  }
  return <><button className="button-accent" onClick={() => { setError(""); setOpen(true); }}><Plus size={16} aria-hidden="true" />새 회사 만들기</button><OfficeDialog compact open={open} onClose={() => setOpen(false)} busy={busy} title="새 회사 만들기" description="회사를 만든 뒤 업무 홈에서 회계 시작 준비를 한 단계씩 진행합니다.">
    <form onSubmit={submit}>
      <label htmlFor="company-name">회사명</label><input id="company-name" name="company_name" required maxLength={200} disabled={busy} />
      <label htmlFor="business-number">사업자등록번호</label><input id="business-number" name="business_number" pattern="[0-9]{10}" inputMode="numeric" placeholder="하이픈 없이 10자리" required disabled={busy} />
      <label htmlFor="taxpayer-type">사업자 유형</label><select id="taxpayer-type" name="taxpayer_type" disabled={busy}><option value="CORPORATION">법인</option><option value="INDIVIDUAL">개인사업자</option></select>
      <label htmlFor="opening-date">개업일</label><input id="opening-date" name="opening_date" type="date" required disabled={busy} />
      <label htmlFor="address">주소</label><input id="address" name="address" required maxLength={500} disabled={busy} />
      {error && <p role="alert" className="error">{error}</p>}
      <button className="primary" disabled={busy}>{busy ? "만드는 중…" : "회사 만들기"}</button>
    </form>
  </OfficeDialog></>;
}
