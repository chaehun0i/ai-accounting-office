# 개발 도구 통합과 검증 경계

이 문서는 개발 환경 도구만 다룬다. 회계 데이터의 정본은 PostgreSQL이며, 개발용 코드 그래프와 Agent 메모리는 회계 원장이나 감사 기록을 대신하지 않는다.

## 바로 사용할 수 있는 코드 그래프

Graphify v0.9.97을 격리 설치한 환경에서 `python scripts/dev_code_graph.py rebuild`로 tracked 백엔드 Python 495개 파일만 분석했다. 결과는 3,591개 노드와 14,669개 연결이었다. 기존 그래프도 `status`와 `explain ToolRegistry`로 재사용했다. 코드는 `.local/code-graph/`로만 출력하며, `.env`, 로컬 설계 정본, 사용자 자료, DB는 입력하지 않는다. 자동 hook은 없다.

Codex는 `.agents/skills/accounting-code-graph/SKILL.md`를 사용한다. Graphify 실행 파일을 별도 설치한 뒤 `GRAPHIFY_EXE`로 지정하고 다음 명령을 실행한다. 다른 worktree의 그래프를 읽을 때는 `GRAPHIFY_GRAPH`를 지정할 수 있다.

```powershell
python scripts/dev_code_graph.py status
python scripts/dev_code_graph.py query "journal ledger"
python scripts/dev_code_graph.py explain ToolRegistry
python scripts/dev_code_graph.py rebuild
```

그래프의 `INFERRED` 연결은 추정이다. 예를 들어 `ToolRegistry`에서 `backend/app/tools/adapters/mcp.py`와 `backend/app/agents/runtime/service.py`로 이어지는 관계는 실제 import와 실행 경계를 소스에서 확인해야 한다. 코드 변경 후 수동으로 `rebuild`한다. Graphify는 개발용 탐색 도구로 유지한다.

## 격리 실험과 채택 판단

| 도구 | 실제 검증 | 현재 판단 |
| --- | --- | --- |
| AI Memory v3.2.9 | 더미 프로젝트에서 MCP 저장 → 새 프로세스 검색·읽기 → 인수인계 수락 → 수정·삭제를 확인했다. 자동 capture와 전역 설정은 사용하지 않았다. | 프로젝트 자동 연결 보류. `ignore_paths`는 모든 shell/미지 도구 호출에 강제 적용되지 않아 민감 정보 제외를 보증할 수 없다. 수동 allowlist 입력만 별도 검토 가능. |
| OpenCode v1.19.5 | Windows CLI 실행과 도움말을 확인했다. | 무료 로컬 모델이나 이미 승인된 provider가 없어 코드 수정 품질·비용 비교는 미검증. Codex를 기본 도구로 유지. |
| Orca v1.4.243 | Windows 설치 파일만 확보했다. | 설치·병렬 Agent 실험 미수행. 현재 Git worktree/Codex 작업 분배와 겹쳐 보류. |
| Ruflo v3.63.7 | `.local` 격리 환경에서 CLI 실행과 최소 초기화가 성공했다. | 제품 런타임 도입 보류. 최소 초기화도 `hooks.enabled: true`를 기록하며 Agent routing, memory, MCP의 기존 구조와 책임이 겹친다. 데몬·실제 모델 호출은 하지 않았다. |
| Claude Plugins Official | 구조와 Skill 패턴을 검토했다. | Claude 전용 hook/command는 가져오지 않고, 저장소 범위 Skill만 사용. |
| REA / HyperFrames / ComfyUI | 적용 시나리오와 리소스·보안 경계를 검토했다. | 역공학, 영상, 생성 미디어는 현재 회계 개발 경로에 직접 필요하지 않아 설치 보류. |

AI Memory 더미 데이터는 `.local/tool-evaluation/` 및 임시 디렉터리에만 있다. 해당 실험에서 `.env`와 비공개 설계 문서의 sentinel이 저장되지 않은 것은 자동 수집을 꺼둔 조건의 결과다. 자동 수집을 켠 환경의 제외 보증으로 해석하지 않는다. 실험 복구는 격리 폴더를 삭제하면 되며, 글로벌 Codex 설정·시작 프로그램은 변경하지 않았다.

## 정적 보안 점검

Cloudflare Security Audit Skill의 격리 조건을 갖춘 전체 감사는 수행하지 않았다. 아래는 실제 소스를 확인한 표본 점검이다. 재현 테스트는 `backend/tests/unit/test_tool_permission_refresh.py`에 있다.

| 경계 | 확인한 근거 | 결과 |
| --- | --- | --- |
| 사용자·회사 권한 | `backend/app/companies/application/service.py`의 `validate_principal`, `require_company` | 활성 세션, 회사 소속, permission 확인 경로가 있다. 모든 API 호출의 누락 여부는 별도 전체 감사 필요. |
| Agent/MCP Tool 권한 | `backend/app/tools/registry.py`의 `execute`, `backend/app/tools/adapters/mcp.py` | Tool 발견 뒤 권한이 철회돼도 실행 시 다시 거부하고 감사 오류 코드를 남기는 단위 테스트 통과. MCP transport 전체 동적 검증은 이번 범위에서 미수행. |
| 회계 변경 범위 | `backend/app/tools/registry.py` | Tool effect 제한과 금지된 기표·마감·지급 작업이 등록 경계에 있다. 신규 Tool 추가 시 재검토 필요. |
| 입력·SQL | Tool Pydantic 검증과 선택한 Repository의 바인딩 사용을 표본 확인 | 해당 표본의 직접 문자열 결합 SQL은 발견하지 않았다. 전체 SQL injection 감사로 표시하지 않는다. |
| Prompt injection | `backend/app/llm/providers/gemini.py`의 사실 데이터 처리 및 출력 스키마 | 방어 경로는 있으나 적대적 입력의 전체 동적 검증은 필요하다. |
| 로그·오류 | `backend/app/core/logging.py`, `backend/app/core/errors.py` | 초대 capability와 일반 500 오류 노출을 제한하는 경로가 있다. 로그 전체 필드의 민감 정보 감사를 완료한 것은 아니다. |

확인된 신규 취약점은 없다. 위 표본 밖의 회사 격리, 외부 MCP 호출, dependency 공급망, prompt injection, 감사 로그 누락은 격리된 전체 감사의 후속 범위다. 파괴적 서비스 테스트는 하지 않았다.

## 개발 중 사용 절차

1. 구조를 찾을 때 코드 그래프 Skill로 검색하고, 연결된 실제 소스와 권한 경계를 확인한다.
2. 코드가 바뀐 뒤 필요한 경우에만 그래프를 수동 재분석한다.
3. AI Memory와 Ruflo는 프로젝트 자동 실행에 연결하지 않는다. 실험이 필요하면 별도 더미 프로젝트에서 수행한다.
4. Tool/MCP 권한을 수정할 때 권한 철회 회귀 테스트와 기존 Agent Tool 집중 테스트를 실행한다.

Graphify 격리 설치가 없는 개발 머신은 실행 파일을 먼저 준비해야 한다. 현재 설치 결과와 격리 실험 산출물은 Git에 포함하지 않는다.
