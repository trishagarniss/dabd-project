"""Versioned Parquet storage with idempotent upsert and snapshot metadata (F-06, F-07)."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.common.config import MAX_SNAPSHOT_VERSIONS, utcnow_iso


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_sha(df: pd.DataFrame) -> str:
    # JSON serialisation also handles nested list/dict cells (e.g. raw DLQ payloads).
    payload = json.dumps(df.to_dict("records"), default=str, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    """Make nested cells hashable/parquet-safe before dedup and snapshot writes."""
    out = frame.copy()
    for column in out.columns:
        sample = out[column].dropna()
        if len(sample) and isinstance(sample.iloc[0], (list, tuple, dict, np.ndarray)):
            out[column] = out[column].apply(
                lambda value: json.dumps(value, default=str, sort_keys=True)
                if isinstance(value, (list, tuple, dict, np.ndarray)) else value
            )
    return out


def read_latest(dataset_path: Path) -> pd.DataFrame:
    """Read a dataset written by write_snapshot, or a plain parquet/csv file."""
    flat = dataset_path.with_suffix(".parquet") if dataset_path.suffix == "" else dataset_path
    if flat.exists():
        return pd.read_parquet(flat)
    if dataset_path.exists() and dataset_path.is_dir():
        parts = sorted(dataset_path.glob("part-*.parquet"))
        if parts:
            return pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    csv = dataset_path.with_suffix(".csv")
    if csv.exists():
        return pd.read_csv(csv)
    return pd.DataFrame()


def snapshot_info(dataset_path: Path) -> dict[str, Any]:
    meta_file = dataset_path.with_suffix(".snapshot.json") if dataset_path.suffix == "" else dataset_path.with_suffix(".json")
    if meta_file.exists():
        return json.loads(meta_file.read_text(encoding="utf-8"))
    flat = dataset_path.with_suffix(".parquet")
    if flat.exists():
        return {"version": "flat", "sha256": _sha256(flat), "row_count": len(pd.read_parquet(flat))}
    return {"version": None, "row_count": 0}


def write_snapshot(df: pd.DataFrame, dataset_path: Path, keys: list[str] | None = None,
                   description: str = "") -> dict[str, Any]:
    """Write a versioned parquet snapshot; optionally merge on business keys (upsert)."""
    dataset_path = Path(dataset_path)
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    df = _normalise(df)

    if keys:
        existing = _normalise(read_latest(dataset_path))
        if not existing.empty and all(k in existing.columns for k in keys):
            if "updated_at" in df.columns and "updated_at" in existing.columns:
                combined = pd.concat([existing, df], ignore_index=True)
                combined = combined.sort_values("updated_at").drop_duplicates(keys, keep="last")
            else:
                combined = pd.concat([df, existing], ignore_index=True).drop_duplicates(keys, keep="first")
            df = combined.reset_index(drop=True)

    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    version_dir = dataset_path / f"version={version}"
    version_dir.mkdir(parents=True, exist_ok=True)
    part = version_dir / "part-00000.parquet"

    # Serialize once, then copy for the immutable version: writing Parquet twice
    # doubled the cost of every global-coverage stream flush.
    flat = dataset_path.with_suffix(".parquet")
    tmp = dataset_path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    shutil.move(str(tmp), str(flat))
    shutil.copyfile(flat, part)

    # Keep a small rolling window of versions. Streaming writes a snapshot every
    # flush, so unbounded version directories would dominate disk and backups.
    versions = sorted(dataset_path.glob("version=*"), key=lambda p: p.name, reverse=True)
    for stale in versions[MAX_SNAPSHOT_VERSIONS:]:
        shutil.rmtree(stale, ignore_errors=True)

    meta = {
        "version": version,
        "description": description,
        "row_count": int(len(df)),
        "sha256": _sha256(flat),
        "content_sha256": _file_sha(df),
        "columns": [str(c) for c in df.columns],
        "written_at": utcnow_iso(),
        "keys": keys or [],
        "snapshots": sorted(p.name for p in dataset_path.glob("version=*")),
    }
    meta_file = dataset_path.with_suffix(".snapshot.json")
    meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def append_jsonl(path: Path, records: list[dict] | dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(records, dict):
        records = [records]
    with path.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    # Multiple processes (API container + local tests) may append concurrently;
    # skip a line that was captured mid-write instead of failing the reader.
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
