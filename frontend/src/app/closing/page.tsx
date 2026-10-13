"use client";

import { ClosingWorkspace } from "@/features/closing/closing-workspace";
import { CompanyPage } from "@/features/navigation/office-shell";

export default function Page() {
  return <CompanyPage href="/closing">{company => <ClosingWorkspace key={company.id} company={company} />}</CompanyPage>;
}
