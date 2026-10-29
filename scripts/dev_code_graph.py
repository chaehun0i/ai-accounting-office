"""Build and query a local, code-only Graphify map of tracked backend sources."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / ".local" / "code-graph"
GRAPH = STATE / "graphify-out" / "graph.json"
PREVIOUS_GRAPH = ROOT / ".local/tool-evaluation/graphify-result/graphify-out/graph.json"
SOURCES = ("backend/app/", "backend/migrations/versions/")


def graphify_executable() -> str:
    configured = os.environ.get("GRAPHIFY_EXE")
    candidates = [
        Path(configured) if configured else None,
        ROOT / ".local/tool-evaluation/graphify-env/Scripts/graphify.exe",
        ROOT / ".local/tool-evaluation/graphify-env/bin/graphify",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return str(candidate)
    installed = shutil.which("graphify")
    if installed:
        return installed
    raise SystemExit(
        "Graphify가 없습니다. GRAPHIFY_EXE에 격리 설치된 실행 파일을 지정하세요."
    )


def code_files() -> list[Path]:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "ls-files", "-z", *SOURCES],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        if relative.suffix != ".py" or not relative.as_posix().startswith(SOURCES):
            continue
        source = ROOT / relative
        if (
            source.is_file()
            and not source.is_symlink()
            and source.resolve().is_relative_to(ROOT)
        ):
            paths.append(relative)
    return paths


def safe_environment() -> dict[str, str]:
    blocked = (
        "TOKEN",
        "SECRET",
        "PASSWORD",
        "API_KEY",
        "OPENAI",
        "ANTHROPIC",
        "GEMINI",
        "GOOGLE",
        "AWS_",
        "AZURE_",
        "MOONSHOT",
        "DEEPSEEK",
    )
    return {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in blocked)
        and key.upper() != "GRAPHIFY_BACKEND"
    }


def graph_path() -> Path:
    configured = os.environ.get("GRAPHIFY_GRAPH")
    for candidate in (Path(configured) if configured else None, GRAPH, PREVIOUS_GRAPH):
        if candidate and candidate.is_file():
            return candidate
    raise SystemExit("그래프가 없습니다. 먼저 rebuild를 실행하세요.")


def rebuild() -> None:
    executable = graphify_executable()
    STATE.mkdir(parents=True, exist_ok=True)
    files = code_files()
    if not files:
        raise SystemExit("분석할 tracked 백엔드 Python 파일이 없습니다.")
    with TemporaryDirectory(prefix="corpus-", dir=STATE) as directory:
        corpus = Path(directory)
        for relative in files:
            target = corpus / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        subprocess.run(
            [
                executable,
                "extract",
                str(corpus),
                "--code-only",
                "--no-cluster",
                "--max-workers",
                "2",
                "--force",
                "--out",
                str(STATE),
            ],
            check=True,
            cwd=ROOT,
            env=safe_environment(),
        )
    if not GRAPH.is_file():
        raise SystemExit("Graphify가 graph.json을 생성하지 않았습니다.")
    print(f"분석 완료: {len(files)}개 Python 파일 → {GRAPH}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rebuild")
    sub.add_parser("status")
    for name, count in (("query", 1), ("explain", 1), ("path", 2)):
        command = sub.add_parser(name)
        command.add_argument("terms", nargs=count)
    args = parser.parse_args()
    if args.command == "rebuild":
        rebuild()
        return
    graph_file = graph_path()
    if args.command == "status":
        graph = json.loads(graph_file.read_text(encoding="utf-8"))
        print(f"{graph_file}: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
        return
    subprocess.run(
        [graphify_executable(), args.command, *args.terms, "--graph", str(graph_file)],
        check=True,
        cwd=ROOT,
        env=safe_environment(),
    )


if __name__ == "__main__":
    main()
