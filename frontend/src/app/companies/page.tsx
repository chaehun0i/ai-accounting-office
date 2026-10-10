"use client";
import { CompanySelector } from "@/features/companies/components/company-selector";
import { CompanyCreate } from "@/features/companies/components/company-create";
import { useCompany } from "@/features/companies/company-provider";
import { roleGuide } from "@/features/companies/selection-state";
export default function CompaniesPage() {
  const company = useCompany();
  return <>{company.companies.length > 0 ? <CompanySelector /> : <section className="panel"><h2>아직 연결된 회사가 없습니다</h2><p>새 회사를 만들거나 회사 관리자에게 초대를 요청해 주세요.</p></section>}{company.active && <section className="panel"><h2>{company.active.company_name}</h2><p>{roleGuide(company.active.role_code)}</p></section>}<CompanyCreate /></>;
}
