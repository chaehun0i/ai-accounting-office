export type Cell = { field_code: string; row_key: string; value: string | boolean; source_type: string; status: string; version: number };
export type Field = { field_code: string; section_code: string; label: string; data_type: string; input_mode: string; required_rule_code: string; enum_source_code: string | null; display_order: number; active: boolean };
export type Workspace = {
  id: string; company_id: string; version: number; status: string; cells: Cell[]; fields: Field[];
  sections: { code: string; label: string; complete: number; total: number; status: string }[];
  enums: Record<string, string[]>; row_keys: Record<string, string[]>;
};
export type Issue = { field_code: string | null; row_key: string; validation_code: string; message: string };
export type Preview = { import_id: string; session_version: number; digest: string; expires_at: string;
  items: { incoming: Cell; current: Cell | null; classification: string }[]; errors: Issue[]; counts: Record<string, number> };
export type Receipt = { id: string; new_count: number; changed_count: number; unchanged_count: number; conflict_count: number; error_count: number };

export function cellKey(field: string, row: string) { return `${field}::${row}`; }
export function conflictKey(cell: Cell) { return `${cell.field_code}:${cell.row_key}`; }
export function isEditable(field: Field) { return field.active && field.input_mode !== "DERIVED_READONLY"; }
export function isVisible(field: Field, taxpayerType: string | boolean) { return field.active && (field.required_rule_code !== "CORPORATION" || taxpayerType === "CORPORATION"); }
export function mergeKey(keys: string[], values: Record<string, string | boolean>): string {
  return keys.map(key => String(values[key] ?? "")).join("|");
}
export const stateLabels: Record<string, string> = {
  COMPLETE: "완료", IN_PROGRESS: "입력 중", EMPTY: "미입력", WARNING: "확인 필요",
  REVIEW_REQUIRED: "검토 필요", READY_TO_COMPLETE: "완료 준비됨", COMPLETED: "준비 완료",
  STALE: "다시 계산 필요", VALID: "확인됨", DRAFT: "초안", INVALID: "입력 확인 필요",
};
export const sourceLabels: Record<string, string> = { MANUAL: "직접 입력", EXCEL_IMPORT: "Excel 입력", SYSTEM_DEFAULT: "기본값", DERIVED: "자동 계산" };
