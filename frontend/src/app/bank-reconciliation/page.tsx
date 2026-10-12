"use client";
import { CompanyPage } from "@/features/navigation/office-shell";
import { BankWorkspace } from "@/features/finance/bank-workspace";
export default function Page() { return <CompanyPage href="/bank-reconciliation">{company => <BankWorkspace key={company.id} company={company} kind="BANK" />}</CompanyPage>; }
