# 업무별 페이지와 공통 내비게이션

기존 한 화면의 기능을 Next.js App Router의 독립 경로로 분리했다. 공통 layout의 AuthProvider·CompanyProvider가 로그인과 선택한 회사를 유지한다. 각 페이지는 필요한 기능만 렌더링하며 회사가 바뀌면 이전 회사의 기능 상태를 폐기한다. DB·Backend 계약과 권한 검증은 변경하지 않았다.

| 경로 | 업무 |
| --- | --- |
| `/` | 업무 홈과 이용 가능한 업무 바로가기 |
| `/companies` | 회사 선택·생성·역할 안내 |
| `/onboarding` | 회계 준비와 초안 입력 |
| `/imports` | 파일 업로드·미리보기·접수 |
| `/transactions` | 거래 입력·조회 |
| `/journals` | 전표 작성·제출·승인·장부 반영 |
| `/ledger` | 계정별 총계정원장 |
| `/trial-balance` | 기간별 합계잔액시산표 |
| `/accounting` | 회계 설정·계정과목·회계기간 |

메뉴 그룹과 permission 계약은 `features/navigation/routes.ts` 한 곳에서 관리한다. 회사 미선택과 권한 부족을 구분해 안내하며 직접 URL 진입에도 같은 화면 접근 검사를 적용한다. 실제 데이터 권한은 기존 Backend가 계속 검증한다. 페이지 이동 시 로그인·회사 context는 유지하지만 저장하지 않은 개별 입력폼의 내용은 유지하지 않으므로 저장 후 이동한다. 여러 회사 사용자가 새로고침하면 회사 선택을 다시 확인한다.

원장·시산표는 같은 조회 컴포넌트를 mode로 재사용하면서 각 API와 표를 독립적으로 표시한다. 원장 전표 링크는 `/journals#journal-UUID`로 연결한다. 전표 페이지 첫 진입·새로고침과 hash 변경 모두 회사 범위로 상세를 조회한다. 금액 계산과 승인 상태를 Frontend가 변경하지 않는다.

## 실제 참고 코드

직접 COPY한 코드는 없다. 화면 구조만 PATTERN으로 참고하고 현재 Next.js·UUID·permission 계약으로 신규 작성했다.

| 출처 | 확인 revision·파일 | 참고한 패턴과 제외한 부분 |
| --- | --- | --- |
| WITH ESG | `720e33c7923a679c2cff694ca12c9f92646ed06b`, `frontend/src/components/Layout/SidebarNav.jsx` | 업무별 메뉴 그룹·회사 context·현재 위치. React Router·역할 문자열 권한 검사·ESG workflow는 제외 |
| 햇들 | `516449c08feb3d065d36d6c556eb59d14625d5d8`, `frontend/src/components/Sidebar.tsx` | 공통 사이드바·홈으로 돌아가기·계정과 권한 안내. Agent·재무 시뮬레이션·UI 전용 권한 체계는 제외 |
| FNB | `1ccb790f1b8b79863fbd42e727287dee65aca866`, `frontend/src/app/App.tsx` | 공통 shell·기능별 화면 경계·로딩/오류 처리. hash 기반 전체 routing·VOC·Incident·Agent 화면은 제외 |

## 검증

- Frontend test: **14 passed**, 실패·skip 0.
- `npm run lint`, `npm run typecheck`, `npm run build`: 통과. 홈을 포함한 업무 경로 9개 생성.
- Compose production 이미지 build와 네 서비스 healthy 확인.
- `navigation-browser-smoke.cjs`: 기존 로컬 계정으로 메뉴 이동, 현재 위치, 새로고침 인증 복구, 관리자 파일 업로드 페이지 접근 제한, 모바일 390px 가로 넘침 검사 통과.
- `accounting-browser-smoke.cjs --allow-synthetic`: 분리된 거래 → 전표 → 별도 사용자 승인 → 장부 반영 → 원장 → 전표 상세 이동·새로고침 → 시산표에서 차변·대변 각 100.0000 검증 통과.

브라우저 스크립트는 설치된 Playwright 경로를 `PLAYWRIGHT_MODULE_PATH`로 지정한다. 화면 주소는 `ACCOUNTING_BROWSER_ORIGIN=http://localhost:3000`, API 주소는 `ACCOUNTING_API_ORIGIN=http://127.0.0.1:8000`을 사용했다. 계정 준비·비밀번호 보관은 README의 로컬 테스트 절차를 따른다. 스크립트는 비밀번호를 출력하지 않는다.
