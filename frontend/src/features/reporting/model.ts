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
