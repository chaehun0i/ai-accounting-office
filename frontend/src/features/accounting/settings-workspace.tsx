"use client";
import { useState } from "react";
import type { Company } from "@/features/companies/selection-state";
import { CompanyProfile } from "@/features/companies/components/company-profile";
import { DimensionManager } from "./dimension-manager";
import { AccountCatalog } from "./account-catalog";
import { AccountingMaster } from "./accounting-master";

export function SettingsWorkspace({ company }: { company: Company }) {
  const [tab, setTab] = useState("company");
  return <><nav className="section-navigation" aria-label="설정 항목">{[["company", "회사정보"], ["accounting", "회계 기준"], ["accounts", "계정과목"], ["dimensions", "관리차원"]].map(([code, label]) => <button key={code} aria-pressed={tab === code} onClick={() => setTab(code)}>{label}</button>)}</nav>
    {tab === "company" ? <CompanyProfile company={company} /> : tab === "accounting" ? <AccountingMaster company={company} showCatalog={false} /> : tab === "dimensions" ? <DimensionManager key={company.id} company={company} /> : <section className="panel"><h2>계정과목</h2><AccountCatalog key={company.id} companyId={company.id} canCreate={company.permissions.includes("account.create")} /></section>}
  </>;
}
