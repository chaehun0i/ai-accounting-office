"use client";

import { AccountingQueryWorkspace } from "@/features/ai-team/accounting-query-workspace";
import { CompanyPage } from "@/features/navigation/office-shell";

export default function Page() {
  return <CompanyPage href="/ai-team">{company => <AccountingQueryWorkspace key={company.id} company={company} />}</CompanyPage>;
}
