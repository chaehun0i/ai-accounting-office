"use client";
import { CompanyPage } from "@/features/navigation/office-shell";
import { LedgerWorkspace } from "@/features/accounting/ledger-workspace";
export default function Page() { return <CompanyPage href="/ledger">{company => <LedgerWorkspace company={company} mode="ledger" />}</CompanyPage>; }
