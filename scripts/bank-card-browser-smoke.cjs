/** 격리된 합성 DB에서 파일 확인과 사람 대사 확정을 검증합니다. */
const assert = require("node:assert/strict");
const path = require("node:path");
const { createRequire } = require("node:module");
const loader = process.env.PLAYWRIGHT_MODULE_PATH ? createRequire(path.join(process.env.PLAYWRIGHT_MODULE_PATH, "package.json")) : require;
const { chromium } = loader("playwright");
async function main() {
  if (!process.argv.includes("--allow-synthetic")) throw new Error("격리 테스트 DB를 먼저 준비해 주세요.");
  const api = process.env.ACCOUNTING_API_ORIGIN || "http://127.0.0.1:8003";
  const origin = process.env.ACCOUNTING_BROWSER_ORIGIN || "http://localhost:3000";
  const browser = await chromium.launch({channel:"msedge",headless:true});
  const context = await browser.newContext(); const page = await context.newPage();
  page.setDefaultTimeout(120000);
  await page.route("**/api/**",async route=>{
    const url=new URL(route.request().url());
    try{
      const response=await route.fetch({url:api+url.pathname.slice(4)+url.search,timeout:120000});
      await route.fulfill({response});
    }catch{
      console.log(`네트워크 중단: ${route.request().method()} ${url.pathname}`);
      await route.abort("failed").catch(()=>{});
    }
  });
  const stamp=Date.now(),email=`bank-browser-${stamp}@example.com`,password="SyntheticAccountingPassword!2026";
  let token, company;
  async function post(url,data,key) {
    const response=await context.request.post(api+url,{data,headers:{"X-CSRF-Protection":"1",...(token?{Authorization:`Bearer ${token}`} : {}),...(company?{"X-Company-ID":company.id}:{}),...(key?{"Idempotency-Key":key}:{})}});
    assert.ok(response.ok(),`${url}: ${response.status()}`);return response.json();
  }
  async function get(url) {const response=await context.request.get(api+url,{headers:{Authorization:`Bearer ${token}`,"X-Company-ID":company.id}});assert.ok(response.ok());return response.json();}
  async function login(account){
    await context.clearCookies();await page.goto(origin);
    await page.getByLabel("이메일",{exact:true}).fill(account);
    await page.getByLabel("비밀번호",{exact:true}).fill(password);
    await page.getByRole("button",{name:"로그인",exact:true}).click();
    await page.getByRole("navigation",{name:"업무 메뉴",exact:true}).waitFor();
  }
  async function upload(kind) {
    console.log(`진행: ${kind} 파일 확인`);
    await page.getByText("새 원천 파일 가져오기",{exact:true}).click();
    const card=kind==="CARD";
    const text=card?"source_id,date,amount,currency,direction,description,source_status\ncard-1,2026-01-02,100,KRW,OUT,software,CAPTURED\n":"source_id,date,amount,currency,direction,description\nbank-1,2026-01-02,100,KRW,IN,receipt\n";
    await page.getByLabel("파일 선택",{exact:true}).setInputFiles({name:"synthetic.csv",mimeType:"text/csv",buffer:Buffer.from(text)});
    await page.getByRole("button",{name:"파일 올리기",exact:true}).click();
    await page.getByRole("button",{name:"검증하고 미리보기",exact:true}).click();
    await page.getByLabel("대상 회사와 항목 연결, 검증 결과를 확인했습니다.",{exact:true}).check();
    await page.getByRole("button",{name:"확인한 자료 접수",exact:true}).click();
    await page.getByRole("button",{name:"확인 자료를 대사 원천으로 연결",exact:true}).click();
    if(!card){await page.getByLabel("시작일",{exact:true}).fill("2026-01-01");await page.getByLabel("종료일",{exact:true}).fill("2026-01-31");await page.getByLabel("기말잔액",{exact:true}).fill("100");}
    const response=page.waitForResponse(r=>r.request().method()==="POST"&&r.url().endsWith(card?"/card-transactions/imports":"/bank-statements/imports"));
    await page.getByRole("button",{name:"원천 자료 생성",exact:true}).click();
    const result=await response;assert.ok(result.ok()); return result.json();
  }
  async function match(){
    console.log("진행: 후보 검토와 확정");
    await page.getByRole("button",{name:"대사 후보 확인",exact:true}).click();
    await page.getByLabel("후보 1 선택",{exact:true}).check();
    await page.getByRole("button",{name:"선택한 배분으로 초안 저장",exact:true}).click();
    const response=page.waitForResponse(r=>r.request().method()==="POST"&&r.url().endsWith("/confirm"));
    await page.getByRole("button",{name:"검토한 대사 확정",exact:true}).click();
    const result=await response;assert.ok(result.ok());return result.json();
  }
  try{
    token=(await post("/auth/register",{email,password})).access_token;
    company=await post("/companies",{company_name:"은행 카드 합성 검증 회사",business_number:"1234567890",taxpayer_type:"INDIVIDUAL",opening_date:"2026-01-01",address:"합성 주소"});
    const templates=await get("/account-templates");await post("/accounting/initialize",{fiscal_year:2026,template_id:templates[0].id});
    const accounts=await get("/accounts");
    const ownerToken=token;
    const writerEmail=`bank-writer-${stamp}@example.com`;
    const writer=await post("/auth/register",{email:writerEmail,password});
    const invitation=await post(`/companies/${company.id}/invitations`,{email:writerEmail,role_code:"ACCOUNTANT"});
    token=writer.access_token;
    await post(`/invitations/${invitation.invite_token}/accept`,{});
    await post("/transactions",{transaction_date:"2026-01-02",accounting_date:"2026-01-02",description:"입금 사실",amount:"100",direction:"INFLOW",source_id:"bank-1"},"bank-source-target");
    await post("/transactions",{transaction_date:"2026-01-02",accounting_date:"2026-01-02",description:"카드 사용 사실",amount:"100",direction:"OUTFLOW",source_id:"card-1"},"card-source-target");
    token=ownerToken;
    console.log("진행: 사용자 로그인");
    await login(email);
    console.log("진행: 은행 화면과 별칭 설정");
    await page.goto(origin+"/bank-reconciliation");
    await page.getByRole("button",{name:"별칭과 장부 계정 연결",exact:true}).click();
    let dialog=page.getByRole("dialog");await dialog.getByLabel("기관 코드",{exact:true}).fill("TEST");await dialog.getByLabel("별칭",{exact:true}).fill("브라우저 운영 계좌");await dialog.getByLabel("장부 통제계정",{exact:true}).selectOption(accounts.find(a=>a.account_name==="보통예금").id);await dialog.getByRole("button",{name:"연결 저장",exact:true}).click();
    await dialog.waitFor({state:"hidden"});
    await login(writerEmail);await page.goto(origin+"/bank-reconciliation");
    await page.getByLabel("계좌",{exact:true}).selectOption((await get("/bank-accounts"))[0].id);
    const statement=await upload("BANK");const confirmed=await match();
    await page.getByRole("button",{name:"장부와 잔액 비교",exact:true}).click();await page.getByText("미해결 차이가 있습니다.",{exact:false}).waitFor();
    await page.getByLabel("해제 사유",{exact:true}).fill("합성 재검토");await page.getByRole("button",{name:"대사 해제",exact:true}).click();await match();
    await page.reload();await page.getByLabel("계좌",{exact:true}).selectOption(statement.bank_account_id);await page.getByLabel("명세 기간",{exact:true}).selectOption(statement.id);await page.getByText("bank-1",{exact:true}).waitFor();
    const current=await get(`/bank-statements/${statement.id}/transactions`);assert.equal(current[0].reconciliation_status,"MATCHED");
    const replayKey="browser-confirm-replay";
    const replay=await post(`/reconciliations/${confirmed.id}/confirm`,{expected_version:confirmed.version},replayKey).catch(()=>null);assert.equal(replay,null);
    await login(email);await page.goto(origin+"/card-reconciliation");await page.getByRole("button",{name:"별칭과 장부 계정 연결",exact:true}).click();
    dialog=page.getByRole("dialog");await dialog.getByLabel("기관 코드",{exact:true}).fill("TEST");await dialog.getByLabel("별칭",{exact:true}).fill("브라우저 법인카드");await dialog.getByLabel("장부 통제계정",{exact:true}).selectOption(accounts.find(a=>a.account_name==="카드미지급금").id);await dialog.getByRole("button",{name:"연결 저장",exact:true}).click();
    await dialog.waitFor({state:"hidden"});
    await login(writerEmail);await page.goto(origin+"/card-reconciliation");
    await page.getByLabel("카드",{exact:true}).selectOption((await get("/card-accounts"))[0].id);
    await upload("CARD");await match();await page.getByRole("button",{name:"장부와 잔액 비교",exact:true}).click();await page.getByText("미해결 차이가 있습니다.",{exact:false}).waitFor();
    await page.screenshot({path:path.resolve(".local/bank-card-browser.png"),fullPage:true});
    const other=await post("/companies",{company_name:"대사 격리 회사",business_number:"9876543210",taxpayer_type:"INDIVIDUAL",opening_date:"2026-01-01",address:"합성 주소"});
    await login(email);
    await page.locator("button.company-switch").click();dialog=page.getByRole("dialog");await dialog.getByLabel("회사",{exact:true}).selectOption(other.id);await dialog.getByRole("button",{name:"선택 완료",exact:true}).click();await dialog.getByRole("button",{name:"닫기",exact:true}).click();
    await page.getByRole("navigation",{name:"업무 메뉴"}).getByRole("link",{name:"은행 대사",exact:true}).click();
    await page.getByText("등록된 별칭이 없습니다.",{exact:false}).waitFor();assert.equal(await page.getByText("bank-1",{exact:true}).count(),0);
    console.log("PASS: 로그인→별칭 연결→CSV 검증/접수→은행 원천→후보→확정→차이 보존→해제/재확정→새로고침→카드 대사→회사 격리");
  }catch(error){await page.screenshot({path:path.resolve(".local/bank-card-browser-failure.png"),fullPage:true});throw error;}finally{await browser.close();}
}
main().catch(error=>{console.error(error.message.split("Call log:")[0]);process.exitCode=1;});
