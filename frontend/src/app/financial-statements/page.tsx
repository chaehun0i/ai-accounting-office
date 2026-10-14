"use client";

import { CompanyPage } from "@/features/navigation/office-shell";
import { FinancialStatements } from "@/features/reporting/financial-statements";

export default function Page() {
  return <CompanyPage href="/financial-statements">{company => <FinancialStatements key={company.id} company={company} />}</CompanyPage>;
}
