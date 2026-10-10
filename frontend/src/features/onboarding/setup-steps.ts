// 단계 위치는 화면 안내이며 완료 판단은 서버의 검증 결과를 사용합니다.
export const setupSteps = [
  { section: "Company", label: "회사정보", description: "회사 기본정보를 확인해 주세요." },
  { section: "Accounting_Settings", label: "회계 기준", description: "장부에 사용할 통화와 회계연도 기준을 확인해 주세요." },
  { section: "Counterparties", label: "거래처", description: "거래처가 있다면 추가해 주세요. 지금 없다면 다음으로 넘어가도 됩니다." },
  { section: "Opening_Balances", label: "기초잔액", description: "기존 장부가 있는지 확인하고 시작 잔액을 준비해 주세요." },
  { section: "Review", label: "최종 확인", description: "입력 내용을 확인한 뒤 회계 준비를 완료해 주세요." },
] as const;

export function savedStep(value: string | null) {
  const index = setupSteps.findIndex(step => step.section === value);
  return index < 0 ? 0 : index;
}

export function stepForSection(section: string) {
  const index = setupSteps.findIndex(step => step.section === section);
  return index < 0 ? setupSteps.length - 1 : index;
}

type InputWorkspace = {
  cells: { field_code: string; row_key: string; value: string | boolean }[];
  fields: { field_code: string; section_code: string; label: string; active: boolean; input_mode: string; required_rule_code: string }[];
};

// 필수 정의를 별도로 복제하지 않고 서버 필드 카탈로그를 사용합니다.
export function missingStepValues(workspace: InputWorkspace, section: string, pending: Record<string, string | boolean>, newRows: string[] = []) {
  const value = (field: string, row: string) => pending[`${field}::${row}`] ?? workspace.cells.find(cell => cell.field_code === field && cell.row_key === row)?.value ?? "";
  const rows = ["Company", "Accounting_Settings"].includes(section) ? ["singleton"] : [...new Set([...workspace.cells.filter(cell => cell.field_code.startsWith(section + ".") && workspace.fields.some(field => field.field_code === cell.field_code && field.input_mode !== "DERIVED_READONLY")).map(cell => cell.row_key), ...newRows])];
  const missing = new Set<string>();
  for (const field of workspace.fields.filter(field => field.section_code === section && field.active && field.input_mode !== "DERIVED_READONLY")) {
    const required = field.required_rule_code === "ALWAYS" || field.required_rule_code === "CORPORATION" && value("Company.taxpayer_type", "singleton") === "CORPORATION";
    if (required && rows.some(row => value(field.field_code, row) === "")) missing.add(field.label);
  }
  if (section === "Opening_Balances" && !rows.length && value("Company.no_opening_balance", "singleton") !== true) missing.add("기초잔액 입력 또는 기초잔액 없음 확인");
  return [...missing];
}
