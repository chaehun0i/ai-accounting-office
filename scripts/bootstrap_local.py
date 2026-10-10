"""로컬 API로 관리자·회계 담당자와 테스트 회사를 준비합니다. 권한을 우회하지 않습니다."""

import argparse
import configparser
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS = ROOT / ".local/development-accounts.ini"


class ApiFailure(Exception):
    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"로컬 계정 준비 요청이 실패했습니다. HTTP {status}")


def request(origin: str, path: str, data=None, *, token=None, company=None):
    headers = {"X-CSRF-Protection": "1", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if company:
        headers["X-Company-ID"] = company
    payload = json.dumps(data).encode() if data is not None else None
    try:
        with urlopen(
            Request(origin + path, data=payload, headers=headers), timeout=30
        ) as response:
            body = response.read()
            return json.loads(body) if body else None
    except HTTPError as error:
        # 응답 원문·토큰·비밀번호를 진단 메시지에 포함하지 않습니다.
        raise ApiFailure(error.code) from None


def prepare(origin: str) -> None:
    parsed = urlsplit(origin)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("로컬 HTTP 서버 주소만 사용할 수 있습니다.")
    if (
        parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("경로나 로그인 정보가 없는 로컬 서버 주소를 사용해 주세요.")
    config = configparser.ConfigParser()
    if ACCOUNTS.exists():
        config.read(ACCOUNTS, encoding="utf-8")
    else:
        for label, email, role in (
            ("회사 관리자", "local-owner@example.com", "OWNER"),
            ("회계 담당자", "local-accountant@example.com", "ACCOUNTANT"),
        ):
            config[label] = {
                "이메일": email,
                "비밀번호": secrets.token_urlsafe(24),
                "역할": role,
            }
        ACCOUNTS.parent.mkdir(exist_ok=True)
        with ACCOUNTS.open("x", encoding="utf-8") as output:
            config.write(output)
        os.chmod(ACCOUNTS, 0o600)

    sessions = []
    try:
        for label in ("회사 관리자", "회계 담당자"):
            values = config[label]
            credentials = {"email": values["이메일"], "password": values["비밀번호"]}
            try:
                result = request(origin, "/auth/login", credentials)
            except ApiFailure as error:
                if error.status != 401:
                    raise
                result = request(origin, "/auth/register", credentials)
            sessions.append(result["access_token"])
        owner, accountant = sessions
        companies = request(origin, "/companies", token=owner)
        company = next(
            (c for c in companies if c["company_name"] == "로컬 회계 테스트 회사"), None
        )
        year = datetime.now(UTC).year
        if company is None:
            company = request(
                origin,
                "/companies",
                {
                    "company_name": "로컬 회계 테스트 회사",
                    "business_number": "1234567890",
                    "taxpayer_type": "INDIVIDUAL",
                    "opening_date": f"{year}-01-01",
                    "address": "로컬 합성 테스트 주소",
                },
                token=owner,
            )
        company_id = company["id"]
        accessible = request(origin, "/companies", token=accountant)
        if not any(c["id"] == company_id for c in accessible):
            invitation = request(
                origin,
                f"/companies/{company_id}/invitations",
                {
                    "email": config["회계 담당자"]["이메일"],
                    "role_code": "ACCOUNTANT",
                },
                token=owner,
            )
            request(
                origin,
                "/invitations/" + invitation["invite_token"] + "/accept",
                {},
                token=accountant,
            )
        try:
            request(origin, "/accounting/settings", token=owner, company=company_id)
        except ApiFailure as error:
            if error.status != 404:
                raise
            templates = request(
                origin, "/account-templates", token=owner, company=company_id
            )
            if not templates:
                raise ValueError("기본 계정과목 양식이 준비되지 않았습니다.")
            request(
                origin,
                "/accounting/initialize",
                {"fiscal_year": year, "template_id": templates[0]["id"]},
                token=owner,
                company=company_id,
            )
        print("로컬 테스트 회사와 계정을 준비했습니다.")
        print("관리자: local-owner@example.com / 회사 설정·승인·장부 반영")
        print("회계 담당자: local-accountant@example.com / 자료 업로드·거래·전표 작성")
        print("각 계정의 비밀번호는 " + str(ACCOUNTS) + "에서 확인하세요.")
    finally:
        for token in sessions:
            request(origin, "/auth/logout", {}, token=token)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://localhost:8000")
    args = parser.parse_args()
    try:
        prepare(args.origin)
    except (ApiFailure, OSError, ValueError, KeyError, configparser.Error):
        parser.exit(
            1,
            "계정 준비를 완료하지 못했습니다. Compose 상태와 기존 계정 파일을 확인해 주세요. 비밀번호 파일은 자동으로 덮어쓰지 않습니다.\n",
        )


if __name__ == "__main__":
    main()
