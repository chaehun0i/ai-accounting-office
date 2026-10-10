"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment, useState, type ReactNode } from "react";
import { AuthProvider, useAuth } from "@/features/auth/auth-provider";
import { AuthForm } from "@/features/auth/auth-form";
import { CompanyProvider, useCompany } from "@/features/companies/company-provider";
import { CompanySelector } from "@/features/companies/components/company-selector";
import { canVisit, officeRoutes } from "./routes";

function Shell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const company = useCompany();
  const pathname = usePathname();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function logout() {
    setBusy(true); setError("");
    try { await auth.logout(); }
    catch (error) { setError(error instanceof Error ? error.message : "로그아웃하지 못했습니다."); }
    finally { setBusy(false); }
  }
  if (!auth.ready) return <main><p role="status">로그인 상태를 확인하고 있습니다…</p></main>;
  if (!auth.user) return <main><h1>AI Accounting Office</h1><AuthForm /></main>;
  return <div className="office-shell">
    <a className="skip-link" href="#office-content">본문으로 이동</a>
    <aside className="office-sidebar">
      <Link href="/" className="office-brand">AI Accounting Office</Link>
      <nav aria-label="업무 메뉴">{officeRoutes.map((route, index) => <Fragment key={route.href}>
        {(index === 0 || officeRoutes[index - 1].group !== route.group) && <p className="menu-group">{route.group}</p>}
        {canVisit(route.href, company.active?.permissions ?? [])
          ? <Link href={route.href} aria-current={pathname === route.href ? "page" : undefined}>{route.label}</Link>
          : <span className="menu-unavailable">{route.label}<small>{company.active ? "권한 필요" : "회사 선택 필요"}</small></span>}
      </Fragment>)}</nav>
    </aside>
    <div className="office-body">
      <header className="office-header"><div><strong>{company.active?.company_name ?? "회사를 선택해 주세요"}</strong><small>{auth.user.email}</small></div><div className="session-bar"><Link href="/companies">회사 선택·관리</Link><button onClick={logout} disabled={busy}>{busy ? "처리 중…" : "로그아웃"}</button></div></header>
      <main id="office-content" className="office-content" tabIndex={-1}>
        {error && <p role="alert" className="error">{error}</p>}
        {company.error && <div className="panel" role="alert"><p>{company.error}</p><button onClick={company.reload}>회사 목록 다시 확인</button></div>}
        {company.loading ? <p role="status">회사 정보를 확인하고 있습니다…</p> : children}
      </main>
    </div>
  </div>;
}

export function OfficeProviders({ children }: { children: ReactNode }) {
  return <AuthProvider><CompanyProvider><Shell>{children}</Shell></CompanyProvider></AuthProvider>;
}

export function CompanyPage({ children, href }: { children: (company: NonNullable<ReturnType<typeof useCompany>["active"]>) => ReactNode; href: string }) {
  const company = useCompany();
  if (!company.active) return <section className="panel"><h1>회사를 먼저 선택해 주세요</h1><p>선택한 회사의 자료만 조회하고 처리합니다.</p>{company.companies.length > 0 ? <CompanySelector /> : <Link href="/companies">회사 만들기·초대 안내</Link>}</section>;
  if (!canVisit(href, company.active.permissions)) return <section className="panel" role="alert"><h1>이 업무에 접근할 권한이 없습니다</h1><p>회사 관리자에게 권한을 확인해 주세요. 승인 업무는 관리자, 작성 업무는 회계 담당자 계정으로 이용할 수 있습니다.</p><Link href="/">업무 홈으로</Link></section>;
  // 회사 전환 시 이전 회사의 입력값·조회 결과를 함께 폐기합니다.
  return <Fragment key={company.active.id}>{children(company.active)}</Fragment>;
}
