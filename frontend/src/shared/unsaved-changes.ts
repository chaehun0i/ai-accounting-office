// 페이지 이동·회사 전환·로그아웃이 동일한 미저장 확인을 사용합니다.
export const beforeLeaveEvent = "office:before-leave";
export function canLeavePage() {
  return window.dispatchEvent(new Event(beforeLeaveEvent, { cancelable: true }));
}
