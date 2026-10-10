// 새 선택·사용자 변경 이후 도착한 이전 회사 응답을 버립니다.
export class SelectionGate {
  private generation = 0;
  next(): number { return ++this.generation; }
  accepts(value: number): boolean { return value === this.generation; }
}
export type Company = {
  id: string; company_name: string; role_code: string; permissions: string[];
  version: number; business_number: string; address: string;
};
export function filterCompanies(companies: Company[], search: string): Company[] {
  return companies.filter(company => company.company_name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
}

export function roleGuide(role: string): string {
  const guides: Record<string, string> = {
    OWNER: "회사 관리자 · 회사 설정, 전표 승인과 장부 반영을 할 수 있습니다. 거래·전표 작성과 자료 업로드는 회계 담당자 계정을 이용해 주세요.",
    ADMIN: "회사 운영 관리자 · 회사 정보와 구성원을 관리합니다. 회계 작성·승인은 해당 역할의 계정을 이용해 주세요.",
    ACCOUNTANT: "회계 담당자 · 자료 업로드, 거래와 전표 작성, 제출을 할 수 있습니다. 제출한 전표는 별도 검토자의 승인이 필요합니다.",
    REVIEWER: "회계 검토자 · 제출된 전표를 검토·승인하고 장부에 반영할 수 있습니다.",
    TAX_ACCOUNTANT: "세무 담당자 · 허용된 자료 업로드와 세무 업무를 담당합니다.",
    TAX_REVIEWER: "세무 검토자 · 허용된 세무 검토 업무를 담당합니다.",
    VIEWER: "조회자 · 허용된 회계 정보를 조회할 수 있습니다.",
    AUDITOR: "감사자 · 허용된 회계 기록을 조회할 수 있습니다.",
  };
  return guides[role] ?? "이 회사에서 허용된 기능을 이용할 수 있습니다. 권한 변경은 회사 관리자에게 문의해 주세요.";
}
