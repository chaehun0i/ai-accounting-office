import assert from "node:assert/strict";
import test from "node:test";
import { dimensionTypes, selectDimensionValue, type DimensionGroup } from "../src/features/accounting/dimension-model.ts";

test("관리차원은 사용자에게 네 가지 분석 유형으로 안내합니다", () => {
  assert.deepEqual(Object.values(dimensionTypes), ["사업장", "부서", "프로젝트", "원가센터"]);
});

test("같은 유형의 선택은 교체하고 다른 분석축은 보존합니다", () => {
  const groups = [
    { id: "d1", dimension_type: "DEPARTMENT", values: [{ id: "v1" }, { id: "v2" }] },
    { id: "d2", dimension_type: "PROJECT", values: [{ id: "p1" }] },
    { id: "d3", dimension_type: "DEPARTMENT", values: [{ id: "v3" }] },
  ] as DimensionGroup[];
  assert.deepEqual(selectDimensionValue(groups, ["v1", "p1"], groups[2], "v3"), ["p1", "v3"]);
  assert.deepEqual(selectDimensionValue(groups, ["v2", "p1"], groups[0], ""), ["p1"]);
});
