export type Period = {
  id: string; start_date: string; end_date: string;
  fiscal_year: number; period_no: number; status: "OPEN" | "CLOSING" | "CLOSED";
  close_version: number;
};

export type Check = {
  check_code: string; severity: "PASS" | "WARNING" | "BLOCKER";
  result_code: string; amount_impact: string; source_type: string | null;
  source_id: string | null; evidence_ref: string | null;
};

export type Adjustment = {
  id: string; adjustment_type: string; status: string; proposed_journal_id: string;
  approval_id: string | null; auto_reverse: boolean; scheduled_reversal_date: string | null;
  reversal_journal_id: string | null; version: number;
};

export type ClosingRun = {
  id: string; accounting_period_id: string; run_version: number; status: string;
  source_digest: string; unadjusted_tb_digest: string; adjusted_tb_digest: string | null;
  bank_reconciliation_digest: string; ar_reconciliation_digest: string;
  ap_reconciliation_digest: string; created_by: string; created_at: string;
  completed_at: string | null; checks?: Check[]; adjustments?: Adjustment[];
};

export type Approval = {
  id: string; action_code: "CLOSE" | "REOPEN"; status: string;
  requester_id: string; reviewer_id: string | null; requested_at: string;
  reason: string;
};

export type TrialRow = {
  account_id: string; account_code: string; account_name: string;
  period_debit: string; period_credit: string;
  ending_debit: string; ending_credit: string;
};

export type Trial = { stage: string; digest: string; rows: TrialRow[] };
export type Account = { id: string; account_code: string; account_name: string; posting_allowed: boolean; status: string };

export const checkLabels: Record<string, string> = {
  TRANSACTIONS_PENDING: "미처리 거래", JOURNALS_PENDING: "미승인 전표",
  BANK_CARD_UNRECONCILED: "은행·카드 대사", AR_GL_MISMATCH: "채권·원장 차이",
  AP_GL_MISMATCH: "채무·원장 차이", TRIAL_BALANCE_UNBALANCED: "시산표 차대변",
  ADJUSTMENT_INCOMPLETE: "필수 결산조정",
};

export const adjustmentLabels: Record<string, string> = {
  ACCRUED_EXPENSE: "발생비용", ACCRUED_REVENUE: "발생수익",
  PREPAID_EXPENSE_RELEASE: "선급비용 환입", UNEARNED_REVENUE_RELEASE: "선수수익 환입",
  MANUAL_CUTOFF_ADJUSTMENT: "기간귀속 수동조정",
};
