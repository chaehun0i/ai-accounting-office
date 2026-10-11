/** 격리된 합성 DB에서 파일 확인→거래 생성→복구·재시도를 검증합니다. */
const assert = require("node:assert/strict");
const path = require("node:path");
const { createRequire } = require("node:module");
const loader = process.env.PLAYWRIGHT_MODULE_PATH ? createRequire(path.join(process.env.PLAYWRIGHT_MODULE_PATH, "package.json")) : require;
const { chromium } = loader("playwright");
async function main() {
  if (!process.argv.includes("--allow-synthetic")) throw new Error("격리 테스트 DB를 먼저 준비해 주세요.");
  const api = process.env.ACCOUNTING_API_ORIGIN || "http://127.0.0.1:8003";
  const origin = process.env.ACCOUNTING_BROWSER_ORIGIN || "http://127.0.0.1:3000";
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const context = await browser.newContext();
  const page = await context.newPage(); page.setDefaultTimeout(120000);
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    const response = await route.fetch({url: api + url.pathname.slice(4) + url.search, timeout:120000});
    await route.fulfill({response});
  });
  const password = "SyntheticAccountingPassword!2026", stamp = Date.now();
  async function post(url, data, token, company, key) {
    const response = await context.request.post(api + url, { data, headers: {
      "X-CSRF-Protection":"1", ...(token ? {Authorization:`Bearer ${token}`} : {}),
      ...(company ? {"X-Company-ID":company} : {}), ...(key ? {"Idempotency-Key":key} : {}),
    }});
    assert.ok(response.ok(), `${url}: ${response.status()}`); return response.json();
  }
  try {
    const owner = await post("/auth/register", {email:`promotion-owner-${stamp}@example.com`,password});
    const email = `promotion-writer-${stamp}@example.com`;
    const writer = await post("/auth/register", {email,password});
    const company = await post("/companies", {company_name:"거래 승격 브라우저 회사",business_number:"1234567890",taxpayer_type:"INDIVIDUAL",opening_date:"2026-01-01",address:"합성 주소"},owner.access_token);
    const invite = await post(`/companies/${company.id}/invitations`,{email,role_code:"ACCOUNTANT"},owner.access_token);
    await post(`/invitations/${invite.invite_token}/accept`,{},writer.access_token);
    const templates = await context.request.get(api+"/account-templates",{headers:{Authorization:`Bearer ${owner.access_token}`,"X-Company-ID":company.id}}).then(r=>r.json());
    await post("/accounting/initialize",{fiscal_year:2026,template_id:templates[0].id},owner.access_token,company.id);
    await context.clearCookies(); await page.goto(origin);
    await page.getByLabel("이메일",{exact:true}).fill(email); await page.getByLabel("비밀번호",{exact:true}).fill(password);
    await page.getByRole("button",{name:"로그인",exact:true}).click();
    await page.getByRole("heading",{name:"업무 홈",exact:true}).waitFor();
    await page.goto(origin+"/imports");
    await page.getByLabel("자료 종류").selectOption("SALES");
    await page.getByLabel("파일 선택").setInputFiles({name:"promotion.csv",mimeType:"text/csv",buffer:Buffer.from("source_id,date,amount,currency\ns1,2026-01-02,100.0001,KRW\ns2,2026-01-03,200,KRW\n")});
    await page.getByRole("button",{name:"파일 올리기",exact:true}).click();
    await page.getByRole("button",{name:"검증하고 미리보기",exact:true}).click();
    await page.getByRole("checkbox").check();
    const confirmation = page.waitForResponse(r=>r.url().endsWith("/confirm"));
    await page.getByRole("button",{name:"확인한 자료 접수",exact:true}).click();
    const receipt = await (await confirmation).json(); assert.equal(receipt.transaction_count,0);
    await page.getByRole("heading",{name:"파일 확인 완료",exact:true}).waitFor();
    const promoted = page.waitForResponse(r=>r.url().endsWith("/promote"));
    await page.getByRole("button",{name:"확인한 자료로 거래 생성",exact:true}).click();
    const result = await (await promoted).json(); assert.equal(result.transaction_count,2);
    await page.getByRole("heading",{name:"거래 생성 완료",exact:true}).waitFor();
    await page.reload(); await page.getByRole("heading",{name:"거래 생성 완료",exact:true}).waitFor();
    const replay = await post(`/imports/${receipt.import_id}/promote`,{expected_version:receipt.confirmed_version,receipt_id:receipt.id,source_digest:receipt.source_digest},writer.access_token,company.id,`promote:${receipt.id}`);
    assert.deepEqual(replay,result);
    await page.getByRole("link",{name:"생성된 거래 보기",exact:true}).click();
    await page.getByRole("heading",{name:"회계 거래",exact:true}).waitFor();
    console.log("PASS: 로그인 → 파일 → 매핑 → 미리보기 → 확인 → 거래 2건 → 새로고침 → 동일 요청 재시도 → 거래 화면");
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode=1; });
