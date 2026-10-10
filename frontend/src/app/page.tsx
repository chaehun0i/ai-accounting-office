"use client";
import Link from "next/link";
import { useCompany } from "@/features/companies/company-provider";
import { roleGuide } from "@/features/companies/selection-state";
import { canVisit, officeRoutes } from "@/features/navigation/routes";
export default function Home() {
  const { active } = useCompany();
  return <><header><p className="eyebrow">오늘의 회계 업무</p><h1>업무 홈</h1><p>데이터 준비부터 전표 승인과 장부 확인까지, 필요한 메뉴에서 업무를 이어가세요.</p></header>
    <section className="panel"><h2>{active?.company_name ?? "회사 선택으로 시작하세요"}</h2><p>{active ? roleGuide(active.role_code) : "회사 선택·관리에서 접근 가능한 회사를 선택하거나 새 회사를 만들 수 있습니다."}</p><Link href="/companies">회사 선택·관리</Link></section>
    <div className="dashboard-links">{officeRoutes.filter(route => route.href !== "/" && route.href !== "/companies" && canVisit(route.href, active?.permissions ?? [])).map(route => <Link className="panel" href={route.href} key={route.href}><small>{route.group}</small><h2>{route.label}</h2><span>업무 열기 →</span></Link>)}</div>
  </>;
}
