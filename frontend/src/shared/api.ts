export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function request<T>(path: string, init: RequestInit = {}, access?: string | null): Promise<T> {
  try {
    const headers = new Headers(init.headers);
    // 파일 업로드의 multipart 경계는 브라우저가 생성합니다.
    if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
    if (init.method && init.method !== "GET") headers.set("X-CSRF-Protection", "1");
    if (access) headers.set("Authorization", `Bearer ${access}`);
    const response = await fetch(`/api${path}`, { ...init, headers, credentials: "same-origin", cache: "no-store" });
    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw new ApiError(response.status, error?.message ?? "요청을 처리하지 못했습니다. 다시 시도해 주세요.");
    }
    return await response.json() as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, "서비스에 연결하지 못했습니다. 연결 상태를 확인한 후 다시 시도해 주세요.");
  }
}
