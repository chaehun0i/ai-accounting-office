// 표시 과정에서도 부동소수점으로 변환하지 않고 정확한 소수부를 유지합니다.
export function displayAmount(value: string): string {
  if (!/^-?\d+(\.\d{1,4})?$/.test(value)) return "금액 확인 필요";
  const [whole, fraction = ""] = value.split(".");
  const grouped = (whole.startsWith("-") ? "-" : "") + BigInt(whole.replace("-", "")).toLocaleString("ko-KR");
  const tail = fraction.replace(/0+$/, "");
  return grouped + (tail ? `.${tail}` : "");
}
