"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AccountingQueryWorkspace } from "@/features/ai-team/accounting-query-workspace";
import { parseAskContext } from "@/features/ai-team/context";
import { CompanyPage } from "@/features/navigation/office-shell";

export default function Page() {
  return <Suspense fallback={<p role="status">AI 회계팀을 불러오고 있습니다…</p>}><AIPage /></Suspense>;
}

function AIPage() {
  const params = useSearchParams();
  const context = parseAskContext(params);
  const contextKey = context ? `${context.kind}:${context.periodId ?? "invalid"}` : "global";
  return <CompanyPage href="/ai-team">{company =>
    <AccountingQueryWorkspace key={`${company.id}:${contextKey}`} company={company} context={context} />
  }</CompanyPage>;
}
