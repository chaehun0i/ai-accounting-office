// 입력 기본값에는 사용자의 현재 달력 날짜를 사용합니다. 회계 판단은 서버가 수행합니다.
export function localDate(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}
export function currentYearRange(now = new Date()): { from: string; to: string } {
  return { from: `${now.getFullYear()}-01-01`, to: `${now.getFullYear()}-12-31` };
}
