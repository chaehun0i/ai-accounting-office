export type Period = { id: string; start_date: string; end_date: string; status: string; close_version: number };
export type StatementSet = {
  id: string; period_id: string; closing_run_id: string; close_version: number;
  taxonomy_version: number; status: string; trial_balance_digest: string; generated_at: string;
};
export type StatementLine = {
  id: string; line_code: string; label: string; parent_code: string | null;
  display_order: number; subtotal_type: "LEAF" | "DERIVED" | "TOTAL"; current_amount: string;
};
export type Statement = {
  id: string; set_id: string; statement_type: "BALANCE_SHEET" | "INCOME_STATEMENT";
  status: string; snapshot_digest: string; lines: StatementLine[];
};
export type Source = {
  account_id: string; account_code: string; account_name: string;
  journal_id: string; journal_line_id: string; journal_no: string;
  entry_date: string; amount: string;
};
export type Account = {
  id: string; account_code: string; account_name: string; account_type: string;
  template_account_id: string | null; posting_allowed: boolean;
};

export function formatMoney(value: string): string {
  const [whole, fractional] = value.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const trimmed = fractional?.replace(/0+$/, "");
  return trimmed ? `${grouped}.${trimmed}` : grouped;
}

export type ReportDefinition = {
  code: "BALANCE_SHEET" | "INCOME_STATEMENT" | "FINANCIAL_METRICS" | "CASH_FLOW" | "CHANGES_IN_EQUITY";
  label: string;
  period_mode: "AS_OF" | "RANGE";
  formats: ("PDF" | "XLSX" | "CSV")[];
  can_generate: boolean;
};
export type ReportPreset = "TODAY" | "THIS_WEEK" | "THIS_MONTH" | "THIS_YEAR" | "CUSTOM";
export type ResolvedReportPeriod = {
  period_preset: ReportPreset; period_mode: "AS_OF" | "RANGE";
  timezone: string; date_from: string | null; date_to: string | null;
  as_of: string | null; partial: boolean;
};
export type ReportRun = {
  id: string; company_id: string; report_code: string; format: string;
  period_preset: ReportPreset; period_mode: "AS_OF" | "RANGE";
  date_from: string | null; date_to: string | null; as_of: string | null;
  period_id: string; statement_set_id: string; close_version: number;
  taxonomy_version: number; source_digest: string; template_version: number;
  status: "REQUESTED" | "GENERATING" | "COMPLETED" | "FAILED";
  requested_by: string; requested_at: string; started_at: string | null;
  completed_at: string | null; error_code: string | null; retry_of_run_id: string | null;
};
export type ReportArtifact = {
  id: string; run_id: string; file_name: string; file_sha256: string;
  size_bytes: number; content_type: string; created_at: string;
};

export function matchesClosedPeriod(period: Period | undefined, resolved: ResolvedReportPeriod | null): boolean {
  if (!period || !resolved || period.status !== "CLOSED") return false;
  return resolved.period_mode === "AS_OF"
    ? resolved.as_of === period.end_date
    : resolved.date_from === period.start_date && resolved.date_to === period.end_date;
}
