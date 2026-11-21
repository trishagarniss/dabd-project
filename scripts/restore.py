"""Verify and restore a SkyPulse backup (F-17).

Usage: python -m scripts.restore --manifest backups/<stamp>/manifest.json [--target DIR]
The default target is the current project root, which simulates restoring after a
component/data loss on the same machine.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify and restore a backup")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--target", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_root = manifest_path.parent
    target_root = Path(args.target) if args.target else ROOT
    target_root = target_root if target_root.is_absolute() else ROOT / target_root
    target_root.mkdir(parents=True, exist_ok=True)

    checked, restored, mismatches = [], [], []
    for entry in manifest["files"]:
        source = source_root / entry["path"]
        relative = Path(entry["path"])
        before = sha256(target_root / relative) if (target_root / relative).exists() else None
        actual = sha256(source) if source.exists() else None
        checked.append({"path": entry["path"], "backup_sha256": entry["sha256"],
                        "source_sha256": actual, "before_sha256": before})
        if actual != entry["sha256"]:
            mismatches.append(entry["path"])
            continue
        if not args.dry_run:
            destination = target_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        restored.append({"path": entry["path"], "sha256": actual,
                         "before": before, "after": actual})

    report = {
        "backup_id": manifest.get("backup_id"),
        "restored_at": datetime.now(timezone.utc).isoformat(),
        "target": str(target_root),
        "dry_run": args.dry_run,
        "checked": len(checked),
        "restored": len(restored),
        "mismatches": mismatches,
        "status": "SUCCESS" if not mismatches else "FAILED",
        "files": restored,
    }
    evidence = ROOT / "evidence" / "restore_report.json"
    evidence.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "checked": report["checked"],
                      "restored": report["restored"], "mismatches": mismatches,
                      "report": str(evidence)}, indent=2))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
