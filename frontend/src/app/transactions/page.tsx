"use client";
import { CompanyPage } from "@/features/navigation/office-shell";
import { TransactionWorkspace } from "@/features/transactions/transaction-workspace";
export default function Page() { return <CompanyPage href="/transactions">{company => <TransactionWorkspace company={company} />}</CompanyPage>; }
