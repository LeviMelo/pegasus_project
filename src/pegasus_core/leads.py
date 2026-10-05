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
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import config

KINDS = ("residual", "subset", "pattern", "relation", "cohort", "observation", "structural")
PROSPECTIVE_PURPOSE = {"BP": "expectation", "BPA": "alarm"}      # the tier of each object (`surprise.PURPOSE_TIER`)
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
    gate: str = "passed"           # "failed": the lens/estimand/scale failed its gate (tools.SURVEY_PLAN); an exploratory lead
    train_last: int | None = None  # a prospective lead (tier BP/BPA, ADR-0012): the last year of the fit it was read against
    purpose: str | None = None     # ... and which object: "expectation" (BP) or "alarm" (BPA)
    note: str = ""
    id: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"lead kind {self.kind!r} not in {KINDS}")
        if self.gate not in ("passed", "failed"):
            raise ValueError(f"gate {self.gate!r}")
        if self.scale not in SCALES:
            raise ValueError(f"effect scale {self.scale!r} not in {SCALES}")
        if self.train_last is not None and self.purpose is None:
            self.purpose = PROSPECTIVE_PURPOSE.get(self.tier)
        if self.train_last is not None and self.purpose not in PROSPECTIVE_PURPOSE.values():
            raise ValueError(f"a prospective lead (train_last {self.train_last}) needs a purpose, not {self.purpose!r}")
        if not self.id:
            key = [self.kind, self.estimand, self.tier, sorted(self.fields), self.locus, self.family]
            body = json.dumps(key + ([self.train_last] if self.train_last is not None else []),   # retrospective ids unchanged
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
    def __init__(self, path: Path | None = None):
        self.path = path or config.home() / "leads"
        self.path.mkdir(parents=True, exist_ok=True)

    def add(self, leads: list[Lead]) -> None:
        if not leads:
            return
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        rows = [{"id": x.id, "at": now, "rank": x.rank, "status": x.status, "kind": x.kind, "family": x.family,
                 "q": x.q, "effect": x.effect, "replication": x.replication,
                 "gate": x.gate, "body": json.dumps(asdict(x), default=_json)} for x in leads]
        pq.write_table(pa.Table.from_pylist(rows), self.path / f"part-{now.replace(':', '')}-{uuid.uuid4().hex[:8]}.parquet")

    def current(self) -> list[Lead]:
        """The latest state of every lead, best rank first."""
        files = sorted(self.path.glob("part-*.parquet"))
        if not files:
            return []
        rows = pa.concat_tables([pq.read_table(f) for f in files], promote_options="default").to_pylist()   # parts differ in nullability
        latest: dict[str, dict] = {}
        for r in sorted(rows, key=lambda r: r["at"]):
            latest[r["id"]] = r
        out = [Lead(**{k: (tuple(v) if k == "interval" and v is not None else v)
                       for k, v in json.loads(r["body"]).items()}) for r in latest.values()]
        return sorted(out, key=lambda x: (x.gate == "failed", -x.rank))      # gate-failed leads after the others

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


def trend_reference(x: Lead) -> str:
    """The estimand of a trend-divergence lead: ``neighbours`` (leads before the national estimand carry no mark)
    or ``national``."""
    return x.provenance.get("stats", {}).get("estimand", "neighbours")


def _json(x: Any) -> Any:
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, np.ndarray):
        return x.tolist()
    return str(x)


def admit(findings: list[Any], rejected: np.ndarray, qvalues: np.ndarray, make) -> list[Lead]:
    """Leads from the findings that error control rejected; ``make(finding, q)`` builds the Lead."""
    return [make(f, float(q)) for f, keep, q in zip(findings, rejected, qvalues, strict=True) if keep]


@dataclass
class Story:
    """The leads of one place (a single-place locus) or of one subset, across fields and lenses."""

    key: str
    places: list[int]
    leads: list[Lead]
    rank: float
    fields: list[str]
    flags: list[str]


def stories(register: list[Lead], max_subset: int = 1) -> list[Story]:
    """Group leads into stories: every lead whose locus is one place joins that place's story; a
    larger subset is its own story. A place with fields moving in opposite directions within one
    block is flagged as a possible substitution (coding or diagnosis moving between codes)."""
    groups: dict[str, list[Lead]] = {}
    for x in register:
        places = list(x.locus.get("places", []))
        key = f"place {places[0]}" if len(places) <= max_subset and places else \
            f"subset {x.id}"
        groups.setdefault(key, []).append(x)
    out = []
    for key, members in groups.items():
        fields_ = sorted({m.fields[0].split(":")[-1] for m in members})
        flags = []
        # substitution: sibling codes (one parent) moving in opposite directions at the same place,
        # read from directional lenses only (trend, space–time, outbreak, change point)
        moves: dict[str, dict[int, list[str]]] = {}
        for m in members:
            if m.estimand not in ("trend_divergence", "space_time", "outbreak", "change_point"):
                continue
            node = m.fields[0].split(":")[-1]
            size = np.log(max(m.effect, 1e-12)) if m.scale == "rate_ratio" else m.effect
            if size == 0:
                continue
            moves.setdefault(_parent(node), {}).setdefault(int(np.sign(size)), []).append(node)
        for parent, by_sign in moves.items():
            if len(by_sign) == 2:
                flags.append(f"substitution in {parent}: up {','.join(sorted(set(by_sign[1])))} / "
                             f"down {','.join(sorted(set(by_sign[-1])))}")
        places = list(members[0].locus.get("places", []))
        if any(m.gate == "failed" for m in members):
            flags.append("gate failed: " + ",".join(sorted({m.estimand for m in members if m.gate == "failed"})))
        out.append(Story(key, places, sorted(members, key=lambda m: (m.gate == "failed", -m.rank)),
                         sum(m.rank for m in members if m.gate != "failed"), fields_, flags))
    return sorted(out, key=lambda st: -st.rank)


def _parent(code: str) -> str:
    """The node above a code in ICD-10 (its group for a category); the code itself if unknown."""
    global _PARENTS
    if _PARENTS is None:
        from . import gateway

        tree = gateway.code_structure("ICD10")
        _PARENTS = dict(zip(tree.column("code").to_pylist(), tree.column("parent").to_pylist(), strict=True))
    return _PARENTS.get(code) or code


def chapter(code: str) -> str:
    """The ICD-10 chapter above a code (the code itself for a chapter or an unknown code)."""
    _parent("")
    seen = 0
    while _PARENTS.get(code) and seen < 10:
        code, seen = _PARENTS[code], seen + 1
    return code


def triage_counts(register: list[Lead]) -> dict[str, dict[str, int]]:
    """Triaged leads counted by class and by ICD chapter (``counts[class][chapter]``) and by replication tier
    (``counts[class]["R1"]`` ...). Leads without a verdict are class ``untriaged``."""
    out: dict[str, dict[str, int]] = {}
    for x in register:
        cls = x.robustness.get("triage", {}).get("class", "untriaged")
        row = out.setdefault(cls, {})
        for key in (chapter(x.fields[0].split(":")[-1]), x.replication):
            row[key] = row.get(key, 0) + 1
    return out


_PARENTS: dict[str, str | None] | None = None
