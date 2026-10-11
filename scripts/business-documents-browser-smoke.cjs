/** 격리된 합성 DB에서 파일 확인→거래 생성→복구·재시도를 검증합니다. */
const assert = require("node:assert/strict");
const path = require("node:path");
const { createRequire } = require("node:module");
const loader = process.env.PLAYWRIGHT_MODULE_PATH ? createRequire(path.join(process.env.PLAYWRIGHT_MODULE_PATH, "package.json")) : require;
const { chromium } = loader("playwright");
async function main() {
  if (!process.argv.includes("--allow-synthetic")) throw new Error("격리 테스트 DB를 먼저 준비해 주세요.");
  const api = process.env.ACCOUNTING_API_ORIGIN || "http://127.0.0.1:8003";
  const origin = process.env.ACCOUNTING_BROWSER_ORIGIN || "http://localhost:3000";
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
    const owner = await post("/auth/register", {email:`documents-owner-${stamp}@example.com`,password});
    const email = `documents-writer-${stamp}@example.com`;
    const writer = await post("/auth/register", {email,password});
    const company = await post("/companies", {company_name:"업무문서 브라우저 회사",business_number:"1234567890",taxpayer_type:"INDIVIDUAL",opening_date:"2026-01-01",address:"합성 주소"},owner.access_token);
    const invite = await post(`/companies/${company.id}/invitations`,{email,role_code:"ACCOUNTANT"},owner.access_token);
    await post(`/invitations/${invite.invite_token}/accept`,{},writer.access_token);
    const templates = await context.request.get(api+"/account-templates",{headers:{Authorization:`Bearer ${owner.access_token}`,"X-Company-ID":company.id}}).then(r=>r.json());
    await post("/accounting/initialize",{fiscal_year:2026,template_id:templates[0].id},owner.access_token,company.id);

    const cp = await post("/counterparties",{display_name:"검증 거래처",legal_name:"검증 거래처"},writer.access_token,company.id);
    const ownerEmail = `documents-owner-${stamp}@example.com`;
    async function login(account) {
      await context.clearCookies(); await page.goto(origin);
      await page.getByLabel("이메일",{exact:true}).fill(account); await page.getByLabel("비밀번호",{exact:true}).fill(password);
      await page.getByRole("button",{name:"로그인",exact:true}).click();
      await page.getByRole("navigation",{name:"업무 메뉴",exact:true}).waitFor();
      await page.getByRole("navigation",{name:"업무 메뉴"}).getByRole("link",{name:"매출 · 매입 문서",exact:true}).click();
    }
    async function fillDocument(number,supply,tax,reason) {
      const dialog=page.getByRole("dialog");
      await dialog.getByLabel("문서번호",{exact:true}).fill(number);
      await dialog.getByLabel("거래처",{exact:true}).selectOption(cp.id);
      for (const label of ["발행일","회계 기준일","지급기일"]) await dialog.getByLabel(label,{exact:true}).fill("2026-10-12");
      await dialog.getByLabel("내용",{exact:true}).fill("합성 회계 용역");
      await dialog.getByLabel("공급가액",{exact:true}).fill(supply);
      await dialog.getByLabel("세액",{exact:true}).fill(tax);
      if(reason) await dialog.getByLabel("정정 사유",{exact:true}).fill(reason);
      const response=page.waitForResponse(r=>r.request().method()==="POST" && /\/(sales-invoices|credit-notes)$/.test(r.url()));
      await dialog.getByRole("button",{name:"초안 저장",exact:true}).click();
      const result=await (await response).json(); assert.ok(result.id); return result;
    }
    async function action(button,confirm) {
      await page.getByRole("button",{name:button,exact:true}).click();
      const response=page.waitForResponse(r=>/\/(submit|approve)$/.test(r.url()));
      await page.getByRole("dialog").getByRole("button",{name:confirm,exact:true}).click();
      const result=await (await response).json(); assert.ok(result.id); return result;
    }
    await login(email);
    await page.getByRole("button",{name:"새 매출 청구서 작성",exact:true}).click();
    const invoice = await fillDocument("BROWSER-S-001","10000000","1000000");
    const submitted = await action("승인 요청","승인 요청");
    await login(ownerEmail);
    await page.getByRole("button",{name:"BROWSER-S-001",exact:true}).click();
    const approved=await action("문서 승인·확정","문서 확정");
    assert.equal(approved.status,"APPROVED"); assert.ok(approved.transaction_id); assert.ok(approved.obligation_id);
    const replay=await post(`/sales-invoices/${invoice.id}/approve`,{expected_version:submitted.version},owner.access_token,company.id,"different-retry-key").catch(()=>null);
    assert.equal(replay,null);
    await page.getByRole("link",{name:"생성된 거래 확인",exact:true}).click();
    await page.getByRole("heading",{name:"회계 거래",exact:true}).waitFor();
    await login(email);
    await page.getByRole("button",{name:"BROWSER-S-001",exact:true}).click();
    await page.getByRole("button",{name:"감액 정정문서 작성",exact:true}).click();
    const note=await fillDocument("BROWSER-CN-001","2000000","200000","공급 취소");
    await action("승인 요청","승인 요청");
    await login(ownerEmail);
    await page.getByLabel("문서 종류",{exact:true}).selectOption("CREDIT_NOTE");
    await page.getByRole("button",{name:"BROWSER-CN-001",exact:true}).click();
    const applied=await action("문서 승인·확정","문서 확정"); assert.equal(applied.status,"APPLIED");
    const obligations=await context.request.get(api+"/receivables?as_of=2026-12-31",{headers:{Authorization:`Bearer ${writer.access_token}`,"X-Company-ID":company.id}}).then(r=>r.json());
    assert.equal(obligations[0].outstanding_amount,"8800000.0000");
    await page.reload(); await page.getByLabel("문서 종류",{exact:true}).selectOption("CREDIT_NOTE");
    await page.getByRole("button",{name:"BROWSER-CN-001",exact:true}).waitFor();
    await page.screenshot({path:require("node:path").resolve(".local/business-document-browser.png"),fullPage:true});
    const other=await post("/companies",{company_name:"업무문서 격리 회사",business_number:"9876543210",taxpayer_type:"INDIVIDUAL",opening_date:"2026-01-01",address:"합성 주소"},owner.access_token);
    await page.reload(); await page.locator("button.company-switch").click();
    await page.getByRole("dialog").getByLabel("회사",{exact:true}).selectOption(other.id);
    await page.getByRole("dialog").getByRole("button",{name:"선택 완료",exact:true}).click();
    await page.getByRole("dialog").getByRole("button",{name:"닫기",exact:true}).click();
    await page.getByRole("navigation",{name:"업무 메뉴"}).getByRole("link",{name:"매출 · 매입 문서",exact:true}).click();
    await page.getByText("등록된 문서가 없습니다.",{exact:false}).waitFor();
    assert.equal(await page.getByRole("button",{name:"BROWSER-S-001",exact:true}).count(),0);
    console.log("PASS: 로그인→매출 문서 작성→승인 요청→별도 사용자 승인→거래 확인→감액 정정→잔액 8,800,000→새로고침→회사 격리");
  } finally { await browser.close(); }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
