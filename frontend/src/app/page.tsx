"use client";
import Link from "next/link";
import { ArrowUpRight, Building2 } from "lucide-react";
import { routeDescriptions, routeIcons } from "@/features/navigation/presentation";
import { useCompany } from "@/features/companies/company-provider";
import { roleGuide } from "@/features/companies/selection-state";
import { canVisit, officeRoutes } from "@/features/navigation/routes";
export default function Home() {
  const { active } = useCompany();
  return <>
    <section className="panel company-summary"><Building2 size={28} aria-hidden="true" /><div><h2>{active?.company_name ?? "회사 선택으로 시작하세요"}</h2><p>{active ? roleGuide(active.role_code) : "회사 선택·관리에서 접근 가능한 회사를 선택하거나 새 회사를 만들 수 있습니다."}</p></div><Link href="/companies">회사 선택·관리</Link></section>
    <div className="dashboard-links">{officeRoutes.filter(route => route.href !== "/" && route.href !== "/companies" && canVisit(route.href, active?.permissions ?? [])).map(route => { const Icon = routeIcons[route.href]; return <Link className="panel" href={route.href} key={route.href}><Icon className="card-icon" size={22} aria-hidden="true" /><ArrowUpRight className="card-arrow" size={20} aria-hidden="true" /><h2>{route.label}</h2><p>{routeDescriptions[route.href]}</p><small>{route.group} · 업무 열기</small></Link>})}</div>
  </>;
}
