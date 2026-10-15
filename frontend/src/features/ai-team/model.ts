export type Period = {
  id: string;
  start_date: string;
  end_date: string;
  fiscal_year: number;
  period_no: number;
  status: "OPEN" | "CLOSING" | "CLOSED";
};

export type QueryRun = {
  id: string;
  period_id: string | null;
  question_text: string | null;
  status: "PENDING" | "RUNNING" | "WAITING_FOR_INPUT" | "COMPLETED" | "BLOCKED" | "FAILED";
  answer_text: string | null;
  answer_amount: string | null;
  answer_resource_id: string | null;
  answer_source_digest: string | null;
  controller_verdict: string | null;
  error_code: string | null;
};

export function queryPayload(periodId: string, question: string) {
  return { period_id: periodId, question: question.trim() };
}

export function queryRequest(companyId: string, periodId: string, question: string, key: string): RequestInit {
  return {
    method: "POST",
    headers: { "X-Company-ID": companyId, "Idempotency-Key": key },
    body: JSON.stringify(queryPayload(periodId, question)),
  };
}

export function isFinal(status: QueryRun["status"]) {
  return status === "COMPLETED" || status === "BLOCKED" || status === "FAILED";
}

export function runMessage(run: QueryRun) {
  if (run.status === "BLOCKED") return "검증 단계에서 답변이 차단됐습니다. 기준 자료와 권한을 확인해 주세요.";
  if (run.status === "FAILED") return "질의를 완료하지 못했습니다. 기간과 권한을 확인한 뒤 다시 시도해 주세요.";
  if (!isFinal(run.status)) return "회계 자료를 확인하고 있습니다…";
  return run.answer_text ?? "표시할 답변이 없습니다.";
}

export function formatAnswerAmount(value: string | null) {
  if (value === null) return null;
  // API의 Decimal 문자열을 계산하거나 본문에서 파싱하지 않습니다.
  return value;
}
