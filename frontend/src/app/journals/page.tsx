"use client";
import { CompanyPage } from "@/features/navigation/office-shell";
import { JournalWorkspace } from "@/features/accounting/journal-workspace";
export default function Page() { return <CompanyPage href="/journals">{company => <JournalWorkspace company={company} />}</CompanyPage>; }
