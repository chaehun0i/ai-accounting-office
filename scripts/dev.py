"""운영체제에 관계없이 사용할 수 있는 개발 명령입니다. 저장소 루트에서 실행하세요."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["env", "infra-start", "infra-stop", "backend-run"]
    )
    args = parser.parse_args()
    if args.command == "env":
        target = ROOT / ".env"
        if target.exists():
            parser.exit(
                message=".env 파일이 이미 있어 기존 설정을 그대로 사용합니다.\n"
            )
        shutil.copyfile(ROOT / ".env.example", target)
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
