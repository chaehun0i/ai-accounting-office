"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";
import { formatMoney, type Period } from "./model";

type Section = { id: string; section_code: string; title: string; display_order: number };
type Template = { id: string; title: string; version: number; sections: Section[] };
type Value = {
  id: string; section_id: string; source_type: string; source_code: string;
  source_id: string; account_id: string | null; label: string; decimal_value: string;
};
type Narrative = { section_id: string; text_value: string; status: string };
type Instance = {
  id: string; period_id: string; revision: number; status: string; source_digest: string;
  source_stale: boolean; created_by: string; version: number;
  values: Value[]; narratives: Narrative[];
};
type Readiness = { status: "READY" | "BLOCKED"; issues: string[]; source_digest: string | null };
type GenerateResult = Instance | { status: "BLOCKED"; issues: string[]; instance_id: null };
type Source = {
  source_type: string; source_code: string; amount: string; source_path: string | null;
  journal_ids: string[]; journal_line_ids: string[]; evidence_ids: string[];
};

const labels: Record<string, string> = {
  PERIOD_NOT_CLOSED: "회계기간이 CLOSED 상태가 아닙니다.",
  STATEMENT_SET_MISSING: "현재 마감 버전의 재무제표 원천이 없습니다.",
  BALANCE_SHEET_SOURCE_REQUIRED: "재무상태표 Snapshot이 필요합니다.",
  INCOME_STATEMENT_SOURCE_REQUIRED: "손익계산서 Snapshot이 필요합니다.",
  CASH_FLOW_SOURCE_REQUIRED: "대사 완료된 현금흐름표 Snapshot이 필요합니다.",
  CASH_FLOW_SOURCE_STALE: "현금흐름표 원천이 현재 재무제표와 다릅니다.",
  EQUITY_SOURCE_REQUIRED: "대사 완료된 자본변동표 Snapshot이 필요합니다.",
  EQUITY_SOURCE_STALE: "자본변동표 원천이 현재 재무제표와 다릅니다.",
  DISCLOSURE_TEMPLATE_REQUIRED: "기간에 유효한 주석 템플릿과 필수 항목 연결이 필요합니다.",
  DISCLOSURE_RECONCILIATION_MISMATCH: "제표 간 금액 대사가 맞지 않아 주석 생성을 차단했습니다.",
  DISCLOSURE_GL_SOURCE_MISMATCH: "재무제표 계정별 원장 출처 합계가 제표 항목과 일치하지 않습니다.",
  REPORT_SOURCE_STALE: "현재 마감 또는 보고서 원천이 변경되어 다시 확인해야 합니다.",
  EQUITY_ROLLFORWARD_MISMATCH: "자본변동과 재무상태표 자본 합계가 일치하지 않습니다.",
  PROFIT_TRANSFER_IS_MISMATCH: "손익 대체 전표와 손익계산서 순이익 표시를 먼저 확인해 주세요.",
};
const failure = (error: unknown) => error instanceof ApiError ? error.message : "주석 원천을 불러오지 못했습니다.";

export function DisclosureWorkspace({ company, period }: { company: Company; period: Period }) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [instance, setInstance] = useState<Instance | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [source, setSource] = useState<Source | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const request = useRef<{ companyId: string; periodId: string; key: string } | null>(null);
  const scope = { "X-Company-ID": company.id };
  const canEdit = company.permissions.includes("disclosure.edit");
  const canApprove = company.permissions.includes("disclosure.approve");

  useEffect(() => {
    let active = true;
    request.current = null;
    setLoading(true); setError(""); setInstance(null); setSource(null); setInstances([]);
    setReadiness(null); setDrafts({});
    Promise.all([
      authenticatedRequest<Template[]>("/disclosures/templates", { headers: scope }),
      authenticatedRequest<Readiness>(`/disclosures/readiness?period_id=${encodeURIComponent(period.id)}`, { headers: scope }),
      authenticatedRequest<Instance[]>(`/disclosures/instances?period_id=${encodeURIComponent(period.id)}`, { headers: scope }),
    ]).then(([templateRows, ready, rows]) => {
      if (!active) return;
      setTemplates(templateRows); setReadiness(ready); setInstances(rows);
      const latest = rows[0];
      if (latest) return authenticatedRequest<Instance>(`/disclosures/instances/${latest.id}`, { headers: scope })
        .then(value => { if (active) { setInstance(value); setDrafts(Object.fromEntries(value.narratives.map(row => [row.section_id, row.text_value]))); } });
    }).catch(reason => { if (active) setError(failure(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company.id, company.permissions, period.id, period.close_version]);

  async function refreshInstance(id: string) {
    const [value, rows] = await Promise.all([
      authenticatedRequest<Instance>(`/disclosures/instances/${id}`, { headers: scope }),
      authenticatedRequest<Instance[]>(`/disclosures/instances?period_id=${encodeURIComponent(period.id)}`, { headers: scope }),
    ]);
    setInstance(value); setInstances(rows);
    setDrafts(Object.fromEntries(value.narratives.map(row => [row.section_id, row.text_value])));
  }

  async function generate() {
    if (!readiness?.source_digest || !canEdit) return;
    if (
      !request.current ||
      request.current.companyId !== company.id ||
      request.current.periodId !== period.id
    ) {
      request.current = { companyId: company.id, periodId: period.id, key: crypto.randomUUID() };
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const value = await authenticatedRequest<GenerateResult>("/disclosures/instances/generate", {
        method: "POST", headers: { ...scope, "Idempotency-Key": request.current.key },
        body: JSON.stringify({ period_id: period.id }),
      });
      request.current = null;
      if ("id" in value) { await refreshInstance(value.id); setNotice("현재 BS/IS/CF/SCE 원천에서 주석 Fact를 고정했습니다."); }
      else setNotice("필수 원천이 없어 주석 생성을 차단했습니다.");
    } catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }

  async function saveNarrative(event: FormEvent<HTMLFormElement>, section: Section) {
    event.preventDefault();
    if (!instance) return;
    setBusy(true); setError("");
    try {
      const value = await authenticatedRequest<{ instance_version: number }>(`/disclosures/instances/${instance.id}/narratives`, {
        method: "PUT", headers: scope,
        body: JSON.stringify({ section_id: section.id, text_value: drafts[section.id] ?? "", expected_version: instance.version }),
      });
      await refreshInstance(instance.id); setNotice(`“${section.title}” 설명 초안을 저장했습니다. 버전 ${value.instance_version}`);
    } catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }

  async function transition(path: "request-review" | "approve" | "reject") {
    if (!instance) return;
    setBusy(true); setError("");
    try {
      await authenticatedRequest(`/disclosures/instances/${instance.id}/${path}`, {
        method: "POST", headers: scope,
        body: JSON.stringify({ expected_version: instance.version, ...(path === "reject" ? { reason: rejectReason } : {}) }),
      });
      await refreshInstance(instance.id); setNotice(path === "approve" ? "독립 검토자가 내부 검증용 주석 revision을 승인했습니다." : path === "reject" ? "검토 의견을 기록했습니다." : "독립 검토를 요청했습니다.");
    } catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }

  async function inspect(value: Value) {
    if (!instance) return;
    setError(""); setSource(null);
    try {
      setSource(await authenticatedRequest<Source>(`/disclosures/instances/${instance.id}/values/${value.id}/source`, { headers: scope }));
    } catch (reason) { setError(failure(reason)); }
  }

  if (loading) return <section className="panel"><p role="status">재무제표 주석 원천을 확인하고 있습니다…</p></section>;
  const template = templates[0];
  const stateLabel = instance?.source_stale ? "STALE · 원천 변경" : instance?.status ?? readiness?.status ?? "BLOCKED";
  return <section className="panel disclosure-workspace">
    <h2>재무제표 주석</h2>
    <p>내부 검증용 주석 Fact는 CLOSED 기간의 BS/IS/CF/SCE Snapshot에서만 생성합니다. 지원되지 않는 Asset·Inventory·Tax 세부자료는 추정하지 않습니다.</p>
    {readiness?.status === "BLOCKED" && <div role="alert"><strong>생성 차단</strong><ul>{readiness.issues.map(issue => <li key={issue}>{labels[issue] ?? issue}</li>)}</ul></div>}
    {readiness?.status === "READY" && <p role="status">원천 준비 완료 · {readiness.source_digest?.slice(0, 12)}… · 모든 숫자는 서버의 원천 Snapshot 금액입니다.</p>}
    {canEdit && readiness?.status === "READY" && <button disabled={busy} onClick={() => void generate()}>{busy ? "처리 중…" : "주석 Fact 생성"}</button>}
    {instances.length > 1 && <label>주석 revision<select aria-label="주석 revision" value={instance?.id ?? ""} onChange={event => { setSource(null); void refreshInstance(event.target.value); }}>
      {instances.map(row => <option key={row.id} value={row.id}>Revision {row.revision} · {row.status} · {row.source_digest.slice(0, 10)}…</option>)}
    </select></label>}
    {instance && <>
      <p>상태 <strong>{stateLabel}</strong> · revision {instance.revision} · template v{template?.version ?? "?"} · source digest {instance.source_digest.slice(0, 12)}…</p>
      {instance.source_stale && <p role="alert">이 승인본은 생성 당시 원천을 보존합니다. 현재 원천과 달라 새 승인·Export에 사용할 수 없습니다.</p>}
      {template?.sections.map(section => {
        const sectionValues = instance.values.filter(value => value.section_id === section.id);
        const narrative = instance.narratives.find(row => row.section_id === section.id);
        return <section className="disclosure-section" key={section.id}>
          <h3>{section.title}</h3>
          {sectionValues.length === 0 ? <p>이 원천에는 표시할 검증 Fact가 없습니다.</p> : <div className="table-scroll"><table><thead><tr><th>항목</th><th>금액</th><th>원천</th></tr></thead><tbody>
            {sectionValues.map(value => <tr key={value.id}><th scope="row">{value.label}<small>{value.account_id ? `GL 계정 · ${value.source_code}` : value.source_code}</small></th><td>{formatMoney(value.decimal_value)}</td><td><button onClick={() => void inspect(value)}>원천 보기</button></td></tr>)}
          </tbody></table></div>}
          <form onSubmit={event => void saveNarrative(event, section)}>
            <label>{section.title} 설명 초안<textarea value={drafts[section.id] ?? narrative?.text_value ?? ""} disabled={!canEdit || instance.status === "REVIEW_REQUESTED" || instance.status === "APPROVED" || instance.source_stale} onChange={event => setDrafts(current => ({ ...current, [section.id]: event.target.value }))} maxLength={4000} /></label>
            <small>{narrative?.status ?? "DRAFT"} · 작성자 설명이며 승인 전에는 승인본이 아닙니다.</small>
            {canEdit && <button disabled={busy || instance.status === "REVIEW_REQUESTED" || instance.status === "APPROVED" || instance.source_stale}>설명 초안 저장</button>}
          </form>
        </section>;
      })}
      {canEdit && ["DRAFT", "REJECTED"].includes(instance.status) && !instance.source_stale && <button disabled={busy} onClick={() => void transition("request-review")}>독립 검토 요청</button>}
      {canApprove && instance.status === "REVIEW_REQUESTED" && !instance.source_stale && <div className="workspace-buttons"><button disabled={busy} onClick={() => void transition("approve")}>승인</button><label>반려 사유<input value={rejectReason} onChange={event => setRejectReason(event.target.value)} maxLength={1000} /></label><button disabled={busy || !rejectReason.trim()} onClick={() => void transition("reject")}>반려</button></div>}
      {instance.status === "APPROVED" && !instance.source_stale && <p>독립 승인된 내부 검증용 revision입니다. <Link href="/reports">Report Center에서 Notes PDF/XLSX/CSV를 생성할 수 있습니다.</Link></p>}
    </>}
    {source && <div className="disclosure-source"><h3>숫자 원천</h3><p>{source.source_type} · {source.source_code} · {formatMoney(source.amount)}</p>
      {source.source_path && <Link href={source.source_path}>원천 상세 열기</Link>}
      {source.journal_ids.length > 0 && <p>Journal: {source.journal_ids.map(id => <Link key={id} href={`/journals/${id}`}>{id} </Link>)}</p>}
      {source.journal_line_ids.length > 0 && <p>Journal Line: {source.journal_line_ids.join(", ")}</p>}
      {source.evidence_ids.length > 0 && <p>Evidence: {source.evidence_ids.join(", ")}</p>}
    </div>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </section>;
}

