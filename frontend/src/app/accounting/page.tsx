"use client";
import { CompanyPage } from "@/features/navigation/office-shell";
import { SettingsWorkspace } from "@/features/accounting/settings-workspace";
export default function Page() { return <CompanyPage href="/accounting">{company => <SettingsWorkspace company={company} />}</CompanyPage>; }
