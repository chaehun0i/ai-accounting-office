"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import { ApiError } from "@/shared/api";
import {
  matchesClosedPeriod,
  type Period,
  type ReportArtifact,
  type ReportDefinition,
  type ReportPreset,
  type ReportRun,
  type ResolvedReportPeriod,
} from "./model";

const presets: { code: ReportPreset; label: string }[] = [
  { code: "CUSTOM", label: "기간 직접 지정" },
  { code: "TODAY", label: "오늘" },
  { code: "THIS_WEEK", label: "이번 주" },
  { code: "THIS_MONTH", label: "이번 달" },
  { code: "THIS_YEAR", label: "이번 회계연도" },
];
const statusLabels: Record<ReportRun["status"], string> = {
  REQUESTED: "생성 요청됨", GENERATING: "생성 중", COMPLETED: "완료", FAILED: "생성 실패",
};
const errorLabels: Record<string, string> = {
  REPORT_SOURCE_STALE: "보고서 원천이 변경됐습니다. 재무제표를 다시 확인해 주세요.",
  STORAGE_UNAVAILABLE: "파일 저장소를 사용할 수 없습니다. 잠시 후 재시도해 주세요.",
  EXPORT_GENERATION_FAILED: "파일 생성에 실패했습니다. 다시 시도해 주세요.",
};
const failure = (error: unknown) => error instanceof ApiError ? error.message : "보고서 요청을 처리하지 못했습니다.";

export function ReportCenter({ company }: { company: Company }) {
  const [catalog, setCatalog] = useState<ReportDefinition[]>([]);
  const [periods, setPeriods] = useState<Period[]>([]);
  const [history, setHistory] = useState<ReportRun[]>([]);
  const [reportCode, setReportCode] = useState("");
  const [periodId, setPeriodId] = useState("");
  const [preset, setPreset] = useState<ReportPreset>("CUSTOM");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [asOf, setAsOf] = useState("");
  const [format, setFormat] = useState<"PDF" | "XLSX" | "CSV">("PDF");
  const [resolved, setResolved] = useState<ResolvedReportPeriod | null>(null);
  const [selectedRun, setSelectedRun] = useState<ReportRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [periodError, setPeriodError] = useState("");
  const [notice, setNotice] = useState("");
  const requestKey = useRef<{ fingerprint: string; key: string } | null>(null);
  const scope = { "X-Company-ID": company.id };
  const definition = catalog.find(row => row.code === reportCode);
  const selectedPeriod = periods.find(row => row.id === periodId);
  const periodMatches = matchesClosedPeriod(selectedPeriod, resolved);
  const canDownload = company.permissions.includes("report.download_history");

  async function refreshHistory() {
    const rows = await authenticatedRequest<ReportRun[]>("/reports/generations", { headers: scope });
    setHistory(rows);
    setSelectedRun(previous => rows.find(row => row.id === previous?.id) ?? previous);
  }

  useEffect(() => {
    let active = true;
    Promise.all([
      authenticatedRequest<ReportDefinition[]>("/reports/catalog", { headers: { "X-Company-ID": company.id } }),
      authenticatedRequest<Period[]>("/closing/periods", { headers: { "X-Company-ID": company.id } }),
      company.permissions.includes("report.download_history")
        ? authenticatedRequest<ReportRun[]>("/reports/generations", { headers: { "X-Company-ID": company.id } })
        : Promise.resolve([]),
    ]).then(([reports, available, runs]) => {
      if (!active) return;
      const closed = available.filter(row => row.status === "CLOSED");
      setCatalog(reports); setPeriods(closed); setHistory(runs);
      setReportCode(reports[0]?.code ?? "");
      setPeriodId(closed[0]?.id ?? "");
      setDateFrom(closed[0]?.start_date ?? "");
      setDateTo(closed[0]?.end_date ?? "");
      setAsOf(closed[0]?.end_date ?? "");
    }).catch(reason => { if (active) setError(failure(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [company.id, company.permissions]);

  useEffect(() => {
    let active = true;
    setResolved(null); setPeriodError("");
    if (!definition || !periodId) return () => { active = false; };
    const query = new URLSearchParams({ period_preset: preset, period_mode: definition.period_mode });
    if (preset === "CUSTOM") {
      if (definition.period_mode === "AS_OF") query.set("as_of", asOf);
      else { query.set("date_from", dateFrom); query.set("date_to", dateTo); }
    }
    setResolving(true);
    authenticatedRequest<ResolvedReportPeriod>(`/report-periods/resolve?${query}`, { headers: { "X-Company-ID": company.id } })
      .then(value => { if (active) setResolved(value); })
      .catch(reason => { if (active) setPeriodError(failure(reason)); })
      .finally(() => { if (active) setResolving(false); });
    return () => { active = false; };
  }, [company.id, definition?.code, definition?.period_mode, periodId, preset, dateFrom, dateTo, asOf]);

  useEffect(() => {
    if (!canDownload || !history.some(row => row.status === "REQUESTED" || row.status === "GENERATING")) return;
    const timer = window.setInterval(() => { void refreshHistory().catch(reason => setError(failure(reason))); }, 2500);
    return () => window.clearInterval(timer);
  }, [company.id, canDownload, history]);

  function selectPeriod(nextId: string) {
    const next = periods.find(row => row.id === nextId);
    setPeriodId(nextId); setPreset("CUSTOM"); setResolved(null);
    setDateFrom(next?.start_date ?? ""); setDateTo(next?.end_date ?? ""); setAsOf(next?.end_date ?? "");
  }

  async function generate() {
    if (!definition || !selectedPeriod || !resolved || !periodMatches) return;
    const payload = {
      report_code: definition.code, format, period_id: selectedPeriod.id, period_preset: preset,
      ...(preset === "CUSTOM" ? definition.period_mode === "AS_OF"
        ? { as_of: asOf } : { date_from: dateFrom, date_to: dateTo } : {}),
    };
    const fingerprint = JSON.stringify(payload);
    if (requestKey.current?.fingerprint !== fingerprint) requestKey.current = { fingerprint, key: crypto.randomUUID() };
    setBusy(true); setError(""); setNotice("");
    try {
      const run = await authenticatedRequest<ReportRun>("/reports/generations", {
        method: "POST", headers: { ...scope, "Idempotency-Key": requestKey.current.key },
        body: JSON.stringify(payload),
      });
      requestKey.current = null;
      setSelectedRun(run);
      if (canDownload) await refreshHistory();
      setNotice(run.status === "COMPLETED" ? "보고서가 생성됐습니다. 이력에서 내려받을 수 있습니다." : statusLabels[run.status]);
    } catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }

  async function retry(run: ReportRun) {
    setBusy(true); setError(""); setNotice("");
    try {
      const next = await authenticatedRequest<ReportRun>(`/reports/generations/${run.id}/retry`, {
        method: "POST", headers: { ...scope, "Idempotency-Key": crypto.randomUUID() },
      });
      const completed = await authenticatedRequest<ReportRun>(`/reports/generations/${next.id}/execute`, { method: "POST", headers: scope });
      setSelectedRun(completed); await refreshHistory();
      setNotice(completed.status === "COMPLETED" ? "보고서를 다시 생성했습니다." : "재시도 결과를 확인해 주세요.");
    } catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }

  async function download(run: ReportRun) {
    setBusy(true); setError("");
    try {
      const artifact = await authenticatedRequest<ReportArtifact>(`/reports/generations/${run.id}/artifact`, { headers: scope });
      const blob = await authenticatedRequest<Blob>(`/reports/generations/${run.id}/download`, { headers: scope }, response => response.blob());
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = artifact.file_name;
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }

  if (loading) return <p role="status" className="loading-message">보고서 종류와 마감된 기간을 불러오고 있습니다…</p>;
  return <div className="workspace-stack report-center">
    <section className="panel">
      <h2>보고서 생성</h2>
      <p>마감된 기간의 재무제표 스냅샷을 파일로 표현합니다. 보고서 생성은 장부를 변경하지 않습니다.</p>
      {definition?.code === "CASH_FLOW" && <p>현금흐름표는 대사 완료된 스냅샷에서만 생성합니다. <Link href="/financial-statements">현금흐름표 원천·대사 확인</Link>을 먼저 마쳐 주세요. 내려받는 파일은 내부 검증용입니다.</p>}
      {catalog.length === 0 ? <p>현재 사용할 수 있는 보고서가 없습니다.</p> : <div className="report-center-form">
        <label>보고서 종류<select aria-label="보고서 종류" value={reportCode} onChange={event => { setReportCode(event.target.value); setResolved(null); }}>
          {catalog.map(row => <option key={row.code} value={row.code}>{row.label}</option>)}
        </select></label>
        {periods.length === 0 ? <p>마감된 회계기간이 없습니다. <Link href="/closing">월마감 확인</Link> 후 재무제표 스냅샷을 준비해 주세요.</p> : <>
          <label>마감된 회계기간<select aria-label="보고서 회계기간" value={periodId} onChange={event => selectPeriod(event.target.value)}>
            {periods.map(row => <option key={row.id} value={row.id}>{row.start_date} ~ {row.end_date} · 마감 v{row.close_version}</option>)}
          </select></label>
          <label>기간 선택<select aria-label="보고기간 프리셋" value={preset} onChange={event => { setPreset(event.target.value as ReportPreset); setResolved(null); }}>
            {presets.map(row => <option key={row.code} value={row.code}>{row.label}</option>)}
          </select></label>
          {preset === "CUSTOM" && (definition?.period_mode === "AS_OF"
            ? <label>기준일<input aria-label="보고서 기준일" type="date" value={asOf} onChange={event => setAsOf(event.target.value)} /></label>
            : <><label>시작일<input aria-label="보고서 시작일" type="date" value={dateFrom} onChange={event => setDateFrom(event.target.value)} /></label>
              <label>종료일<input aria-label="보고서 종료일" type="date" value={dateTo} onChange={event => setDateTo(event.target.value)} /></label></>)}
          <label>출력 형식<select aria-label="출력 형식" value={format} onChange={event => setFormat(event.target.value as typeof format)}>
            {(definition?.formats ?? []).map(value => <option key={value} value={value}>{value}</option>)}
          </select></label>
          <div className="report-period-result" aria-live="polite">
            {resolving ? "회사 기간 정책을 적용하고 있습니다…" : resolved ? <>
              <strong>서버가 해석한 실제 기간</strong> {resolved.as_of ?? `${resolved.date_from} ~ ${resolved.date_to}`}
              <small> · {resolved.period_mode} · {resolved.timezone}{resolved.partial ? " · 일부 기간" : ""}</small>
            </> : periodError || "기간을 선택해 주세요."}
          </div>
          {resolved && !periodMatches && <p role="alert">해석된 기간과 선택한 CLOSED 회계기간이 일치하지 않습니다. 해당 마감 기간을 선택하거나 날짜를 조정해 주세요.</p>}
          {definition?.can_generate ? <button className="button-accent" disabled={busy || resolving || !periodMatches} onClick={() => void generate()}>
            {busy ? "처리 중…" : "보고서 생성"}
          </button> : <p>생성 권한이 없습니다. 이력 조회와 다운로드만 이용할 수 있습니다.</p>}
        </>}
      </div>}
      {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    </section>
    {selectedRun && <section className="panel" aria-label="선택한 보고서 상태"><h2>생성 상태</h2>
      <p><strong>{statusLabels[selectedRun.status]}</strong> · {catalog.find(row => row.code === selectedRun.report_code)?.label ?? selectedRun.report_code} · {selectedRun.format}</p>
      <p>원천 스냅샷 {selectedRun.statement_set_id} · 마감 버전 {selectedRun.close_version} · 원천 digest {selectedRun.source_digest.slice(0, 12)}…</p>
      {selectedRun.error_code && <p role="alert">{errorLabels[selectedRun.error_code] ?? selectedRun.error_code}</p>}
      {selectedRun.status === "COMPLETED" && canDownload && <button disabled={busy} onClick={() => void download(selectedRun)}>파일 다운로드</button>}
    </section>}
    <section className="panel"><div className="section-toolbar"><h2>생성 이력</h2>{canDownload && <button onClick={() => void refreshHistory().catch(reason => setError(failure(reason)))}>새로고침</button>}</div>
      {!canDownload ? <p>이력 조회 권한이 없습니다.</p> : history.length === 0 ? <p>생성된 보고서가 없습니다.</p> : <div className="table-scroll"><table><thead><tr><th>보고서</th><th>기간</th><th>형식</th><th>상태</th><th>생성자·요청 시각</th><th>원천</th><th>작업</th></tr></thead><tbody>
        {history.map(run => <tr key={run.id}><th scope="row">{catalog.find(row => row.code === run.report_code)?.label ?? run.report_code}</th>
          <td>{run.as_of ?? `${run.date_from} ~ ${run.date_to}`}</td><td>{run.format}</td>
          <td>{statusLabels[run.status]}{run.error_code && <small>{errorLabels[run.error_code] ?? run.error_code}</small>}</td>
          <td>{run.requested_by}<small>{new Date(run.requested_at).toLocaleString("ko-KR")}</small></td>
          <td>마감 v{run.close_version}<small>스냅샷 {run.statement_set_id.slice(0, 8)}… · {run.source_digest.slice(0, 8)}…</small></td>
          <td><div className="workspace-buttons"><button onClick={() => setSelectedRun(run)}>상태</button>
            {run.status === "COMPLETED" && <button disabled={busy} onClick={() => void download(run)}>다운로드</button>}
            {run.status === "FAILED" && catalog.find(row => row.code === run.report_code)?.can_generate && <button disabled={busy} onClick={() => void retry(run)}>재시도</button>}
          </div></td></tr>)}
      </tbody></table></div>}
    </section>
  </div>;
}
