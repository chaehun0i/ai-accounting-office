"use client";
import { CompanyPage } from "@/features/navigation/office-shell";
import { AccountingMaster } from "@/features/accounting/accounting-master";
export default function Page() { return <CompanyPage href="/accounting">{company => <AccountingMaster company={company} />}</CompanyPage>; }
