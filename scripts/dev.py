"""운영체제에 관계없이 사용할 수 있는 개발 명령입니다. 저장소 루트에서 실행하세요."""

import argparse
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["env", "auth-key", "infra-start", "infra-stop", "backend-run"]
    )
    args = parser.parse_args()
    if args.command == "env":
        target = ROOT / ".env"
        if target.exists():
            parser.exit(
                message=".env 파일이 이미 있어 기존 설정을 그대로 사용합니다.\n"
            )
        shutil.copyfile(ROOT / ".env.example", target)
        content = target.read_text(encoding="utf-8")
        content = content.replace("AUTH_SIGNING_KEY=local_placeholder_generate_a_unique_key",
                                  f"AUTH_SIGNING_KEY={secrets.token_urlsafe(48)}")
        target.write_text(content, encoding="utf-8")
        return
    if args.command == "auth-key":
        target = ROOT / ".env"
        content = target.read_text(encoding="utf-8")
        if any(line.startswith("AUTH_SIGNING_KEY=") for line in content.splitlines()):
            parser.exit(message="인증 서명 키가 이미 설정되어 있습니다. 기존 키를 유지합니다.\n")
        with target.open("a", encoding="utf-8") as output:
            output.write(f"\nAUTH_SIGNING_KEY={secrets.token_urlsafe(48)}\n")
        return
    if args.command.startswith("infra-"):
        command = [
            "docker",
            "compose",
            "--env-file",
            str(ROOT / ".env"),
            "-f",
            str(ROOT / "infra/docker-compose.yml"),
        ]
        command += ["up", "-d", "--wait"] if args.command == "infra-start" else ["down"]
        subprocess.run(command, cwd=ROOT, check=True)
        return
    sys.path.insert(0, str(ROOT / "backend"))
    # backend 작업 디렉터리를 기준으로 루트의 .env 파일을 읽습니다.
    import os

    import uvicorn
    from app.core.config import load_settings

    os.chdir(ROOT / "backend")
    settings = load_settings()
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=str(settings.backend_host),
        port=settings.backend_port,
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
