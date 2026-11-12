export function equityReviewActions(status: string, stale: boolean, permissions: string[]): string[] {
  if (stale) return [];
  if (["NOT_REQUESTED", "REJECTED"].includes(status) && permissions.includes("financial_statement.generate")) return ["request-review"];
  if (status === "REVIEW_REQUESTED" && permissions.includes("financial_statement.approve")) return ["approve", "reject"];
  return [];
}
