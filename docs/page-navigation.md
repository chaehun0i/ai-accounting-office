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

## ESG 화면 구성과 FNB 상호작용

ESG의 `frontend/src/styles/mains.css`, `PageHeader.css`, `onboardingModal.css`와 `components/Layout/HeaderNav.jsx`를 추가 확인했다. 밝은 상단 헤더, `#EFF6F1` 사이드바, 녹색 제목 표시, 접히는 메뉴 그룹, 왼쪽 온보딩 항목/오른쪽 입력 영역, 흐린 팝업 배경과 고정 헤더·하단 버튼을 ADAPT했다. 텍스트 대비를 위해 강조색은 더 진한 녹색을 사용한다. 원 프로젝트 로고·가상 프로젝트·연도 상태·Redux·ESG workflow는 가져오지 않았다.

FNB의 `frontend/package.json`, `frontend/src/app/AppShell.tsx`에서 실제 사용하는 라이브러리를 확인했다.

| 라이브러리 | 고정 버전 | 적용 책임 |
| --- | --- | --- |
| `framer-motion` | 14.1.0 | 페이지 진입 0.18초 전환, 사용자 움직임 줄이기 설정 |
| `lucide-react` | 1.55.0 | 업무 메뉴·페이지 제목·버튼의 일관된 아이콘 |
| `@radix-ui/react-dialog` | 1.1.23 | 팝업 포커스 제한, Escape, 배경 스크롤 잠금 |

FNB 버전 범위를 그대로 복사하지 않고 실제 설치 가능한 고정 버전과 lockfile을 사용한다. Bootstrap·Redux·차트·Excel JS 라이브러리는 이번 화면 동작에 필요하지 않아 추가하지 않았다. ESG의 CSS 메뉴 펼침과 팝업 진입 패턴을 재작성했고, 페이지 전환은 FNB의 Motion 패턴을 ADAPT했다. 공식 [Motion 접근성 문서](https://motion.dev/docs/react-accessibility)와 [Lucide React 문서](https://lucide.dev/guide/react)를 확인했다.

팝업 공통 계약은 `shared/ui/dialog.tsx`가 소유한다. 회사 선택·회사 생성·Excel 업로드·온보딩 완료·전표 승인/반려/장부 반영/역분개에 동일한 제목·설명·스크롤 본문·하단 버튼을 제공한다. 배경 클릭은 닫지 않으며, 처리 중에는 Escape·닫기·중복 확인을 차단한다. 닫은 뒤 열기 버튼으로 포커스를 돌린다. 승인 권한·회계 계산·정본 변경은 기존 서버 Application Command가 계속 검증한다.

데스크톱은 사이드바 축소·메뉴 그룹 펼침을 제공한다. 모바일은 상단 메뉴 버튼으로 열고, 메뉴 선택과 Escape로 닫는다. `prefers-reduced-motion`은 CSS와 Motion에 함께 적용하여 이동·확대·점멸을 끈다. 가상의 통계나 미구현 메뉴는 표시하지 않는다.

### UI/UX 보완 검증 결과

- Windows lockfile 설치는 네트워크 지연 후 `npm ci --offline --no-audit --no-fund`로 151개 패키지를 설치했다. Linux Docker의 `npm ci`는 플랫폼별 패키지를 포함하여 153개를 설치했다.
- Windows와 Linux 모두 lint·타입 검사·테스트 **14 passed**, 실패·skip 0. Windows와 Docker production build 모두 통과했다.
- 실제 Edge에서 회사 선택/생성·Excel 팝업, Tab 포커스 제한, Escape 닫기, 열기 버튼 포커스 복귀, 배경 클릭 보호를 확인했다. 메뉴 그룹·사이드바 접기/펼치기, 모바일 메뉴 선택 후 닫기, 390px 가로 넘침 방지, 움직임 줄이기도 통과했다.
- 새 확인 팝업을 포함한 거래 → 전표 → 별도 사람 승인 → 장부 반영 → 원장 → 전표 상세 새로고침 → 시산표 차변·대변 100.0000 흐름을 재검증했다.
- 최초 브라우저 검사에서 비동기 포커스 복귀 완료를 기다리지 않던 부분과 메뉴/본문의 동일 버튼 이름 선택을 수정한 후 통과했다. 화면 캡처도 팝업 진입 애니메이션 완료 후 확인했다.
- DB·Backend 업무 계약은 변경하지 않았고 회계 계산·서버 권한·승인 경계를 유지했다. 화면의 처리 중 닫기 차단은 공통 busy 계약으로 적용했다. 모든 서버 오류와 팝업 조합을 브라우저에서 전수 검증했다는 의미는 아니다.
