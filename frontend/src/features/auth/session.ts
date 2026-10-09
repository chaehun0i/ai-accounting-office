import { ApiError, request } from "@/shared/api";

export type User = { id: string; email: string; status: string };
export type AuthResponse = { user: User; access_token: string; expires_in: number };

// Access token은 현재 페이지 메모리에만 보관합니다. Refresh token은 HttpOnly cookie가 소유합니다.
let access: string | null = null;
let recovery: Promise<AuthResponse> | null = null;
let generation = 0;

export function clearSession() { generation += 1; access = null; }
export function applySession(result: AuthResponse) { generation += 1; access = result.access_token; }

export function recoverSession(): Promise<AuthResponse> {
  if (recovery) return recovery;
  const current = generation;
  const restore = () => request<AuthResponse>("/auth/refresh", { method: "POST" });
  // 여러 탭에서도 최신 cookie가 반영된 뒤 rotation하도록 순서를 맞춥니다.
  const pending = typeof navigator !== "undefined" && navigator.locks
    ? navigator.locks.request("aao-refresh", restore) : restore();
  recovery = Promise.resolve(pending).then(result => {
    if (current !== generation) throw new ApiError(401, "로그인 상태가 변경되었습니다. 다시 확인해 주세요.");
    access = result.access_token;
    return result;
  }).finally(() => { recovery = null; });
  return recovery;
}

export async function authenticatedRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!access) await recoverSession();
  try { return await request<T>(path, init, access); }
  catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
    await recoverSession();
    return request<T>(path, init, access);
  }
}
