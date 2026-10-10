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
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
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
    await page.getByRole("combobox", { name: /업무 회계기간/ }).waitFor();
    await page.getByRole("heading", { name: "최근 회계 기록", exact: true }).waitFor();
    await page.getByRole("combobox", { name: /업무 회계기간/ }).locator("option").nth(1).waitFor({ state: "attached" });
    await page.screenshot({ path: ".local/accounting-dashboard.png", fullPage: true });
    await page.getByRole("button", { name: "사이드바 접기", exact: true }).click();
    assert.equal(await page.getByRole("button", { name: "사이드바 펼치기", exact: true }).getAttribute("aria-expanded"), "false");
    await page.getByRole("button", { name: "사이드바 펼치기", exact: true }).click();
    const menu = page.getByRole("navigation", { name: "업무 메뉴" });
    await menu.getByRole("button", { name: "회계 업무", exact: true }).click();
    assert.equal(await menu.getByRole("button", { name: "회계 업무", exact: true }).getAttribute("aria-expanded"), "false");
    await menu.getByRole("button", { name: "회계 업무", exact: true }).click();
    await page.locator(".company-switch").click();
    await page.getByRole("dialog", { name: "회사 선택", exact: true }).waitFor();
    await page.keyboard.press("Shift+Tab");
    assert.ok(await page.evaluate(() => !!document.activeElement.closest('[role="dialog"]')));
    await page.keyboard.press("Escape");
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    await page.waitForFunction(() => document.activeElement?.classList.contains("company-switch"));
    for (const [label, route] of [["회사 관리", "/companies"], ["회계 준비", "/onboarding"], ["파일 가져오기", "/imports"], ["거래", "/transactions"], ["전표 · 승인", "/journals"], ["총계정원장", "/ledger"], ["합계잔액시산표", "/trial-balance"], ["회계 설정 · 계정과목", "/accounting"]]) {
      await menu.getByRole("link", { name: label, exact: true }).click();
      await page.waitForURL(origin + route);
      assert.equal(await menu.getByRole("link", { name: label, exact: true }).getAttribute("aria-current"), "page");
    }
    await menu.getByRole("link", { name: "회계 준비", exact: true }).click();
    await page.getByRole("button", { name: /^계정과목 · 서버 제공/ }).click();
    await page.getByRole("region", { name: "서버 계정과목 목록", exact: true }).getByText("보통예금", { exact: true }).waitFor();
    assert.equal(await page.getByRole("button", { name: "항목 추가", exact: true }).count(), 0);
    await page.getByLabel("계정코드·계정명 검색").fill("보통예금");
    assert.equal(await page.locator(".table-scroll tbody tr").count(), 1);
    await page.getByRole("button", { name: /^거래처 ·/ }).click();
    await page.getByRole("button", { name: "항목 추가", exact: true }).click();
    const rowEditor = page.getByRole("dialog", { name: "거래처 입력", exact: true });
    await rowEditor.waitFor();
    await page.keyboard.press("Escape");
    await rowEditor.waitFor({ state: "hidden" });
    await page.getByRole("button", { name: /^회사 기본정보 ·/ }).click();
    await page.getByRole("button", { name: "Excel 업로드", exact: true }).click();
    const excel = page.getByRole("dialog", { name: "Excel로 현재 초안 채우기", exact: true });
    await excel.waitFor();
    await excel.evaluate(element => Promise.all(element.getAnimations().map(animation => animation.finished)));
    await page.screenshot({ path: ".local/esg-excel-dialog.png", fullPage: true });
    await page.mouse.click(3, 3);
    assert.ok(await excel.isVisible());
    await page.keyboard.press("Escape");
    await excel.waitFor({ state: "hidden" });
    await page.waitForFunction(() => document.activeElement?.textContent === "Excel 업로드");
    await page.screenshot({ path: ".local/esg-workspace.png", fullPage: true });
    await menu.getByRole("link", { name: "회사 관리", exact: true }).click();
    await page.getByRole("button", { name: "새 회사 만들기", exact: true }).click();
    await page.getByRole("dialog", { name: "새 회사 만들기", exact: true }).waitFor();
    await page.keyboard.press("Escape");
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    await menu.getByRole("link", { name: "회계 설정 · 계정과목", exact: true }).click();
    await page.waitForURL(origin + "/accounting");
    await page.reload();
    await page.getByRole("heading", { name: "회계 기준 정보", exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await page.getByRole("button", { name: "업무 메뉴 열기", exact: true }).click();
    await menu.getByRole("link", { name: "업무 홈", exact: true }).click();
    assert.equal(await page.getByRole("button", { name: "업무 메뉴 열기", exact: true }).getAttribute("aria-expanded"), "false");
    await page.emulateMedia({ reducedMotion: "reduce" });
    assert.equal(await page.locator(".office-shell").evaluate(element => getComputedStyle(element).transitionDuration), "0s");
    await page.getByRole("button", { name: "로그아웃", exact: true }).click();
    await context.clearCookies();
    await login("회사 관리자");
    await page.goto(origin + "/imports");
    await page.getByRole("heading", { name: "이 업무에 접근할 권한이 없습니다", exact: true }).waitFor();
    await page.screenshot({ path: ".local/navigation-mobile.png", fullPage: true });
    console.log("페이지 검증 통과: 독립 경로 9개, 메뉴 이동, 현재 위치, 인증 복구, 권한 안내, 모바일 배치, 메뉴 접기·펼치기, 팝업 포커스·Escape·배경 클릭 보호, 움직임 줄이기");
  } catch (error) { await page.screenshot({ path: ".local/navigation-failure.png", fullPage: true }); throw error; } finally { await browser.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
