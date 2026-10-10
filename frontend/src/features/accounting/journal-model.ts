// 화면 합계도 정수 소수점 단위로 계산하며 서버 결과를 최종 기준으로 사용합니다.
export type EditableLine = {account_id:string; debit_amount:string; credit_amount:string; memo:string};
export function units(text:string):bigint {if(!/^\d+(\.\d{0,4})?$/.test(text))throw new Error("금액은 소수점 네 자리까지 입력해 주세요.");const [whole,fraction=""]=text.split(".");return BigInt(whole)*10000n+BigInt(fraction.padEnd(4,"0"));}
export function money(value:bigint):string {const sign=value<0n?"-":"";const n=value<0n?-value:value;return sign+(n/10000n).toString()+"."+(n%10000n).toString().padStart(4,"0");}
export function lineTotals(lines:EditableLine[]) {let debit=0n,credit=0n;let valid=lines.length>=2;for(const l of lines){const d=units(l.debit_amount||"0"),c=units(l.credit_amount||"0");debit+=d;credit+=c;valid=valid&&Boolean(l.account_id)&&((d>0n&&c===0n)||(c>0n&&d===0n));}return {debit:money(debit),credit:money(credit),difference:money(debit-credit),valid,balanced:valid&&debit===credit};}
export const journalStatus:Record<string,string>={DRAFT:"작성 중",PROPOSED:"제출됨",REVIEW_REQUIRED:"승인 대기",APPROVED:"승인됨",REJECTED:"반려됨",POSTED:"장부 반영 완료"};
