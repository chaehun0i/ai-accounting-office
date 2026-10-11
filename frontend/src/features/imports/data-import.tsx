"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";

type Import = { id: string; version: number; original_filename: string; source_type: string };
type Mapping = { sheet_index: number; column_index: number; canonical_field_code: string | null };
type Columns = {
  columns: { sheet_index: number; sheet_name: string; column_index: number; source_header: string; mapping: Mapping & { status: string } }[];
  fields: { code: string; label: string; required: boolean }[];
};
type Preview = {
  version: number; preview_digest: string; valid: boolean; row_count: number; expires_at: string;
  errors: { sheet_index: number; row_number: number; column_index: number; message: string }[];
  rows: { sheet_index: number; row_number: number; values: [string, string][] }[];
};
type Receipt = {
  id: string; import_id: string; evidence_count: number; created_at: string;
  source_digest: string; confirmed_version: number; status: string; transaction_count: number;
  review_count: number; failed_count: number;
  rows: { sheet_index: number; row_number: number; transaction_id: string; status: string; review_code: string | null }[];
};
const sources = [
  ["BANK_TRANSACTION", "은행 거래"], ["CARD_TRANSACTION", "카드 거래"], ["SALES", "매출"],
  ["PURCHASE", "매입"], ["EXPENSE", "비용"], ["OPENING_BALANCE", "기초잔액"], ["COUNTERPARTY", "거래처"],
];

export function DataImport({ company }: { company: Company }) {
  const [file, setFile] = useState<File>();
  const [source, setSource] = useState("BANK_TRANSACTION");
  const [value, setValue] = useState<Import>();
  const [columns, setColumns] = useState<Columns>();
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [dirty, setDirty] = useState(false);
  const [preview, setPreview] = useState<Preview>();
  const [consent, setConsent] = useState(false);
  const [key, setKey] = useState("");
  const [promotionKey, setPromotionKey] = useState("");
  const [receipt, setReceipt] = useState<Receipt>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const headers = { "X-Company-ID": company.id };
  const canUpload = ["import.create", "evidence.upload"].every(p => company.permissions.includes(p));
  const canPreview = company.permissions.includes("import.preview");
  const canMap = company.permissions.includes("import.mapping.update");
  const canConfirm = company.permissions.includes("import.confirm");

  useEffect(() => {
    let active = true;
    const id = sessionStorage.getItem(`confirmed-import:${company.id}`);
    if (id) {
      void Promise.all([
        authenticatedRequest<Import>(`/imports/${id}`, { headers: { "X-Company-ID": company.id } }),
        authenticatedRequest<Receipt>(`/imports/${id}/receipt`, { headers: { "X-Company-ID": company.id } }),
      ]).then(([saved, receipt]) => {
        if (active) { setValue(saved); setSource(saved.source_type); setReceipt(receipt); setPromotionKey(`promote:${receipt.id}`); }
      }).catch(() => { if (active) setError("이전 접수 자료를 불러오지 못했습니다. 회사와 접근 권한을 확인해 주세요."); });
    }
    return () => { active = false; };
  }, [company.id]);

  function reset() {
    setValue(undefined); setColumns(undefined); setPreview(undefined); setReceipt(undefined);
    setConsent(false); setDirty(false); setMappings([]); setError(""); setKey(""); setPromotionKey("");
  }
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); }
    catch (error) { setError(error instanceof Error ? error.message : "자료를 처리하지 못했습니다. 다시 확인해 주세요."); }
    finally { setBusy(false); }
  }
  async function upload() {
    if (!file) return;
    await perform(async () => {
      if (file.size > 2_000_000) throw new Error("파일 크기는 2MB까지 지원합니다. 파일을 나누어 올려 주세요.");
      const form = new FormData(); form.set("file", file); form.set("source_type", source);
      form.set("target_context", source === "COUNTERPARTY" ? "DOMAIN_MASTER" : "TRANSACTION_CANONICAL");
      const result = await authenticatedRequest<Import>("/imports", { method: "POST", headers, body: form });
      setValue(result);
      const detected = await authenticatedRequest<Columns>(`/imports/${result.id}/columns`, { headers });
      setColumns(detected); setMappings(detected.columns.map(c => ({
        sheet_index: c.sheet_index, column_index: c.column_index, canonical_field_code: c.mapping.canonical_field_code,
      })));
    });
  }
  async function verify() {
    if (!value) return;
    setPreview(undefined); setConsent(false);
    await perform(async () => {
      let current = value;
      if (dirty) {
        current = await authenticatedRequest<Import>(`/imports/${value.id}/mapping`, {
          method: "PUT", headers, body: JSON.stringify({ expected_version: value.version, mappings }),
        });
        setValue(current); setDirty(false);
      }
      const result = await authenticatedRequest<Preview>(`/imports/${current.id}/preview`, {
        method: "POST", headers, body: JSON.stringify({ expected_version: current.version }),
      });
      setValue({ ...current, version: result.version }); setPreview(result); setKey(crypto.randomUUID());
    });
  }
  async function confirm() {
    if (!value || !preview || !consent || dirty) return;
    await perform(async () => {
      const result = await authenticatedRequest<Receipt>(`/imports/${value.id}/confirm`, {
        method: "POST", headers: { ...headers, "Idempotency-Key": key },
        body: JSON.stringify({ expected_version: preview.version, preview_digest: preview.preview_digest, confirmed: true }),
      });
      setReceipt(result); setPromotionKey(`promote:${result.id}`);
      sessionStorage.setItem(`confirmed-import:${company.id}`, result.import_id);
    });
  }
  async function promote() {
    if (!receipt || !value) return;
    await perform(async () => {
      const result = await authenticatedRequest<Receipt>(`/imports/${value.id}/promote`, {
        method: "POST", headers: { ...headers, "Idempotency-Key": promotionKey },
        body: JSON.stringify({ expected_version: receipt.confirmed_version, receipt_id: receipt.id, source_digest: receipt.source_digest }),
      });
      setReceipt(result);
    });
  }
  if (!canUpload || !canPreview) return <section className="panel"><h2>자료 가져오기</h2><p>자료 업로드 권한이 필요합니다. 회사 관리자에게 문의해 주세요.</p></section>;
  return <section className="panel" aria-labelledby="import-title">
    <h2 id="import-title">자료 가져오기</h2>
    <p>파일을 올리고 항목 연결과 검증 결과를 확인하세요. 접수만으로 장부에 반영되지는 않습니다.</p>
    <p className="muted">UTF-8 CSV 또는 XLSX · 최대 2MB, 총 1,000행, 40열, 5개 시트 · 수식은 값으로 바꾸어 주세요.</p>
    <label>자료 종류<select value={source} disabled={busy} onChange={e => { setSource(e.target.value); reset(); }}>{sources.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
    <label>파일 선택<input type="file" accept=".csv,.xlsx" disabled={busy} onChange={e => { setFile(e.target.files?.[0]); reset(); }} /></label>
    <button disabled={busy || !file || !!value} onClick={upload}>파일 올리기</button>
    {value && columns && !receipt && <>
      <h3>{value.original_filename} · 항목 연결</h3>
      <table><thead><tr><th>시트 / 원본 열</th><th>가져올 항목</th><th>확인</th></tr></thead><tbody>{columns.columns.map((column, index) => <tr key={`${column.sheet_index}-${column.column_index}`}>
        <td>{column.sheet_name} / {column.source_header}</td><td><select aria-label={`${column.sheet_name} ${column.source_header} 항목 연결`} value={mappings[index]?.canonical_field_code ?? ""} disabled={busy || !canMap} onChange={e => {
          setMappings(old => old.map((m, i) => i === index ? { ...m, canonical_field_code: e.target.value || null } : m));
          setDirty(true); setPreview(undefined); setConsent(false);
        }}><option value="">가져오지 않음</option>{columns.fields.map(field => <option key={field.code} value={field.code}>{field.label}{field.required ? " (필수)" : ""}</option>)}</select></td>
        <td>{column.mapping.status === "AMBIGUOUS" ? "항목을 직접 선택해 주세요" : column.mapping.status === "UNMAPPED" ? "연결되지 않음" : "연결됨"}</td>
      </tr>)}</tbody></table>
      <button disabled={busy || (dirty && !canMap)} onClick={verify}>{dirty ? "수정한 연결로 검증하기" : "검증하고 미리보기"}</button>
      {preview && <div aria-live="polite">
        <h3>미리보기 · {preview.row_count}행</h3>
        <p>{preview.valid ? "검증을 통과했습니다. 확인 후 접수해 주세요." : "오류를 수정한 후 다시 검증해 주세요."}</p>
        <p>유효시간: {new Date(preview.expires_at).toLocaleString("ko-KR")}까지</p>
        {preview.errors.map((item, index) => <p role="alert" key={index}>시트 {item.sheet_index + 1}, {item.row_number}행, {item.column_index + 1}열: {item.message}</p>)}
        <details><summary>대표 행 보기 (최대 5행, 민감한 텍스트 숨김)</summary>{preview.rows.map(row => <dl key={`${row.sheet_index}-${row.row_number}`}>{row.values.map(([code, text]) => <div key={code}><dt>{columns.fields.find(f => f.code === code)?.label ?? code}</dt><dd>{text}</dd></div>)}</dl>)}</details>
        <label><input type="checkbox" checked={consent} disabled={busy || !preview.valid || !canConfirm} onChange={e => setConsent(e.target.checked)} />대상 회사와 항목 연결, 검증 결과를 확인했습니다.</label>
        <button className="primary" disabled={busy || !consent || !preview.valid || dirty || !canConfirm} onClick={confirm}>확인한 자료 접수</button>
        {!canConfirm && <p>자료 접수 권한이 필요합니다. 회사 관리자에게 문의해 주세요.</p>}
      </div>}
    </>}
    {receipt && <div role="status">
      <h3>{receipt.transaction_count > 0 ? "거래 생성 완료" : "파일 확인 완료"}</h3>
      <p>{receipt.transaction_count > 0 ? "거래가 준비되었습니다. 전표 작성과 승인·장부 반영은 별도로 진행해 주세요." : "파일과 검증 결과를 보존했습니다. 아직 거래나 장부에 반영되지 않았습니다."}</p>
      {receipt.status === "CONFIRMED" && source !== "OPENING_BALANCE" && <>
        <button className="primary" disabled={busy || !canConfirm || !company.permissions.includes("transaction.create")} onClick={promote}>확인한 자료로 거래 생성</button>
        <p>실패하면 파일을 다시 올리지 않고 같은 버튼으로 재시도할 수 있습니다.</p>
      </>}
      {source === "OPENING_BALANCE" && <p>기초잔액은 초기 회사 설정의 기초 전표 흐름에서 처리해 주세요.</p>}
      <p>생성·연결된 거래 {receipt.transaction_count}건 · 보완 필요 {receipt.review_count}건 · 실패 {receipt.failed_count}건</p>
      {receipt.transaction_count > 0 && <Link href="/transactions">생성된 거래 보기</Link>}
      {receipt.rows?.map(row => <p key={`${row.sheet_index}-${row.row_number}`}>시트 {row.sheet_index + 1}, {row.row_number}행: {row.status === "REUSED" ? "기존 거래 연결" : "새 거래 생성"}{row.review_code && " · 거래처 정보를 확인해 주세요"}</p>)}
    </div>}
    {busy && <p role="status">자료를 확인하고 있습니다…</p>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}
