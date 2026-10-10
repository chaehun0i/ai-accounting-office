import { BookOpen, Building2, ClipboardList, FileInput, Home, ListChecks, ReceiptText, Settings2, Table2, type LucideIcon } from "lucide-react";
export const routeIcons: Record<string, LucideIcon> = {
  "/": Home, "/companies": Building2, "/onboarding": ListChecks, "/imports": FileInput,
  "/transactions": ReceiptText, "/journals": ClipboardList, "/ledger": BookOpen,
  "/trial-balance": Table2, "/accounting": Settings2,
};
export const routeDescriptions: Record<string, string> = {
  "/": "회계 업무의 준비부터 승인과 장부 확인까지 한곳에서 이어가세요.",
  "/companies": "함께 관리할 회사를 선택하고 이용 권한을 확인합니다.",
  "/onboarding": "기본 정보를 입력하고 회계 시작에 필요한 내용을 준비합니다.",
  "/imports": "파일을 미리 확인한 뒤 선택한 자료만 안전하게 접수합니다.",
  "/transactions": "경제적 사건과 원본 증빙을 기록하고 확인합니다.",
  "/journals": "분개를 작성하고 별도 검토자의 승인 후 장부에 반영합니다.",
  "/ledger": "장부에 반영된 계정별 내역과 누적잔액을 확인합니다.",
  "/trial-balance": "회계기간별 차변·대변과 계정 잔액을 함께 확인합니다.",
  "/accounting": "회사의 회계 기준, 계정과목과 회계기간을 관리합니다.",
};
