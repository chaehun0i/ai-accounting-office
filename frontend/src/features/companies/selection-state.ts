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
