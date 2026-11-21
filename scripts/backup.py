"""Create a checksummed local backup of all state required by F-17.

State: object data (Bronze/Silver/Gold/Reference), catalog + lineage, broker offsets,
model registry/artifacts, configuration and evidence. No cloud storage is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = [
    "data/bronze", "data/silver", "data/gold", "data/reference", "data/lineage",
    "data/state", "config", "src/ml/models", "src/ml/experiments",
    "src/ml/tracking_store", "evidence", ".env.example", "docker-compose.yml",
    "requirements.txt", "pytest.ini",
]
EXCLUDE_PARTS = {"coverage_html", "__pycache__", ".pytest_cache", "throughput_run", "warmup"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup SkyPulse local state")
    parser.add_argument("--output", default=None, help="Backup directory (default: backups/<utc-stamp>)")
    parser.add_argument("--keep", type=int, default=1,
                        help="Number of backups to retain in backups/ (newest included). 0 disables pruning.")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = Path(args.output) if args.output else ROOT / "backups" / stamp
    output = output if output.is_absolute() else ROOT / output
    output.mkdir(parents=True, exist_ok=True)

    files = []
    for relative in INCLUDE:
        source = ROOT / relative
        if not source.exists():
            continue
        if source.is_file():
            candidates = [source]
        else:
            candidates = [p for p in source.rglob("*")
                          if p.is_file() and not EXCLUDE_PARTS.intersection(p.parts)]
        for path in candidates:
            # Self-referential: the manifest records the hash of this file, which
            # changes when we write the latest manifest. Exclude it from checksums.
            if path.relative_to(ROOT).as_posix() == "evidence/backup_manifest_latest.json":
                continue
            target = output / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            files.append({
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            })

    manifest = {
        "backup_id": stamp,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": sorted(files, key=lambda item: item["path"]),
        "database_note": "PostgreSQL is rebuilt from config/init_db.sql; run pg_dump separately for production data.",
    }
    payload = json.dumps(manifest, indent=2)
    (output / "manifest.json").write_text(payload, encoding="utf-8")
    (ROOT / "evidence" / "backup_manifest_latest.json").write_text(payload, encoding="utf-8")
    pruned = []
    if args.keep > 0:
        backup_root = ROOT / "backups"
        if backup_root.exists():
            older = [p for p in backup_root.iterdir()
                     if p.is_dir() and p != output and (p / "manifest.json").exists()]
            older.sort(key=lambda p: p.name, reverse=True)
            for stale in older[max(0, args.keep - 1):]:
                shutil.rmtree(stale)
                pruned.append(stale.name)

    print(json.dumps({"backup": str(output), "file_count": len(files),
                      "total_bytes": manifest["total_bytes"], "kept": args.keep,
                      "pruned": pruned}, indent=2))


if __name__ == "__main__":
    main()
