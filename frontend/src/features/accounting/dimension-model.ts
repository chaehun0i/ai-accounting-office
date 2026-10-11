export const dimensionTypes: Record<string, string> = {
  BUSINESS_UNIT: "사업장", DEPARTMENT: "부서", PROJECT: "프로젝트", COST_CENTER: "원가센터",
};
export type Dimension = {
  id: string; dimension_code: string; name: string; dimension_type: string;
  status: string; required_policy: string; version: number;
};
export type DimensionValue = {
  id: string; dimension_id: string; value_code: string; name: string; status: string;
  parent_value_id: string | null; effective_from: string | null; effective_to: string | null; version: number;
};
export type DimensionGroup = Dimension & { values: DimensionValue[] };

// 같은 분석 유형은 분개당 하나만 선택하며 최종 유효성은 서버에서 확인합니다.
export function selectDimensionValue(groups: DimensionGroup[], selected: string[], group: DimensionGroup, value: string): string[] {
  const sameType = new Set(groups.filter(g => g.dimension_type === group.dimension_type).flatMap(g => g.values.map(v => v.id)));
  return [...selected.filter(id => !sameType.has(id)), ...(value ? [value] : [])];
}
