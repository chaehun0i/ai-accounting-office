type Section = { code: string; complete: number; total: number; status: string };

// 서버가 산출한 입력 대상만 집계하며 시스템 기본값은 분모에 다시 더하지 않습니다.
export function workspaceSummary(sections: Section[]) {
  const input = sections.filter(section => section.code !== "COA");
  const complete = input.reduce((sum, section) => sum + section.complete, 0);
  const total = input.reduce((sum, section) => sum + section.total, 0);
  return {
    complete, total,
    percent: total ? Math.round(complete / total * 100) : 0,
    warnings: input.filter(section => section.status === "WARNING").length,
    inProgress: input.filter(section => section.status === "IN_PROGRESS").length,
    empty: input.filter(section => section.status === "EMPTY").length,
  };
}
