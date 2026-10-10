/** 기존 로컬 테스트 계정으로 페이지 이동·새로고침·권한 안내·모바일 배치를 확인합니다. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const loader = createRequire(path.join(process.env.PLAYWRIGHT_MODULE_PATH, "package.json"));
const { chromium } = loader("playwright");
const origin = process.env.ACCOUNTING_BROWSER_ORIGIN || "http://localhost:3000";

async function main() {
  const text = fs.readFileSync(path.join(__dirname, "../.local/development-accounts.ini"), "utf8");
  const accounts = Object.fromEntries(text.split(/\[([^\]]+)\]/).slice(1).reduce((rows, value, index, all) => {
    if (index % 2 === 0) rows.push([value, Object.fromEntries(all[index + 1].trim().split(/\r?\n/).map(line => line.split(/\s*=\s*/)))]);
    return rows;
  }, []));
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(60000);
  async function login(label) {
    await page.goto(origin);
    await page.getByLabel("이메일", { exact: true }).fill(accounts[label]["이메일"]);
    await page.getByLabel("비밀번호", { exact: true }).fill(accounts[label]["비밀번호"]);
    await page.getByRole("button", { name: "로그인", exact: true }).click();
    await page.getByRole("heading", { name: "업무 홈", exact: true }).waitFor();
  }
  try {
    await login("회계 담당자");
    assert.equal(await page.getByRole("heading", { name: "회계 전표", exact: true }).count(), 0);
    const menu = page.getByRole("navigation", { name: "업무 메뉴" });
    for (const [label, route] of [["회사 관리", "/companies"], ["회계 준비", "/onboarding"], ["파일 가져오기", "/imports"], ["거래", "/transactions"], ["전표 · 승인", "/journals"], ["총계정원장", "/ledger"], ["합계잔액시산표", "/trial-balance"], ["회계 설정 · 계정과목", "/accounting"]]) {
      await menu.getByRole("link", { name: label, exact: true }).click();
      await page.waitForURL(origin + route);
      assert.equal(await menu.getByRole("link", { name: label, exact: true }).getAttribute("aria-current"), "page");
    }
    await page.reload();
    await page.getByRole("heading", { name: "회계 기준 정보", exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await page.getByRole("button", { name: "로그아웃", exact: true }).click();
    await context.clearCookies();
    await login("회사 관리자");
    await page.goto(origin + "/imports");
    await page.getByRole("heading", { name: "이 업무에 접근할 권한이 없습니다", exact: true }).waitFor();
    await page.screenshot({ path: ".local/navigation-mobile.png", fullPage: true });
    console.log("페이지 검증 통과: 독립 경로 9개, 메뉴 이동, 현재 위치, 인증 복구, 권한 안내, 모바일 배치");
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
