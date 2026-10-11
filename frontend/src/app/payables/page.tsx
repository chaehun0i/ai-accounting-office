"use client";
import { CompanyPage } from "@/features/navigation/office-shell";
import { FinanceWorkspace } from "@/features/finance/finance-workspace";
export default function Page() { return <CompanyPage href="/payables">{company => <FinanceWorkspace key={company.id} company={company} kind="AP" />}</CompanyPage>; }
