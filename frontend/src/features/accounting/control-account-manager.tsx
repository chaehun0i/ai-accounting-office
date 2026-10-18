"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/features/auth/auth-provider";
import { authenticatedRequest } from "@/features/auth/session";
import { ApiError } from "@/shared/api";
import { controlApi, roleNames, roles, type ChangeEvent, type ChangeRequest, type Impact, type Mapping, type Role } from "./control-account-api";

type Account = { id: string; account_code: string; account_name: string; account_type: string; status: string; posting_allowed: boolean; version: number };
const statusNames: Record<string, string> = { REQUESTED: "승인 대기", APPROVED: "승인됨", REJECTED: "거절됨", EXECUTED: "적용 완료" };
const eventNames: Record<string, string> = { REQUESTED: "신청", APPROVED: "승인", REJECTED: "거절", EXECUTED: "적용" };
const referenceNames: Record<string, string> = { POSTED_JOURNAL: "확정 전표", AR_REFERENCE: "채권 참조", AP_REFERENCE: "채무 참조", BANK_REFERENCE: "은행 계정 참조", CARD_REFERENCE: "카드 계정 참조" };
function factDescription(fact: Impact["facts"][number]): string {
  if (fact.code === "MAPPING_VERSION") return `현재 역할 버전 ${fact.count}`;
  if (fact.code === "TARGET_VERSION") return `대상 계정 버전 ${fact.count}`;
  if (fact.code === "TARGET_MISSING") return fact.count ? "대상 계정을 찾을 수 없음" : "대상 계정 확인됨";
  if (fact.code === "TARGET_INACTIVE") return fact.count ? "대상 계정이 비활성" : "대상 계정 활성";
  if (fact.code === "TARGET_NOT_POSTABLE") return fact.count ? "대상 계정에 전기할 수 없음" : "대상 계정 전기 가능";
  if (fact.code === "TARGET_TYPE_MISMATCH") return fact.count ? "대상 계정 유형이 역할과 다름" : "대상 계정 유형 일치";
  if (fact.code === "OTHER_ROLE_COLLISION") return fact.count ? `다른 역할과 ${fact.count}건 충돌` : "다른 역할과 충돌 없음";
  return `${fact.subject === "CURRENT" ? "현재" : "대상"} 계정 ${referenceNames[fact.code] ?? fact.code} ${fact.count}건`;
}
export function ControlAccountManager({ companyId, canManage }: { companyId: string; canManage: boolean }) {
  const { user } = useAuth();
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [requests, setRequests] = useState<ChangeRequest[]>([]);
  const [impacts, setImpacts] = useState<Record<string, Impact>>({});
  const [events, setEvents] = useState<Record<string, ChangeEvent[]>>({});
  const [preview, setPreview] = useState<{ role: Role; target: string; mappingVersion: number; accountVersion: number; impact: Impact } | null>(null);
  const [role, setRole] = useState<Role>("AR");
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const executeKeys = useRef(new Map<string, string>());
  const accountName = (id: string | null) => id ? accounts.find(account => account.id === id)?.account_name ?? id : "미지정";
  const load = useCallback(async () => {
    const [mappingRows, accountRows, requestRows] = await Promise.all([
      controlApi.mappings(companyId),
      authenticatedRequest<Account[]>("/accounts", { headers: { "X-Company-ID": companyId } }),
      canManage ? controlApi.requests(companyId) : Promise.resolve([]),
    ]);
    setMappings(mappingRows); setAccounts(accountRows); setRequests(requestRows);
  }, [companyId, canManage]);
  useEffect(() => {
    let active = true;
    setMappings([]); setAccounts([]); setRequests([]); setImpacts({}); setEvents({});
    executeKeys.current.clear();
    setRole("AR"); setTarget(""); setPreview(null); setReason(""); setError(""); setNotice(""); setLoading(true);
    void load().catch(failure => { if (active) setError(failure instanceof Error ? failure.message : "관리 정보를 불러오지 못했습니다."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [load]);
  async function create() {
    const mapping = mappings.find(item => item.role === role);
    const account = accounts.find(item => item.id === target);
    if (!mapping || !account || !preview || preview.role !== role || preview.target !== target || preview.mappingVersion !== mapping.version || preview.accountVersion !== account.version || preview.impact.blocking) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const created = await controlApi.create(companyId, role, account.id, mapping.version, account.version);
      setTarget(""); setPreview(null); await load();
      const impact = await controlApi.impact(companyId, created.id);
      setImpacts(current => ({ ...current, [created.id]: impact }));
      setNotice("변경 요청이 등록됐습니다. 다른 권한자가 영향도를 확인하고 승인해야 합니다.");
    } catch (failure) { await handleFailure(failure); }
    finally { setBusy(false); }
  }
  async function inspectTarget() {
    const mapping = mappings.find(item => item.role === role);
    const account = accounts.find(item => item.id === target);
    if (!mapping || !account) return;
    setBusy(true); setError(""); setPreview(null);
    try {
      const impact = await controlApi.preview(companyId, role, account.id, mapping.version, account.version);
      setPreview({ role, target: account.id, mappingVersion: mapping.version, accountVersion: account.version, impact });
    } catch (failure) { await handleFailure(failure); }
    finally { setBusy(false); }
  }
  async function handleFailure(failure: unknown) {
    if (failure instanceof ApiError && failure.status === 409) {
      setPreview(null);
      await load().catch(() => undefined);
      setError("계정이나 역할 상태가 변경됐습니다. 최신 상태를 확인하고 다시 신청해 주세요.");
    } else setError(failure instanceof Error ? failure.message : "요청을 처리하지 못했습니다.");
  }
  async function inspect(request: ChangeRequest) {
    setBusy(true); setError("");
    try {
      const [impact, history] = await Promise.all([controlApi.impact(companyId, request.id), controlApi.events(companyId, request.id)]);
      setImpacts(current => ({ ...current, [request.id]: impact }));
      setEvents(current => ({ ...current, [request.id]: history }));
    } catch (failure) { await handleFailure(failure); }
    finally { setBusy(false); }
  }
  async function command(request: ChangeRequest, action: "approve" | "reject" | "execute") {
    setBusy(true); setError(""); setNotice("");
    try {
      const keyId = `${request.id}:${request.version}`;
      let key = executeKeys.current.get(keyId);
      if (action === "execute" && !key) {
        key = crypto.randomUUID(); executeKeys.current.set(keyId, key);
      }
      await controlApi.command(companyId, request, action, reason.trim(), key);
      await load(); setReason("");
      const [impact, history] = await Promise.all([controlApi.impact(companyId, request.id), controlApi.events(companyId, request.id)]);
      setImpacts(current => ({ ...current, [request.id]: impact }));
      setEvents(current => ({ ...current, [request.id]: history }));
      setNotice({ approve: "변경 요청을 승인했습니다.", reject: "변경 요청을 거절했습니다.", execute: "역할 매핑을 적용했습니다." }[action]);
    } catch (failure) { await handleFailure(failure); }
    finally { setBusy(false); }
  }
  const requiredType = ["AR", "TAX_INPUT", "BANK_CASH", "CARD_CLEARING"].includes(role) ? "ASSET" : "LIABILITY";
  const targetOptions = accounts.filter(account => account.status === "ACTIVE" && account.posting_allowed && account.account_type === requiredType);
  return <section aria-label="Control Account 역할 관리">
    <h3>Control Account 역할 관리</h3>
    <p className="muted">역할은 계정명으로 추정하지 않습니다. 변경 신청과 다른 관리자의 승인 후 장부에 적용됩니다.</p>
    {loading && <p role="status">역할 매핑을 불러오는 중입니다.</p>}
    {error && <p role="alert">{error} <button type="button" disabled={busy} onClick={() => void load()}>다시 불러오기</button></p>}
    {notice && <p role="status">{notice}</p>}
    {!loading && <div className="table-scroll"><table><thead><tr><th>역할</th><th>현재 계정</th><th>버전</th></tr></thead><tbody>{roles.map(code => {
      const mapping = mappings.find(item => item.role === code);
      return <tr key={code}><td>{roleNames[code]}</td><td>{accountName(mapping?.account_id ?? null)}</td><td>{mapping?.version ?? "—"}</td></tr>;
    })}</tbody></table></div>}
    {canManage && !loading && <div><h4>변경 신청</h4><label>역할<select value={role} onChange={event => { setRole(event.target.value as Role); setTarget(""); setPreview(null); }}>{roles.map(code => <option key={code} value={code}>{roleNames[code]}</option>)}</select></label>
      <label>대상 계정<select value={target} onChange={event => { setTarget(event.target.value); setPreview(null); }}><option value="">계정 선택</option>{targetOptions.map(account => <option key={account.id} value={account.id}>{account.account_code} · {account.account_name}</option>)}</select></label>
      <button type="button" disabled={busy || !target || target === mappings.find(item => item.role === role)?.account_id} onClick={() => void inspectTarget()}>영향 검사</button>
      {preview && <div><p>영향 검사: {preview.impact.blocking ? "차단 항목 있음" : "신청 가능"}</p><ul>{preview.impact.facts.map((fact, index) => <li key={`${fact.code}-${fact.subject}-${index}`}>{factDescription(fact)}{fact.blocking ? " · 차단" : ""}</li>)}</ul><button type="button" disabled={busy || preview.impact.blocking} onClick={() => void create()}>검사 결과 확인 후 변경 신청</button></div>}</div>}
    <h4>변경 요청</h4>{requests.length === 0 && !loading && <p>변경 요청이 없습니다.</p>}
    {requests.map(request => <article key={request.id}><h5>{roleNames[request.role]} · {accountName(request.current_account_id)} → {accountName(request.target_account_id)}</h5>
      <p>상태: {statusNames[request.status] ?? request.status} · 신청: {new Date(request.created_at).toLocaleString("ko-KR")} · 영향 서명: <code>{request.impact_digest.slice(0, 12)}</code></p>
      <button type="button" disabled={busy} onClick={() => void inspect(request)}>영향과 이력 확인</button>
      {impacts[request.id] && <div><p>현재 영향 상태: {impacts[request.id].blocking ? "차단 항목 있음" : "차단 항목 없음"}</p><ul>{impacts[request.id].facts.map((fact, index) => <li key={`${fact.code}-${fact.subject}-${index}`}>{factDescription(fact)}{fact.blocking ? " · 차단" : ""}</li>)}</ul></div>}
      {events[request.id] && <div><strong>변경 이력</strong><ul>{events[request.id].map(event => <li key={event.id}>{eventNames[event.event_type] ?? event.event_type} · {new Date(event.occurred_at).toLocaleString("ko-KR")} · {accountName(event.before_account_id)} → {accountName(event.after_account_id)}</li>)}</ul></div>}
      {canManage && request.status === "REQUESTED" && request.requester_id !== user?.id && <div><label>거절 사유<input value={reason} onChange={event => setReason(event.target.value)} maxLength={500} /></label><button type="button" disabled={busy || !impacts[request.id] || impacts[request.id].blocking} onClick={() => void command(request, "approve")}>승인</button><button type="button" disabled={busy || !reason.trim()} onClick={() => void command(request, "reject")}>거절</button></div>}
      {canManage && request.status === "APPROVED" && request.requester_id !== user?.id && <button type="button" disabled={busy || !impacts[request.id] || impacts[request.id].blocking} onClick={() => void command(request, "execute")}>승인된 변경 적용</button>}
    </article>)}
  </section>;
}
