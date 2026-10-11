"use client";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { displayAmount } from "@/shared/amount";
import { localDate } from "@/shared/calendar";
import { ConfirmationDialog, OfficeDialog } from "@/shared/ui/dialog";
import { documentActions, documentLabels, documentPaths, documentStatuses, documentTotals, type BusinessDocument, type DocumentKind, type DocumentLine } from "./model";

type Counterparty = { id: string; display_name: string };
type Editor = { kind: DocumentKind; original: BusinessDocument | null; editing: BusinessDocument | null };
const freshLine = (index: number): DocumentLine => ({ line_no: index, description: "", supply_amount: "0", tax_amount: "0" });

export function DocumentWorkspace({ company }: { company: Company }) {
  const [kind, setKind] = useState<DocumentKind>("SALES_INVOICE");
  const [rows, setRows] = useState<BusinessDocument[]>([]), [counterparties, setCounterparties] = useState<Counterparty[]>([]);
  const [selected, setSelected] = useState<BusinessDocument | null>(null), [editor, setEditor] = useState<Editor | null>(null);
  const [lines, setLines] = useState<DocumentLine[]>([freshLine(1)]), [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const requestKey = useRef(crypto.randomUUID());
  useEffect(() => {
    let active = true;
    if (!company.permissions.includes("invoice.read")) return;
    Promise.all([
      authenticatedRequest<BusinessDocument[]>(documentPaths[kind], { headers: { "X-Company-ID": company.id } }),
      authenticatedRequest<Counterparty[]>("/counterparties", { headers: { "X-Company-ID": company.id } }),
    ]).then(([documents, parties]) => { if (active) { setRows(documents); setCounterparties(parties); } })
      .catch(reason => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company.id, company.permissions, kind, revision]);
  function open(value: Editor) {
    requestKey.current = crypto.randomUUID(); setEditor(value); setError("");
    setLines(value.editing?.lines.map(line => ({ ...line })) ?? [freshLine(1)]);
  }
  function lineChange(index: number, field: keyof DocumentLine, value: string) {
    setLines(current => current.map((line, i) => i === index ? { ...line, [field]: value } : line));
  }
  let totals: ReturnType<typeof documentTotals> | null = null;
  try { totals = documentTotals(lines); } catch { /* 입력 중인 금액이 유효하지 않으면 저장을 막습니다. */ }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!editor || !totals) return;
    const form = new FormData(event.currentTarget); setBusy(true); setError(""); setSaved("");
    const original = editor.original, editing = editor.editing;
    const payload = {
      document_no: String(form.get("number")), counterparty_id: form.get("counterparty"),
      issue_date: form.get("issue"), accounting_date: form.get("accounting"), due_date: form.get("due"),
      source_system: editing?.source_system ?? "MANUAL", source_id: editing?.source_id ?? requestKey.current,
      lines: lines.map((line, index) => ({ ...line, line_no: index + 1 })),
      ...(original ? { original_document_type: original.document_type, original_document_id: original.id,
        expected_version: original.version, reason_code: String(form.get("reason")) } : {}),
      ...(editing ? { expected_version: editing.version } : {}),
    };
    try {
      const value = await authenticatedRequest<BusinessDocument>(documentPaths[editor.kind] + (editing ? `/${editing.id}` : ""), {
        method: editing ? "PATCH" : "POST", headers: { "X-Company-ID": company.id, "Idempotency-Key": requestKey.current }, body: JSON.stringify(payload),
      });
      setKind(editor.kind); setSelected(value); setEditor(null); setRevision(v => v + 1); setSaved("문서를 저장했습니다.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "문서를 저장하지 못했습니다."); }
    finally { setBusy(false); }
  }
  async function act() {
    if (!selected || !pending) return; setBusy(true); setError("");
    try {
      const value = await authenticatedRequest<BusinessDocument>(`${documentPaths[selected.document_type]}/${selected.id}/${pending}`, {
        method: "POST", headers: { "X-Company-ID": company.id, "Idempotency-Key": requestKey.current }, body: JSON.stringify({ expected_version: selected.version }),
      });
      setSelected(value); setRevision(v => v + 1); setPending(null); setSaved(pending === "approve" ? "문서가 확정되었습니다. 장부 반영은 전표 승인 후 진행합니다." : "승인을 요청했습니다.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "문서 상태를 다시 확인해 주세요."); }
    finally { setBusy(false); }
  }
  if (!company.permissions.includes("invoice.read")) return <p role="alert">업무문서를 조회할 권한이 없습니다.</p>;
  const partyName = (id: string) => counterparties.find(party => party.id === id)?.display_name ?? "거래처 확인 필요";
  return <section className="panel">
    <div className="section-heading"><div><h2>매출 · 매입 문서</h2><p>문서를 확정하면 거래와 채권·채무가 생성됩니다. 장부 반영은 별도 전표 승인 절차입니다.</p></div>
      {company.permissions.includes("invoice.create") && !kind.includes("NOTE") && <button className="button-accent" onClick={() => open({ kind, original: null, editing: null })}>새 {documentLabels[kind]} 작성</button>}</div>
    <label>문서 종류<select value={kind} onChange={event => { setKind(event.target.value as DocumentKind); setSelected(null); setLoading(true); setError(""); }}>
      {Object.entries(documentLabels).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
    </select></label>
    {error && <p role="alert">{error}</p>}{saved && <p role="status">{saved}</p>}
    {loading ? <p role="status">문서를 불러오는 중입니다…</p> : rows.length === 0 ? <p>등록된 문서가 없습니다. 매출·매입 문서를 작성해 주세요.</p> : <div className="table-scroll"><table><thead><tr><th>문서번호</th><th>거래처</th><th>발행일</th><th>지급기일</th><th>총액</th><th>상태</th></tr></thead><tbody>
      {rows.map(value => <tr key={value.id}><td><button onClick={() => setSelected(value)}>{value.document_no}</button></td><td>{partyName(value.counterparty_id)}</td><td>{value.issue_date}</td><td>{value.due_date}</td><td>{displayAmount(value.total_amount)}원</td><td>{documentStatuses[value.status] ?? "상태 확인 필요"}</td></tr>)}
    </tbody></table></div>}
    {selected && <article><h3>{selected.document_no} · {documentStatuses[selected.status]}</h3><p>{partyName(selected.counterparty_id)} · 공급가 {displayAmount(selected.supply_amount)}원 · 세액 {displayAmount(selected.tax_amount)}원 · 총액 {displayAmount(selected.total_amount)}원</p>
      <ul>{selected.lines.map(line => <li key={line.line_no}>{line.description} · 공급가 {displayAmount(line.supply_amount)}원 · 세액 {displayAmount(line.tax_amount)}원</li>)}</ul>
      {selected.status === "DRAFT" && !selected.document_type.includes("NOTE") && company.permissions.includes("invoice.create") && <button onClick={() => open({ kind: selected.document_type, original: null, editing: selected })}>초안 수정</button>}
      {documentActions(selected, company.permissions).map(action => <button key={action} disabled={busy} onClick={() => { requestKey.current = crypto.randomUUID(); setPending(action); }}>{action === "approve" ? "문서 승인·확정" : "승인 요청"}</button>)}
      {selected.status === "APPROVED" && company.permissions.includes("credit_note.create") && <><button onClick={() => open({ kind: "CREDIT_NOTE", original: selected, editing: null })}>감액 정정문서 작성</button><button onClick={() => open({ kind: "DEBIT_NOTE", original: selected, editing: null })}>증액 정정문서 작성</button></>}
      {selected.transaction_id && <p><Link href={`/transactions#transaction-${selected.transaction_id}`}>생성된 거래 확인</Link></p>}
      {selected.obligation_id && <p><Link href={(selected.document_type === "SALES_INVOICE" || selected.original_document_type === "SALES_INVOICE" ? "/receivables" : "/payables") + `#${selected.obligation_id}`}>채권·채무와 정산 내역 확인</Link></p>}
      {selected.original_document_id && <p>원문서 식별자: {selected.original_document_id} · 정정 사유: {selected.reason_code}</p>}
      <p>가져오기 출처: {selected.source_import_id ?? "직접 작성"} · 증빙: {selected.evidence_id ?? "연결된 증빙 없음"}</p>
    </article>}
    <OfficeDialog open={!!editor} onClose={() => setEditor(null)} busy={busy} title={editor ? documentLabels[editor.kind] : "문서 작성"} description="공급가액과 세액은 원천 문서의 금액입니다. 세무 신고 검증 결과가 아닙니다.">
      {error && <p role="alert">{error}</p>}{editor && <form key={requestKey.current} onSubmit={save}>
        <label>문서번호<input name="number" required maxLength={100} defaultValue={editor.editing?.document_no ?? ""} /></label>
        <label>거래처<select name="counterparty" required defaultValue={editor.original?.counterparty_id ?? editor.editing?.counterparty_id ?? ""}>{!editor.original && <option value="">거래처 선택</option>}{counterparties.filter(party => !editor.original || party.id === editor.original.counterparty_id).map(party => <option key={party.id} value={party.id}>{party.display_name}</option>)}</select></label>
        <label>발행일<input name="issue" type="date" required defaultValue={editor.editing?.issue_date ?? localDate()} /></label><label>회계 기준일<input name="accounting" type="date" required defaultValue={editor.editing?.accounting_date ?? localDate()} /></label><label>지급기일<input name="due" type="date" required defaultValue={editor.editing?.due_date ?? localDate()} /></label>
        {editor.original && <label>정정 사유<input name="reason" required maxLength={100} /></label>}
        {lines.map((line, index) => <fieldset key={index}><legend>항목 {index + 1}</legend><label>내용<input value={line.description} required maxLength={500} onChange={event => lineChange(index, "description", event.target.value)} /></label><label>공급가액<input inputMode="decimal" required value={line.supply_amount} onChange={event => lineChange(index, "supply_amount", event.target.value)} /></label><label>세액<input inputMode="decimal" required value={line.tax_amount} onChange={event => lineChange(index, "tax_amount", event.target.value)} /></label><button type="button" disabled={lines.length === 1} onClick={() => setLines(values => values.filter((_, i) => i !== index))}>항목 삭제</button></fieldset>)}
        <button type="button" disabled={lines.length >= 500} onClick={() => setLines(values => [...values, freshLine(values.length + 1)])}>항목 추가</button>
        <p aria-live="polite">{totals ? `공급가 ${displayAmount(totals.supply)}원 · 세액 ${displayAmount(totals.tax)}원 · 총액 ${displayAmount(totals.total)}원` : "금액을 확인해 주세요."}</p>
        <button className="button-accent" disabled={busy || !totals}>{busy ? "저장 중…" : "초안 저장"}</button>
      </form>}
    </OfficeDialog>
    <ConfirmationDialog open={!!pending} onClose={() => setPending(null)} onConfirm={act} busy={busy} title={pending === "approve" ? "문서를 확정할까요?" : "승인을 요청할까요?"} description="확정 후 금액은 직접 수정할 수 없습니다. 변경은 정정문서를 사용합니다." confirmLabel={pending === "approve" ? "문서 확정" : "승인 요청"}><p>문서 확정은 장부 반영과 다릅니다. 전표 작성·사람 승인·확정 절차가 별도로 필요합니다.</p>{error && <p role="alert">{error}</p>}</ConfirmationDialog>
  </section>;
}
