"use client";

import { useEffect, useState } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";
import { FieldEditor } from "./field-editor";
import { ConfirmationDialog } from "@/shared/ui/dialog";
import { ExcelImportDialog } from "./excel-import-dialog";
import { cellKey, isEditable, isVisible, mergeKey, sourceLabels, stateLabels, type Issue, type Receipt, type Workspace } from "./model";

export function OnboardingWorkspace({ company }: { company: Company }) {
  const [workspace, setWorkspace] = useState<Workspace>();
  const [section, setSection] = useState("Company");
  const [pending, setPending] = useState<Record<string, string | boolean>>({});
  const [newRows, setNewRows] = useState<Record<string, string[]>>({});
  const [issues, setIssues] = useState<Issue[]>([]);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [modal, setModal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [denied, setDenied] = useState(false);
  const [completeKey] = useState(() => crypto.randomUUID());
  const headers = { "X-Company-ID": company.id };
  async function reload() {
    const result = await authenticatedRequest<Workspace>("/onboarding", { headers });
    setWorkspace(result); setPending({}); setNewRows({});
  }
  useEffect(() => {
    let active = true;
    authenticatedRequest<Workspace>("/onboarding", { headers: { "X-Company-ID": company.id } })
      .then(value => { if (active) setWorkspace(value); })
      .catch(e => { if (active) { setError(e.message); setDenied(e instanceof ApiError && e.status === 403); } });
    return () => { active = false; };
  }, [company.id]);
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : "처리하지 못했습니다. 다시 시도해 주세요."); }
    finally { setBusy(false); }
  }
  async function openingJournal() {
    if (!workspace) return;
    await perform(async () => {
      const result=await authenticatedRequest<{id:string}>("/opening-balances/imports",{method:"POST",headers:{...headers,"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({expected_version:workspace.version})});
      setNotice(`기초 전표 초안을 만들었습니다. 회계 전표에서 제출하고 별도 승인자의 승인을 받아 장부에 반영해 주세요. 전표 식별자: ${result.id}`);
    });
  }
  async function save() {
    if (!workspace) return;
    await perform(async () => {
      const values: { field_code: string; row_key: string; value: string | boolean }[] = [];
      for (const itemSection of workspace.sections) {
        const fields = workspace.fields.filter(f => f.section_code === itemSection.code && isEditable(f));
        const keys = workspace.row_keys[itemSection.code];
        const rows = keys ? [...new Set(workspace.cells.filter(c => c.field_code.startsWith(`${itemSection.code}.`) && c.source_type !== "DERIVED").map(c => c.row_key)), ...(newRows[itemSection.code] ?? [])] : ["singleton"];
        for (const row of rows) {
          if (!fields.some(f => cellKey(f.field_code, row) in pending)) continue;
          const rowValues: Record<string, string | boolean> = {};
          for (const field of fields) rowValues[field.field_code.split(".")[1]] = pending[cellKey(field.field_code, row)] ?? workspace.cells.find(c => c.field_code === field.field_code && c.row_key === row)?.value ?? "";
          const targetKey = keys ? mergeKey(keys, rowValues) : "singleton";
          for (const field of fields) {
            const value = rowValues[field.field_code.split(".")[1]];
            if (value === "" && workspace.cells.some(c => c.field_code === field.field_code && c.row_key === row)) throw new Error(`${field.label}은 빈 값으로 저장할 수 없습니다. 새 값을 입력해 주세요.`);
            if (value !== "") values.push({ field_code: field.field_code, row_key: targetKey, value });
          }
        }
      }
      const result = await authenticatedRequest<Workspace>("/onboarding/values", { method: "PATCH", headers, body: JSON.stringify({ expected_version: workspace.version, values }) });
      setWorkspace(result); setPending({}); setNewRows({}); setIssues([]); setNotice("초안을 저장했습니다.");
    });
  }
  async function validate() {
    if (!workspace) return;
    await perform(async () => {
      const result = await authenticatedRequest<{ workspace: Workspace; issues: Issue[] }>("/onboarding/validate", { method: "POST", headers, body: JSON.stringify({ expected_version: workspace.version }) });
      setWorkspace(result.workspace); setIssues(result.issues); setNotice(result.issues.length ? "확인이 필요한 항목이 있습니다." : "완료 준비가 되었습니다.");
    });
  }
  async function complete() {
    if (!workspace) return;
    await perform(async () => {
      const result = await authenticatedRequest<Receipt>("/onboarding/complete", { method: "POST", headers: { ...headers, "Idempotency-Key": completeKey }, body: JSON.stringify({ expected_version: workspace.version }) });
      setCompleteOpen(false); await reload(); setNotice(`회계 시작 준비를 완료했습니다. 접수번호: ${result.id}`);
    });
  }
  const dirty = Object.keys(pending).length > 0;
  const readOnly = busy || workspace?.status === "COMPLETED" || !company.permissions.includes("onboarding.edit");
  const fields = workspace?.fields.filter(f => f.section_code === section).sort((a, b) => a.display_order - b.display_order) ?? [];
  const taxpayerType = pending[cellKey("Company.taxpayer_type", "singleton")] ?? workspace?.cells.find(c => c.field_code === "Company.taxpayer_type")?.value ?? "";
  const keys = workspace?.row_keys[section];
  const rows = workspace ? keys ? [...new Set(workspace.cells.filter(c => c.field_code.startsWith(`${section}.`) && c.source_type !== "DERIVED").map(c => c.row_key)), ...(newRows[section] ?? [])] : ["singleton"] : [];
  return <section className="panel" aria-labelledby="onboarding-heading">
    <div className="session-bar"><h2 id="onboarding-heading">회계 시작 준비</h2>
      <button onClick={() => setModal(true)} disabled={!workspace || busy || dirty || workspace.status === "COMPLETED" || !company.permissions.includes("onboarding.import")}>Excel 업로드</button>
    </div>
    <p>아래 항목을 직접 입력해 주세요. Excel은 현재 초안을 채우는 보조 수단이며 저장 전 변경사항은 먼저 저장해 주세요.</p>
    {error && <div role="alert" className="error"><p>{denied ? "온보딩을 조회할 권한이 없습니다. 회사 관리자에게 문의해 주세요." : error}</p><button disabled={busy} onClick={() => perform(reload)}>최신 내용 다시 불러오기</button></div>}
    {!workspace && !error && <p role="status">초안을 불러오고 있습니다…</p>}
    {workspace && <>
      <p role="status">{stateLabels[workspace.status] ?? "시작 준비 중"}{dirty ? " · 저장하지 않은 변경사항" : ""}</p>
      <div className="onboarding-workspace-grid"><nav aria-label="온보딩 항목" className="section-navigation">{workspace.sections.map(s => <button key={s.code} aria-pressed={section === s.code} onClick={() => setSection(s.code)}>{s.label} · {stateLabels[s.status]} ({s.complete}/{s.total})</button>)}</nav><div className="onboarding-editor">
      <h3>{workspace.sections.find(s => s.code === section)?.label}</h3>
      {rows.length === 0 && <p className="muted">아직 입력한 항목이 없습니다. 필요한 항목을 추가해 주세요.</p>}
      {keys && <button disabled={readOnly} onClick={() => setNewRows(previous => ({ ...previous, [section]: [...(previous[section] ?? []), `new-${crypto.randomUUID()}`] }))}>항목 추가</button>}
      {rows.map(row => <fieldset key={row} disabled={readOnly}><legend>{keys ? row.startsWith("new-") ? "새 항목" : row : "기본 입력"}</legend>
        {fields.filter(field => isEditable(field) && isVisible(field, taxpayerType)).map(field => {
          const current = workspace.cells.find(c => c.field_code === field.field_code && c.row_key === row);
          const fieldKey = cellKey(field.field_code, row);
          return <div key={fieldKey}><FieldEditor field={field} value={pending[fieldKey] ?? current?.value ?? ""} options={field.enum_source_code ? workspace.enums[field.enum_source_code] : undefined}
            disabled={readOnly || !!keys?.includes(field.field_code.split(".")[1]) && !row.startsWith("new-")} onChange={value => setPending(previous => ({ ...previous, [fieldKey]: value }))} />
            {current && <small>{sourceLabels[current.source_type]} · {stateLabels[current.status]}</small>}</div>;
        })}
      </fieldset>)}
      {fields.filter(f => !isEditable(f)).map(field => { const current = workspace.cells.find(c => c.field_code === field.field_code); return <p key={field.field_code}>{field.label}: {String(current?.value ?? "계산 전")} · {stateLabels[current?.status ?? "STALE"]}</p>; })}
      <div className="session-bar"><button onClick={save} disabled={readOnly || !dirty}>{busy ? "저장 중…" : "초안 저장"}</button>
        <button onClick={validate} disabled={readOnly || dirty}>검증하고 다시 계산</button>
        <button onClick={() => setCompleteOpen(true)} disabled={busy || dirty || workspace.status !== "READY_TO_COMPLETE" || !company.permissions.includes("onboarding.complete")}>준비 완료 및 회계정보 반영</button></div>
      {issues.length > 0 && <section aria-label="검증 결과"><h3>확인할 내용</h3>{issues.map((issue, i) => <p key={i} className="error">{workspace.fields.find(f => f.field_code === issue.field_code)?.label ?? issue.row_key}: {issue.message}</p>)}</section>}
      {section === "Opening_Balances" && company.permissions.includes("journal.propose") && <button disabled={busy || Object.keys(pending).length > 0} onClick={openingJournal}>저장된 기초잔액으로 전표 작성</button>}
    {notice && <p role="status">{notice}</p>}
      {completeOpen && <ConfirmationDialog open onClose={() => setCompleteOpen(false)} onConfirm={() => void complete()} busy={busy} title="회계 준비 완료" description="검증한 초안을 회사 회계정보에 반영합니다. 미지원 항목이나 오류가 있으면 서버에서 완료를 차단합니다." confirmLabel="확인 후 회계정보 반영"><p>대상 회사: {company.company_name}</p><p>기초잔액은 여기서 장부에 확정되지 않습니다. 별도 전표 작성과 승인 절차가 필요합니다.</p>{error && <p role="alert">{error}</p>}</ConfirmationDialog>}
      {modal && <ExcelImportDialog workspace={workspace} onApplied={reload} onClose={() => setModal(false)} />}
      </div></div>
    </>}
  </section>;
}
