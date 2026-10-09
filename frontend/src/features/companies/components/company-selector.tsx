"use client";

import { useState } from "react";
import { useCompany } from "../company-provider";
import { filterCompanies } from "../selection-state";

export function CompanySelector() {
  const company = useCompany();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("");
  const filtered = filterCompanies(company.companies, search);
  return <section className="panel" aria-labelledby="company-title">
    <p className="eyebrow">회사 선택</p>
    <h2 id="company-title">어느 회사에서 시작할까요?</h2>
    <p className="muted">접근할 수 있는 회사만 표시됩니다. 회사마다 이용 가능한 기능이 다를 수 있어요.</p>
    <label htmlFor="company-search">회사명 검색</label>
    <input id="company-search" type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="회사 이름을 입력하세요" />
    <label htmlFor="company-list">회사</label>
    <select id="company-list" value={selected} onChange={event => setSelected(event.target.value)} disabled={company.loading}>
      <option value="">회사를 선택하세요</option>
      {filtered.map(item => <option key={item.id} value={item.id}>{item.company_name}</option>)}
    </select>
    {!filtered.length && company.companies.length > 0 && <p className="muted">검색 결과가 없습니다. 다른 이름으로 검색해 주세요.</p>}
    <button className="primary" disabled={!selected || company.loading || !filtered.some(item => item.id === selected)} onClick={() => void company.select(selected)}>선택 완료</button>
    {company.loading && <p role="status">회사 접근 권한을 확인하고 있습니다…</p>}
  </section>;
}
