"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { beforeLeaveEvent, canLeavePage } from "@/shared/unsaved-changes";
import { ApiError } from "@/shared/api";
import { FieldEditor } from "./field-editor";
import { AccountCatalog } from "@/features/accounting/account-catalog";
import { setupSteps, savedStep, stepForSection, missingStepValues } from "./setup-steps";
import { ConfirmationDialog, OfficeDialog } from "@/shared/ui/dialog";
import { ExcelImportDialog } from "./excel-import-dialog";
import { cellKey, isEditable, isVisible, mergeKey, sourceLabels, stateLabels, type Issue, type Workspace } from "./model";

export function OnboardingWorkspace({ company, initialWorkspace, onCompleted }: { company: Company; initialWorkspace?: Workspace; onCompleted?: (workspace: Workspace) => void }) {
  const [workspace, setWorkspace] = useState<Workspace | undefined>(initialWorkspace);
  const [stepIndex, setStepIndex] = useState(0);
  const [section, setSection] = useState("Company");
  const [editingRow, setEditingRow] = useState<string | null>(null);
  const [pending, setPending] = useState<Record<string, string | boolean>>({});
  const [newRows, setNewRows] = useState<Record<string, string[]>>({});
  const [issues, setIssues] = useState<Issue[]>([]);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [modal, setModal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [denied, setDenied] = useState(false);
  const [openingJournalId, setOpeningJournalId] = useState("");
  const dirty = Object.keys(pending).length > 0;
  useEffect(() => {
    if (!dirty) return;
    function beforeUnload(event: BeforeUnloadEvent) { event.preventDefault(); }
    function confirmLeave(event: Event) {
      if (!window.confirm("저장하지 않은 내용이 있습니다. 저장하지 않고 이동할까요?")) event.preventDefault();
    }
    function beforeNavigate(event: MouseEvent) {
      const link = (event.target as HTMLElement).closest<HTMLAnchorElement>("a[href]");
      if (!link || link.origin !== window.location.origin || link.pathname === window.location.pathname) return;
      if (!canLeavePage()) { event.preventDefault(); event.stopPropagation(); }
    }
    window.addEventListener(beforeLeaveEvent, confirmLeave);
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", beforeNavigate, true);
    return () => { window.removeEventListener(beforeLeaveEvent, confirmLeave); window.removeEventListener("beforeunload", beforeUnload); document.removeEventListener("click", beforeNavigate, true); };
  }, [dirty]);
  const [completeKey] = useState(() => crypto.randomUUID());
  const headers = { "X-Company-ID": company.id };
  async function reload() {
    const result = await authenticatedRequest<Workspace>("/onboarding", { headers });
    setWorkspace(result); setPending({}); setNewRows({}); return result;
  }
  useEffect(() => {
    try {
      const index = savedStep(window.localStorage.getItem(`office:setup-step:${company.id}`));
      setStepIndex(index); setSection(setupSteps[index].section);
    } catch { /* 브라우저 저장소가 꺼져 있으면 첫 단계부터 안내합니다. */ }
    if (initialWorkspace) return;
    let active = true;
    authenticatedRequest<Workspace>("/onboarding", { headers: { "X-Company-ID": company.id } })
      .then(value => { if (active) setWorkspace(value); })
      .catch(e => { if (active) { setError(e.message); setDenied(e instanceof ApiError && e.status === 403); } });
    return () => { active = false; };
  }, [company.id, initialWorkspace]);
  async function perform(action: () => Promise<unknown>) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); return true; } catch (e) { setError(e instanceof Error ? e.message : "처리하지 못했습니다. 다시 시도해 주세요."); return false; }
    finally { setBusy(false); }
  }
  async function openingJournal() {
    if (!workspace) return;
    await perform(async () => {
      const result=await authenticatedRequest<{id:string}>("/opening-balances/imports",{method:"POST",headers:{...headers,"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({expected_version:workspace.version})});
      setOpeningJournalId(result.id); setNotice("기초 전표를 만들었습니다. 전표를 확인한 뒤 제출해 주세요. 승인 후 장부에 반영할 수 있습니다.");
    });
  }
  async function save() {
    if (!workspace) return false;
    return perform(async () => {
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
      setWorkspace(result); setPending({}); setNewRows({}); setEditingRow(null); setIssues([]); setNotice("초안을 저장했습니다.");
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
      await authenticatedRequest("/onboarding/complete", { method: "POST", headers: { ...headers, "Idempotency-Key": completeKey }, body: JSON.stringify({ expected_version: workspace.version }) });
      setCompleteOpen(false); const finished = await reload(); onCompleted?.(finished); setNotice("회계 준비를 완료했습니다. 거래와 전표 입력을 시작할 수 있습니다.");
      try { window.localStorage.removeItem(`office:setup-step:${company.id}`); } catch { /* 단계 위치는 완료 정본이 아닙니다. */ }
    });
  }
  const readOnly = busy || workspace?.status === "COMPLETED" || !company.permissions.includes("onboarding.edit");
  const fields = workspace?.fields.filter(f => f.section_code === section).sort((a, b) => a.display_order - b.display_order) ?? [];
  const taxpayerType = pending[cellKey("Company.taxpayer_type", "singleton")] ?? workspace?.cells.find(c => c.field_code === "Company.taxpayer_type")?.value ?? "";
  const keys = workspace?.row_keys[section];
  const rows = workspace ? keys ? [...new Set(workspace.cells.filter(c => c.field_code.startsWith(`${section}.`) && c.source_type !== "DERIVED").map(c => c.row_key)), ...(newRows[section] ?? [])] : ["singleton"] : [];
  function closeRowEditor() {
    if (editingRow?.startsWith("new-") && !Object.keys(pending).some(key => key.endsWith(`::${editingRow}`))) {
      setNewRows(previous => ({ ...previous, [section]: (previous[section] ?? []).filter(row => row !== editingRow) }));
    }
    setEditingRow(null);
  }
  function moveStep(index: number) {
    setStepIndex(index); setSection(setupSteps[index].section); setEditingRow(null); setError("");
    try { window.localStorage.setItem(`office:setup-step:${company.id}`, setupSteps[index].section); } catch { /* 입력 내용은 서버에 저장하므로 단계 위치 저장 실패와 무관합니다. */ }
  }
  async function nextStep() {
    if (!workspace) return;
    const missing = missingStepValues(workspace, section, pending, newRows[section]);
    if (missing.length) { setError(`${missing.join(", ")} 항목을 확인해 주세요.`); return; }
    if (dirty && !await save()) return;
    moveStep(Math.min(stepIndex + 1, setupSteps.length - 1));
  }
  const activeSection = workspace?.sections.find(item => item.code === section);
  if (workspace?.status === "COMPLETED") return <section className="panel setup-complete"><h2>회계 준비를 마쳤습니다</h2><p>초기 설정을 다시 진행할 필요가 없습니다. 변경할 내용은 설정에서 관리하세요.</p><div className="workspace-buttons"><Link className="button-link" href="/">업무 홈으로</Link><Link href="/accounting">설정 관리</Link></div></section>;
  return <section className="panel setup-wizard" aria-labelledby="onboarding-heading">
    <div className="session-bar"><div><span className="eyebrow">처음 한 번, 회사별 설정</span><h2 id="onboarding-heading">회계 시작 준비</h2></div>
      <button onClick={() => setModal(true)} disabled={!workspace || busy || dirty || workspace.status === "COMPLETED" || !company.permissions.includes("onboarding.import")}>Excel 업로드</button>
    </div>
    <p className="muted">한 단계씩 확인하면 됩니다. 저장한 내용은 다음에 접속해도 이어서 확인할 수 있습니다.</p>
    {error && <div role="alert" className="error"><p>{denied ? "온보딩을 조회할 권한이 없습니다. 회사 관리자에게 문의해 주세요." : error}</p><button disabled={busy} onClick={() => { if (!dirty || window.confirm("저장하지 않은 변경사항을 버리고 다시 불러올까요?")) void perform(reload); }}>최신 내용 다시 불러오기</button></div>}
    {!workspace && !error && <p role="status">초안을 불러오고 있습니다…</p>}
    {workspace && <>
      <ol className="setup-stepper" aria-label="초기 설정 단계">{setupSteps.map((step, index) => <li key={step.section} aria-current={stepIndex === index ? "step" : undefined}><button disabled={busy || index > stepIndex} onClick={() => moveStep(index)}><span>{index + 1}</span>{step.label}</button></li>)}</ol>
      <div className="setup-step-heading"><span className="eyebrow">{stepIndex + 1} / {setupSteps.length} 단계</span><h3>{setupSteps[stepIndex].label}</h3><p>{setupSteps[stepIndex].description}</p></div>
      {notice && <p role="status">{notice}{openingJournalId && <> <Link href={`/journals#journal-${openingJournalId}`}>기초 전표 확인하기 →</Link></>}</p>}
      <div className="onboarding-editor">
      {stepIndex === setupSteps.length - 1 && <section aria-label="입력 요약"><div className="setup-review">{setupSteps.slice(0, -1).map((step, index) => <div key={step.section}><strong>{step.label}</strong><span>{step.section === "Counterparties" ? `${new Set(workspace.cells.filter(cell => cell.field_code.startsWith("Counterparties.")).map(cell => cell.row_key)).size}개 거래처` : step.section === "Opening_Balances" ? workspace.cells.some(cell => cell.field_code === "Company.no_opening_balance" && cell.value === true) ? "신규 회사 · 기초잔액 없음" : "기초잔액 확인 필요" : step.section === "Company" ? String(workspace.cells.find(cell => cell.field_code === "Company.company_name")?.value ?? "입력 전") : "저장한 회계 기준 확인"}</span><button onClick={() => moveStep(index)}>수정</button></div>)}</div><details><summary>기본 계정과목 확인</summary><AccountCatalog companyId={company.id} /></details><p className="muted">추가 자료는 Excel로 가져올 수 있습니다. 아직 지원하지 않는 항목이 있으면 완료 전에 안내하며, 입력 자료는 보관합니다.</p></section>}
      {section !== "Review" && <>
      <div className="section-toolbar"><div><h3>{activeSection?.label}</h3></div><span className="status-chip">{dirty ? "저장 필요" : "저장된 내용"}</span></div>
      <p className="muted">{section === "Company" ? "사업자 유형에 따라 필요한 정보가 달라집니다. 회사 정보를 확인해 주세요." : section === "Accounting_Settings" ? "기능통화와 회계연도 시작 월 등 장부의 기본 기준을 확인해 주세요." : section === "Opening_Balances" ? "기존 장부의 잔액을 입력해 주세요. 신규 회사라 잔액이 없다면 아래에서 ‘예’를 선택해 주세요." : section === "COA" ? "미리 준비된 계정목록입니다. 별도로 입력하지 않아도 됩니다." : "필요한 항목을 추가하고 저장해 주세요."}</p>
      {section === "Opening_Balances" && <div className="opening-choice"><FieldEditor field={workspace.fields.find(field => field.field_code === "Company.no_opening_balance")!} value={pending[cellKey("Company.no_opening_balance", "singleton")] ?? workspace.cells.find(cell => cell.field_code === "Company.no_opening_balance")?.value ?? ""} disabled={readOnly} onChange={value => setPending(previous => ({ ...previous, [cellKey("Company.no_opening_balance", "singleton")]: value }))} /><p className="muted">기존 잔액이 없다면 ‘예’를 선택하세요. 이미 입력한 잔액은 이 선택으로 삭제되지 않습니다.</p></div>}
      {section === "COA" ? <AccountCatalog companyId={company.id} /> : <>
      {keys && rows.length > 0 && <div className="table-scroll"><table><thead><tr><th>항목</th><th>입력 내용</th><th>상태</th><th>작업</th></tr></thead><tbody>{rows.map(row => {
        const cells = workspace.cells.filter(cell => cell.row_key === row && cell.field_code.startsWith(`${section}.`));
        return <tr key={row}><td>{row.startsWith("new-") ? "새 항목" : String(cells.find(cell => /\.(legal_name|account_name|asset_name|item_name)$/.test(cell.field_code))?.value ?? row.replaceAll("|", " · "))}</td><td>{cells.slice(0, 3).map(cell => String(cell.value)).join(" · ") || "입력 전"}</td><td><span className="status-chip">{cells.some(cell => cell.status === "STALE") ? "다시 확인 필요" : cells.length ? "입력됨" : "미입력"}</span></td><td><button onClick={() => setEditingRow(row)}>{readOnly ? "상세 보기" : "입력·수정"}</button></td></tr>;
      })}</tbody></table></div>}
      {rows.length === 0 && <p className="muted">아직 입력한 항목이 없습니다. 필요한 항목을 추가해 주세요.</p>}
      {keys && <button disabled={readOnly} onClick={() => { const row = `new-${crypto.randomUUID()}`; setNewRows(previous => ({ ...previous, [section]: [...(previous[section] ?? []), row] })); setEditingRow(row); }}>항목 추가</button>}
      {rows.filter(row => !keys || row === editingRow).map(row => { const editor = <fieldset key={row} disabled={readOnly}><legend>{keys ? row.startsWith("new-") ? "새 항목" : "입력 내용" : "기본 입력"}</legend>
        {fields.filter(field => field.field_code !== "Company.no_opening_balance" && isEditable(field) && isVisible(field, taxpayerType)).map(field => {
          const current = workspace.cells.find(c => c.field_code === field.field_code && c.row_key === row);
          const fieldKey = cellKey(field.field_code, row);
          return <div key={fieldKey}><FieldEditor field={field} value={pending[fieldKey] ?? current?.value ?? ""} options={field.enum_source_code ? workspace.enums[field.enum_source_code] : undefined}
            disabled={readOnly || !!keys?.includes(field.field_code.split(".")[1]) && !row.startsWith("new-")} onChange={value => setPending(previous => ({ ...previous, [fieldKey]: value }))} />
            {current && current.source_type === "EXCEL_IMPORT" && <small>{sourceLabels[current.source_type]}</small>}{current && ["INVALID", "STALE"].includes(current.status) && <small className="error">{stateLabels[current.status]}</small>}</div>;
        })}
      </fieldset>; return keys ? <OfficeDialog key={row} open onClose={closeRowEditor} title={`${activeSection?.label} ${readOnly ? "상세" : "입력"}`} description="작성한 내용은 저장을 눌러야 보관됩니다. 닫은 뒤에도 이 페이지에서는 이어서 작성할 수 있습니다." busy={busy} footer={<button disabled={readOnly || !dirty} onClick={save}>{busy ? "저장 중…" : "변경 내용 저장"}</button>}>{error && <p role="alert" className="error">{error}</p>}{editor}</OfficeDialog> : <div key={row}>{editor}</div>; })}
      {fields.filter(f => !isEditable(f)).map(field => { const current = workspace.cells.find(c => c.field_code === field.field_code); return <p key={field.field_code}>{field.label}: {String(current?.value ?? "계산 전")} · {stateLabels[current?.status ?? "STALE"]}</p>; })}
      </>}
      </>}
      <div className="workspace-save-bar"><div><strong>{busy ? "처리 중입니다…" : dirty ? "저장하지 않은 변경사항" : "변경한 내용이 없습니다"}</strong><small>{dirty ? "다음으로 이동할 때 변경 내용을 저장합니다." : "이전 단계로 돌아가 확인할 수 있습니다."}</small></div><div className="workspace-buttons">
        {stepIndex > 0 && <button disabled={busy} onClick={() => moveStep(stepIndex - 1)}>이전</button>}
        {dirty && <button onClick={save} disabled={readOnly}>저장</button>}
        {stepIndex < setupSteps.length - 1 ? <button className="button-accent" onClick={nextStep} disabled={busy || dirty && readOnly}>{dirty ? "저장하고 다음" : "다음"}</button> : <><button onClick={validate} disabled={readOnly || dirty}>입력 내용 확인</button><button className="button-accent" onClick={() => setCompleteOpen(true)} disabled={busy || dirty || workspace.status !== "READY_TO_COMPLETE" || !company.permissions.includes("onboarding.complete")}>회계 준비 완료</button></>}
      </div></div>
      {stepIndex === setupSteps.length - 1 && workspace.status !== "READY_TO_COMPLETE" && <p className="muted">‘입력 내용 확인’을 통과하면 완료할 수 있습니다. 최종 완료는 회사 관리자 권한이 필요합니다.</p>}
      {issues.length > 0 && <section aria-label="검증 결과"><h3>확인할 내용</h3>{issues.map((issue, i) => { const code = issue.field_code?.split(".")[0] ?? issue.row_key; return <div key={i} className="validation-item"><p className="error">{workspace.fields.find(f => f.field_code === issue.field_code)?.label ?? "입력 내용"}: {issue.message}</p>{workspace.sections.some(item => item.code === code) && <button onClick={() => { moveStep(stepForSection(code)); setSection(code); if (issue.row_key !== "singleton") setEditingRow(issue.row_key); }}>해당 항목 확인</button>}</div>; })}</section>}
      {section === "Opening_Balances" && company.permissions.includes("journal.propose") && <button disabled={busy || Object.keys(pending).length > 0} onClick={openingJournal}>저장된 기초잔액으로 전표 작성</button>}
      {completeOpen && <ConfirmationDialog open onClose={() => setCompleteOpen(false)} onConfirm={() => void complete()} busy={busy} title="회계 준비 완료" description="검증한 초안을 회사 회계정보에 반영합니다. 아직 확인하지 않은 항목이 있으면 먼저 보완하도록 안내합니다." confirmLabel="확인 후 회계정보 반영"><p>대상 회사: {company.company_name}</p><p>기초잔액은 여기서 장부에 확정되지 않습니다. 별도 전표 작성과 승인 절차가 필요합니다.</p>{error && <p role="alert">{error}</p>}</ConfirmationDialog>}
      {modal && <ExcelImportDialog workspace={workspace} onApplied={async () => { await reload(); }} onClose={() => setModal(false)} />}
      </div>
    </>}
  </section>;
}
