/** 전용 합성 테스트 환경에서 거래·전표·승인·확정·원장·시산표를 검증합니다. */
const assert = require("node:assert/strict");
const path = require("node:path");
const { createRequire } = require("node:module");
const loader = process.env.PLAYWRIGHT_MODULE_PATH ? createRequire(path.join(process.env.PLAYWRIGHT_MODULE_PATH, "package.json")) : require;
const { chromium } = loader("playwright");

async function main() {
  if (!process.argv.includes("--allow-synthetic")) throw new Error("전용 테스트 DB를 준비한 뒤 --allow-synthetic 옵션을 사용해 주세요.");
  const origin = process.env.ACCOUNTING_BROWSER_ORIGIN || "http://127.0.0.1:3001";
  const api = process.env.ACCOUNTING_API_ORIGIN || "http://127.0.0.1:8001";
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || "msedge", headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(60000);
  const stamp = Date.now();
  const ownerEmail = `accounting-owner-${stamp}@example.com`, writerEmail = `accounting-writer-${stamp}@example.com`;
  const password = "SyntheticAccountingPassword!2026";
  async function request(route, data, token, company) {
    const response = await context.request.post(api + route, { headers: { "X-CSRF-Protection": "1", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(company ? { "X-Company-ID": company } : {}) }, data });
    assert.ok(response.ok(), `${route}: ${response.status()}`);
    return response.json();
  }
  async function login(email) {
    await context.clearCookies();
    await page.goto(origin);
    await page.getByLabel("이메일", { exact: true }).fill(email);
    await page.getByLabel("비밀번호", { exact: true }).fill(password);
    await page.getByRole("button", { name: "로그인", exact: true }).click();
    await page.getByRole("heading", { name: "회계 전표", exact: true }).waitFor();
  }
  try {
    const owner = await request("/auth/register", { email: ownerEmail, password });
    const writer = await request("/auth/register", { email: writerEmail, password });
    const company = await request("/companies", { company_name: "회계 브라우저 검증 회사", business_number: "1234567890", taxpayer_type: "INDIVIDUAL", opening_date: "2026-01-01", address: "합성 테스트 주소" }, owner.access_token);
    const invitation = await request(`/companies/${company.id}/invitations`, { email: writerEmail, role_code: "ACCOUNTANT" }, owner.access_token);
    await request(`/invitations/${invitation.invite_token}/accept`, {}, writer.access_token);
    const templates = await context.request.get(api + "/account-templates", { headers: { Authorization: `Bearer ${owner.access_token}`, "X-Company-ID": company.id } }).then(r => r.json());
    await request("/accounting/initialize", { fiscal_year: 2026, template_id: templates[0].id }, owner.access_token, company.id);
    await login(writerEmail);
    const transactions = page.locator("section").filter({ has: page.getByRole("heading", { name: "회계 거래", exact: true }) });
    await transactions.getByLabel("조회 시작일").fill("2026-01-01");
    await transactions.getByLabel("조회 종료일").fill("2026-12-31");
    await transactions.getByLabel("거래일", { exact: true }).fill("2026-01-02");
    await transactions.getByLabel("내용", { exact: true }).fill("브라우저 합성 거래");
    await transactions.getByLabel("금액", { exact: true }).fill("100.0000");
    const created = page.waitForResponse(r => r.url().endsWith("/api/transactions") && r.request().method() === "POST");
    await transactions.getByRole("button", { name: "거래 저장", exact: true }).click();
    const transaction = await (await created).json();
    const journal = page.locator("section").filter({ has: page.getByRole("heading", { name: "회계 전표", exact: true }) });
    await journal.getByLabel("조회 시작일").fill("2026-01-01");
    await journal.getByLabel("조회 종료일").fill("2026-12-31");
    await journal.getByLabel("전표일", { exact: true }).fill("2026-01-02");
    await journal.getByLabel("적요", { exact: true }).fill("브라우저 복식부기 검증");
    await journal.getByLabel("연결할 거래 식별자 (선택)").fill(transaction.id);
    const accounts = journal.getByLabel("계정 1", { exact: true });
    await accounts.locator("option").nth(1).waitFor({state:"attached"});
    const accountId = await accounts.locator("option").nth(1).getAttribute("value");
    await accounts.selectOption(accountId);
    await journal.getByLabel("계정 2", { exact: true }).selectOption(await accounts.locator("option").nth(2).getAttribute("value"));
    await journal.getByLabel("차변", { exact: true }).nth(0).fill("100.0000");
    await journal.getByLabel("대변", { exact: true }).nth(1).fill("100.0000");
    await journal.getByRole("button", { name: "분개 추가", exact: true }).click();
    await journal.getByRole("button", { name: "분개 삭제", exact: true }).nth(2).click();
    await journal.getByRole("button", { name: "전표 초안 저장", exact: true }).click();
    await journal.getByRole("heading", { name: "전표 상세", exact: true }).waitFor();
    await journal.getByRole("button", { name: "제출", exact: true }).click();
    await journal.getByRole("button", { name: "승인 요청", exact: true }).click();
    await journal.getByText("브라우저 복식부기 검증 · 승인 대기", { exact: true }).waitFor();
    await page.getByRole("button", { name: "로그아웃", exact: true }).click();
    await login(ownerEmail);
    await journal.getByLabel("조회 시작일").fill("2026-01-01");
    await journal.getByLabel("조회 종료일").fill("2026-12-31");
    await journal.getByRole("button", { name: /번호 미부여.*브라우저 복식부기 검증/ }).click();
    await journal.getByRole("button", { name: "승인", exact: true }).click();
    await journal.getByRole("button", { name: "장부 반영", exact: true }).click();
    await journal.getByText("브라우저 복식부기 검증 · 장부 반영 완료", { exact: true }).waitFor();
    const reports = page.locator("section").filter({ has: page.getByRole("heading", { name: "총계정원장 · 합계잔액시산표", exact: true }) });
    const period = reports.getByLabel("회계기간", { exact: true });
    await period.selectOption(await period.locator("option").nth(1).getAttribute("value"));
    await reports.getByLabel("원장 계정", { exact: true }).selectOption(accountId);
    await reports.getByRole("button", { name: "장부 조회", exact: true }).click();
    await reports.getByText(/기간 차변 100.0000 · 기간 대변 100.0000/).waitFor();
    assert.ok(await reports.getByRole("link", { name: "J-2026-000001", exact: true }).count());
    await reports.getByRole("link", { name: "J-2026-000001", exact: true }).click();
    await page.screenshot({ path: ".local/accounting-browser-success.png", fullPage: true });
    console.log("브라우저 검증 통과: 로그인, 회사 선택, 거래 생성, 분개 추가·삭제, 제출, 별도 사용자 승인, 장부 반영, 원장, 시산표, 전표 이동");
  } catch (error) {
    await page.screenshot({ path: ".local/accounting-browser-failure.png", fullPage: true });
    throw error;
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
