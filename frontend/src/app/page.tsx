"use client";
import { CompanyHome } from "@/features/navigation/company-home";
import Link from "next/link";
import { Building2 } from "lucide-react";
import { useCompany } from "@/features/companies/company-provider";
export default function Home() {
  const { active } = useCompany();
  return <>
    {!active && <section className="panel company-summary"><Building2 size={28} aria-hidden="true" /><div><h2>회사 선택으로 시작하세요</h2><p>회사 선택·관리에서 접근 가능한 회사를 선택하거나 새 회사를 만들 수 있습니다.</p></div><Link href="/companies">회사 선택·관리</Link></section>}
    {active && <CompanyHome key={active.id} company={active} />}

  </>;
}
