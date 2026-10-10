import type { Field } from "./model";

const labels: Record<string,string> = {
 CORPORATION:"법인", INDIVIDUAL:"개인", BUSINESS:"사업자", OTHER:"기타", KRW:"대한민국 원 (KRW)",
 ASSET:"자산", LIABILITY:"부채", EQUITY:"자본", REVENUE:"수익", EXPENSE:"비용", DEBIT:"차변", CREDIT:"대변",
 K_GAAP:"일반기업회계기준", K_IFRS:"한국채택국제회계기준", STANDARD:"기본 보고 분류", "Asia/Seoul":"대한민국 표준시",
 CUSTOMER:"고객", SUPPLIER:"공급업체", PAYEE:"지급 대상", TAX_COUNTERPARTY:"세무 거래처",
 STRAIGHT_LINE:"정액법", FIFO:"선입선출법", WEIGHTED_AVERAGE:"가중평균법",
};
export function FieldEditor({ field, value, options, disabled, onChange }: {
  field: Field; value: string | boolean; options?: string[]; disabled: boolean; onChange: (value: string | boolean) => void;
}) {
  return <label>{field.label}
    {field.field_code === "Accounting_Settings.fiscal_year_start_month" ? <select value={String(value).replace(/\.0+$/, "")} disabled={disabled} onChange={e => onChange(e.target.value)}>
      <option value="">선택해 주세요</option>{Array.from({ length: 12 }, (_, index) => String(index + 1)).map(month => <option key={month} value={month}>{month}월</option>)}
    </select> : field.data_type === "BOOLEAN" ? <select value={value === "" ? "" : String(value)} disabled={disabled} onChange={e => onChange(e.target.value === "" ? "" : e.target.value === "true")}>
      <option value="">선택해 주세요</option><option value="true">예</option><option value="false">아니요</option>
    </select> : options ? <select disabled={disabled} value={String(value)} onChange={e => onChange(e.target.value)}>
      <option value="">선택해 주세요</option>{options.map(v => <option key={v} value={v}>{labels[v] ?? v}</option>)}
    </select> : <input disabled={disabled} type={field.data_type === "DATE" ? "date" : "text"} inputMode={field.data_type === "NUMERIC" ? "decimal" : "text"}
      value={String(value)} onChange={e => onChange(e.target.value)} maxLength={500} />}
  </label>;
}
