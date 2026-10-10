"use client";
import Link from "next/link";
import { canLeavePage } from "@/shared/unsaved-changes";
import { usePathname } from "next/navigation";
import { useRef, useState, type ReactNode } from "react";
import { MotionConfig, motion, useReducedMotion } from "framer-motion";
import { Building2, ChevronDown, ChevronRight, CircleCheck, LogOut, Menu, PanelLeftClose, PanelLeftOpen, ShieldCheck } from "lucide-react";
import { AuthProvider, useAuth } from "@/features/auth/auth-provider";
import { AuthForm } from "@/features/auth/auth-form";
import { CompanyProvider, useCompany } from "@/features/companies/company-provider";
import { CompanySelector } from "@/features/companies/components/company-selector";
import { OfficeDialog } from "@/shared/ui/dialog";
import { canVisit, officeRoutes } from "./routes";
import { routeDescriptions, routeIcons } from "./presentation";

function Shell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const company = useCompany();
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();
  const menuButton = useRef<HTMLButtonElement>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [compact, setCompact] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [companyOpen, setCompanyOpen] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<string[]>([]);
  const current = officeRoutes.find(route => route.href === pathname) ?? officeRoutes[0];
  const PageIcon = routeIcons[current.href];
  async function logout() {
    if (!canLeavePage()) return;
    setBusy(true); setError("");
    try { await auth.logout(); setMobileOpen(false); setCompanyOpen(false); }
    catch (error) { setError(error instanceof Error ? error.message : "로그아웃하지 못했습니다."); }
    finally { setBusy(false); }
  }
  function toggleGroup(group: string) { setCollapsedGroups(previous => previous.includes(group) ? previous.filter(value => value !== group) : [...previous, group]); }
  if (!auth.ready) return <main><p role="status" className="loading-message">로그인 상태를 확인하고 있습니다…</p></main>;
  if (!auth.user) return <div className="auth-screen"><div className="auth-intro"><span className="brand-symbol"><BookMark /></span><span className="eyebrow">AI Accounting Office</span><h1>숫자는 명확하게,<br />회계 업무는 편안하게.</h1><p>거래와 증빙, 전표 승인과 장부를<br />한 흐름으로 관리하세요.</p><span className="auth-assurance"><ShieldCheck size={18} aria-hidden="true" /> 회사별 권한과 안전한 승인 절차</span></div><main className="auth-form"><AuthForm /></main></div>;
  return <div className={`office-shell${compact ? " is-compact" : ""}${mobileOpen ? " mobile-menu-open" : ""}`}>
    <a className="skip-link" href="#office-content">본문으로 이동</a>
    <header className="office-header">
      <div className="header-brand"><Link href="/" className="office-brand"><span className="brand-symbol"><BookMark /></span><span>Accounting Office<small>나의 회계 사무실</small></span></Link>
        <button className="icon-button desktop-toggle" aria-label={compact ? "사이드바 펼치기" : "사이드바 접기"} aria-expanded={!compact} aria-controls="office-sidebar" onClick={() => setCompact(value => !value)}>{compact ? <PanelLeftOpen size={20} /> : <PanelLeftClose size={20} />}</button>
        <button ref={menuButton} className="icon-button mobile-toggle" aria-label="업무 메뉴 열기" aria-expanded={mobileOpen} aria-controls="office-sidebar" onClick={() => setMobileOpen(value => !value)}><Menu size={22} /></button></div>
      <div className="header-workspace"><span className="company-badge">회계 워크스페이스</span><button className="company-switch" onClick={() => setCompanyOpen(true)}><Building2 size={16} aria-hidden="true" /><span>{company.active?.company_name ?? "회사 선택"}</span><ChevronDown size={14} aria-hidden="true" /></button></div>
      <div className="header-account"><span className="user-avatar" aria-hidden="true">{auth.user.email.slice(0, 1).toUpperCase()}</span><span className="user-email">{auth.user.email}</span><button onClick={logout} disabled={busy}><LogOut size={15} aria-hidden="true" />{busy ? "처리 중…" : "로그아웃"}</button></div>
    </header>
    <aside className="office-sidebar" id="office-sidebar" onKeyDown={event => { if (event.key === "Escape") { setMobileOpen(false); menuButton.current?.focus(); } }}>
      <div className="sidebar-caption">나의 워크스페이스</div>
      <nav aria-label="업무 메뉴">{[...new Set(officeRoutes.map(route => route.group))].map((group, index) => {
        const expanded = !collapsedGroups.includes(group) || compact;
        return <div className="nav-group" key={group}><button className="menu-group" aria-expanded={expanded} aria-controls={`nav-group-${index}`} onClick={() => toggleGroup(group)}><span>{group}</span><ChevronDown size={15} className={expanded ? "chevron-open" : ""} aria-hidden="true" /></button>
          <div id={`nav-group-${index}`} className={`nav-accordion${expanded ? " expanded" : ""}`} inert={!expanded}><div>{officeRoutes.filter(route => route.group === group).map(route => {
            const Icon = routeIcons[route.href];
            return canVisit(route.href, company.active?.permissions ?? [])
              ? <Link key={route.href} href={route.href} title={route.label} aria-label={route.label} aria-current={pathname === route.href ? "page" : undefined} onClick={() => setMobileOpen(false)}><Icon size={18} aria-hidden="true" /><span className="nav-label">{route.label}</span>{pathname === route.href && <span className="nav-active-dot" />}</Link>
              : <span key={route.href} className="menu-unavailable" title={route.label}><Icon size={18} aria-hidden="true" /><span className="nav-label">{route.label}<small>{company.active ? "권한 필요" : "회사 선택 필요"}</small></span></span>;
          })}</div></div></div>;
      })}</nav>
      <div className="sidebar-footer"><CircleCheck size={19} aria-hidden="true" /><p>정확한 기록, 안전한 승인<small>선택한 회사의 자료만 관리합니다.</small></p><Link href="/companies" onClick={() => setMobileOpen(false)}>회사 선택·관리 <ChevronRight size={14} aria-hidden="true" /></Link></div>
    </aside>
    <div className="office-body">
      <main id="office-content" className="office-content" tabIndex={-1}>
        <div className="page-breadcrumb">회계 사무실 <ChevronRight size={13} aria-hidden="true" /> {current.group} <ChevronRight size={13} aria-hidden="true" /> <strong>{current.label}</strong></div>
        <div className="page-title"><span className="page-title-icon"><PageIcon size={25} aria-hidden="true" /></span><div><small>{current.group}</small><h1>{current.label}</h1><p>{routeDescriptions[current.href]}</p></div></div>
        {error && <p role="alert" className="error">{error}</p>}
        {company.error && <div className="panel" role="alert"><p>{company.error}</p><button onClick={company.reload}>회사 목록 다시 확인</button></div>}
        <motion.div key={`${pathname}:${company.active?.id ?? "none"}`} initial={reduceMotion ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduceMotion ? 0 : 0.18 }}>
          {company.loading ? <p role="status" className="loading-message">회사 정보를 확인하고 있습니다…</p> : children}
        </motion.div>
      </main>
    </div>
    <OfficeDialog compact open={companyOpen} onClose={() => setCompanyOpen(false)} title="회사 선택" description="접근 가능한 회사만 표시합니다. 회사마다 이용할 수 있는 업무가 다를 수 있습니다." busy={company.loading}>
      {company.companies.length > 0 ? <CompanySelector /> : <p>아직 연결된 회사가 없습니다. 회사 관리에서 새 회사를 만들거나 관리자에게 초대를 요청해 주세요.</p>}
    </OfficeDialog>
  </div>;
}
function BookMark() { return <span aria-hidden="true">A</span>; }
export function OfficeProviders({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user"><AuthProvider><CompanyProvider><Shell>{children}</Shell></CompanyProvider></AuthProvider></MotionConfig>;
}
export function CompanyPage({ children, href }: { children: (company: NonNullable<ReturnType<typeof useCompany>["active"]>) => ReactNode; href: string }) {
  const company = useCompany();
  if (!company.active) return <section className="panel"><h2>회사를 먼저 선택해 주세요</h2><p>선택한 회사의 자료만 조회하고 처리합니다.</p>{company.companies.length > 0 ? <CompanySelector /> : <Link href="/companies">회사 만들기·초대 안내</Link>}</section>;
  if (!canVisit(href, company.active.permissions)) return <section className="panel" role="alert"><h2>이 업무에 접근할 권한이 없습니다</h2><p>회사 관리자에게 권한을 확인해 주세요. 승인 업무는 관리자, 작성 업무는 회계 담당자 계정으로 이용할 수 있습니다.</p><Link href="/">업무 홈으로</Link></section>;
  // 회사 전환 시 이전 회사의 입력값·조회 결과를 함께 폐기합니다.
  return <div key={company.active.id}>{children(company.active)}</div>;
}
