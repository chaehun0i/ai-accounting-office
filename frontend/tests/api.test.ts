import assert from "node:assert/strict";
import test from "node:test";
import { request } from "../src/shared/api.ts";

test("파일 업로드는 브라우저의 multipart 경계를 유지하고 인증·회사 범위를 전달합니다", async (t) => {
  t.mock.method(globalThis, "fetch", async (_url: string, init: RequestInit) => {
    const headers = new Headers(init.headers);
    assert.equal(headers.get("Content-Type"), null);
    assert.equal(headers.get("Authorization"), "Bearer test-only-access");
    assert.equal(headers.get("X-CSRF-Protection"), "1");
    assert.equal(headers.get("X-Company-ID"), "test-company");
    assert.ok(init.body instanceof FormData);
    return Response.json({ status: "received" });
  });
  const form = new FormData(); form.set("source_type", "SALES");
  assert.deepEqual(await request("/imports", { method: "POST", headers: { "X-Company-ID": "test-company" }, body: form }, "test-only-access"), { status: "received" });
});
