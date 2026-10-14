"""Content-addressed artefacts under PEGASUS_HOME (ARCHITECTURE §11.3).

An artefact is a table (Parquet) or arrays (``.npz``) with a JSON manifest. Its
address hashes the key: what it is, the data versions it read and the code
version that made it. A stale artefact is never served, because a changed input
is a different address.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
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
    tmp = path / f"table.{os.getpid()}.parquet.tmp"
    pq.write_table(table, tmp, compression="zstd")
    _manifest(path, key, meta, rows=table.num_rows)     # first: data in place implies its manifest is
    _replace(tmp, path / "table.parquet")
    return path


def get_table(kind: str, key: dict[str, Any]) -> pa.Table | None:
    path = address(kind, key) / "table.parquet"
    if not path.exists():
        return None
    _touch(path.parent)
    return pq.read_table(path)


def has_table(kind: str, key: dict[str, Any]) -> bool:
    """Whether a table is stored under the key: a path test, nothing read (``get_table`` reads the Parquet file)."""
    return (address(kind, key) / "table.parquet").exists()


def put_arrays(kind: str, key: dict[str, Any], arrays: dict[str, np.ndarray],
               meta: dict[str, Any] | None = None) -> Path:
    path = address(kind, key)
    path.mkdir(parents=True, exist_ok=True)
    tmp = path / f"arrays.{os.getpid()}.tmp.npz"      # one temporary per writer: concurrent writers of one address must not collide
    np.savez_compressed(tmp, **arrays)
    _manifest(path, key, meta)                           # first: data in place implies its manifest is
    _replace(tmp, path / "arrays.npz")
    return path


def get_arrays(kind: str, key: dict[str, Any]) -> dict[str, np.ndarray] | None:
    path = address(kind, key) / "arrays.npz"
    if not path.exists():
        return None
    _touch(path.parent)
    with np.load(path, allow_pickle=False) as data:
        return {k: data[k] for k in data.files}


def manifest(kind: str, key: dict[str, Any]) -> dict[str, Any] | None:
    """An entry's manifest, None when there is none or it cannot be read (written by another process just now)."""
    path = address(kind, key) / "manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _replace(tmp: Path, target: Path) -> None:
    """Move a finished temporary onto its address. On Windows the move fails while another process reads or
    replaces the target; the address is content-addressed, so the target that is there is the same artefact."""
    for attempt in range(5):
        try:
            tmp.replace(target)
            return
        except PermissionError:
            if attempt == 4:
                if target.exists():
                    tmp.unlink(missing_ok=True)
                    return
                raise
            time.sleep(0.5 * (attempt + 1))


_MANIFESTS: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}


def manifests(kind: str) -> list[dict[str, Any]]:
    """Every manifest of a kind (the key it was stored under, and its metadata), unordered. Each entry's is read once
    per process and kept: four readings of 13,000 manifests took 70 s of a one-state study's scope (infarto_alagoas,
    2026-10-13); an entry removed since is dropped, a new one read."""
    folder = config.home() / kind
    seen = _MANIFESTS.setdefault((str(folder), kind), {})
    try:
        names = {e.name for e in os.scandir(folder) if e.is_dir()}
    except OSError:
        return []
    for gone in set(seen) - names:
        del seen[gone]
    for name in names - set(seen):
        try:
            seen[name] = json.loads((folder / name / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue    # a manifest being written by another process, or an entry without one: read next time
    return list(seen.values())


def _manifest(path: Path, key: dict[str, Any], meta: dict[str, Any] | None, **extra: Any) -> None:
    body = {"key": key, "code_version": config.code_version(), "data_code_version": config.data_code_version(),
            "written": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **extra, **(meta or {})}
    # whole or not at all: a lane reading a manifest another writes had read half of it (the reviews, 2026-10-14)
    tmp = path / f"manifest.{os.getpid()}.json.tmp"
    tmp.write_text(json.dumps(body, indent=1, default=str), encoding="utf-8")
    _replace(tmp, path / "manifest.json")


#: The kinds `gc` may evict: caches of pegasus_data reads, rebuilt from the lake when asked again. Fits, results and
#: registers are never evicted.
CACHE_KINDS = ("gateway", "blockdata")


def _touch(entry: Path) -> None:
    """Stamp an entry as read now (its manifest's mtime), for `gc`'s least-recently-read order."""
    with contextlib.suppress(OSError):  # a manifest being written by another process
        os.utime(entry / "manifest.json")


def gc(budget_gb: float, keep_hours: float = 24.0, dry_run: bool = False) -> dict[str, Any]:
    """Evict the least recently read entries of `CACHE_KINDS` until they hold at most ``budget_gb``; an entry read or
    written within ``keep_hours`` is kept whatever the budget (a running job may be about to read it)."""
    import shutil

    entries = []
    for kind in CACHE_KINDS:
        for manifest_path in (config.home() / kind).glob("*/manifest.json"):
            entry = manifest_path.parent
            try:
                size = sum(f.stat().st_size for f in entry.iterdir())
                entries.append((manifest_path.stat().st_mtime, size, entry))
            except OSError:
                continue
    total = sum(size for _, size, _ in entries)
    cutoff, budget = time.time() - keep_hours * 3600, budget_gb * 1e9
    out = {"entries": len(entries), "bytes": total, "evicted": 0, "evicted_bytes": 0}
    for stamp, size, entry in sorted(entries, key=lambda e: e[0]):
        if total <= budget or stamp >= cutoff:
            break
        if not dry_run:
            shutil.rmtree(entry, ignore_errors=True)
        total -= size
        out["evicted"] += 1
        out["evicted_bytes"] += size
    out["bytes_after"] = total
    return out
