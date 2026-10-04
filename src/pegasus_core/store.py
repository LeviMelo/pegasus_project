"""Content-addressed artefacts under PEGASUS_HOME (ARCHITECTURE §11.3).

An artefact is a table (Parquet) or arrays (``.npz``) with a JSON manifest. Its
address hashes the key: what it is, the data versions it read and the code
version that made it. A stale artefact is never served, because a changed input
is a different address.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import config


def address(kind: str, key: dict[str, Any]) -> Path:
    digest = hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()[:20]
    return config.home() / kind / digest


def put_table(kind: str, key: dict[str, Any], table: pa.Table, meta: dict[str, Any] | None = None) -> Path:
    path = address(kind, key)
    path.mkdir(parents=True, exist_ok=True)
    tmp = path / "table.parquet.tmp"
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(path / "table.parquet")
    _manifest(path, key, meta, rows=table.num_rows)
    return path


def get_table(kind: str, key: dict[str, Any]) -> pa.Table | None:
    path = address(kind, key) / "table.parquet"
    return pq.read_table(path) if path.exists() else None


def put_arrays(kind: str, key: dict[str, Any], arrays: dict[str, np.ndarray],
               meta: dict[str, Any] | None = None) -> Path:
    path = address(kind, key)
    path.mkdir(parents=True, exist_ok=True)
    tmp = path / "arrays.tmp.npz"
    np.savez_compressed(tmp, **arrays)
    tmp.replace(path / "arrays.npz")
    _manifest(path, key, meta)
    return path


def get_arrays(kind: str, key: dict[str, Any]) -> dict[str, np.ndarray] | None:
    path = address(kind, key) / "arrays.npz"
    if not path.exists():
        return None
    with np.load(path, allow_pickle=False) as data:
        return {k: data[k] for k in data.files}


def manifest(kind: str, key: dict[str, Any]) -> dict[str, Any] | None:
    path = address(kind, key) / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _manifest(path: Path, key: dict[str, Any], meta: dict[str, Any] | None, **extra: Any) -> None:
    body = {"key": key, "code_version": config.code_version(), "data_code_version": config.data_code_version(),
            "written": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **extra, **(meta or {})}
    (path / "manifest.json").write_text(json.dumps(body, indent=1, default=str), encoding="utf-8")
