"use client";

import { useState } from "react";
import { OfficeDialog } from "@/shared/ui/dialog";
import { authenticatedRequest } from "@/features/auth/session";
import { conflictKey, type Preview, type Receipt, type Workspace } from "./model";

export function ExcelImportDialog({ workspace, onApplied, onClose }: { workspace: Workspace; onApplied: () => Promise<void>; onClose: () => void }) {
  const [file, setFile] = useState<File>();
  const [preview, setPreview] = useState<Preview>();
  const [choices, setChoices] = useState<Record<string, "KEEP_CURRENT" | "APPLY_IMPORT">>({});
  const [receipt, setReceipt] = useState<Receipt>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [key, setKey] = useState("");
  const headers = { "X-Company-ID": workspace.company_id };
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : "파일을 처리하지 못했습니다."); }
    finally { setBusy(false); }
  }
  async function download() {
    await perform(async () => {
      const blob = await authenticatedRequest<Blob>("/onboarding/templates/current", { headers }, r => r.blob());
      const url = URL.createObjectURL(blob); const link = document.createElement("a");
      link.href = url; link.download = "accounting-onboarding-v1.xlsx"; link.click(); URL.revokeObjectURL(url);
    });
  }
  async function upload() {
    if (!file) return;
    await perform(async () => {
      const body = new FormData(); body.set("file", file);
      const imported = await authenticatedRequest<{ import_id: string }>("/onboarding/imports", { method: "POST", headers, body });
      const result = await authenticatedRequest<Preview>(`/onboarding/imports/${imported.import_id}/preview`, {
        method: "POST", headers, body: JSON.stringify({ expected_version: workspace.version }),
      });
      setPreview(result); setChoices({}); setKey(crypto.randomUUID());
    });
  }
  async function apply() {
    if (!preview) return;
    await perform(async () => {
      const result = await authenticatedRequest<Receipt>(`/onboarding/imports/${preview.import_id}/apply`, {
        method: "POST", headers: { ...headers, "Idempotency-Key": key }, body: JSON.stringify({ expected_version: preview.session_version, preview_digest: preview.digest, choices }),
      });
      setReceipt(result); await onApplied();
    });
  }
  const conflicts = preview?.items.filter(i => i.classification === "CONFLICT") ?? [];
  return <OfficeDialog open onClose={onClose} busy={busy} title="Excel로 현재 초안 채우기" description="파일은 초안에만 반영됩니다. 기존 값과 다르면 적용할 값을 직접 선택해 주세요.">
    <button onClick={download} disabled={busy}>공식 양식 다운로드</button>
    <label>Excel 파일<input type="file" accept=".xlsx" disabled={busy} onChange={e => { setFile(e.target.files?.[0]); setPreview(undefined); setReceipt(undefined); setChoices({}); }} /></label>
    <button onClick={upload} disabled={busy || !file || !!receipt}>{busy ? "처리 중…" : "업로드 후 미리보기"}</button>
    {error && <p role="alert" className="error">{error}</p>}
    {preview && !receipt && <section aria-label="병합 검토">
      <p>새 입력값 {preview.counts.APPLY} · 동일 {preview.counts.UNCHANGED} · 충돌 {preview.counts.CONFLICT} · 오류 {preview.counts.ERROR}</p>
      {preview.errors.map((e, i) => <p key={i} className="error">{e.message} ({e.row_key})</p>)}
      {conflicts.map(item => <label key={conflictKey(item.incoming)}>
        {workspace.fields.find(f => f.field_code === item.incoming.field_code)?.label} — {item.incoming.row_key}
        <p>현재: {String(item.current?.value ?? "없음")} / Excel: {String(item.incoming.value)}</p>
        <select aria-label="충돌 해결" value={choices[conflictKey(item.incoming)] ?? ""} onChange={e => {
          setChoices(previous => ({ ...previous, [conflictKey(item.incoming)]: e.target.value as "KEEP_CURRENT" | "APPLY_IMPORT" })); setKey(crypto.randomUUID());
        }}><option value="">적용할 값을 선택해 주세요</option><option value="KEEP_CURRENT">현재 값 유지</option><option value="APPLY_IMPORT">Excel 값 적용</option></select>
      </label>)}
      <button onClick={apply} disabled={busy || preview.errors.length > 0 || conflicts.some(i => !choices[conflictKey(i.incoming)])}>선택한 내용 초안에 적용</button>
    </section>}
    {receipt && <p role="status">초안에 적용했습니다. 새 입력값 {receipt.new_count}, 변경 {receipt.changed_count}, 동일 {receipt.unchanged_count}. 실제 회사 회계정보는 최종 완료 시 반영됩니다.</p>}
  </OfficeDialog>;
}
