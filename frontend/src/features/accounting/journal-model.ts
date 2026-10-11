// 화면 합계도 정수 소수점 단위로 계산하며 서버 결과를 최종 기준으로 사용합니다.
export type EditableLine = {account_id:string; debit_amount:string; credit_amount:string; memo:string; counterparty_id?:string|null};
export function units(text:string):bigint {if(!/^\d+(\.\d{0,4})?$/.test(text))throw new Error("금액은 소수점 네 자리까지 입력해 주세요.");const [whole,fraction=""]=text.split(".");return BigInt(whole)*BigInt(10000)+BigInt(fraction.padEnd(4,"0"));}
export function money(value:bigint):string {const sign=value<BigInt(0)?"-":"";const n=value<BigInt(0)?-value:value;return sign+(n/BigInt(10000)).toString()+"."+(n%BigInt(10000)).toString().padStart(4,"0");}
export function lineTotals(lines:EditableLine[]) {let debit=BigInt(0),credit=BigInt(0);let valid=lines.length>=2;for(const l of lines){const d=units(l.debit_amount||"0"),c=units(l.credit_amount||"0");debit+=d;credit+=c;valid=valid&&Boolean(l.account_id)&&((d>BigInt(0)&&c===BigInt(0))||(c>BigInt(0)&&d===BigInt(0)));}return {debit:money(debit),credit:money(credit),difference:money(debit-credit),valid,balanced:valid&&debit===credit};}
export const journalStatus:Record<string,string>={DRAFT:"작성 중",PROPOSED:"제출됨",REVIEW_REQUIRED:"승인 대기",APPROVED:"승인됨",REJECTED:"반려됨",POSTED:"장부 반영 완료"};

// 화면의 동작 목록은 상태와 권한을 함께 확인하며, 최종 승인은 서버가 판단합니다.
const actions=[
 ["submit","제출","DRAFT","journal.submit"],
 ["request-review","승인 요청","PROPOSED","journal.submit"],
 ["approve","승인","REVIEW_REQUIRED","journal.approve"],
 ["reject","반려","REVIEW_REQUIRED","journal.approve"],
 ["post","장부 반영","APPROVED","journal.post"],
 ["reverse","역분개 작성","POSTED","journal.reverse"],
] as const;
export function availableJournalActions(status:string,permissions:readonly string[]){return actions.filter(([, ,state,permission])=>status===state&&permissions.includes(permission));}
