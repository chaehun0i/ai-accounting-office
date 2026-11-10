"""Copy the local object store into a new archive and restore without overwriting files."""

import argparse
import hashlib
import json
import time
import zipfile
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def manifest(root: Path) -> dict[str, str]:
    result = {}
    for item in sorted(root.rglob("*")):
        if item.is_symlink() or not item.resolve().is_relative_to(root.resolve()):
            raise ValueError("Storage links are not allowed")
        if item.is_file():
            result[item.relative_to(root).as_posix()] = hashlib.sha256(
                item.read_bytes()
            ).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".local" / "storage")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    output = ROOT / ".local" / "release-gate" / ("storage_" + uuid4().hex[:12])
    if output.is_relative_to(source):
        parser.error("Backup destination cannot be inside the source store")
    before = manifest(source)
    if not before:
        parser.error("The store is empty; an empty backup is not a recovery proof")
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    archive = output / "objects.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as stream:
        for name in before:
            stream.write(source / name, name)
    restored = output / "restored"
    restored.mkdir()
    with zipfile.ZipFile(archive) as stream:
        for member in stream.infolist():
            target = restored / member.filename
            if member.is_dir() or not target.resolve().is_relative_to(
                restored.resolve()
            ):
                raise ValueError("Invalid archive member")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as destination:
                destination.write(stream.read(member))
    report = {
        "files": len(before),
        "source_stable": before == manifest(source),
        "restored_sha256_match": before == manifest(restored),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "duration_seconds": round(time.monotonic() - started, 2),
        "database_consistent_backup_verified": False,
    }
    (output / "storage-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    if not report["source_stable"] or not report["restored_sha256_match"]:
        raise SystemExit("Storage recovery mismatch; source was not modified")


if __name__ == "__main__":
    main()
