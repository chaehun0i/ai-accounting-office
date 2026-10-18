"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AccountingQueryWorkspace } from "@/features/ai-team/accounting-query-workspace";
import { askContextKey, parseAskContext } from "@/features/ai-team/context";
import { CompanyPage } from "@/features/navigation/office-shell";

export default function Page() {
  return <Suspense fallback={<p role="status">AI 회계팀을 불러오고 있습니다…</p>}><AIPage /></Suspense>;
}

function AIPage() {
  const params = useSearchParams();
  const context = parseAskContext(params);
  return <CompanyPage href="/ai-team">{company =>
    <AccountingQueryWorkspace key={askContextKey(company.id, context)} company={company} context={context} />
  }</CompanyPage>;
}
