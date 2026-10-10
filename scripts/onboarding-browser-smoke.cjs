/** 실제 브라우저로 직접 입력과 Excel 병합을 검증합니다. 전용 테스트 DB에서만 실행하세요. */
const { createRequire } = require("node:module");
const path = require("node:path");
const assert = require("node:assert/strict");
const loader = process.env.PLAYWRIGHT_MODULE_PATH ? createRequire(path.join(process.env.PLAYWRIGHT_MODULE_PATH, "package.json")) : require;
const { chromium } = loader("playwright");

async function main() {
  if (!process.argv.includes("--allow-synthetic")) throw new Error("전용 테스트 환경을 준비한 뒤 --allow-synthetic 옵션으로 실행해 주세요.");
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || "msedge", headless: true });
  const page = await browser.newPage();
  const email = `onboarding-browser-${Date.now()}@example.com`;
  const consoleErrors = [];
  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.setDefaultTimeout(30000);
  try {
    await page.goto(process.env.ONBOARDING_BROWSER_ORIGIN || "http://127.0.0.1:3000");
    await page.getByRole("button", { name: "처음 방문하셨나요? 계정 만들기" }).click();
    await page.getByLabel("이메일", { exact: true }).fill(email);
    await page.getByLabel("비밀번호", { exact: true }).fill("SyntheticBrowserPassword!2026");
    await page.getByRole("button", { name: "계정 만들기", exact: true }).click();
    await page.getByRole("button", { name: "로그아웃", exact: true }).click();
    await page.getByLabel("이메일", { exact: true }).fill(email);
    await page.getByLabel("비밀번호", { exact: true }).fill("SyntheticBrowserPassword!2026");
    await page.getByRole("button", { name: "로그인", exact: true }).click();
    await page.getByText("새 회사 만들기", { exact: true }).click();
    await page.getByLabel("회사명", { exact: true }).fill("브라우저 검증 회사");
    await page.getByLabel("사업자등록번호", { exact: true }).fill("1234567890");
    await page.getByLabel("개업일", { exact: true }).fill("2025-01-01");
    await page.getByLabel("주소", { exact: true }).fill("합성 테스트 주소");
    await page.getByRole("button", { name: "회사 만들기", exact: true }).click();
    const workspace = page.locator("section[aria-labelledby=onboarding-heading]");
    await workspace.getByRole("heading", { name: "회계 시작 준비", exact: true }).waitFor();
    const companyId = await page.locator("#company-list option").nth(1).getAttribute("value");
    await page.locator("#company-list").selectOption(companyId);
    await page.getByRole("button", { name: "선택 완료", exact: true }).click();
    await workspace.getByRole("button", { name: "Excel 업로드", exact: true }).waitFor();
    assert.equal(await workspace.getByRole("button", { name: "Excel 업로드", exact: true }).count(), 1);
    await workspace.getByLabel("회사명", { exact: true }).fill("직접 입력한 회사");
    await workspace.getByRole("button", { name: "초안 저장", exact: true }).click();
    await workspace.getByText("초안을 저장했습니다.", { exact: true }).waitFor();
    await page.reload();
    await workspace.getByLabel("회사명", { exact: true }).waitFor();
    assert.equal(await workspace.getByLabel("회사명", { exact: true }).inputValue(), "직접 입력한 회사");
    await workspace.getByRole("button", { name: "Excel 업로드", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Excel 파일", { exact: true }).setInputFiles(path.resolve("backend/tests/fixtures/onboarding/onboarding-syn-mfg-2025-derived-v1.xlsx"));
    await dialog.getByRole("button", { name: "업로드 후 미리보기", exact: true }).click();
    await dialog.getByRole("region", { name: "병합 검토" }).waitFor();
    const choices = dialog.getByRole("combobox", { name: "충돌 해결" });
    assert.ok(await choices.count() > 0);
    for (let i = 0; i < await choices.count(); i++) await choices.nth(i).selectOption("APPLY_IMPORT");
    await dialog.getByRole("button", { name: "선택한 내용 초안에 적용", exact: true }).click();
    await dialog.getByText(/초안에 적용했습니다/).waitFor();
    await dialog.getByRole("button", { name: "닫기", exact: true }).click();
    assert.equal(await workspace.getByLabel("회사명", { exact: true }).inputValue(), "가온푸드웍스 주식회사");
    await workspace.getByLabel("회사명", { exact: true }).fill("Excel 뒤 직접 수정한 회사");
    await workspace.getByRole("button", { name: "초안 저장", exact: true }).click();
    await workspace.getByText("초안을 저장했습니다.", { exact: true }).waitFor();
    await workspace.getByRole("button", { name: "검증하고 다시 계산", exact: true }).click();
    await workspace.getByRole("region", { name: "검증 결과" }).waitFor();
    assert.ok(await workspace.getByRole("button", { name: "준비 완료 및 회계정보 반영", exact: true }).isDisabled());
    assert.ok(await workspace.getByText(/회계정보 반영 기능이 준비되면/).count() > 0);
    assert.equal(consoleErrors.filter(message => /same key|unique.*key/i.test(message)).length, 0);
    console.log("브라우저 검증 통과: 인증, 회사 선택, 직접 입력 복구, Excel 충돌 해결, 초안 적용, 수동 수정, 검증, 미지원 승격 차단");
  } catch (error) {
    await page.screenshot({ path: ".local/onboarding-browser-failure.png", fullPage: true });
    throw error;
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.stack); process.exitCode = 1; });
