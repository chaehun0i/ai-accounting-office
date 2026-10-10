// 입력률이 아닌 서버의 준비 상태를 기준으로 다음 동작을 안내합니다.
export function workspaceGuidance(status: string, dirty: boolean, canEdit: boolean) {
  if (status === "COMPLETED") return { title: "회계 준비를 마쳤습니다", description: "저장한 정보를 확인할 수 있습니다. 거래와 전표 입력을 시작해 보세요." };
  if (!canEdit) return { title: "입력 내용을 확인할 수 있습니다", description: "수정이 필요하면 회사 관리자 또는 입력 담당자에게 요청해 주세요." };
  if (dirty) return { title: "변경 내용을 먼저 저장해 주세요", description: "아직 저장되지 않은 내용이 있습니다. 저장한 뒤 입력 내용에 빠진 것이 없는지 확인해 보세요." };
  if (status === "READY_TO_COMPLETE") return { title: "회계를 시작할 준비가 되었습니다", description: "내용을 확인했다면 회계 준비를 완료해 주세요. 기초잔액의 장부 반영은 별도 전표와 승인이 필요합니다." };
  if (status === "REVIEW_REQUIRED") return { title: "확인이 필요한 내용이 있습니다", description: "입력 내용 확인을 눌러 안내를 확인하고, 해당 항목을 보완해 주세요." };
  return { title: "회사정보부터 차례로 확인해 주세요", description: "입력한 내용을 저장한 뒤 ‘입력 내용 확인’으로 빠진 항목이나 오류를 확인할 수 있습니다." };
}
export function sectionStatus(section: { code: string; status: string; total: number }) {
  if (section.code === "COA") return "준비된 계정목록";
  if (section.status === "WARNING") return "확인 필요";
  if (section.total === 0) return "내용 확인";
  return ({ COMPLETE: "입력 완료", IN_PROGRESS: "작성 중", EMPTY: "입력 전" } as Record<string, string>)[section.status] ?? "내용 확인";
}
