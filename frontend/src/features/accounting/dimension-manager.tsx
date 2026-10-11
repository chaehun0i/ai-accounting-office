"use client";
import { loadDimensionGroups } from "./dimension-queries";

import { useEffect, useState, type FormEvent } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { dimensionTypes, type DimensionGroup, type DimensionValue } from "./dimension-model";

export function DimensionManager({ company }: { company: Company }) {
  const [groups, setGroups] = useState<DimensionGroup[]>([]);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false);
  const [error, setError] = useState(""), [saved, setSaved] = useState("");
  const [revision, setRevision] = useState(0);
  const canRead = company.permissions.includes("dimension.read"), canManage = company.permissions.includes("dimension.manage");
  useEffect(() => {
    let active = true;
    if (canRead) loadDimensionGroups(company.id).then(data => { if (active) setGroups(data); }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company.id, canRead, revision]);
  async function mutate(path: string, body: object, method = "POST") {
    setBusy(true); setError(""); setSaved("");
    try {
      await authenticatedRequest(path, { method, headers: { "X-Company-ID": company.id }, body: JSON.stringify(body) });
      setRevision(r => r + 1);
      setSaved("저장했습니다. 전표 작성에서 사용할 수 있습니다.");
    } catch (e) { setError(e instanceof Error ? e.message : "저장하지 못했습니다. 최신 내용을 확인해 주세요."); }
    finally { setBusy(false); }
  }
  function create(event: FormEvent<HTMLFormElement>, group?: DimensionGroup) {
    event.preventDefault(); const f = new FormData(event.currentTarget);
    if (group) void mutate(`/accounting/dimensions/${group.id}/values`, { value_code: f.get("code"), name: f.get("name"), parent_value_id: f.get("parent") || null, effective_from: f.get("from") || null, effective_to: f.get("to") || null });
    else void mutate("/accounting/dimensions", { dimension_code: f.get("code"), name: f.get("name"), dimension_type: f.get("type"), required_policy: "OPTIONAL" });
  }
  function toggle(group: DimensionGroup, value?: DimensionValue) {
    if (value) void mutate(`/accounting/dimensions/${group.id}/values/${value.id}`, { value_code: value.value_code, name: value.name, parent_value_id: value.parent_value_id, effective_from: value.effective_from, effective_to: value.effective_to, status: value.status === "ACTIVE" ? "INACTIVE" : "ACTIVE", expected_version: value.version }, "PATCH");
    else void mutate(`/accounting/dimensions/${group.id}`, { name: group.name, status: group.status === "ACTIVE" ? "INACTIVE" : "ACTIVE", required_policy: group.required_policy, expected_version: group.version }, "PATCH");
  }
  if (!canRead) return <p role="status">관리차원 조회 권한이 없습니다. 회사 관리자에게 문의해 주세요.</p>;
  return <section className="panel"><h2>관리차원</h2><p>계정과목을 늘리지 않고 사업장·부서·프로젝트별로 장부를 나누어 봅니다. 기존 전표의 금액은 바뀌지 않습니다.</p>
    {loading && <p role="status">관리차원을 불러오는 중입니다…</p>}{error && <p role="alert">{error}</p>}{saved && <p role="status">{saved}</p>}
    {canManage && <form onSubmit={e => create(e)}><h3>분석축 추가</h3><label>관리차원 코드<input name="code" pattern="[A-Z0-9][A-Z0-9_-]{0,39}" required maxLength={40} /></label><label>관리차원 이름<input name="name" required maxLength={200} /></label><label>분석 유형<select name="type">{Object.entries(dimensionTypes).map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label><button disabled={busy}>{busy ? "저장 중…" : "관리차원 추가"}</button></form>}
    {!loading && groups.length === 0 && <p>등록된 관리차원이 없습니다. 필요한 분석축부터 추가해 주세요.</p>}
    {groups.map(g => <article key={g.id}><h3>{g.name} · {dimensionTypes[g.dimension_type]}</h3><p>{g.dimension_code} · {g.status === "ACTIVE" ? "사용 중" : "사용 중지"} · {g.required_policy === "REQUIRED" ? "모든 분개 필수" : "선택 입력"}</p>{canManage && <button disabled={busy} onClick={() => toggle(g)}>{g.status === "ACTIVE" ? "분석축 사용 중지" : "분석축 다시 사용"}</button>}
      <ul>{g.values.map(v => <li key={v.id}>{v.value_code} {v.name} · {v.status === "ACTIVE" ? "사용 중" : "사용 중지"} · {v.effective_from || "시작 제한 없음"} ~ {v.effective_to || "종료 제한 없음"}{canManage && <button disabled={busy} onClick={() => toggle(g, v)}>{v.status === "ACTIVE" ? "항목 사용 중지" : "항목 다시 사용"}</button>}</li>)}</ul>
      {canManage && <form onSubmit={e => create(e, g)}><h4>{g.name} 항목 추가</h4><label>항목 코드<input name="code" required pattern="[A-Z0-9][A-Z0-9_-]{0,39}" maxLength={40} /></label><label>항목 이름<input name="name" required maxLength={200} /></label><label>상위 항목<select name="parent"><option value="">없음</option>{g.values.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label><label>적용 시작일<input name="from" type="date" /></label><label>적용 종료일<input name="to" type="date" /></label><button disabled={busy}>항목 추가</button></form>}
    </article>)}
  </section>;
}
