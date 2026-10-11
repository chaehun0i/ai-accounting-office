import { money, units } from "../accounting/journal-model.ts";

export type DocumentKind = "SALES_INVOICE" | "PURCHASE_INVOICE" | "CREDIT_NOTE" | "DEBIT_NOTE";
export type DocumentLine = { line_no: number; description: string; supply_amount: string; tax_amount: string };
export type BusinessDocument = {
  id: string; document_type: DocumentKind; document_no: string; counterparty_id: string;
  issue_date: string; accounting_date: string; due_date: string; status: string; version: number;
  supply_amount: string; tax_amount: string; total_amount: string; lines: DocumentLine[];
  transaction_id: string | null; obligation_id: string | null; source_import_id: string | null;
  evidence_id: string | null; original_document_id: string | null; original_document_type: DocumentKind | null;
  reason_code: string | null; source_system: string; source_id: string; approved_at: string | null;
};
export const documentLabels: Record<DocumentKind, string> = {
  SALES_INVOICE: "매출 청구서", PURCHASE_INVOICE: "매입 청구서", CREDIT_NOTE: "감액 정정문서", DEBIT_NOTE: "증액 정정문서",
};
export const documentPaths: Record<DocumentKind, string> = {
  SALES_INVOICE: "/sales-invoices", PURCHASE_INVOICE: "/purchase-invoices", CREDIT_NOTE: "/credit-notes", DEBIT_NOTE: "/debit-notes",
};
export const documentStatuses: Record<string, string> = { DRAFT: "작성 중", REVIEW_REQUIRED: "승인 대기", APPROVED: "문서 확정", APPLIED: "정정 반영" };
export function documentTotals(lines: DocumentLine[]) {
  let supply = BigInt(0), tax = BigInt(0);
  for (const line of lines) { supply += units(line.supply_amount); tax += units(line.tax_amount); }
  return { supply: money(supply), tax: money(tax), total: money(supply + tax) };
}
export function documentActions(value: BusinessDocument, permissions: readonly string[]) {
  return value.status === "DRAFT" && permissions.includes("invoice.review") ? ["submit"] :
    value.status === "REVIEW_REQUIRED" && permissions.includes("invoice.approve") ? ["approve"] : [];
}
