"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "@/shared/api";
import { askBookkeeper, getQueryRun, listPeriods } from "./api";
import { questionDraft, selectContextPeriod, type AskContext } from "./context";
import { isFinal, type Period, type QueryRun } from "./model";

export function useAccountingQuery(companyId: string, context: AskContext | null) {
  const [periods, setPeriods] = useState<Period[]>([]);
  const [periodId, setPeriodId] = useState("");
  const [question, setQuestion] = useState("");
  const [run, setRun] = useState<QueryRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [contextNotice, setContextNotice] = useState("");
  const [showSource, setShowSource] = useState(false);
  const [periodRevision, setPeriodRevision] = useState(0);
  const retry = useRef<{ signature: string; key: string } | null>(null);
  const requestVersion = useRef(0);
  const active = useRef(true);

  useEffect(() => {
    let cancelled = false;
    active.current = true;
    setLoading(true);
    setError("");
    setContextNotice("");
    setPeriods([]);
    setPeriodId("");
    setQuestion(questionDraft(context));
    setRun(null);
    setShowSource(false);
    retry.current = null;
    listPeriods(companyId).then(values => {
      if (cancelled) return;
      const selection = selectContextPeriod(values, context);
      setPeriods(values);
      setPeriodId(selection.periodId);
      setContextNotice(selection.notice);
    }).catch(reason => { if (!cancelled) setError(errorMessage(reason)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; active.current = false; requestVersion.current += 1; };
  }, [companyId, context?.kind, context?.periodId,
    context?.kind === "financial_statement" ? context.statementType : null,
    context?.kind === "financial_statement" ? context.lineCode : null,
    periodRevision]);

  function clearResult() {
    requestVersion.current += 1;
    retry.current = null;
    setRun(null);
    setShowSource(false);
    setError("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = question.trim();
    if (busy || !periodId || !text) return;
    const version = ++requestVersion.current;
    const signature = JSON.stringify([companyId, periodId, text]);
    if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
    const key = retry.current.key;
    setBusy(true);
    setError("");
    setRun(null);
    try {
      let result = await askBookkeeper(companyId, periodId, text, key);
      for (let attempt = 0; !isFinal(result.status) && attempt < 15; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        if (!active.current || requestVersion.current !== version) return;
        result = await getQueryRun(companyId, result.id);
      }
      if (!active.current || requestVersion.current !== version) return;
      setRun(result);
      if (isFinal(result.status)) retry.current = null;
    } catch (reason) {
      if (active.current && requestVersion.current === version) setError(errorMessage(reason));
    } finally {
      if (active.current && requestVersion.current === version) setBusy(false);
    }
  }

  return {
    periods, periodId, question, run, loading, busy, error, contextNotice, showSource,
    setPeriodId, setQuestion, setShowSource, clearResult, submit,
    reloadPeriods: () => setPeriodRevision(value => value + 1),
  };
}

function errorMessage(reason: unknown) {
  if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) return "이 회사의 회계 자료를 조회할 권한이 없습니다.";
  if (reason instanceof ApiError && reason.status === 404) return "선택한 회계기간 또는 자료를 찾을 수 없습니다.";
  return reason instanceof ApiError ? reason.message : "질의를 처리하지 못했습니다. 다시 시도해 주세요.";
}
