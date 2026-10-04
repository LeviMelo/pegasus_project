"""Leads: test results admitted by error control (ARCHITECTURE §9.1).

A lead is born from a finding (a lens, a subset, a pattern, a pair, a cohort
contrast) only after its family's FDR, and carries its replication, its
robustness flags and its provenance. The register is a versioned Parquet
table: a lead's later states (replicated, explained away, retired) are new rows
with the same id, never edits.

Ranking is evidence × effect × replication, never p alone:

    rank = −log10(q) · |log effect| · (1 + replication tier)

with effect on its own scale (rate ratio, ρ via Fisher's z, log RR).
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import config

KINDS = ("residual", "subset", "pattern", "relation", "cohort", "observation", "structural")
SCALES = ("rate_ratio", "rho", "log_rr", "share_absorbed", "sd")


@dataclass
class Lead:
    kind: str
    estimand: str
    tier: str
    fields: list[str]
    locus: dict[str, Any]
    effect: float
    scale: str
    interval: tuple[float, float] | None
    p: float
    q: float
    family: str
    null: str
    calibrated: bool
    replication: str = "R0"
    replications: dict[str, Any] = field(default_factory=dict)
    robustness: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    status: str = "open"           # open | replicated | explained | retired
    note: str = ""
    id: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"lead kind {self.kind!r} not in {KINDS}")
        if self.scale not in SCALES:
            raise ValueError(f"effect scale {self.scale!r} not in {SCALES}")
        if not self.id:
            body = json.dumps([self.kind, self.estimand, self.tier, sorted(self.fields), self.locus, self.family],
                              sort_keys=True, default=str)
            self.id = hashlib.sha256(body.encode()).hexdigest()[:16]
        self.provenance.setdefault("code_version", config.code_version())
        self.provenance.setdefault("data_version", config.data_code_version())

    @property
    def rank(self) -> float:
        tier = int(self.replication[1]) if self.replication.startswith("R") else 0
        if self.scale == "rho":
            size = abs(float(np.arctanh(np.clip(self.effect, -0.999, 0.999))))
        elif self.scale in ("rate_ratio",):
            size = abs(float(np.log(max(self.effect, 1e-12))))
        else:
            size = abs(self.effect)
        return float(-np.log10(max(self.q, 1e-300)) * size * (1 + tier))


class Register:
    def __init__(self):
        self.path = config.home() / "leads"
        self.path.mkdir(parents=True, exist_ok=True)

    def add(self, leads: list[Lead]) -> None:
        if not leads:
            return
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        rows = [{"id": x.id, "at": now, "rank": x.rank, "status": x.status, "kind": x.kind, "family": x.family,
                 "q": x.q, "effect": x.effect, "replication": x.replication,
                 "body": json.dumps(asdict(x), default=_json)} for x in leads]
        pq.write_table(pa.Table.from_pylist(rows), self.path / f"part-{now.replace(':', '')}-{uuid.uuid4().hex[:8]}.parquet")

    def current(self) -> list[Lead]:
        """The latest state of every lead, best rank first."""
        files = sorted(self.path.glob("part-*.parquet"))
        if not files:
            return []
        rows = pa.concat_tables([pq.read_table(f) for f in files]).to_pylist()
        latest: dict[str, dict] = {}
        for r in sorted(rows, key=lambda r: r["at"]):
            latest[r["id"]] = r
        out = [Lead(**{k: (tuple(v) if k == "interval" and v is not None else v)
                       for k, v in json.loads(r["body"]).items()}) for r in latest.values()]
        return sorted(out, key=lambda x: -x.rank)

    def get(self, lead_id: str) -> Lead:
        for x in self.current():
            if x.id == lead_id:
                return x
        raise KeyError(lead_id)

    def update(self, lead: Lead, **changes: Any) -> Lead:
        for k, v in changes.items():
            setattr(lead, k, v)
        self.add([lead])
        return lead


def _json(x: Any) -> Any:
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, np.ndarray):
        return x.tolist()
    return str(x)


def admit(findings: list[Any], rejected: np.ndarray, qvalues: np.ndarray, make) -> list[Lead]:
    """Leads from the findings that error control rejected; ``make(finding, q)`` builds the Lead."""
    return [make(f, float(q)) for f, keep, q in zip(findings, rejected, qvalues, strict=True) if keep]
