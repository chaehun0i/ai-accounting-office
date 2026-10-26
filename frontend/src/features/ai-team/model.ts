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
  graph_name: string;
};

export type QueryStep = {
  step_no: number;
  node_name: string;
  status: string;
};

export const teamStepLabel: Record<string, string> = {
  accounting_lead: "Accounting Lead · 검토 계획",
  closing_agent: "Closing Agent · 마감 검사",
  ar_agent: "AR Agent · 채권 대사",
  ap_agent: "AP Agent · 채무 대사",
  compose_team_answer: "역할별 결과 통합",
  controller_agent: "Controller · 출처와 차이 검증",
};

export function canReviewTeam(permissions: readonly string[]) {
  return ["period.read", "receivable.read", "payable.read"].every(permission => permissions.includes(permission));
}

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

export function runStatusLabel(status: QueryRun["status"]) {
  return {
    PENDING: "대기 중", RUNNING: "자료 확인 중", WAITING_FOR_INPUT: "입력 대기",
    COMPLETED: "조회 완료", BLOCKED: "검증 차단", FAILED: "실행 실패",
  }[status];
}

export function runMessage(run: QueryRun) {
  if (run.status === "BLOCKED") return run.error_code === "TEAM_SOURCE_CONFLICT"
    ? "역할별 조회 중 원천이 변경되었거나 대사 결과가 맞지 않아 공동 검토를 차단했습니다. 최신 기간 자료를 확인하고 다시 실행해 주세요."
    : "검증 단계에서 답변이 차단됐습니다. 기준 자료와 권한을 확인해 주세요.";
  if (run.status === "FAILED") return run.error_code === "AUTHORIZATION_DENIED"
    ? "기간·채권·채무 조회 권한을 다시 확인해 주세요."
    : "질의를 완료하지 못했습니다. 기간과 권한을 확인한 뒤 다시 시도해 주세요.";
  if (!isFinal(run.status)) return "회계 자료를 확인하고 있습니다…";
  return run.answer_text ?? "표시할 답변이 없습니다.";
}
