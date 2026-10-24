"use client";

import { CompanyPage } from "@/features/navigation/office-shell";
import { ReportCenter } from "@/features/reporting/report-center";

export default function Page() {
  return <CompanyPage href="/reports">{company => <ReportCenter key={company.id} company={company} />}</CompanyPage>;
}
