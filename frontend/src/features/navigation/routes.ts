/** 메뉴와 페이지 접근 안내가 같은 권한 정의를 사용합니다. 서버 권한 검증은 별도로 유지합니다. */
export const officeRoutes = [
  { href: "/", label: "업무 홈", group: "시작", permission: null },
  { href: "/companies", label: "회사 관리", group: "시작", permission: null },
  { href: "/onboarding", label: "회계 준비", group: "데이터 준비", permission: "onboarding.read" },
  { href: "/imports", label: "파일 가져오기", group: "데이터 준비", permission: "import.create" },
  { href: "/transactions", label: "거래", group: "회계 업무", permission: "transaction.read" },
  { href: "/journals", label: "전표 · 승인", group: "회계 업무", permission: "journal.read" },
  { href: "/receivables", label: "채권", group: "수금 · 지급", permission: "receivable.read" },
  { href: "/payables", label: "채무", group: "수금 · 지급", permission: "payable.read" },
  { href: "/ledger", label: "총계정원장", group: "장부 조회", permission: "ledger.read" },
  { href: "/trial-balance", label: "합계잔액시산표", group: "장부 조회", permission: "ledger.read" },
  { href: "/accounting", label: "설정 관리", group: "설정", permission: "account.read" },
] as const;
export function canVisit(href: string, permissions: readonly string[]) {
  const route = officeRoutes.find(route => route.href === href);
  return !!route && (route.permission === null || permissions.includes(route.permission));
}
