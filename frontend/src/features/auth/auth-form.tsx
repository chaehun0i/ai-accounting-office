"use client";

import { useState, type FormEvent } from "react";
import { useAuth } from "./auth-provider";

export function AuthForm() {
  const auth = useAuth();
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    try { await auth.login(email, password, register); setPassword(""); }
    catch (error) { setError(error instanceof Error ? error.message : "로그인 정보를 확인해 주세요."); }
    finally { setBusy(false); }
  }
  return <section className="panel" aria-labelledby="auth-title">
    <p className="eyebrow">나의 회계 사무실</p>
    <h2 id="auth-title">{register ? "계정 만들기" : "다시 만나 반갑습니다"}</h2>
    <p className="muted">로그인하고 함께 관리할 회사를 선택하세요.</p>
    {auth.error && <div role="alert"><p>{auth.error}</p><button onClick={auth.retry}>다시 연결</button></div>}
    <form onSubmit={submit}>
      <label htmlFor="email">이메일</label>
      <input id="email" type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required maxLength={320} disabled={busy} />
      <label htmlFor="password">비밀번호</label>
      <input id="password" type="password" autoComplete={register ? "new-password" : "current-password"} value={password} onChange={e => setPassword(e.target.value)} minLength={register ? 12 : 1} maxLength={128} required disabled={busy} aria-describedby={register ? "password-help" : undefined} />
      {register && <small id="password-help">12자 이상 128자 이하로 입력해 주세요. 긴 문장도 사용할 수 있습니다.</small>}
      {error && <p role="alert" className="error">{error}</p>}
      <button className="primary" disabled={busy}>{busy ? "확인 중…" : register ? "계정 만들기" : "로그인"}</button>
    </form>
    <button className="text-button" disabled={busy} onClick={() => { setRegister(!register); setError(""); setPassword(""); }}>{register ? "이미 계정이 있어요" : "처음 방문하셨나요? 계정 만들기"}</button>
  </section>;
}
