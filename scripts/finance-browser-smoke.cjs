/** 전용 테스트 API와 실제 Compose 화면에서 채권채무 정산을 검증합니다. */
const assert = require("node:assert/strict");
const path = require("node:path");
const { createRequire } = require("node:module");
const loader = process.env.PLAYWRIGHT_MODULE_PATH ? createRequire(path.join(process.env.PLAYWRIGHT_MODULE_PATH, "package.json")) : require;
const { chromium } = loader("playwright");

async function main() {
  if (!process.argv.includes("--allow-synthetic")) throw new Error("전용 테스트 DB/API를 먼저 준비해 주세요.");
  const origin = process.env.ACCOUNTING_BROWSER_ORIGIN || "http://localhost:3000";
  const api = process.env.ACCOUNTING_API_ORIGIN || "http://127.0.0.1:8002";
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || "msedge", headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(60000);
  // 브라우저 API 요청만 격리 DB로 보냅니다. 개발 회사와 세션은 변경하지 않습니다.
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    const response = await route.fetch({ url: api + url.pathname.slice(4) + url.search });
    await route.fulfill({ response });
  });
  const stamp = Date.now();
  const ownerEmail = `finance-owner-${stamp}@example.com`, writerEmail = `finance-writer-${stamp}@example.com`;
  const password = "SyntheticAccountingPassword!2026";
  async function request(route, body, token, company) {
    const response = await context.request.post(api + route, { headers: {
      "X-CSRF-Protection": "1", "Idempotency-Key": crypto.randomUUID(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(company ? { "X-Company-ID": company } : {}),
    }, data: body });
    assert.ok(response.ok(), `${route}: ${response.status()}`);
    return response.json();
  }
  async function get(route, token, company) {
    const response = await context.request.get(api + route, { headers: { Authorization: `Bearer ${token}`, "X-Company-ID": company } });
    assert.ok(response.ok(), `${route}: ${response.status()}`);
    return response.json();
  }
  try {
    const owner = await request("/auth/register", { email: ownerEmail, password });
    const writer = await request("/auth/register", { email: writerEmail, password });
    const company = await request("/companies", { company_name: "재무 브라우저 검증 회사", business_number: "1234567890", taxpayer_type: "INDIVIDUAL", opening_date: "2026-01-01", address: "합성 테스트 주소" }, owner.access_token);
    const invite = await request(`/companies/${company.id}/invitations`, { email: writerEmail, role_code: "ACCOUNTANT" }, owner.access_token);
    await request(`/invitations/${invite.invite_token}/accept`, {}, writer.access_token);
    const templates = await get("/account-templates", owner.access_token, company.id);
    await request("/accounting/initialize", { fiscal_year: 2026, template_id: templates[0].id }, owner.access_token, company.id);
    const accounts = Object.fromEntries((await get("/accounts", writer.access_token, company.id)).map(value => [value.account_name, value.id]));
    const periods = await get("/accounting/periods", writer.access_token, company.id);
    const cp = await request("/counterparties", { display_name: "브라우저 거래처", legal_name: "브라우저 거래처" }, writer.access_token, company.id);
    async function posted(description, lines, day) {
      let journal = await request("/journals", { accounting_period_id: periods[0].id, entry_date: day, description, lines }, writer.access_token, company.id);
      for (const [actor, action] of [[writer, "submit"], [writer, "request-review"], [owner, "approve"], [owner, "post"]]) {
        journal = await request(`/journals/${journal.id}/${action}`, { expected_version: journal.version, approval_id: journal.approval_id, reason: "합성 전표 검토 완료" }, actor.access_token, company.id);
      }
      return journal;
    }
    const facts = [];
    for (const [kind, title, action, control, original, paid] of [
      ["AR", "채권", "수금", "매출채권", "11000000", "5500000"],
      ["AP", "채무", "지급", "매입채무", "3300000", "1650000"],
    ]) {
      const source = await posted(`${title} 발생 검증`, [
        { account_id: accounts[control], counterparty_id: cp.id, [kind === "AR" ? "debit_amount" : "credit_amount"]: original },
        { account_id: accounts[kind === "AR" ? "매출" : "소모품비"], [kind === "AR" ? "credit_amount" : "debit_amount"]: original },
      ], "2026-01-02");
      const settlement = await posted(`${action} 검증`, [
        { account_id: accounts[control], counterparty_id: cp.id, [kind === "AR" ? "credit_amount" : "debit_amount"]: paid },
        { account_id: accounts["보통예금"], [kind === "AR" ? "debit_amount" : "credit_amount"]: paid },
      ], "2026-01-10");
      facts.push({ kind, title, action, source, settlement, original, paid });
    }
    await context.clearCookies();
    await page.goto(origin);
    await page.getByLabel("이메일", { exact: true }).fill(writerEmail);
    await page.getByLabel("비밀번호", { exact: true }).fill(password);
    await page.getByRole("button", { name: "로그인", exact: true }).click();
    await page.getByRole("heading", { name: "업무 홈", exact: true }).waitFor();
    for (const fact of facts) {
      await page.getByRole("navigation", { name: "업무 메뉴" }).getByRole("link", { name: fact.title, exact: true }).click();
      await page.getByLabel("조회 기준일", { exact: true }).fill("2026-01-31");
      await page.getByRole("button", { name: `${fact.title} 등록`, exact: true }).click();
      let dialog = page.getByRole("dialog");
      await dialog.getByLabel("확정 전표").selectOption(fact.source.id);
      await dialog.getByLabel("결제 기한").fill("2026-01-20");
      await dialog.getByRole("button", { name: "등록", exact: true }).click();
      await dialog.waitFor({ state: "hidden" });
      await page.getByRole("button", { name: `${fact.action} 등록`, exact: true }).click();
      dialog = page.getByRole("dialog");
      await dialog.getByLabel("확정 전표").selectOption(fact.settlement.id);
      await dialog.getByLabel(`${fact.action}액`, { exact: true }).fill(fact.paid);
      await dialog.getByRole("button", { name: "등록", exact: true }).click();
      await dialog.waitFor({ state: "hidden" });
      await page.getByRole("button", { name: "배분 검토", exact: true }).click();
      dialog = page.getByRole("dialog");
      await dialog.getByLabel("브라우저 거래처 배분액", { exact: true }).fill(fact.paid);
      const saved = page.waitForResponse(response => response.url().includes("/allocations") && response.request().method() === "POST");
      await dialog.getByRole("button", { name: "배분 저장", exact: true }).click();
      assert.equal((await saved).status(), 200);
      await dialog.getByRole("button", { name: "배분 확정", exact: true }).click();
      await dialog.waitFor({ state: "hidden" });
      await page.getByText("보조부와 원장 잔액이 일치합니다.", { exact: true }).waitFor();
      await page.getByRole("cell", { name: "일부 결제", exact: true }).waitFor();
      await page.reload();
      await page.getByRole("cell", { name: "일부 결제", exact: true }).waitFor();
      await page.getByText("보조부와 원장 잔액이 일치합니다.", { exact: true }).waitFor();
    }
    await page.screenshot({ path: path.join(process.cwd(), ".local/finance-browser-success.png"), fullPage: true });
    console.log("PASS: 로그인·회사·채권·채무·부분 정산·원장 대사·재접속");
  } finally {
    await context.close();
    await browser.close();
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
