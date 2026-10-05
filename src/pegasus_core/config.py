"""Homes, versions and seeds (ARCHITECTURE §11.1, §11.3).

PegaSUS writes only under ``PEGASUS_HOME``. pegasus_data is reached through its
API with two roots: ``PEGASUS_DATA_ROOT``, where PegaSUS's own queries fetch
and build (never pegasus_data's maintainer home), and ``PEGASUS_POPULATION_ROOT``,
read for population series already built there.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from functools import cache, lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def home() -> Path:
    path = Path(os.environ.get("PEGASUS_HOME", REPO / "pegasus_home"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_root() -> str:
    return os.environ.get("PEGASUS_DATA_ROOT", "C:/Users/Galaxy/pegasus_core_data")


def population_root() -> str:
    return os.environ.get("PEGASUS_POPULATION_ROOT",
                          "C:/Users/Galaxy/LEVI/projects/pegasus_data/pegasus_data_home")


def population_source() -> str:
    """The exposure the gateway reads unless a call names one: ``popsvs`` (IBGE's projection as the MoH
    distributes it) ``account-2`` (pegasus_data's modelled population account, with intervals; ADR-0010) or ``account-3`` / ``account-4``
    (its complete tensor, single ages; ADR-0010 amended)."""
    return os.environ.get("PEGASUS_POPULATION", "popsvs")


def population_pinned() -> str | None:
    """The source ``PEGASUS_POPULATION`` names, None when it is unset (then ``monolith.default_population`` chooses
    per field: ``hybrid`` where the events are the newborn's, ``popsvs`` otherwise; ADR-0010 amended)."""
    return os.environ.get("PEGASUS_POPULATION") or None


@lru_cache(maxsize=1)
def code_version() -> str:
    """This repository's commit, plus ``+dirty`` when the tree has changes."""
    return _git_version(REPO)


@lru_cache(maxsize=1)
def data_version() -> str:
    """The data version in every artefact key: pegasus_data's package version, until it
    exposes publication-level data versions (ARCHITECTURE §13). Not its commit: the
    repository is developed concurrently, and a commit key would invalidate every
    cached aggregate on each of its edits. The commit is recorded in each manifest."""
    import pegasus_data

    return str(pegasus_data.__version__)


@cache
def resource_version(file: str) -> str:
    """The sha256 (12 characters) of one of pegasus_data's shipped resources, from its manifest:
    the key of anything derived from that resource (code structures, graphs), so a rebuilt
    resource is a new key even when the package version is unchanged."""
    import json

    import pegasus_data

    manifest = Path(pegasus_data.__file__).resolve().parent / "resources" / "manifest.json"
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    entries = entries.get("resources", entries)
    entry = next(v for v in entries.values() if isinstance(v, dict) and v.get("file") == file)
    return str(entry["sha256"])[:12]


@lru_cache(maxsize=1)
def data_code_version() -> str:
    """pegasus_data's version and commit, recorded in manifests and the ledger."""
    import pegasus_data

    return f"{pegasus_data.__version__}@{_git_version(Path(pegasus_data.__file__).resolve().parents[2])}"


def _git_version(path: Path) -> str:
    try:
        head = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        return f"{head}{'+dirty' if dirty else ''}" or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def seed(*parts: object) -> int:
    """A deterministic 64-bit seed from (object, cell, purpose) (ARCHITECTURE §11.4)."""
    digest = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "little") & 0x7FFF_FFFF_FFFF_FFFF


def supply_exponents() -> dict[str, float] | None:
    """``PEGASUS_SUPPLY=volume:1,utilisation:0.5``: the facility-supply exponents given instead of chosen by likelihood
    (`facility.fit_supply`); unset: chosen."""
    raw = os.environ.get("PEGASUS_SUPPLY")
    return None if not raw else {k: float(v) for k, v in (kv.split(":") for kv in raw.split(","))}
