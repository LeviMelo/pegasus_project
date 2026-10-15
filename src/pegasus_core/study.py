"""Studies (ARCHITECTURE §3): one declaration in, one study folder out.

A researcher declares a topic (seeds in any code system), a period, a place, grains and a depth; `resolve` turns it into
a scope (what the study reads and why, at what cost), `run` computes it over PegaSUS's machinery and writes the folder,
`export` materialises the folder for use elsewhere. The folder references the lake and the store and copies nothing
(P23): its `study.duckdb` holds views onto them, and its own files are what the study produces (findings, descriptive
tables, figures, the report).

This is the first version (BACKLOG phase 1): the scope reads the seeds' codes in each event type's *primary* classifier,
the questions are today's registry, and the depth sets the download budget. Later phases widen each step without
changing the interface or the folder.
"""

from __future__ import annotations

import functools
import html
import json
import os
import shutil
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import config, control, fields, gateway, leads, questions, store

DEPTHS = ("survey", "standard", "deep", "exhaustive")
SEED_SYSTEMS = ("icd10", "sinan", "terms", "records")
#: a records seed's keys: the dataset (and its event), the condition on pegasus_data roles (its grammar, ADR-0193 there),
#: the topic's name, and the events it is rated per
RECORD_KEYS = {"dataset", "event", "condition", "name", "per"}
CONDITION_OPS = ("<", "<=", ">", ">=", "==", "in", "not in")
#: the field kinds a study reads beyond counts (ARCHITECTURE §5.2): the declared readers pegasus_data's roles give every
#: source (`update.System`'s keys), and ``linked``, each usable person path's linked share as a field of its own
READERS = ("measures", "compositions", "intervals", "flows", "quality", "supports", "linked")
#: the relations a study reads (ARCHITECTURE §8): among its own and related fields, with every context (time-varying,
#: over lags and distances), and the data-space screen against every fitted field
RELATIONS = ("fields", "contexts", "screen")
#: (``chapters`` is false at every depth: a code set is the topic's field, and its chapter's fit is a modelling choice
#: a person makes; SIM's chapter I robust refit held 23 GB and SIH's ran out of memory, 2026-10-11)
#: every depth is a preset of the declaration's own choices (author, 2026-10-12: choices a person understands, not
#: budgets); a key the declaration sets overrides its depth's. ``download`` in gigabytes (years in the lake are free),
#: ``related`` a count of related codes read strongest first (each wherever recorded), ``draws`` plausible link sets for the persons
#: A depth cuts along the axes a study's time multiplies by (the review of the study, 2026-10-14: the lens passes are
#: 75-90 % of a lane, and the presets had switched only the fields and the replication): the fields read (readers,
#: related), the questions asked of each (None: all), the replicate null worlds of every Monte Carlo test (`NULLS`),
#: the per-item passes (triage and corroboration; the later years' replication; the persons).
PRESETS = {
    "survey": {"readers": [], "related": 0, "relations": ["fields"], "chapters": False, "persons": False,
               "replicate": False, "download": 2.0, "draws": 1, "related_questions": [],
               "questions": ["excess", "step", "trend", "cluster", "share"], "nulls": 0.25, "triage": False},
    "standard": {"readers": list(READERS), "related": 3, "relations": ["fields"], "chapters": False, "persons": False,
                 "replicate": False, "download": 10.0, "draws": 1, "related_questions": [],
                 "questions": None, "nulls": 1.0, "triage": True},
    "deep": {"readers": list(READERS), "related": 8, "relations": ["fields", "contexts"], "chapters": False,
             "persons": True, "replicate": True, "download": 40.0, "draws": 10, "related_questions": [],
             "questions": None, "nulls": 1.0, "triage": True},
    "exhaustive": {"readers": list(READERS), "related": 20, "relations": list(RELATIONS), "chapters": False,
                   "persons": True, "replicate": True, "download": float("inf"), "draws": 20,
                   "related_questions": [], "questions": None, "nulls": 4.0, "triage": True},
}
KEYS = {"study", "topic", "period", "where", "grain", "depth", "q", "hypotheses", "contexts", "ratios", "questions",
        "nulls", *PRESETS["survey"]}
RATIO_KEYS = {"numerator", "denominator", "lag"}
TOPIC_KEYS = {"seeds", "include", "exclude", "only"}


# ---------------------------------------------------------------------- the declaration


@dataclass
class Declaration:
    study: str
    seeds: dict[str, list[str]]
    years: list[int]
    path: Path
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    only: list[str] = field(default_factory=list)      # the datasets (or systems) the study is restricted to
    where: Any = "BR"
    grain: list[str] = field(default_factory=lambda: ["year"])
    depth: str = "survey"
    q: float = 0.05
    hypotheses: list[dict] = field(default_factory=list)
    contexts: Any = "auto"
    ratios: list[dict] = field(default_factory=list)   # {numerator, denominator: "DATASET[:event][:codes]", lag: years}
    questions: list[str] | None = None  # the questions asked of every field (None: the depth's, `PRESETS`)
    nulls: float | None = None           # replicate null worlds per test, a factor on each method's own (`NULLS`)
    triage: bool | None = None           # every answer triaged and corroborated (None: the depth's)
    # the choices each depth presets (`PRESETS`), None where the declaration leaves them to its depth (`choice`)
    readers: list[str] | None = None     # the field kinds read beyond counts (`READERS`)
    related: float | list | None = None  # how many related codes are read as fields of their own, strongest first, or which
    relations: list[str] | None = None   # the relations read (`RELATIONS`)
    chapters: bool | None = None         # the topic's nodes read inside their fitted chapters, or as code sets
    persons: bool | None = None          # the cohort scan over linked persons
    replicate: bool | None = None        # leads selected on the earlier years and tested once on the last `LATER_YEARS`
    download: float | None = None        # gigabytes the study may download
    draws: int | None = None             # plausible link sets the persons step averages over
    related_questions: list[str] | None = None  # the questions asked of the related codes' fields (preset: none, they
                                                # are read to relate them to the topic: a lead, never a cause)

    def choice(self, key: str):
        """The declaration's ``key``, or its depth's preset (`PRESETS`)."""
        v = getattr(self, key)
        return PRESETS[self.depth][key] if v is None else v


#: the precision of every Monte Carlo test, in words: a factor on each method's own replicate null worlds (a p-value's
#: floor is about 1/(R + 1); quick halves the excess question's 40 worlds' resolution twice over)
NULLS = {"quick": 0.25, "standard": 1.0, "precise": 4.0}


def _area(where) -> list[int] | None:
    """A declaration's ``where`` as the codes `config.study_area` reads: None for Brazil ("BR"); else a list of states
    (abbreviation "RS" or code 43) and municipalities (six or seven digits)."""
    if where in (None, "BR", ["BR"]):
        return None
    names = {v["uf_sigla"]: int(v["uf_code"]) for v in gateway.municipality_names().values()}
    out = []
    for w in (where if isinstance(where, list) else [where]):
        w = str(w).strip().upper()
        if w in names:
            out.append(names[w])
        elif w.isdigit() and len(w) == 2 and int(w) in names.values():
            out.append(int(w))
        elif w.isdigit() and len(w) in (6, 7) and w[:6] in gateway.municipality_names():
            out.append(int(w[:6]))
        else:
            raise ValueError(f"where {w!r}: BR, a state (RS or 43) or a municipality code (431690)")
    return sorted(set(out))


class DeclarationError(ValueError):
    """A declaration that cannot be read, with every problem named."""


def load(path: str | Path) -> Declaration:
    """Read and validate a study declaration (ARCHITECTURE §3.1). Every problem is reported at once."""
    import yaml

    path = Path(path)
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    problems = []
    if not isinstance(doc, dict):
        raise DeclarationError(f"{path}: a declaration is a mapping of keys, not {type(doc).__name__}")
    for k in sorted(set(doc) - KEYS):
        problems.append(f"unknown key {k!r} (keys: {', '.join(sorted(KEYS))})")
    if not doc.get("study"):
        problems.append("'study' (the study's name) is required")
    topic = doc.get("topic") or {}
    for k in sorted(set(topic) - TOPIC_KEYS):
        problems.append(f"unknown topic key {k!r} (keys: {', '.join(sorted(TOPIC_KEYS))})")
    seeds = topic.get("seeds") or {}
    if not seeds:
        problems.append("'topic.seeds' is required: codes in any of " + ", ".join(SEED_SYSTEMS))
    for k in sorted(set(seeds) - set(SEED_SYSTEMS)):
        problems.append(f"unknown seed system {k!r} (systems: {', '.join(SEED_SYSTEMS)})")
    for i, r in enumerate(seeds.get("records") or []):
        where_ = f"topic.seeds.records[{i}]"
        if not isinstance(r, dict):
            problems.append(f"{where_}: write {{dataset, condition: [{{role, op, value}}], name, per}}")
            continue
        for k in sorted(set(r) - RECORD_KEYS):
            problems.append(f"{where_}: unknown key {k!r} (keys: {', '.join(sorted(RECORD_KEYS))})")
        if not r.get("dataset") or not r.get("name"):
            problems.append(f"{where_}: dataset and name are required")
        clauses = r.get("condition")
        if not isinstance(clauses, list) or not clauses:
            problems.append(f"{where_}: condition is a list of clauses, e.g. [{{role: birth.weight, op: '<', "
                            "value: 2500}]")
            continue
        for j, c in enumerate(clauses):
            ops = [o for o in CONDITION_OPS if o in (c or {})] if isinstance(c, dict) else []
            if not isinstance(c, dict) or not c.get("role") or not (c.get("op") in CONDITION_OPS or ops):
                problems.append(f"{where_}.condition[{j}]: {{role: <pegasus_data role>, op: one of "
                                f"{', '.join(CONDITION_OPS)}, value: ...}} or {{role, in: [codes]}}")
    period = doc.get("period", "2010-2023")
    try:
        first, last = ((int(x) for x in str(period).split("-")) if not isinstance(period, list) else
                       (int(period[0]), int(period[-1])))
        years = list(range(first, last + 1))
        if not years:
            problems.append(f"period {period!r} is empty")
    except (TypeError, ValueError):
        problems.append(f"period {period!r}: write FIRST-LAST, e.g. 2010-2025")
        years = []
    depth = doc.get("depth", "survey")
    if depth not in DEPTHS:
        problems.append(f"depth {depth!r}: one of {', '.join(DEPTHS)}")
    grain = doc.get("grain", ["year"])
    grain = [grain] if isinstance(grain, str) else list(grain)
    for g in grain:
        if g not in ("year", "month", "week"):
            problems.append(f"grain {g!r}: year, month or week")
    ratios = doc.get("ratios") or []
    for i, r in enumerate(ratios if isinstance(ratios, list) else [ratios]):
        if not isinstance(r, dict) or not r.get("numerator") or not r.get("denominator"):
            problems.append(f"ratios[{i}]: write {{numerator: DATASET[:event][:codes], denominator: ..., lag: years}}")
            continue
        for k in sorted(set(r) - RATIO_KEYS):
            problems.append(f"ratios[{i}]: unknown key {k!r} (keys: {', '.join(sorted(RATIO_KEYS))})")
        if not isinstance(r.get("lag", 0), int) or r.get("lag", 0) < 0:
            problems.append(f"ratios[{i}]: lag {r.get('lag')!r} is a whole number of years, 0 or more")
    if topic.get("include"):
        problems.append("topic.include (fields forced in, ARCHITECTURE §3.1) is not built yet: it would be ignored; "
                        "topic.only restricts the study to datasets or systems, topic.exclude leaves them out")
    from .questions import QUESTIONS
    names = [getattr(q, "name", q) for q in QUESTIONS]
    for k, allowed in (("questions", names), ("related_questions", names), ("readers", list(READERS)),
                       ("relations", list(RELATIONS))):
        v = doc.get(k)
        if v is not None and (not isinstance(v, list) or set(v) - set(allowed)):
            problems.append(f"{k} {v!r}: a list among {', '.join(allowed)}")
    nulls = doc.get("nulls")
    if nulls is not None and not (isinstance(nulls, str | int | float) and not isinstance(nulls, bool)
                                  and (nulls in NULLS or (not isinstance(nulls, str) and nulls > 0))):
        problems.append(f"nulls {nulls!r}: {', '.join(NULLS)}, or a factor on each test's replicate null worlds")
    if doc.get("draws") is not None and (not isinstance(doc["draws"], int) or doc["draws"] < 1):
        problems.append(f"draws {doc['draws']!r}: how many plausible link sets the persons step averages over, 1 or more")
    if doc.get("chapters") is not None and not isinstance(doc["chapters"], bool):
        problems.append(f"chapters {doc['chapters']!r}: true (the topic's codes inside their fitted chapters) or false "
                        "(as code sets of their own)")
    for k, what in (("persons", "the cohort scan over linked persons"),
                    ("replicate", "leads tested once on the later years they were not selected on")):
        if doc.get(k) is not None and not isinstance(doc[k], bool):
            problems.append(f"{k} {doc[k]!r}: true or false ({what})")
    if doc.get("download") is not None and (not isinstance(doc["download"], (int, float)) or doc["download"] < 0):
        problems.append(f"download {doc['download']!r}: gigabytes the study may download, 0 or more")
    rel = doc.get("related")
    named = isinstance(rel, list) and all(isinstance(c, str) for c in rel)
    if rel is not None and rel != "all" and not named and (isinstance(rel, bool) or not isinstance(rel, int) or rel < 0):
        problems.append(f"related {rel!r}: how many related codes to read as fields of their own, strongest first "
                        "(0 for none, or all), or the codes themselves ([H32])")
    where = doc.get("where", "BR")
    try:
        area = _area(where)
    except ValueError as exc:
        problems.append(str(exc))
        area = None
    named = doc.get("contexts", "auto")
    if isinstance(named, list):
        known = set(gateway.declared_fields())
        unknown = [c for c in named if isinstance(c, str) and c not in known]
        if unknown:
            problems.append(f"contexts {unknown}: no declared context field of that name (`pegasus-core contexts` "
                            "lists them)")
    if problems:
        raise DeclarationError(f"{path}:\n  - " + "\n  - ".join(problems))
    return Declaration(study=str(doc["study"]), seeds={k: ([dict(c) for c in v] if k == "records" else [str(c) for c in v])
                                                       for k, v in seeds.items()}, years=years,
                       path=path, include=list(topic.get("include") or []), exclude=list(topic.get("exclude") or []),
                       only=list(topic.get("only") or []),
                       where=area or "BR", grain=grain, depth=depth, q=float(doc.get("q", 0.05)),
                       hypotheses=list(doc.get("hypotheses") or []), contexts=doc.get("contexts", "auto"),
                       ratios=list(ratios) if isinstance(ratios, list) else [ratios],
                       related=(float("inf") if rel == "all" else list(rel) if isinstance(rel, list) else float(rel)) if rel is not None else None,
                       download=float(doc["download"]) if doc.get("download") is not None else None,
                       chapters=doc.get("chapters"), questions=doc.get("questions"), readers=doc.get("readers"),
                       relations=doc.get("relations"), persons=doc.get("persons"), replicate=doc.get("replicate"),
                       related_questions=doc.get("related_questions"),
                       nulls=(float(NULLS.get(nulls, nulls)) if nulls is not None else None),
                       triage=doc.get("triage"),
                       draws=doc.get("draws"))


# ---------------------------------------------------------------------- the scope


@dataclass
class Item:
    """One event type the study reads: its blocks, the topic's nodes in it, the years, why, and at what cost."""
    dataset: str
    event: str
    blocks: list[str]
    nodes: list[str] | None
    years: list[int]
    reason: str
    status: str = "in"                   # in | deferred
    download_gb: float = 0.0
    records: int | None = None           # the topic's events in its years (all events for an agravo's own dataset)
    mentions: list[str] | None = None    # declared readers of every code a record carries (certificate lines, all diagnoses)
    source: dict | None = None           # a reader of its own: {"codes": [...]} for a code set read as one field
    readers: dict = field(default_factory=dict)   # the declared readers the depth adds (`update.System`'s keys)
    denominator: tuple | None = None     # a ratio's denominator dataset and lag (its exposure is in ``source``)
    est_seconds: float | None = None     # the run's predicted wall clock for this item (`_estimate`)
    fields: int = 1                      # the fields its run fits and asks: its counts and each reader (`_estimate`)
    #: those readers, (name, reader, blocks), listed once at the scope (`_estimate`): what scope.yml shows before a run,
    #: what its lane fits and asks and what its products read (each had listed them again, `update.system_readers`)
    field_list: list | None = None
    extract: bool = False                # its codes read from an extract of the dataset, file by file (`_extract_or_lake`)
    confirm_last: int | None = None      # stage E's later years: its leads selected on the years up to it, tested after
    questions: list[str] | None = None   # the declaration's questions (None: every question)
    note: str = ""
    #: a second coding of the topic's own events (an alternative classifier of the primary's structure: SIM's cause
    #: before investigation): counted and described, asked nothing, given no supports or linked shares
    count_only: bool = False
    q: float = 0.05                      # the study's false-discovery level, carried to the item's lane (`_plan`)
    triage: bool = True                  # its answers triaged and corroborated (the depth's, `PRESETS`)


@dataclass
class Scope:
    study: str
    depth: str
    items: list[Item]
    excluded: list[dict]                 # what a seed named and the study does not read, with why
    contexts: list                       # declared field names, and entries {field, where, over, name, reason}
    budget_gb: float
    related: list[dict] = field(default_factory=list)   # codes found with the seeds on the same records (`cooccur`)
    paths: list[dict] = field(default_factory=list)     # declared links touching the read sources, with their runs' verdicts
    link_runs: list[dict] = field(default_factory=list)  # national link runs the items read and the store lacks, priced
    medicines: list[dict] = field(default_factory=list)  # the topic's declared treatments: substances, use, citation, reads
    lane_overlap: float = 1.0            # items' summed seconds over the lanes' wall clock, measured (`_phase_record`)
    overhead_seconds: float = 0.0        # the measured scope, store and products phases of the last run at this depth

    def to_dict(self) -> dict:
        """The scope as plain values (numpy scalars from the counts made plain: YAML refuses them)."""
        return json.loads(json.dumps(self._dict(), default=lambda o: o.item() if hasattr(o, "item") else str(o)))

    def _dict(self) -> dict:
        return {"study": self.study, "depth": self.depth, "download_budget_gb": self.budget_gb,
                "read": [asdict(i) for i in self.items if i.status == "in"],
                "deferred": [asdict(i) for i in self.items if i.status != "in"],
                "not_read": self.excluded, "contexts": self.contexts, "related_codes": self.related,
                "person_paths": self.paths, "link_runs_to_compute": self.link_runs, "medicines": self.medicines,
                "minutes_by_choice": self.minutes_by_choice(),
                "estimated_minutes": round((self._lanes_seconds() + sum(r["est_seconds"] or 0 for r in self.link_runs)
                                            + self.overhead_seconds) / 60, 1)}

    def _lanes_seconds(self) -> float:
        """The lanes' wall clock: the items' sum over the measured overlap, but never less than the longest lane, a
        dataset's items run one after another (the leptospirosis slice: one lane held nearly every field, and its 11.5
        minutes, the sum over an overlap of 2, ran past twice that, 2026-10-13)."""
        read = [i for i in self.items if i.status == "in"]
        lanes: dict[str, float] = {}
        for i in read:
            lanes[i.dataset] = lanes.get(i.dataset, 0.0) + (i.est_seconds or 0.0)
        return max(sum(lanes.values()) / self.lane_overlap, max(lanes.values(), default=0.0))

    def minutes_by_choice(self) -> dict:
        """The estimated minutes behind each choice the declaration makes, so a person sees what to cut: per dataset
        (``topic.only`` / ``topic.exclude``), the related fields (``related``) read and the next ones deferred, the
        persons' linked shares and link runs (``depth``), the declared ratios, and the fixed phases."""
        def kind(it):
            if it.reason.startswith("related code"):
                return "related"
            if (it.source or {}).get("source") == "linked":
                return "persons"
            return "ratios" if it.denominator else "topic"

        out: dict = {"topic, by dataset": {}, "related": {}, "persons": 0.0, "ratios": 0.0}
        for it in self.items:
            m = (it.est_seconds or 0.0) / self.lane_overlap / 60
            k = kind(it)
            if it.status != "in":
                if k == "related" and it.est_seconds:
                    out["related"].setdefault("next, each", []).append(
                        f"{_related_code(it)} in {it.dataset}"
                        + (f" {it.source['classifier']}" if (it.source or {}).get("classifier") else "") + f": {m:.1f}")
                continue
            if k == "topic":
                d = out["topic, by dataset"]
                d[it.dataset] = d.get(it.dataset, 0.0) + m
            elif k == "related":
                out["related"]["read"] = out["related"].get("read", 0.0) + m
                out["related"]["fields read"] = out["related"].get("fields read", 0) + 1
            else:
                out[k] += m
        out["persons"] += sum(r["est_seconds"] or 0 for r in self.link_runs) / 60
        out["scope, store and products"] = self.overhead_seconds / 60
        return json.loads(json.dumps(out, default=float), parse_float=lambda x: round(float(x), 1))


def _field_spec(text: str) -> tuple[str, str, list[str]]:
    """``DATASET[:event][:codes]`` -> (dataset, event, codes): the event defaults to the dataset's only event type."""
    ds, *rest = str(text).split(":")
    types = [e["name"] for e in gateway.event_types(ds)] if ds in set(gateway.event_datasets()) else []
    if not types:
        raise LookupError(f"{ds}: no dataset with event types by that name")
    event = rest[0] if rest and rest[0] else (types[0] if len(types) == 1 else None)
    if event not in types:
        raise LookupError(f"{text}: name the event type, one of {types}")
    codes = [_icd(c) for c in rest[1].split(",")] if len(rest) > 1 and rest[1] else []
    return ds, event, codes


def _condition_text(clauses: list[dict]) -> str:
    """A condition's clauses as a reader reads them: "birth.weight < 2500 and birth.delivery in [2]"."""
    out = []
    for c in clauses:
        op = c.get("op") or next((o for o in CONDITION_OPS if o in c), "")
        value = c.get("value", c.get(op))
        out.append(f"{c['role']} {op} {value}" + (f" {c['unit']}" if c.get("unit") else ""))
    return " and ".join(out)


def _icd(code: str) -> str:
    return code.replace(".", "").strip().upper()


def _one_institution(x) -> str | None:
    """The one establishment a lead's triage found its events in, if any: a triage's ``facility`` is a dict of its
    evidence, or False where none was found (deep17's products died on the bool)."""
    fac = (x.robustness.get("triage") or {}).get("facility")
    return fac.get("one_institution") if isinstance(fac, dict) else None


def _corroboration_text(corr: dict) -> str | None:
    """What another system said of a finding: its best source's test (observed against the null's median, p, and the
    q over every lead when tested), or why it was not tested; None when it was not asked (only signals are). The
    table had kept the reason alone, empty for every lead that was tested (the smoke study's 67 signals)."""
    if not corr:
        return None
    if not corr.get("tested"):
        return corr.get("reason") or "not tested"
    q = f", q {corr['q']:.2g}" if corr.get("q") is not None else ""
    return (f"{corr.get('label') or corr.get('source')}: {corr.get('observed', float('nan')):.3g} against "
            f"{corr.get('null_median', float('nan')):.3g} expected, p {corr.get('p', 1.0):.2g}{q}")


def _rows_table(rows: list[dict]) -> pa.Table:
    """Rows as a table over the union of their keys, in first-seen order: pyarrow takes the columns of the first row
    alone, so a column only some rows carry (an institution's facts, a cohort's estimate beside its notes) was dropped
    whenever the first row lacked it (review 2026-10-11)."""
    keys = list(dict.fromkeys(k for r in rows for k in r))
    return pa.Table.from_pylist([{k: r.get(k) for k in keys} for r in rows])


def _cost(dataset: str, years: list[int]) -> tuple[list[int], dict[int, float | None]]:
    """The years ``dataset`` publishes among ``years`` before its confirmation reserve (`control.reserved`: only a
    claim reads it; the years after it too are left out, since the fits read years by position, a trend and an AR(1)
    over consecutive years, and would take 2023 to 2025 for one step), and the gigabytes each would download: 0 when
    in the lake, None when the catalog does not size it (never read as free)."""

    published = gateway.published_years(dataset)
    held = control.reserved(dataset)
    ys = [y for y in years if (not published or y in published) and (not held or y < min(held))]
    volume = _volumes(dataset, config.data_root())
    # read once per scope (`resolve` clears it): not across a run, whose `ensure_lake` extends the lake; per call, the
    # deep scope priced each related code in every served dataset by a fresh read. A year is the lake's when it holds
    # it whole (`gateway.lake_whole_years`)
    if dataset not in _LAKE:
        _LAKE[dataset] = gateway.lake_whole_years(dataset)
    lake = _LAKE[dataset]
    return ys, {y: (0.0 if y in lake else volume.get(y)) for y in ys}


_LAKE: dict[str, frozenset[int]] = {}


@functools.cache
def _volumes(dataset: str, root: str) -> dict[int, float]:
    """The catalog's gigabytes per year of ``dataset``, once per process: a scope prices many items of one dataset
    (its classifier, code sets, mentions, related codes), and each `pg.explore` was a query of the 254 MB catalog
    (79 % of a scope's resolution, py-spy 2026-10-11)."""
    import pegasus_data as pg

    try:
        return {int(r["year"]): float(r.get("gigabytes") or 0.0) for r in pg.explore(dataset, root=root).rows}
    except Exception:  # noqa: BLE001 - a dataset the catalog does not size: counted as free, said in the note
        return {}


#: the share of the data root's free disk a lake may take for one item; a code set needing more is read as an extract
EXTRACT_DISK_SHARE = 0.5


def _extract_held(it: Item, years: list[int]) -> list[int]:
    """The ``years`` an existing extract holds whole for a code-set item's codes on its classifier (its own, else the
    event type's primary): free to read, as a lake year is."""
    codes = (it.source or {}).get("codes")
    if not codes or not years:
        return []
    column = (it.source or {}).get("classifier") or next(
        (c["column"] for c in gateway.event_type(it.dataset, it.event).get("classifiers") or [] if c["role"] == "primary"),
        None)
    return gateway.extract_years(it.dataset, column, list(codes), years) if column else []


def _extract_or_lake(it: Item, gb: float) -> None:
    """A code set whose download would not fit the disk as a lake (more than `EXTRACT_DISK_SHARE` of the data root's
    free space: SIA-PA 2010-2025 is 175 GB against under 180 GB free) is read as an extract of its codes: the dataset's
    files downloaded and read one by one, only its records kept (`pegasus_data.extract`). The download is the same."""
    import shutil

    if not (it.source or {}).get("codes"):
        return
    free = shutil.disk_usage(config.data_root()).free / 2**30
    if gb > EXTRACT_DISK_SHARE * free:
        it.extract = True
        it.note = (it.note + "; " if it.note else "") + (
            f"read as an extract of its codes: {gb:.0f} GB downloaded file by file against {free:.0f} GB free, only its "
            "records kept")


def _records(it: Item, years: list[int]) -> int:
    """The topic's events of an item over ``years``: its nodes' codes in the classifier's counts (the cached counts the
    fit reads, so counting costs the fit nothing), every event for an agravo's own dataset."""
    import pyarrow.compute as pc

    total = 0
    src = it.source or {}
    prefixes = list(it.nodes or []) + list(src.get("codes") or [])
    listed = src.get("source") == "code_list"
    if listed:              # a code list is counted by ICD category (`gateway.code_list_counts`)
        prefixes = list(dict.fromkeys(p[:3] for p in prefixes))
    # kept by what it counts: each estimate re-read the national counts to count one state's (59 s of a one-state
    # scope's 329, infarto_alagoas, 2026-10-13)
    key = {"what": "topic_records", "dataset": it.dataset, "event": it.event, "years": sorted(int(y) for y in years),
           "source": {k: v for k, v in src.items() if k in ("source", "column", "classifier", "codes")},
           "prefixes": prefixes, "extract": bool(it.extract), "area": sorted(config.study_area() or []),
           "data": config.data_version(), "code": config.code_key(_records)}
    kept = store.get_table("study", key)
    if kept is not None:
        return int(kept.column("n")[0].as_py())
    for y in years:
        # every event, whatever its cell: a foetal death has no age, and counted by cells SIM-DOFET held no P37.1
        # (the Santa Maria hypothesis's own source left out, 2026-10-11); a code list by its own reader, its field's
        # name ("codes:LINHAA_O") is no column (deep7's probes of SIM-DOFET and SIM-DOREXT failed on it, 2026-10-12)
        area = (tuple(sorted(config.study_area())) if config.study_area() else None)
        c = (gateway.code_list_counts(it.dataset, it.event, y, src["column"], area=area).counts if listed else
             gateway.event_counts(it.dataset, it.event, y, classifier=src.get("classifier"), cell=False,
                                  codes=tuple(src.get("codes") or ()) if it.extract else (), area=area).counts)
        if config.study_area() is not None:                 # the study's area's records only
            c = c.filter(pa.array(config.in_area(c.column("u").to_numpy())))
        if prefixes:
            hit = pc.starts_with(c.column("code"), prefixes[0])
            for n in prefixes[1:]:
                hit = pc.or_(hit, pc.starts_with(c.column("code"), n))
            c = c.filter(pc.fill_null(hit, False))
        total += int(pc.sum(c.column("y")).as_py() or 0)
    store.put_table("study", key, pa.table({"n": [total]}))
    return total


def _estimate(decl: Declaration, items: list[Item]) -> None:
    """Each item's predicted wall clock (BACKLOG 9.1), from measured throughput, as if nothing were stored: a cap must
    hold when a code edit re-keys every step (slice5's estimate, priced from a cached run, priced no refit, 2026-10-12).
    Every field the item reads (its primary counts and each reader its depth adds, `update.system_readers`) costs one
    fit, by the nearest stored fit of the same dataset and block scaled by years, or by the stores' log-log relation of
    fit seconds to events; and one pass of its questions, at the median measured seconds of a field's questions in the
    same dataset and area (`update` records them), else in any (the leptospirosis slice: 130 fields priced as one,
    17.6 min estimated, over 35 run)."""
    from . import update

    fits = [m for m in store.manifests("monolith") if m.get("fit_seconds")]
    if len(fits) >= 10:
        e = np.log([max(float(m.get("events") or 1.0), 1.0) for m in fits])
        b, a = np.polyfit(e, np.log([float(m["fit_seconds"]) for m in fits]), 1)
    else:
        a, b = 3.0, 0.3
    area = sorted(config.study_area() or []) or None
    marks = [m for m in store.manifests("update") if m.get("seconds") is not None]
    asked = [m for m in marks if m.get("step") == "questions"]
    # an item's own steps, once per item whatever its fields: the later years' retraining and confirmation, triage over
    # its answers, the prospective questions of its held-out years; priced at nothing, a recomputing slice ran twice
    # its estimate (the leptospirosis slice past its cap, 2026-10-13)
    item_steps = [m for m in marks if m.get("step") in ("later_years", "triage", "prospective")]

    def per_item(dataset, years, steps):
        # each step by what it scales with: years only where its mark recorded them (a triage mark has none, and a 46 s
        # triage had been priced at ten times that for ten years: 30 of Alagoas's estimated minutes; the review of the
        # study, 2026-10-14), places always
        total = 0.0
        for step in steps:
            for pool in ([m for m in item_steps if m.get("step") == step and m.get("dataset") == dataset
                          and m.get("area") == area],
                         [m for m in item_steps if m.get("step") == step and m.get("dataset") == dataset],
                         [m for m in item_steps if m.get("step") == step]):
                if pool:
                    total += float(np.median([float(m["seconds"])
                                              * (len(years) / max(len(m["years"]), 1) if m.get("years") else 1.0)
                                              * size(tuple(area or ())) / size(tuple(m.get("area") or ()))
                                              for m in pool]))
                    break
        return total
    from .questions import QUESTIONS

    codes = [int(c) for c in gateway.municipality_names() if str(c).isdigit()]
    size = functools.cache(lambda area: max(int(config.in_area(codes, frozenset(area) if area else None).sum()), 1))

    nulls = float(decl.choice("nulls"))

    def per_field(dataset, years):
        # a measurement scaled by years and by the places its area holds (a question's cost is per place and period:
        # Rio Grande do Sul's 497 municipalities against Brazil's 5,570), from marks at the study's replicate scale where
        # there are any, else scaled by it (an upper bound: not every lens draws replicates; quick slices had priced
        # standard studies at a quarter, the review of the study, 2026-10-14)
        for pool in ([m for m in asked if m.get("dataset") == dataset and m.get("area") == area],
                     [m for m in asked if m.get("dataset") == dataset],
                     [m for m in asked if m.get("area") == area], asked):
            if pool:
                same = [m for m in pool if float(m.get("nulls") or 1.0) == nulls]
                return float(np.median([float(m["seconds"]) * len(years) / max(len(m.get("years") or [1]), 1)
                                        * size(tuple(area or ())) / size(tuple(m.get("area") or ()))
                                        * (1.0 if same else nulls / float(m.get("nulls") or 1.0))
                                        for m in (same or pool)]))
        # nothing measured yet: the leptospirosis slice's ~390 fields' fits and questions in Rio Grande do Sul, 9 years,
        # took ~33 min (2026-10-12), about 5 s each, scaled the same way; replaced by the store's own once one ran
        return 5.0 * len(years) / 9 * size(tuple(area or ())) / size((43,))
    for it in items:
        if it.status != "in" or not it.years:
            continue
        share = len(it.questions if it.questions is not None else decl.choice("questions") or QUESTIONS) / len(QUESTIONS)
        if it.count_only:
            share, n = 0.0, 1                       # a second coding: counted and described, asked nothing
        else:
            try:
                plan = _plan(it)
                it.field_list = [list(x) for x in update.system_readers(plan.systems[0], plan, list(it.blocks))]
                n = 1 + len(it.field_list)
            except Exception:  # noqa: BLE001 - a reader list that cannot be built here is built (and fails) in the run
                n = 1
        fit = 0.0
        for block in it.blocks:
            # the nearest stored fit: same dataset and block, the same area and event first, scaled by years and
            # places (a national fit of 14 years, 354 s, had priced each of Rio Grande do Sul's fields)
            same = [m for m in fits if m["key"].get("dataset") == it.dataset and m["key"].get("block") == block]
            item_codes = sorted((it.source or {}).get("codes") or [])
            same = ([m for m in same if m["key"].get("area") == area and m["key"].get("event") == it.event
                     and sorted((m["key"].get("args") or {}).get("codes") or []) == item_codes]
                    or [m for m in same if m["key"].get("area") == area and m["key"].get("event") == it.event]
                    or [m for m in same if m["key"].get("area") == area] or same)
            if same:
                m = max(same, key=lambda m: len(m["key"].get("years") or []))
                fit += (float(m["fit_seconds"]) * len(it.years) / max(len(m["key"].get("years") or [1]), 1)
                        * size(tuple(area or ())) / size(tuple(m["key"].get("area") or ())))
            else:
                fit += float(np.exp(a + b * np.log(max(float(it.records or 1), 1.0))))
        it.fields = n
        # a replicating depth also trains on the years before the later ones and confirms on them
        # (`update._later_years`): priced by its own recorded seconds with the item's other steps (the leptospirosis
        # slice's later years, priced at nothing, took two thirds of its run, 2026-10-13). Doubling every field as
        # well counted it twice: Alagoas's infarction study was priced at 83 minutes and ran in 27 (2026-10-13)
        replicating = decl.choice("replicate") and len(it.years) >= 2 * LATER_YEARS + 2 and not it.count_only
        steps = per_item(it.dataset, it.years, (("triage",) if decl.choice("triage") and not it.count_only else ())
                         + (("later_years", "prospective") if replicating else ()))
        it.est_seconds = round(n * (fit + per_field(it.dataset, it.years) * share) + steps, 1)


def _associated(decl: Declaration, scope: Scope, log) -> list[dict]:
    """The conditions named beside the topic on its own records (`cooccur.associated`): every read source whose records
    carry several codes (`fields.declared_mentions`: a certificate's lines, an admission's diagnoses), over the years
    its topic item reads, in the study's area."""
    from . import cooccur

    seeds = sorted(set(decl.seeds.get("icd10") or []))
    if not seeds:
        return []
    out, done = [], set()
    for it in (i for i in scope.items if i.status == "in" and i.years):
        if it.dataset in done or (it.source or {}).get("population"):
            continue
        done.add(it.dataset)
        for role, cols in gateway.code_groups(it.dataset).items():
            try:
                rows = cooccur.associated(it.dataset, it.event, list(it.years), list(cols), seeds, q=decl.q)
            except Exception as exc:  # noqa: BLE001 - a source whose records cannot be read is said
                log(f"study: associated {it.dataset} {role}: {type(exc).__name__}: {exc}")
                continue
            base = {"dataset": it.dataset, "geography": _whole()[0], "variable": role,
                    **_period(None, f"{min(it.years)}-{max(it.years)}")}
            for r in rows:
                at = {**base, "value": r["code"], "value_label": r["label"]}
                out += [_estimate_row("associated causes", "proportion", at, estimate=r["share"], low=r["share_low"],
                                      high=r["share_high"], interval="Clopper-Pearson", numerator=r["with_code"],
                                      denominator=r["topic_records"], denominator_kind="the topic's records"),
                        _estimate_row("associated causes", "count", {**at, "note": "every record of the area and years "
                                                                                    "naming it, the topic's or not"},
                                      estimate=r["records_with_code"]),
                        _estimate_row("associated causes", "lift", at, estimate=r["lift"], low=r["lift_low"],
                                      high=r["lift_high"], interval="exact, Poisson on the expected", p=r["p"], q=r["q"],
                                      numerator=r["with_code"], denominator=r["expected"],
                                      denominator_kind="expected records (same sex and ten-year age band)")]
    return out


def _related_codes(decl: Declaration, items: list[Item], seeds: list[str], log) -> list[dict]:
    """The codes related to the seeds on the same records (BACKLOG 4.2, `cooccur.associated` at the study's q), wherever
    a read item's records carry several codes (`fields.declared_mentions`: certificate lines, all diagnoses, anomaly
    lists), over the item's years in the lake; each with its strength (lift and interval) and FDR. Only where related
    fields are read (`related`): the report's table of them is estimates.parquet's (associated causes), made in the products."""
    from . import cooccur

    if not seeds or not decl.choice("related"):
        return []
    out, seen = [], set()
    # every read dataset whose records carry several codes, however its items are fitted: keyed on the item's mention
    # readers, a code-set item (a survey's, or `chapters: false`) found no related code at all (2026-10-11)
    for it in (i for i in items if i.status == "in" and fields.declared_mentions(i.dataset)):
        if (it.dataset, it.event) in seen:
            continue
        seen.add((it.dataset, it.event))
        for d in fields.declared_mentions(it.dataset):
            src = fields.mentions_source(it.dataset, d.column)
            cols = src["column"] if isinstance(src["column"], list) else [src["column"]]
            try:
                rows = cooccur.associated(it.dataset, it.event, list(it.years), cols, seeds, q=decl.q)
            except Exception as exc:  # noqa: BLE001 - a source whose records cannot be read is said, not hidden
                log(f"study: related codes in {it.dataset} {d.column}: {type(exc).__name__}: {exc}")
                continue
            # ``years`` is the span shown; ``item_years`` every year read, which the related code's own field reads (its
            # span alone made a two-year field of fourteen, its fits taking 2010 and 2023 for consecutive, 2026-10-11)
            out += [{"dataset": it.dataset, "event": it.event, "where": d.column, "years": [it.years[0], it.years[-1]],
                     "item_years": [int(y) for y in it.years], **r} for r in rows if r["related"]]
    return sorted(out, key=lambda r: -r["lift"])


#: the verdicts of a stored link run (pegasus_data judges each before any result: the pairs a shifted key finds by
#: chance, the held-out agreements) under which its pairs are read
USABLE_LINKS = ("viable", "use with caution")


def _link_runs() -> list[dict]:
    """Every stored run of a current link spec (pegasus_data's link store), with its file stem."""
    import pegasus_data as pg
    from pegasus_data.linkage import store as link_store

    out = []
    for r in link_store.runs(pg.load_settings(root=config.data_root())):
        run = r.get("run") or {}
        if run.get("current"):
            out.append({**r, "stem": f"{run.get('method')}_{run.get('geography')}_{run.get('period')}_{run.get('spec_digest')}"})
    return out


def _person_paths(items: list[Item], runs: list[dict]) -> list[dict]:
    """Scope v2's person paths (BACKLOG 4.3, 6.2): every declared link (pegasus_data `links.yml`) with a side on a read
    source, what it pairs, and each stored run's verdict; ``verdict`` is the best of them, "not run" when none is
    stored. A path is not a field: `_linked_items` reads the ones whose runs are usable."""
    read = {gateway.dataset_key(i.dataset) for i in items if i.status == "in"}
    rank = {"viable": 2, "use with caution": 1}
    out = []
    for name, spec in gateway.link_specs().items():
        ends = [gateway.dataset_key(spec.left.dataset), gateway.dataset_key(spec.right.dataset)]
        if not set(ends) & read:
            continue
        mine = sorted((r for r in runs if r["run"].get("spec") == name), key=lambda r: str(r["run"].get("period")))
        best = max((r.get("verdict") or "not viable" for r in mine), key=lambda v: rank.get(v, 0), default="not run")
        out.append({"link": name, "left": spec.left.dataset, "right": spec.right.dataset,
                    "sides_read": [s for s, k in zip(("left", "right"), ends, strict=True) if k in read],
                    "what": " ".join(str(spec.description).split()), "verdict": best,
                    "runs": [{"period": r["run"].get("period"), "method": r["run"].get("method"), "pairs": r.get("pairs"),
                              "chance_percent": r.get("chance_percent"),
                              "chance_upper95_percent": r.get("chance_upper95_percent"), "verdict": r.get("verdict")}
                             for r in mine]})
    return out


def _linked_items(items: list[Item], paths: list[dict], runs: list[dict], excluded: list[dict]) -> list[Item]:
    """The linked-share fields of the person paths (ARCHITECTURE §5.2): on every read source a usable path has a side
    on, the share of the source's events paired across the link (`fields.link_source`), over the years whose covering
    runs (`gateway.covering_runs`: a padded side's records of a year are paired by the runs around it) are all stored
    with a usable verdict. A year without one is left out and said, never read as unlinked. Only a path whose other
    side the study reads: the persons it follows are in systems it covers (B58 deaths' share linked to dengue
    notifications was a field of the exhaustive scope, 2026-10-12)."""
    from pegasus_data.linkage.engine import link_method, stored_key

    verdicts = {(r["run"].get("spec"), r["stem"]): r.get("verdict") for r in runs}
    read = {gateway.dataset_key(i.dataset) for i in items if i.status == "in"}
    out = []
    for p in (p for p in paths if p["verdict"] in USABLE_LINKS):
        method = link_method(p["link"])
        # a source's own events, or a code set of them (SIM's infarction deaths: the share that died after an admission,
        # the rest without one; code sets had no linked share, and a study of a cause of death no linkage, 2026-10-13)
        for it in (i for i in items if i.status == "in" and not i.count_only and (i.source is None or (
                (i.source or {}).get("codes") and set(i.source) <= {"codes", "classifier", "structure"}))):
            for side in (s for s in p["sides_read"] if gateway.same_dataset(p[s], it.dataset)):
                column = f"link:{p['link']}:{side}"
                other = p["right" if side == "left" else "left"]
                if gateway.dataset_key(other) not in read:
                    excluded.append({"seed": f"{it.dataset}:{column}", "why": f"its other side, {other}, is not read "
                                     "by the study"})
                    continue
                d = next((x for x in fields.declared_links(it.dataset, it.event) if x.column == column), None)
                if d is None:
                    continue
                if d.reason:
                    excluded.append({"seed": f"{it.dataset}:{column}", "why": d.reason})
                    continue
                spec_side = getattr(gateway.link_specs()[p["link"]], side)
                if (it.source or {}).get("codes") and spec_side.where:
                    # a code set on a side filtered to other events (the maternal deaths' link, an infarction's
                    # deaths): every one unlinked by construction, a zero no one measured (2026-10-13)
                    classifier = it.source.get("classifier") or fields.link_source(it.dataset, it.event,
                                                                                    column).get("classifier")
                    try:
                        n, kept = gateway.side_holds(p["link"], side, classifier, list(it.source["codes"]),
                                                     max(it.years))
                    except KeyError as exc:
                        excluded.append({"seed": f"{it.dataset}:{column}", "why": str(exc).strip("'\"")})
                        continue
                    if not kept:
                        excluded.append({"seed": f"{it.dataset}:{column}", "why": f"its side keeps none of the code "
                                         f"set's {n} records of {max(it.years)} ({spec_side.where})"})
                        continue
                other_side = getattr(gateway.link_specs()[p["link"]], "right" if side == "left" else "left")
                if (it.source or {}).get("codes") and other_side.where:
                    # the partner side filtered to other events (an infarction admission paired only with maternal
                    # deaths): the share would measure those events, never the topic's; read on its primary classifier
                    other_cls = next((c["column"] for e in gateway.event_types(other)
                                      for c in e.get("classifiers") or [] if c["role"] == "primary"), None)
                    try:
                        if other_cls is None:
                            raise KeyError(f"{other}: no primary classifier, its side's filter cannot be tested on "
                                           "the code set")
                        n, kept = gateway.side_holds(p["link"], "right" if side == "left" else "left", other_cls,
                                                     list(it.source["codes"]), max(it.years))
                    except KeyError as exc:
                        excluded.append({"seed": f"{it.dataset}:{column}", "why": str(exc).strip("'\"")})
                        continue
                    if not kept:
                        excluded.append({"seed": f"{it.dataset}:{column}", "why": f"its partner side, {other}, keeps "
                                         f"none of the code set's {n} records of {max(it.years)} ({other_side.where})"})
                        continue

                def usable(z: int, link: str = p["link"], method: str = method) -> bool:
                    # a run touching the confirmation reserve is a claim's, never a field's (`run_touches_reserve`)
                    return (verdicts.get((link, stored_key(link, method, z, "BR").stem)) in USABLE_LINKS
                            and not gateway.run_touches_reserve(link, z))

                ys = [y for y in it.years if all(usable(z) for z in gateway.covering_runs(p["link"], side, y))]
                if not ys:
                    excluded.append({"seed": f"{it.dataset}:{column}", "why": f"no year of {it.years[0]}-{it.years[-1]} "
                                     f"has every covering run of {p['link']} stored with a usable verdict"})
                    continue
                verdict = sorted({r["verdict"] for r in p["runs"] if r["verdict"] in USABLE_LINKS})
                items.append(Item(it.dataset, it.event, list(it.blocks), it.nodes, ys,
                                  f"person path {p['link']}: the share of its {side} side's events paired with "
                                  f"{p['right' if side == 'left' else 'left']} ({', '.join(verdict)})",
                                  source={**fields.link_source(it.dataset, it.event, column), **(it.source or {})},
                                  records=it.records,
                                  note="" if ys == it.years else f"years {sorted(set(it.years) - set(ys))} have no usable run"))
                out.append(items[-1])
    return out


def _concept_items(decl: Declaration, nodes: list[str], codes: list[str], items: list[Item], excluded: list[dict],
                   served: set[str]) -> None:
    """Scope v2's sources beyond the primary classifiers (ARCHITECTURE §4, BACKLOG 4.3), from pegasus_data's concept
    index (`pegasus_data.concept_index`):
    - every other ICD-10 classifier holding the seeds (SIA's diagnoses), read as a code set on that classifier;
    - the event types whose records name the codes as their condition (`pegasus_data.condition_codes`: a role of model
      ``event_type`` on ICD-10, SINAN's agravo code) beyond the seeded ones, read as a code set on that column;
    - SIGTAP procedures whose name matches a term (toxoplasma serology, the heel-prick IgM), read as a code set on
      every SIGTAP classifier. A procedure only *compatible* with the codes (a caesarean under O98.6) is not the topic's
      event: it is recorded in the scope's notes, and reached through its diagnoses."""
    import pegasus_data as pg

    prefixes = sorted(set(nodes) | set(codes))
    terms = decl.seeds.get("terms", [])
    if not prefixes and not terms:
        return
    ix = pg.concept_index(prefixes, terms, root=config.data_root())
    seeded = {it.dataset for it in items if it.source is None and it.nodes is None}
    procedures = sorted({r["code"] for r in ix["labels"] if r["structure"] == "SIGTAP" and r["level"] == "procedure"})
    for ds in sorted(served):
        for et in gateway.event_types(ds):
            for c in et.get("classifiers") or []:
                if c.get("role") == "primary" and c.get("structure") == "ICD10":
                    continue                    # read by the primary loop, with its tree
                if c.get("structure") == "ICD10" and prefixes:       # its records decide (`_records`)
                    # a classifier pegasus_data declares a recoding of the primary (`recodes`: SIM's CAUSABAS_O, the
                    # cause before investigation) codes the same events again: its rates are described beside the
                    # primary's, its questions, supports and links would restate the primary's (Alagoas's infarction
                    # deaths were asked twice over, 2026-10-14); another facet (SIA's diagnosis beside its procedure)
                    # reaches records the primary's codes do not, and is read whole
                    again = bool(c.get("recodes"))
                    items.append(Item(ds, et["name"], ["*"], None, [], f"its {c['role']} classifier {c['column']} "
                                      f"(ICD-10) carries {', '.join(prefixes)}, read as one code set"
                                      + (": a second coding of the same events, counted and described only" if again
                                         else ""),
                                      source={"classifier": c["column"], "codes": prefixes}, count_only=again))
                elif c.get("structure") == "SIGTAP" and procedures:
                    # the instruments SIGTAP registers each procedure on, against the column's (pegasus_data
                    # `can_record`): SIGTAP is every SIA dataset's tree, and the serology procedures, recorded by BPA
                    # and AIH only, made the survey decode 6,800 APAC files for none (2026-10-11); None (undeclared or
                    # unlisted) keeps the code
                    ok = [p for p in procedures if pg.can_record(ds, c["column"], [p], root=config.data_root()) is not False]
                    if not ok:
                        excluded.append({"seed": f"{ds}:{et['name']}", "why": f"its {c['column']} records instruments "
                                         f"SIGTAP registers none of {', '.join(procedures)} on"})
                        continue
                    # one field per SIGTAP chapter: a term matches procedures of different purposes, and a health-
                    # education activity summed with the antibody tests read as serology (2026-10-12)
                    for chapter, group in _by_chapter("SIGTAP", ok).items():
                        items.append(Item(ds, et["name"], ["*"], None, [], f"its {c['role']} classifier {c['column']} "
                                          f"(SIGTAP) holds the procedures named for the topic of its chapter {chapter} "
                                          f"({', '.join(group)})",
                                          source={"classifier": c["column"], "structure": "SIGTAP", "codes": group}))
    # the code lists a source declares on ICD-10 (SINASC's CODANOMAL, a birth's anomalies; a group of columns read as one
    # set, a certificate's lines), in a source no item above reads the seeds in: the topic's events on its records,
    # counted once under each category (`gateway.code_list_counts`). Reached only as a related field before, a
    # congenital anomaly could not be studied on its own source (the SINASC audit's microcephaly, 2026-10-14)
    if prefixes:
        tree = {r["code"]: r for r in gateway.code_tree("ICD10").to_pylist()}
        reading = {it.dataset for it in items if it.nodes or (it.source or {}).get("codes")}
        for ds in sorted(served - reading):
            lists = [fields.mentions_source(ds, d.column) for d in fields.declared_mentions(ds)]
            lists += [src for d in fields.declared_codes(ds) if not d.reason
                      and (src := fields.codes_source(ds, d.column)).get("source") == "code_list"
                      and src.get("structure") == "ICD10"]
            for et in gateway.event_types(ds) if lists else ():
                for src in lists:
                    items.append(Item(ds, et["name"], sorted({_chapter(tree, p) for p in prefixes}), prefixes, [],
                                      f"its code list {src['classifier'].split(':', 1)[1]} (ICD-10) is read for "
                                      f"{', '.join(prefixes)}: every code its records carry", source=src))
    # the columns that name a record's condition (the roles' event-type columns on ICD-10: SINAN's agravo code), where
    # the index counted the codes and no classifier above reads them already
    read = {(it.dataset, (it.source or {}).get("classifier")) for it in items}
    for d in ix["conditions"]:
        if d["dataset"] in seeded or d["dataset"] not in served or (d["dataset"], d["column"]) in read:
            continue
        for et in gateway.event_types(d["dataset"]):
            if any(c.get("column") == d["column"] and c.get("role") == "primary" for c in et.get("classifiers") or []):
                continue                    # its primary classifier: read with its tree by the primary loop
            items.append(Item(d["dataset"], et["name"], ["*"], None, [], f"its records' condition code ({d['column']}) "
                              f"carries {', '.join(f'{k} ({v})' for k, v in d['codes'].items())} in {d['year']}",
                              source={"classifier": d["column"], "codes": sorted(d["codes"])}))
    compatible = sorted({(r["procedure"], r["procedure_name"]) for r in ix["procedures"]})
    if compatible:
        excluded.append({"seed": "SIGTAP compatibility", "why": f"{len(compatible)} procedures are allowed under the codes "
                         "(not the topic's events: reached through their diagnoses): "
                         + "; ".join(f"{c} {n}" for c, n in compatible[:12]) + (" …" if len(compatible) > 12 else "")})
    weak = [r for r in ix["labels"] if r["structure"] == "ICD10" and not any(r["code"].startswith(p) for p in prefixes)]
    if weak:
        excluded.append({"seed": "terms", "why": "ICD-10 labels match a term but no seed holds them (a name, the weakest "
                         "evidence; add them as seeds to read them): " + ", ".join(f"{r['code']} {r['label']}" for r in weak)})


def resolve(decl: Declaration, log=print) -> Scope:
    """The scope of a declaration (ARCHITECTURE §4, version 1): every event type whose primary classifier holds the
    seeds' ICD-10 nodes, and the SINAN agravos named; each with the years it publishes and their download cost,
    deferred past the depth's budget."""
    _LAKE.clear()                         # the lake as it is now (`_cost`)
    if decl.where not in (None, "BR"):    # the study's area (`config.study_area`), read by every count and block
        os.environ["PEGASUS_AREA"] = ",".join(str(a) for a in decl.where)
    else:
        os.environ.pop("PEGASUS_AREA", None)
    os.environ["PEGASUS_NULLS"] = str(decl.choice("nulls"))   # every test's replicate worlds (`config.replicates`)
    items: list[Item] = []
    excluded: list[dict] = []
    served = set(gateway.event_datasets())
    for code in decl.seeds.get("sinan", []):
        ds = f"SINAN-{code.upper()}"
        if ds not in served:
            excluded.append({"seed": f"sinan:{code}", "why": "no SINAN dataset with event types by that code"})
            continue
        for et in gateway.event_types(ds):
            items.append(Item(ds, et["name"], ["*"], None, [], f"seed sinan:{code} (the agravo's own notifications)"))
    for r in decl.seeds.get("records", []):
        ds = str(r["dataset"])
        if ds not in served:
            excluded.append({"seed": f"records:{r['name']}", "why": f"no dataset {ds} with event types"})
            continue
        types = gateway.event_types(ds)
        base = str(r.get("event") or types[0]["name"])
        if base not in {e["name"] for e in types}:
            excluded.append({"seed": f"records:{r['name']}", "why": f"{ds} has no event type {base} "
                             f"({', '.join(e['name'] for e in types)})"})
            continue
        # a subset of births is a share of births (low birth weight per live birth); anything else per its residents
        # unless the seed names the events it is rated per (an infant death per live birth)
        kind = next(e for e in types if e["name"] == base).get("kind")
        per = r.get("per") or (f"{ds}:{base}" if kind == "birth" else None)
        if per and ":" not in str(per):
            per_types = gateway.event_types(str(per))
            per = f"{per}:{per_types[0]['name']}" if per_types else per
        event = gateway.condition_event(base, list(r["condition"]), str(r["name"]), per)
        items.append(Item(ds, event, ["*"], None, [], f"seed records: {r['name']} ({ds} {base} where "
                          f"{_condition_text(r['condition'])}" + (f"; per {per}" if per else "") + ")"))
    tree = {r["code"]: r for r in gateway.code_tree("ICD10").to_pylist()}
    nodes, codes = [], []
    for raw in decl.seeds.get("icd10", []):
        c = _icd(raw)
        if c not in tree:
            excluded.append({"seed": f"icd10:{raw}", "why": "not a node of the ICD-10 tree"})
        elif tree[c]["level"] == "subcategory":
            codes.append(c)      # read as a code set of its own: its category holds other conditions
        else:
            nodes.append(c)
    if nodes or codes:
        for ds in sorted(served):
            for et in gateway.event_types(ds):
                prim = next((c for c in et.get("classifiers") or [] if c.get("role") == "primary"), None)
                if not prim or prim.get("structure") != "ICD10":
                    continue
                try:
                    reg = fields.Registry(ds, et["name"], "ICD10", classifier=prim["column"])
                except Exception as exc:  # noqa: BLE001 - a dataset whose tree cannot be read is said, not hidden
                    excluded.append({"seed": f"{ds}:{et['name']}", "why": f"its classifier tree could not be read: {exc}"})
                    continue
                for c in (c for c in codes if c in reg.level):
                    items.append(Item(ds, et["name"], ["*"], None, [], f"its primary classifier ({prim['column']}) "
                                      f"holds {c} ({tree[c]['label']}), read as a field of its own (its category "
                                      f"{tree[c]['parent']} holds other conditions)", source={"codes": [c]}))
                held = [n for n in nodes if n in reg.level]
                if held and not decl.choice("chapters"):
                    # the topic's codes as one field of their own (a survey's default, or `chapters: false`): its node
                    # inside a fitted chapter (every infectious disease in 5,570 places over 16 years, for B58) was most
                    # of the survey's hours, and the chapter's context is standard depth's (2026-10-11)
                    items.append(Item(ds, et["name"], ["*"], None, [], f"its primary classifier ({prim['column']}) "
                                      f"holds {', '.join(held)}, read as a field of its own (not inside its chapter)",
                                      source={"codes": held}))
                    # and anywhere on its records (every diagnosis of an admission, every line of a certificate): the
                    # multiple-cause reading, and the only one of a code the source records beside the primary (SIH
                    # writes self-harm's X60-X84 as a secondary diagnosis of the injury: 7 primary records in ten
                    # years of Rio Grande do Sul, the suicide study read none, 2026-10-15)
                    for d in fields.declared_mentions(ds)[:1]:
                        src = fields.mentions_source(ds, d.column)
                        # one field, the code set anywhere on the record (each record once), not a field per code
                        items.append(Item(ds, et["name"], ["*"], None, [],
                                          f"{', '.join(held)} anywhere on its records "
                                          f"({src['classifier'].split(':', 1)[1]}): the multiple-cause reading",
                                          source={**src, "codes": held}))
                elif held:
                    mentions = [d.column for d in fields.declared_mentions(ds)] or None
                    items.append(Item(ds, et["name"], sorted({reg.chapter(n) for n in held}), held, [],
                                      f"its primary classifier ({prim['column']}) holds {', '.join(held)}"
                                      + (f"; also read in every code its records carry ({', '.join(mentions)})"
                                         if mentions else ""), mentions=mentions))
    _concept_items(decl, nodes, codes, items, excluded, served)
    for r in decl.ratios:
        try:
            num, den = _field_spec(r["numerator"]), _field_spec(r["denominator"])
        except LookupError as exc:
            excluded.append({"seed": f"ratio {r['numerator']} / {r['denominator']}", "why": str(exc)})
            continue
        lag = int(r.get("lag", 0))
        exposure = f"events:{den[0]}:{den[1]}" + (f":{','.join(den[2])}" if den[2] else "") + (f"@{lag}" if lag else "")
        items.append(Item(num[0], num[1], ["*"], None, [], f"declared ratio: {r['numerator']} per {r['denominator']}"
                          + (f" {lag} year(s) earlier" if lag else ""),
                          source={"population": exposure, **({"codes": num[2]} if num[2] else {})},
                          denominator=(den[0], lag)))
    # the declaration's own choice (`topic.only` / `topic.exclude`), before anything is priced or counted: the keys
    # were accepted and never applied, so no study could be cut down (2026-10-11)
    items = _declared_only(decl, items, excluded)
    # a declared relation's leader is read as the topic's sources are, whatever ``only`` says (declaring the relation
    # is asking for it): priced, fetched into the lake and counted, asked nothing. Read only by the products, it had
    # been fetched by none, and the test could not read it (the SINASC study's Zika, 2026-10-14)
    for h in decl.hypotheses:
        if str(h.get("component")) == "relation" and h.get("leader"):
            ds, _, ev = str(h["leader"]).partition(":")
            if ds not in served:
                excluded.append({"seed": f"relation leader {ds}", "why": "no dataset with event types by that name"})
                continue
            ev = ev or gateway.event_types(ds)[0]["name"]
            if not any(i.dataset == ds and i.event == ev for i in items):
                items.append(Item(ds, ev, ["*"], None, [], f"the leader of a declared relation "
                                  f"({h.get('note') or h['leader']})", count_only=True))
    # the cost: years in the lake are free, the rest download; the budget is spent cheapest first, and a source
    # whose tree holds the topic but whose records hold none is not read (its tree is not its records)
    budget = decl.choice("download")
    priced = []
    for it in items:
        ys, cost = _cost(it.dataset, decl.years)
        held = _extract_held(it, ys)
        if held:                          # its codes already extracted, whole, for these years: free, read from there
            cost = {y: (0.0 if y in held else c) for y, c in cost.items()}
            it.extract = True
        if it.denominator:
            # a ratio reads its denominator's years too (``lag`` earlier): both are priced, and only years both publish
            dys, dcost = _cost(it.denominator[0], [y - it.denominator[1] for y in decl.years])
            ys = [y for y in ys if y - it.denominator[1] in dys]
            cost = {y: (None if cost[y] is None or dcost[y - it.denominator[1]] is None
                        else cost[y] + dcost[y - it.denominator[1]]) for y in ys}
        # an event type rated per other events (live births, total births: pegasus_data's ``exposure``) reads them too:
        # its years are those its exposure publishes, priced with it (SIM-DOFET and the SINAN agravos, rated per
        # SINASC's 2024 births the lake did not hold, failed a download-free national run, 2026-10-13)
        declared = (gateway.event_type(it.dataset, it.event) or {}).get("exposure") or {}
        for ev in ([] if (it.source or {}).get("population") else declared.get("events") or []):
            eys, ecost = _cost(ev.split(":")[0], ys)
            ys = [y for y in ys if y in eys]
            cost = {y: (None if cost[y] is None or ecost[y] is None else cost[y] + ecost[y]) for y in ys}
        if not ys:
            it.status, it.note = "deferred", "publishes none of the study's years"
            continue
        paid = [y for y in ys if cost[y] != 0.0]
        priced.append((sum(cost[y] or 0.0 for y in paid), it, ys, cost, paid))
    spent, bought = 0.0, set()          # a dataset-year is downloaded once, whatever number of items read it
    for _, it, ys, cost, paid in sorted(priced, key=lambda r: r[0]):
        paid = [y for y in paid if (it.dataset, y) not in bought]
        gb = sum(cost[y] or 0.0 for y in paid)
        unknown = [y for y in paid if cost[y] is None]
        free = [y for y in ys if y not in paid]
        if paid and (spent + gb <= budget) and (not unknown or budget == float("inf")):
            it.years, it.download_gb = ys, round(gb, 2)
            spent += gb
            bought |= {(it.dataset, y) for y in paid}
            _extract_or_lake(it, gb)
        elif free and not paid:
            it.years = ys
        elif free:
            it.years = free
            it.note = (f"years {paid} deferred: {gb:.1f} GB to download against the study's budget of {budget:g} GB"
                       + (f"; {unknown} not sized by the catalog" if unknown else ""))
        elif not paid:
            it.years = ys
        else:
            it.status, it.years, it.download_gb = "deferred", ys, round(gb, 2)
            it.note = (f"{gb:.1f} GB to download against the study's budget of {budget:g} GB"
                       + (f"; {unknown} not sized by the catalog" if unknown else ""))
            continue
        held = [y for y in it.years if cost.get(y) == 0.0]
        if it.extract or not held:
            # counted when its data is there (`_prepare_store` builds its lake or extract; `_probe` reads one year
            # first): pricing a scope downloads nothing (the standard scope fetched SIA-AD's 2.5 GB to count it,
            # 2026-10-11)
            continue
        try:
            # over the years the lake holds, free: counted only when every year was held, CIHA (2009–2023 in the
            # lake, 2024–2025 not) went to a probe of its preliminary 2025 and was left out (2026-10-11)
            it.records = _records(it, held)
        except Exception as exc:  # noqa: BLE001 - a source that cannot be counted is deferred with why
            it.status, it.note = "deferred", f"its records could not be counted: {type(exc).__name__}: {exc}"
            continue
        if it.records == 0 and it.mentions:
            it.note = (it.note + "; " if it.note else "") + "no record has the topic as its primary code: read through its mentions"
        elif 0 < it.records < len(held) and not it.mentions:
            # fewer than one of the topic's records a year, nationally: no question can see a departure in it (SIA-PS
            # held 14 and its whole lake, 2,284 files, was built for them, 2026-10-12)
            it.status = "none"
            excluded.append({"seed": f"{it.dataset}:{it.event}", "why": f"{it.records} of the topic's records in "
                             f"{held[0]}-{held[-1]}, fewer than one a year: too few for any question"})
        elif it.records == 0:
            it.status = "none"
            excluded.append({"seed": f"{it.dataset}:{it.event}", "why": f"its tree holds {held_codes(it)} "
                             f"but its records hold none in {held[0]}-{held[-1]}, the years the lake holds"})
    if not decl.choice("readers"):
        # a survey reads the topic's primary codes; its codes anywhere on the records only where the primary reading
        # is too sparse for any question (a code a source records beside the primary one)
        primary = {(i.dataset, i.event) for i in items if i.status == "in" and (i.source or {}).get("codes")
                   and not i.reason.startswith("related")}
        for it in items:
            if (it.status == "in" and (it.source or {}).get("source") == "code_list" and "multiple-cause" in it.reason
                    and (it.dataset, it.event) in primary):
                it.status = "none"
                excluded.append({"seed": f"{it.dataset}:{it.event}:{(it.source or {}).get('classifier')}",
                                 "why": "a survey reads the topic's primary codes; anywhere on the records at standard "
                                        "depth or with readers declared"})
    items = [i for i in items if i.status != "none"]
    for it in items:
        # a code set's field is the codes' events only, a ratio's the numerator per denominator event: the declared
        # readers would read every event of the type against the population
        chosen = decl.choice("readers")
        it.readers = {} if it.source else {k: "all" for k in chosen if k != "linked"}
        it.questions = decl.choice("questions")
        # a code list's field is a code set too (its categories on the list): read at its other places as one is
        coded = bool(it.source) and ("codes" in it.source or it.source.get("source") == "code_list")             and not ({"population", "support"} & set(it.source))
        # a record condition's topic is one field as a code set is (its records' characteristics are the case mix's,
        # read by the products): as a whole type, every composition of SINASC had been a field of its own, 142 of
        # them for low birth weight in one state (2026-10-15)
        if gateway.split_event(it.event)[1] is not None and not it.source:
            it.readers = {"supports": "all"} if "supports" in chosen and not it.count_only else {}
            continue
        if coded and "supports" in chosen and not it.count_only:
            it.readers = {"supports": "all"}     # the code set at its other places
    # a dataset read as nested events (SINAN's notification, every row; its case, the rows its classification
    # confirms): its fields are asked of the narrower, the topic's own object, and the wider is counted only; asked of
    # both, every field ran twice and every finding came twice (the leptospirosis slice: 130 fields twice, over its
    # cap, 2026-10-12)
    narrower = {it.dataset for it in items if not it.source and gateway.event_type(it.dataset, it.event).get("status")}
    for it in items:
        if (it.readers and not it.source and it.dataset in narrower
                and not gateway.event_type(it.dataset, it.event).get("status")):
            it.readers = {}
            it.note = (it.note + "; " if it.note else "") + "counted only: its fields are asked of its confirmed events"
    runs = _link_runs()
    paths = _person_paths(items, runs)
    if "linked" in decl.choice("readers"):
        _linked_items(items, paths, runs, excluded)     # else the paths are listed; each linked share is a fit of its own
    _estimate(decl, items)
    contexts = sorted(gateway.declared_fields()) if decl.contexts == "auto" else list(decl.contexts)
    medicines = [{"substance": sub["name"], "use": sub.get("use", ""), "conditions": t["conditions"], "source": t["source"],
                  "note": t["note"], "catmat": sub.get("catmat"),
                  "contexts": [f"{sub['name']} ({r['field']})" for r in sub.get("reads") or ()]}
                 for t in (gateway.treatments(nodes + codes) if nodes or codes else []) for sub in t["substances"]]
    contexts += _medicines(nodes + codes)
    related = _related_codes(decl, items, sorted(set(nodes) | set(codes)), log)
    extra: list[tuple[float, Item]] = []            # (strength, item): the related codes' fields, the strongest read
    if decl.choice("related"):
        # each related code read as one field in each source that records it (a lead, never a cause)
        strength: dict[str, float] = {}
        for r in (r for r in related if r["related"]):
            strength[r["code"]] = max(strength.get(r["code"], 0.0), float(r.get("lift_low") or 0.0))
        extra += [(strength.get(_related_code(it), 0.0), it)
                  for it in _related_fields(decl, [r for r in related if r["related"]], served,
                                            {i.dataset for i in items if i.status == "in"})]
    kept = _declared_only(decl, [it for _, it in extra], excluded)
    # one field once before ranking: a related code read where the topic's own field already reads it (SIH's B58)
    # took a place among the strongest and was then dropped (`_one_per_field`), and the next ones listed it thrice
    kept = [it for it in _one_per_field(items + kept) if any(it is k for k in kept)]
    items += _strongest(decl, [(w, it) for w, it in extra if any(it is k for k in kept)])
    if decl.choice("replicate"):
        # replication in later years (ARCHITECTURE §8.3, acceptance item 6): selected on the years up to the last
        # LATER_YEARS held out, tested once on them; the survey's findings stood at R0 with nothing to replicate them
        for it in items:
            if it.status == "in" and not it.count_only and len(it.years) >= 2 * LATER_YEARS + 2:
                it.confirm_last = sorted(it.years)[-LATER_YEARS - 1]
    items = _shared_blocks(_one_per_field(items))
    for it in items:
        # the topic's fields and their linked shares are asked the declaration's questions; a related code's field is
        # read to relate it to the topic (`related_questions`, preset none): asked all eleven, 160 related fields made
        # the exhaustive scope's hours (2026-10-12)
        it.questions = ([] if it.count_only else decl.choice("related_questions") if it.reason.startswith("related code")
                        else decl.choice("questions"))
        it.q = float(decl.q)
        it.triage = bool(decl.choice("triage"))
    overlap, fixed, per_field = _phase_record(decl)
    overhead = fixed + per_field * sum(i.fields for i in items if i.status == "in")
    return Scope(decl.study, decl.depth, items, excluded, contexts, budget, related, paths,
                 _link_runs_needed([i for i in items if i.status == "in"]), medicines, overlap, overhead)


def _one_per_field(items: list[Item]) -> list[Item]:
    """One item per field: a code set read on the event type's primary classifier is the same field as the code set
    without one (SIH's B58 was read as the topic's and again as a related code found in SIM, on DIAG_PRINC, and the
    report listed each finding twice, 2026-10-12). The first keeps its reason; the later one is dropped."""
    out, seen = [], set()
    for it in items:
        src = dict(it.source or {})
        # a plain code set only: a linked share reads its classifier explicitly (`gateway.linked_counts` counts under
        # "*" without one, and Alagoas's linked infarction shares read no event, 2026-10-13)
        if src.get("classifier") and src.get("codes") and not src.get("source"):
            primary = next((c["column"] for c in gateway.event_type(it.dataset, it.event).get("classifiers") or []
                            if c["role"] == "primary"), None)
            if src["classifier"] == primary:
                src.pop("classifier")
                it.source = src
        key = (gateway.dataset_key(it.dataset), it.event, tuple(it.blocks), tuple(it.nodes or ()),
               json.dumps(src, sort_keys=True, default=str))       # years apart: the topic's item, first, reads more
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _shared_blocks(items: list[Item]) -> list[Item]:
    """Related codes read as nodes of one fitted block are one item, their nodes together: the block is fitted once and
    asked of each (the exhaustive scope held 504 such items in 124 blocks, each priced and run as a fit of its own,
    2026-10-12). Only read items of the same dataset, event, blocks, reader and years are joined."""
    out, by = [], {}
    for it in items:
        if it.status != "in" or not it.nodes or not it.reason.startswith("related code"):
            out.append(it)
            continue
        key = (gateway.dataset_key(it.dataset), it.event, tuple(it.blocks), json.dumps(it.source, sort_keys=True,
               default=str), tuple(it.years), it.confirm_last)
        if key not in by:
            by[key] = it
            out.append(it)
            continue
        m = by[key]
        m.nodes = sorted(set(m.nodes) | set(it.nodes))
        m.est_seconds = max(m.est_seconds or 0.0, it.est_seconds or 0.0) or None
        m.reason = (m.reason.split(" (with related codes")[0] + f" (with related codes "
                    f"{', '.join(n for n in m.nodes if n != m.nodes[0])} in the same block)")
    return out


def _dataset_matches(name: str, entry: str) -> bool:
    """Whether ``name`` is the dataset ``entry`` names (any spelling: `parse_dataset`), or of the system it names alone
    ("SIASUS" is every SIA dataset)."""
    from pegasus_data._request import parse_dataset

    def canon(x):
        try:
            return parse_dataset(x)
        except Exception:  # noqa: BLE001 - a name pegasus_data does not parse is compared as written
            return (x, None)

    a, b = canon(name), canon(entry)
    return a == b or (b[1] in (None, b[0]) and "-" not in entry and "." not in entry and a[0] == b[0])


def _declared_only(decl: Declaration, items: list[Item], excluded: list[dict]) -> list[Item]:
    """The items the declaration allows: when ``topic.only`` names datasets (or systems), only theirs; never those
    ``topic.exclude`` names. What is left out is listed with why."""
    out = []
    for it in items:
        if decl.only and not any(_dataset_matches(it.dataset, e) for e in decl.only):
            why = "not among the declaration's topic.only"
        elif any(_dataset_matches(it.dataset, e) for e in decl.exclude):
            why = "named in the declaration's topic.exclude"
        else:
            out.append(it)
            continue
        row = {"seed": f"{it.dataset}:{it.event}", "why": why}
        if row not in excluded:     # one row per source and why (SINASC's denominator items, listed 300 times)
            excluded.append(row)
    return out


#: the later years a deep study holds out to replicate its leads in (`Item.confirm_last`)
LATER_YEARS = 3


#: the next strongest related codes the scope prices beyond those read, so it shows what reading more would cost (every
#: related code stays listed with its strength in ``related_codes``)
RELATED_SHOWN = 3


def _related_code(it: Item) -> str:
    return ((it.source or {}).get("codes") or it.nodes or [""])[0]


def _strongest(decl: Declaration, extra: list[tuple[float, Item]]) -> list[Item]:
    """The related fields ``extra`` (strength, item), by code: every field of the declaration's ``related`` strongest
    codes read (the lower bound of the code's lift; a code is read wherever it is recorded: "related: 4" had read one
    code, H32, in four of its fourteen places, 2026-10-12), those of the next `RELATED_SHOWN` codes deferred with their
    cost. The rest are neither priced nor items: each stays in the scope's ``related_codes`` with its strength."""
    n = decl.choice("related")
    best: dict[str, float] = {}
    for w, it in extra:
        best[_related_code(it)] = max(best.get(_related_code(it), float("-inf")), w)
    order = sorted(best, key=lambda c: -best[c])
    if isinstance(n, list):
        # the codes the declaration names, read whatever their strength (a paper's related conditions are chosen by
        # their meaning: ocular toxoplasmosis, not every HIV admission, 2026-10-13); the strongest others shown
        wanted = [c.replace(".", "") for c in n]
        order = [c for c in wanted if c in best] + [c for c in order if c not in wanted]
        n = len([c for c in wanted if c in best])
    rank = {c: k for k, c in enumerate(order[:int(min(n, len(order))) + RELATED_SHOWN], 1)}
    added = [it for _, it in extra if _related_code(it) in rank]
    for it in added:
        it.questions = decl.choice("related_questions")
    _estimate(decl, added)
    for it in added:
        k = rank[_related_code(it)]
        if k > n:
            it.status = "deferred"
            it.note = (f"related code {k} by strength ({_related_code(it)}, lift's lower bound "
                       f"{best[_related_code(it)]:.1f}), past the {'declared' if decl.related is not None else decl.depth} "
                       f"{n:g}: related: {k} reads it")
    return added


def _phase_record(decl: Declaration) -> tuple[float, float, float]:
    """From the measured runs (their provenance's ``phases`` and ``products_seconds``): how many items' seconds one
    second of the lanes held (their overlap); the scope, store and products phases' fixed seconds; and the products'
    seconds per field asked (each field's tables, figures, maps and groups). This study's own last run at this depth
    first, else the median of the others at this depth, else of any. A run's products scale with its fields, not its
    items: priced per item, from small studies whose capture and hypotheses dominate, the national exhaustive scope's
    199 items were priced at 115 min of products (2026-10-12). (1, 0, 0) before any run."""
    import glob

    def record(prov):
        ph = prov.get("phases") or {}
        if not ph.get("lanes"):
            return None
        steps = [v for v in (prov.get("steps") or {}).values() if isinstance(v, dict)]
        summed = sum(float(v.get("seconds") or 0) for v in steps)
        asked = max(sum(1 for v in steps for k in v if k.startswith("questions ")), 1)
        ps = prov.get("products_seconds") or {}
        per = sum(float(v) for k, v in ps.items() if k.startswith("fields")) if ps else 0.0
        whole = float(ph.get("scope", 0) + ph.get("store", 0) + ph.get("products", 0))
        # without products_seconds (runs before 2026-10-12) its products are all fixed: an underestimate of the fields'
        return max(summed / float(ph["lanes"]), 1.0), max(whole - per, 0.0), per / asked

    path = folder_of(decl) / "provenance.json"
    try:
        prov = json.loads(path.read_text(encoding="utf-8"))
        own = record(prov) if prov.get("depth") == decl.depth else None
    except (OSError, ValueError):
        own = None
    if own:
        return own
    others, anywhere = [], []
    for p in glob.glob(str(decl.path.parent / "*" / "provenance.json")):
        try:
            pr = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if r := record(pr):
            (others if pr.get("depth") == decl.depth else anywhere).append(r)
    others = others or anywhere
    if not others:
        return 1.0, 0.0, 0.0
    return tuple(float(np.median([r[k] for r in others])) for k in range(3))


def _link_runs_needed(read: list[Item]) -> list[dict]:
    """The national link runs the items' plans read (`update.plan_links`: their person fields and the links through
    which corroboration removes shared records) that the store lacks, each priced by the stored runs' measured wall
    time (the link's own, else every link's median; None when none was measured): `_prepare_store` computes them."""
    from . import update

    others = [[o.dataset, o.event] for o in read]
    specs = gateway.link_specs()
    want: dict[tuple[str, int], None] = {}
    published: dict[str, frozenset[int]] = {}
    for it in read:
        plan = _plan(it, [o for o in others if o[0] != it.dataset])
        try:
            links = update.plan_links(plan)
        except Exception:  # noqa: BLE001 - an item whose links cannot be listed computes none here; its run says why
            continue
        for link, side in links:
            if link not in specs:
                continue
            sides = (specs[link].left.dataset, specs[link].right.dataset)
            for z in sorted({z for y in it.years for z in gateway.covering_runs(link, side, y) if z <= max(it.years)}):
                if all(z in published.setdefault(d, gateway.published_years(d)) for d in sides):
                    want[(link, z)] = None
    missing = [(link, z) for link, z in want if gateway.link_report(link, z) is None]
    if not missing:
        return []
    timed: dict[str, list[float]] = {}
    for link in {k for k, _ in missing}:
        for report in (Path(config.data_root()) / "lake" / "links" / link).glob("*.json"):
            sec = json.loads(report.read_text(encoding="utf-8")).get("seconds")
            if sec:
                timed.setdefault(link, []).append(float(sec))
    every = [x for v in timed.values() for x in v]
    return [{"link": link, "year": z,
             "est_seconds": float(np.median(timed.get(link) or every)) if (timed.get(link) or every) else None}
            for link, z in missing]


def _medicines(codes: list[str]) -> list[dict]:
    """The topic's medicines as context entries (acceptance item 1: "BNAFAR/SNGPC for those medicines"): every
    substance an official document gives for the seed codes (`gateway.treatments`), read through each declared field
    that counts it, with its filter and denominator, and the document as its reason. Retail sales are a context of the
    topic, never its count: SUS dispenses the strategic component outside them."""
    out = []
    for t in gateway.treatments(codes) if codes else []:
        for sub in t["substances"]:
            for read in sub.get("reads") or ():
                out.append({"field": read["field"], "where": dict(read["where"]), **({"over": read["over"]} if read.get("over") else {}),
                            "name": f"{sub['name']} ({read['field']})",
                            "reason": f"{sub['name']}: {sub.get('use', '')}; treatment of {', '.join(t['conditions'])} "
                                      f"({t['source']})"})
    return out


#: the latest years a study reads persons in (each a cohort scan over every person of the year), and the link draws
PERSON_YEARS = 3


def _persons(decl: Declaration, scope: Scope, log) -> list[dict]:
    """The cohort scan (`tools.cohort`, ARCHITECTURE §7.8, acceptance item 5) for every read source whose records are the
    topic's persons (an agravo's own notifications, or a source whose records carry the topic's related codes) and a
    person on a usable declared link (`USABLE_LINKS`; pegasus_data links' ``person``): its persons of the latest
    `PERSON_YEARS` years whose scopes hold them, against every person kind they reach through those links, and against
    the study's related codes on the source's own code lists (a birth's anomalies). A source with no usable link, or
    whose persons carry no attribute, is said, not scanned."""
    from pegasus_data.linkage.engine import links_file
    from pegasus_data.semantics.curation import read_yaml

    from . import tools

    raw = read_yaml(links_file()).get("links") or {}
    usable = [p for p in scope.paths if p.get("verdict") in USABLE_LINKS]
    kinds: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for p in usable:
        roles = list((raw.get(p["link"]) or {}).get("person") or [])
        if len(roles) != 2:
            continue
        a, b = (gateway.data_code(p["left"]), roles[0]), (gateway.data_code(p["right"]), roles[1])
        kinds.setdefault(a, set()).add(b)
        kinds.setdefault(b, set()).add(a)
    out, done = [], set()
    # the narrower event first (a confirmed case before the notification it is one of): the cohort is the topic's
    # cases, and the notifications had been scanned, discarded ones included (257 of 2023's congenital
    # notifications in Rio Grande do Sul against 186 confirmed, 2026-10-12)
    ordered = sorted((i for i in scope.items if i.status == "in"),
                     key=lambda i: not gateway.event_type(i.dataset, i.event).get("status"))
    for it in ordered:
        for kind, reach in kinds.items():
            if not gateway.same_dataset(kind[0], it.dataset) or (it.dataset, kind) in done:
                continue
            done.add((it.dataset, kind))
            # the outcome on the person's own record: the topic's codes on a declared code list the study reads in this
            # source (`_related_fields`: SINASC's CODANOMAL with an anomaly found beside the topic's codes)
            same = [("record", f"{col}~{','.join(o.nodes)}") for o in scope.items
                    if o.status == "in" and gateway.same_dataset(o.dataset, it.dataset) and o.nodes
                    and (o.source or {}).get("source") == "code_list" for col in (o.source or {}).get("column") or []]
            same = list(dict.fromkeys(same))
            # the persons must be the topic's: an agravo's own notifications (every record is the topic), a source
            # whose own records carry the topic's related codes (a birth's anomalies), or a code set's own records (the
            # topic's admissions, read at the scan by their codes: every admission of SIH is not; the Alagoas study's
            # SIH-SIM persons had been said "no source", 2026-10-14)
            src = it.source or {}
            coded = bool(src.get("codes")) and not src.get("source") and not it.count_only
            if not (it.reason.startswith("seed sinan:") or same or coded):
                continue
            classifier = (src.get("classifier") or next((c["column"] for c in gateway.event_type(it.dataset, it.event)
                                                         .get("classifiers") or [] if c.get("role") == "primary"), None)
                          if coded else None)
            outcomes = [(d, role) for d, role in sorted(reach)] + same
            years = [y for y in sorted(it.years)[::-1] if gateway.person_scopes(kind, y)][:PERSON_YEARS]
            label = f"{it.dataset} {kind[1]}"
            if not years:
                out.append({"cohort": label, "note": "no year of the study holds its persons' link runs"})
                continue
            for y in years:
                mine = sorted({o.dataset for o in scope.items if o.status == "in"})   # the persons of its own links
                key = {"what": "study_cohort", "kind": list(kind), "event": it.event, "outcomes": outcomes, "year": y,
                       **({"classifier": classifier, "codes": sorted(src["codes"])} if coded else {}),
                       "draws": decl.choice("draws"), "q": decl.q, "data": config.data_version(),
                       "code": config.code_key(tools.cohort), "datasets": mine}
                key = _study_key(key)
                hit = store.get_table("study_table", key)
                if hit is not None:
                    out.extend(hit.to_pylist())
                    continue
                notes: list[dict] = []
                try:
                    found = tools.cohort(it.dataset, it.event, kind[1], outcomes, y, draws=decl.choice("draws"),
                                         q=decl.q, log=log, datasets=mine, notes=notes, classifier=classifier,
                                         codes=tuple(src.get("codes") or ()) if coded else ())
                except Exception as exc:  # noqa: BLE001 - a cohort that cannot be read is said; the others run
                    out.append({"cohort": label, "year": y, "note": f"not scanned: {type(exc).__name__}: {exc}"})
                    continue
                rows = [{"cohort": label, "year": y, "outcome": x.fields[1].removeprefix("person:"),
                         "attribute": x.locus.get("attribute"), "level": x.locus.get("level"),
                         "reference": x.locus.get("reference"), "rr": float(x.effect),
                         "low": float(x.interval[0]) if x.interval else None,
                         "high": float(x.interval[1]) if x.interval else None, "q": float(x.q)} for x in found]
                rows += [{"cohort": label, "year": y, **n} for n in notes]     # an outcome no direct link reached
                store.put_table("study_table", key, _rows_table(rows) if rows else pa.table({"cohort": pa.array([], pa.string())}))
                out.extend(rows)
    for r in out:
        # a contrast of a missing level is the records' completeness, not a risk: Alagoas's deaths with a linked
        # admission had education blank 5.4x as often, hospital certificates leaving it (2026-10-14); kept, and said
        if r.get("level") is not None:
            r["recording"] = str(r["level"]) in ("blank", "not recorded", "value missing")
    if not out:
        # said, never an empty table: leptospirosis' slice wrote none, read as a part missing (2026-10-12)
        topic = sorted({i.dataset for i in scope.items if i.status == "in" and i.reason.startswith("seed sinan:")})
        out.append({"cohort": ", ".join(topic) or "the topic's sources",
                    "note": "no persons scanned: no declared person link with a usable run reaches the topic's own "
                            "records (pegasus_data links.yml)" if not usable else
                            "no persons scanned: the usable links reach no source whose records are the topic's persons"})
    return out


def _capture(decl: Declaration, scope: Scope, log) -> list[dict]:
    """Capture–recapture over the read systems (`capture`, acceptance items 2 and 5): the population pegasus_data
    declares for the topic's codes, over the study's years whose covering runs of every link between its lists are
    stored with a usable verdict and touch no reserve; pooled across them. Linkage uncertainty is not drawn here: the
    undrawn persons, said in the report."""
    from . import capture

    read = sorted({gateway.data_code(i.dataset) for i in scope.items if i.status == "in"})
    codes = list(decl.seeds.get("icd10") or [])

    def usable(links: list[str], year: int) -> str | None:
        # a year's persons are its own runs' (`gateway.persons`): each link's run of that year, stored usable and
        # touching no reserve (every padded neighbour had been required, and no year passed); the worst verdict
        verdicts = [None if gateway.run_touches_reserve(link, year) else
                    (gateway.link_report(link, year) or {}).get("verdict") for link in links]
        if not links or any(v not in USABLE_LINKS for v in verdicts):
            return None
        return "viable" if all(v == "viable" for v in verdicts) else "use with caution"

    try:
        if capture.lists_of(read, codes) is None:
            # said, never an empty table
            return [{"population": "", "note": f"no capture population declared for {', '.join(codes) or 'the topic'} "
                     "whose lists are among the read sources (pegasus_data captures.yml)"}]
        return capture.capture(read, codes, list(decl.years), usable, log=log)
    except Exception as exc:  # noqa: BLE001 - a capture that cannot be read is said; the folder stands
        log(f"study: capture: {type(exc).__name__}: {exc}")
        return [{"population": "", "note": f"not computed: {type(exc).__name__}: {exc}"}]


def _capture_note(scope: Scope) -> str:
    """Whether the read systems can estimate each other's completeness (capture–recapture, ARCHITECTURE §5.2): three
    systems linked pairwise by viable runs, from the scope's person paths; otherwise which links stand in the way. Every
    link of a pair is named: a pair's links pair different records (SIH × SIM: admissions that ended in death, or the
    topic's admissions to the certificates naming it). Two lists cannot test their own dependence (a child admitted is
    likelier to be notified), so a pair alone gives a lower bound at best, and none is stated as an estimate."""
    read = {gateway.dataset_key(i.dataset) for i in scope.items if i.status == "in"}
    links: dict[frozenset, list[tuple[str, str]]] = {}
    for p in scope.paths:
        a, b = gateway.dataset_key(p["left"]), gateway.dataset_key(p["right"])
        if a in read and b in read and a != b and set(p.get("sides_read") or ()) >= {"left", "right"}:
            links.setdefault(frozenset((a, b)), []).append((p["link"], p["verdict"]))
    names = sorted(read)
    edges = lambda t: (frozenset((t[0], t[1])), frozenset((t[0], t[2])), frozenset((t[1], t[2])))   # noqa: E731
    triangles = [(a, b, c) for i, a in enumerate(names) for j, b in enumerate(names[i + 1:], i + 1) for c in names[j + 1:]
                 if all(x in links for x in edges((a, b, c)))]
    said = lambda x: " or ".join(f"{name} {verdict}" for name, verdict in links[x])   # noqa: E731
    ready = [t for t in triangles if all(any(v == "viable" for _, v in links[x]) for x in edges(t))]
    if ready:
        return ("Three systems are linked pairwise by viable runs (" + "; ".join(
            " × ".join(t) + ": " + "; ".join(said(x) for x in edges(t)) for t in ready) + "): their completeness is "
            "estimable by capture–recapture where these links pair the topic's records; not computed at this depth.")
    if triangles:
        return ("No completeness is estimated: capture–recapture needs three systems linked pairwise by viable runs. "
                + " ".join(" × ".join(t) + ": " + "; ".join(said(x) for x in edges(t)) + "." for t in triangles)
                + " Two linked lists cannot test their own dependence, so a pair would give a lower bound at best.")
    pairs = "; ".join(f"{' × '.join(sorted(k))}: {said(k)}" for k in sorted(links, key=sorted))
    return ("No completeness is estimated: no three read systems are linked pairwise" +
            (f" (linked pairs: {pairs}). Two lists cannot test their own dependence, so a pair would give a lower bound "
             "at best." if pairs else "."))


def _chapter(tree: dict, code: str) -> str:
    """The ICD-10 chapter holding ``code``, up its parents (the block a code's node is fitted in)."""
    for _ in range(10):
        if code not in tree or tree[code]["level"] == "chapter":
            break
        code = tree[code]["parent"]
    return code if code in tree and tree[code]["level"] == "chapter" else "*"


def _related_fields(decl: Declaration, related: list[dict], served: set[str], topic: set[str]) -> list[Item]:
    """Each related code as one field in each source that records it (ARCHITECTURE §4.3, acceptance item 1: births with
    the anomalies found beside the topic's codes in admissions or deaths), over the study's years already in the lake
    (a related code buys no download). In a source that holds the topic (``topic``), the code on its primary ICD-10
    classifier (else its first) as a code set; in any other, the code anywhere on its records: its declared mention
    group (every line of a certificate), else its first code list (SINASC's anomalies), as the code's node of that
    list's tree. One field a source: read on every classifier and every certificate line apart, the exhaustive scope
    held 725 fields of 20 codes, 31 hours (2026-10-12); in every source's diagnosis columns, the deep scope 386 items
    and 848 minutes, B20–B24 in radiotherapy and dialysis authorisations among them (2026-10-11)."""
    tree = {r["code"]: r for r in gateway.code_tree("ICD10").to_pylist()}
    found = {}
    for r in related:
        found.setdefault((r["code"], gateway.dataset_key(r["dataset"])), r)
    out, seen = [], set()
    for r in sorted(related, key=lambda r: -float(r.get("lift_low") or 0.0)):
        code = r["code"]
        if code not in tree:
            continue
        for ds in sorted(served):
            try:
                ets = gateway.event_types(ds)
                ys, cost = _cost(ds, decl.years)
            except Exception:  # noqa: BLE001 - a source that cannot be listed is not read for it
                continue
            ys = [y for y in ys if cost.get(y) == 0.0]
            if not ys:
                continue
            here = found.get((code, gateway.dataset_key(ds)))
            why = (f"related code {code} ({r['label']}): on {here['with_code']:.0f} of its records with the topic's codes, "
                   f"{here['lift']:.1f} times expected" if here else
                   f"related code {code} ({r['label']}), found on {r['dataset']} records with the topic's codes")
            mine = any(gateway.same_dataset(ds, t) for t in topic)
            for et in ets:
                if (ds, et["name"], code) in seen:
                    continue
                if mine:
                    icd = [c for c in et.get("classifiers") or [] if c.get("structure") == "ICD10"]
                    c = next((c for c in icd if c["role"] == "primary"), icd[0] if icd else None)
                    if c is None:
                        continue
                    seen.add((ds, et["name"], code))
                    out.append(Item(ds, et["name"], ["*"], None, ys, why + ("" if c["role"] == "primary" else
                                                                             f"; read in its {c['column']}"),
                                    source={"codes": [code]} if c["role"] == "primary" else
                                    {"classifier": c["column"], "codes": [code]}))
                    continue
                lists = [fields.mentions_source(ds, d.column) for d in fields.declared_mentions(ds)]
                lists += [src for d in fields.declared_codes(ds) if not d.reason
                          and (src := fields.codes_source(ds, d.column)).get("source") == "code_list"
                          and src.get("structure") == "ICD10"]
                if not lists:
                    continue
                seen.add((ds, et["name"], code))
                out.append(Item(ds, et["name"], [_chapter(tree, code)], [code], ys,
                                f"{why}; read anywhere on its records ({lists[0]['classifier'].split(':', 1)[1]})",
                                source=lists[0]))
    return out


# ---------------------------------------------------------------------- the run


def nothing_read(scope: Scope) -> str:
    """Why a scope reads no source, and what to change: the download budget an item needs, or what a seed named."""
    need = [i.download_gb for i in scope.items if i.status == "deferred" and i.download_gb]
    if need:
        return (f"nothing is read: every source is deferred past the download budget of {scope.budget_gb:g} GB; "
                f"`download: {np.ceil(min(need) + 0.5):.0f}` reads the first ({min(need):.1f} GB), years in the lake "
                "are free")
    why = "; ".join(f"{x['seed']}: {x['why']}" for x in scope.excluded[:5])
    return f"nothing is read: no source holds the topic's codes in the study's years and place ({why})"


def folder_of(decl: Declaration) -> Path:
    return decl.path.parent / decl.study


def run(decl: Declaration, log=print, products_only: bool = False) -> Path:
    """Compute the study and write its folder (ARCHITECTURE §3.4). Each read event type runs through `update` on its own
    years with the topic's nodes; the leads of those fields become the findings. ``products_only``: the lanes are not
    run, the products are written from the fits and answers the store holds (a change to the products measured in
    minutes; a field whose fit is not stored is a note)."""
    import yaml

    t0 = time.time()
    _CASE_FATALITY_DONE.clear()
    # the study's area for this process and its lanes (`config.study_area`): every block is the area's
    if decl.where not in (None, "BR"):
        os.environ["PEGASUS_AREA"] = ",".join(str(a) for a in decl.where)
    else:
        os.environ.pop("PEGASUS_AREA", None)
    out = folder_of(decl)
    out.mkdir(parents=True, exist_ok=True)
    # this run's products only: an earlier run's report, provenance, README and figures had stood beside a killed run's
    # new tables, and `body` read the old "every step ran" (the review of the study, 2026-10-14); a table the code no
    # longer writes had stayed in the folder and in study.duckdb (the ten estimates.parquet replaced, 2026-10-14)
    for old in ("report.html", "provenance.json", "README.md", "METHODS.md", "municipalities.geojson",
                *(p.name for p in out.glob("*.parquet")), *(p.name for p in out.glob("study.*.duckdb.tmp"))):
        (out / old).unlink(missing_ok=True)
    for old in ("figures", "expectations"):
        if (out / old).exists():
            shutil.rmtree(out / old, ignore_errors=True)
    shutil.copyfile(decl.path, out / "study.yml")
    phases, t = {}, time.time()
    scope = resolve(decl, log=log)
    phases["scope"] = round(time.time() - t, 1)
    estimate = scope.to_dict()["estimated_minutes"]            # made before running (acceptance item 10), kept as made
    (out / "scope.yml").write_text(yaml.safe_dump(scope.to_dict(), sort_keys=False, allow_unicode=True), encoding="utf-8")
    read = [i for i in scope.items if i.status == "in"]
    if not read:
        # an empty folder is never written as a study (dengue in Goiás deferred every item past its budget, 2026-10-15)
        raise DeclarationError(f"{decl.path}: {nothing_read(scope)}")
    t = time.time()
    read = _probe(scope, read, log)
    prepared = _prepare_store(decl, read, log)
    read = _count_prepared(scope, read, log)
    # from here nothing downloads: the scope priced what the study reads and the store step fetched it; the lanes
    # inherit the limit (`gateway.max_download`)
    os.environ["PEGASUS_MAX_DOWNLOAD"] = "0"
    (out / "scope.yml").write_text(yaml.safe_dump({**scope.to_dict(), "estimated_minutes": estimate}, sort_keys=False,
                                                  allow_unicode=True), encoding="utf-8")
    phases["store"], t = round(time.time() - t, 1), time.time()
    steps = {} if products_only else _run_items(decl, read, log)
    phases["lanes"], t = round(time.time() - t, 1), time.time()
    products = _Lap()
    tables = _write_products(decl, scope, out, log, products)
    phases["products"] = round(time.time() - t, 1)
    # the wall clock of each phase against the scope's estimate (acceptance item 10), what the next estimate reads
    prov = {"study": decl.study, "depth": decl.depth, "written": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "seconds": round(time.time() - t0, 1), "phases": phases, "products_seconds": dict(products),
            "estimated_minutes": estimate,
            "code_version": config.code_version(), "data_version": config.data_version(), "store": prepared,
            "steps": steps, "products_only": products_only, "store_tables": tables,
            "products_failed": dict(products.failed),
            "products_gaps": dict(products.gaps)}
    (out / "provenance.json").write_text(json.dumps(prov, indent=1, default=str), encoding="utf-8")
    os.environ.pop("PEGASUS_MAX_DOWNLOAD", None)
    log(f"study {decl.study}: written to {out} in {time.time() - t0:.0f} s")
    return out


def held_codes(it: Item) -> str:
    return ", ".join(it.nodes or (it.source or {}).get("codes") or ["its events"])


def _probe(scope: Scope, read: list[Item], log) -> list[Item]:
    """Before a source's years are fetched to count the topic in them, its latest year alone: an item priced without a
    count (its data not in the lake) whose probe year holds none of the topic's records, and that has no mentions to
    read them through, is left out with why, and its other years are never fetched. Survey10 decoded 6,800 files of
    SIA-AN and SIA-AR, all its years, for items holding none (2026-10-11)."""
    keep = []
    for it in read:
        if it.records is not None or it.extract or it.mentions or not it.years or it.denominator:
            keep.append(it)
            continue
        # the years the lake holds, all of them (free; a related code's item comes here uncounted); else its largest
        # published year, the most records and the most complete (the newest is often preliminary, a fraction of a
        # year: CIHA's 2025 held none of the topic, its 2009–2023 do)
        import pegasus_data as pg

        held = sorted(set(it.years) & set(pg.lake_coverage(it.dataset, root=config.data_root())))
        volume = _volumes(it.dataset, config.data_root())
        probe = held or [max(it.years, key=lambda y: (volume.get(y) or 0.0, y))]
        year = probe[-1]
        try:
            if not held:
                gateway.ensure_lake(it.dataset, probe, log=log)
            n = _records(it, probe)
        except Exception as exc:  # noqa: BLE001 - a probe that fails decides nothing: the item goes on, its run says why
            log(f"study: probe {it.dataset} {year}: {type(exc).__name__}: {exc}")
            keep.append(it)
            continue
        if held:
            it.records = n
        if held and 0 < n < len(held) and not it.mentions:
            it.status = "none"
            scope.excluded.append({"seed": f"{it.dataset}:{it.event}", "why": f"{n} of the topic's records in "
                                   f"{held[0]}-{held[-1]}, fewer than one a year: too few for any question"})
            continue
        if n == 0:
            it.status = "none"
            scope.excluded.append({"seed": f"{it.dataset}:{it.event}", "why": f"its tree holds {held_codes(it)} but "
                                   f"{probe[0]}-{year} hold none of them" + ("" if held else "; its other years were not fetched")})
            log(f"study: {it.dataset} {it.event} {held_codes(it)}: none in {probe[0]}-{year}")
            continue
        keep.append(it)
    scope.items = [i for i in scope.items if i.status != "none"]
    return keep


def _count_prepared(scope: Scope, read: list[Item], log) -> list[Item]:
    """The items pricing admitted uncounted (their data was not in the lake: `resolve` downloads nothing), counted now
    that `_prepare_store` built it, by the rule `resolve` applies: none of the topic's records, and no mentions to read
    them through, is no field (SIA-AN's serology codes, 0 records in 2010–2014, had been fitted and failed, survey10)."""
    keep = []
    for it in read:
        # an extract's item too, from its extract: a code set split by SIGTAP chapter held none of Rio Grande do Sul's
        # records (a health-education activity) and its fit failed on an empty table (2026-10-12)
        if it.records is None:
            try:
                it.records = _records(it, it.years)
            except Exception as exc:  # noqa: BLE001 - counted by its own run then, which says why if it cannot
                log(f"study: {it.dataset} {it.event}: records not counted after the store: {type(exc).__name__}: {exc}")
            if it.records == 0 and not it.mentions:
                it.status = "none"
                scope.excluded.append({"seed": f"{it.dataset}:{it.event}", "why": f"its tree holds {held_codes(it)} but its "
                                       f"records hold none in {it.years[0]}-{it.years[-1]} (counted once its lake was built)"})
                continue
        keep.append(it)
    scope.items = [i for i in scope.items if i.status != "none"]
    return keep


def _prepare_store(decl: Declaration, read: list[Item], log) -> dict:
    """The store products the items share, made once, here, before the lanes: every item's lake (its own dataset's and
    its links' sides) and the national link runs its plan reads (`update._ensure_lake`, `update._ensure_links`). Made
    inside the lanes, a link run (8-12 min and 11 GB a year for CIHA's deaths, 2026-10-11) held a lane's memory and
    its group, and two lanes reading one link both computed it. Serial: one FTP connection, and a link run's memory is
    the largest a study holds; an item's own run then finds them stored."""
    from . import update

    t0 = time.time()
    others = [[o.dataset, o.event] for o in read]
    out: dict = {}
    for ds in dict.fromkeys(i.dataset for i in read if i.extract):
        try:
            _ensure_extract([i for i in read if i.extract and i.dataset == ds], out, log)
        except Exception as exc:  # noqa: BLE001 - the items' own runs fail on it and record why
            out[f"extract {ds}"] = f"failed: {type(exc).__name__}: {exc}"
    for it in read:
        plan = _plan(it, [o for o in others if o[0] != it.dataset])
        try:
            update._ensure_lake(plan, out, log)
            update._ensure_links(plan, out, log)
        except Exception as exc:  # noqa: BLE001 - the item's own run tries again and records its failure
            out[f"store {_step_name(it)}"] = f"failed: {type(exc).__name__}: {exc}"
    if decl.choice("persons"):
        _capture_links(decl, read, out, log)
    out["seconds"] = round(time.time() - t0, 1)
    log(f"study {decl.study}: store prepared in {out['seconds']:.0f} s")
    return out


def _capture_links(decl: Declaration, read: list[Item], out: dict, log) -> None:
    """The national runs of the links between the capture population's lists (`capture.lists_of`), for the study's
    years every list publishes: no item's plan reads them (SIH's toxoplasmosis admissions to SIM had no run for
    2019-2021, and no year could be captured). A run that cannot be made is said, as an item's link is."""
    from . import capture

    found = capture.lists_of(sorted({gateway.data_code(i.dataset) for i in read}), list(decl.seeds.get("icd10") or []))
    if not found:
        return
    sides = [v["dataset"] for v in found["lists"].values()]
    years = [y for y in decl.years if all(y in gateway.published_years(d) for d in sides)]
    for link in found["links"]:
        for y in years:
            if gateway.run_touches_reserve(link, y) or gateway.link_report(link, y) is not None:
                continue
            t = time.time()
            try:
                pairs = gateway.stored_pairs(link, y, compute=True)
                log(f"link {link} {y}: {pairs.num_rows} pairs ({time.time() - t:.0f} s)")
            except Exception as exc:  # noqa: BLE001 - a year that cannot be linked is not captured, and said
                out[f"link {link} {y}"] = f"failed: {type(exc).__name__}: {exc}"


def _ensure_extract(items: list[Item], out: dict, log) -> None:
    """The records of a dataset's extract items, in one pass over its files (`pegasus_data.build_extract`): each
    item's codes on its classifier (its own, else the event type's primary); resumes where an earlier run stopped."""
    import pegasus_data as pg

    # only the years no extract already holds whole for an item's codes: the slice's SIA-PA item (B58, P37.1, a subset
    # of the national extract's filter) built an extract of its own and began reading 2,746 files (2026-10-12)
    items = [it for it in items if set(it.years) - set(_extract_held(it, list(it.years)))]
    if not items:
        out["extract"] = "held whole by an existing extract"
        return
    filters: dict[str, set[str]] = {}
    for it in items:
        column = (it.source or {}).get("classifier") or next(
            c["column"] for c in gateway.event_type(it.dataset, it.event).get("classifiers") or [] if c["role"] == "primary")
        filters.setdefault(column, set()).update(it.source["codes"])
    years = sorted({y for it in items for y in it.years})
    m = pg.build_extract(items[0].dataset, years, {c: sorted(v) for c, v in filters.items()}, root=config.data_root(),
                         log=log)
    kept = sum(v["kept"] for v in m["files"].values())
    out[f"extract {items[0].dataset}"] = f"{len(m['files'])} files read, {kept:,} records kept, {len(m['failed'])} failed"


def _step_name(it: Item) -> str:
    # one step per item: a dataset read as a code set, a chapter and a ratio is three
    return f"{it.dataset} {it.event} {','.join(it.blocks)}" + (f" {json.dumps(it.source, sort_keys=True)}" if it.source else "")


def _lane_file(study_name: str, pid: int) -> Path:
    return config.home() / "lanes" / study_name / f"{pid}.json"


def _lane_left(study_name: str, seconds: float) -> None:
    """This lane's estimated seconds still to run, for the scheduler (`_run_items`), which ranks lanes by it."""
    path = _lane_file(study_name, os.getpid())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"left": float(seconds)}), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass        # an advisory for the scheduler: the parent reading it (Windows) must not fail the lane's items


def _lanes_left(study_name: str) -> dict[int, float]:
    out = {}
    for f in (config.home() / "lanes" / study_name).glob("*.json"):
        try:
            out[int(f.stem)] = float(json.loads(f.read_text(encoding="utf-8"))["left"])
        except (OSError, ValueError, KeyError):
            continue
    return out


def _run_group(decl_study: str, group: list[Item], others: list, device: str | None, threads: int | None) -> dict:
    """One lane's work: a dataset's items in order (they share its fits and caches), on ``device`` with ``threads``.
    A module function so a spawned process can run it."""
    from . import jobs, update

    if device:
        os.environ["PEGASUS_DEVICE"] = device
    if threads:
        jobs.threads(threads)
    import psutil

    steps = {}
    parent = os.getppid()
    for k, it in enumerate(group):
        if not psutil.pid_exists(parent):
            # the study that started this lane is gone (killed, or relaunched on new code): its remaining items would
            # write the register and the ledger with code that no longer runs (the review of the study, 2026-10-14)
            print(f"study {decl_study}: the parent process {parent} is gone; this lane stops", flush=True)
            break
        _lane_left(decl_study, sum(i.est_seconds or 0.0 for i in group[k:]))
        print(f"study {decl_study}: {it.dataset} {it.event} {it.years[0]}-{it.years[-1]} blocks {it.blocks}"
              + (f" [{device}]" if device else ""), flush=True)
        step = _step_name(it)
        try:
            t_item = time.time()
            steps[step] = config.on_cpu_if_cuda_fails(update.run, _plan(it, [o for o in others if o[0] != it.dataset]),
                                                      log=print)
            steps[step]["seconds"] = round(time.time() - t_item, 1)
        except Exception as exc:  # noqa: BLE001 - one source failing is recorded in the folder, the others still run
            where = traceback.extract_tb(exc.__traceback__)[-3:]
            steps[step] = {"error": f"{type(exc).__name__}: {exc}",
                           "at": [f"{Path(w.filename).name}:{w.lineno} {w.name}" for w in where]}
            print(f"study {decl_study}: {step} failed: {type(exc).__name__}: {exc} at {steps[step]['at']}", flush=True)
        if device:
            steps[step]["device"] = os.environ.get("PEGASUS_DEVICE") or device     # cpu after a CUDA failure
        steps[step]["peak_gb"] = _peak_gb()              # the lane's peak so far: what the next study admits it by
    return steps


def _peak_gb() -> float:
    """This process's peak resident memory in GB (the peak working set on Windows, the maximum RSS elsewhere)."""
    import psutil

    info = psutil.Process().memory_info()
    peak = getattr(info, "peak_wset", None)
    if peak is None:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    return round(peak / 2**30, 2)


#: a lane's expected peak when no earlier study measured its dataset. A code-set lane peaks near 2.5 GB (TOXG, TOXC,
#: DOFET P37.1) and SIH's chapter lanes at 13.5-14.2 GB (2026-10-11); a lane that outgrows its admission is paused
#: (`_run_items`), so the default need not be the worst case: at 12 GB every unmeasured lane ran alone
LANE_DEFAULT_GB = float(os.environ.get("PEGASUS_LANE_DEFAULT_GB", "6"))


def _lane_estimates(decl: Declaration) -> dict[str, float]:
    """Each dataset's largest measured lane peak (``peak_gb``) in the provenance of the studies beside this one."""
    out: dict[str, float] = {}
    for path in decl.path.parent.glob("*/provenance.json"):
        try:
            steps = json.loads(path.read_text(encoding="utf-8")).get("steps") or {}
        except (OSError, ValueError):
            continue
        for step, v in steps.items():
            if isinstance(v, dict) and v.get("peak_gb"):
                ds = step.split(" ", 1)[0]
                out[ds] = max(out.get(ds, 0.0), float(v["peak_gb"]))
    return out


#: lanes a study may run at once (``PEGASUS_STUDY_LANES``), the free memory a new lane needs before it starts
#: (``PEGASUS_LANE_FREE_GB``) and the memory kept for the rest of the machine; measured, not guessed: a lane starts only
#: while the machine's available memory is above both
STUDY_LANES = int(os.environ.get("PEGASUS_STUDY_LANES", "3"))
LANE_FREE_GB = float(os.environ.get("PEGASUS_LANE_FREE_GB", "6"))
#: the available memory below which every lane but the largest is paused (`_run_items`)
LANE_PRESSURE_GB = float(os.environ.get("PEGASUS_LANE_PRESSURE_GB", "2"))


#: seconds without CPU after which a lane counts as idle (`_run_items`' balance)
LANE_QUIET_S = 60.0


def _may_resume(avail_gb: float, lane_gb: float, others_working: bool) -> bool:
    """Whether a paused lane resumes: its memory fits beside the floor, or no other lane computes (then the paused lanes
    are the only work left, and waiting frees nothing)."""
    return avail_gb > LANE_FREE_GB + lane_gb or not others_working


def _run_items(decl: Declaration, read: list[Item], log) -> dict:
    """The study's items, in lanes (BACKLOG 9.5): the items of one dataset form a group run in order in one lane (they
    share its fits, caches and the share denominator: two lanes would fit one block twice and race on its key); groups
    run in parallel processes, the largest first (by `_estimate`'s seconds), while the machine has `LANE_FREE_GB` of
    available memory to start another, up to `STUDY_LANES`; at most one lane computes on the GPU (the largest group
    still waiting when the card is free), the others on the CPU, and the cores are shared between lanes. One lane is
    the sequential run. A failure in a lane is its items' errors; the others go on."""
    import concurrent.futures as cf
    import contextlib
    import multiprocessing as mp

    import psutil

    others = [[o.dataset, o.event] for o in read]
    shutil.rmtree(config.home() / "lanes" / decl.study, ignore_errors=True)     # an earlier run's lanes: reused pids
    groups: dict[str, list[Item]] = {}
    for it in read:
        groups.setdefault(it.dataset, []).append(it)
    order = sorted(groups.values(), key=lambda g: -sum(i.est_seconds or 0 for i in g))
    lanes = max(1, min(STUDY_LANES, len(order)))
    if lanes == 1:
        return _run_group(decl.study, read, others, None, None)
    import torch

    gpu = torch.cuda.is_available() and not os.environ.get("PEGASUS_DEVICE")
    per_lane = max(2, (os.cpu_count() or 4) // lanes)
    known = _lane_estimates(decl)
    need = {g[0].dataset: known.get(g[0].dataset, LANE_DEFAULT_GB) for g in order}
    me = psutil.Process()

    def room() -> float:
        # available memory less what the running lanes may still take: each up to its dataset's measured peak
        held = sum(c.memory_info().rss for c in me.children(recursive=True)) / 2**30
        expect = sum(need[g[0].dataset] for _, g in running.values())
        return psutil.virtual_memory().available / 2**30 - max(expect - held, 0.0)

    steps: dict = {}
    pending, running, lost = list(order), {}, []
    paused: dict[int, psutil.Process] = {}
    cpu_seen: dict[int, tuple[float, float]] = {}      # pid -> (its CPU seconds, when they last grew)

    def balance() -> None:
        # Lanes grow after they are admitted: three survey lanes held 42 GB committed on a 31.6 GB machine, and all of
        # them paged (SIM-DO chapter I's robust refit alone 23 GB, 2026-10-11). Under pressure every lane but the
        # largest is suspended, so the system pages the idle ones out and the largest runs at its own speed; they are
        # resumed one at a time, the smallest first, as memory frees.
        avail = psutil.virtual_memory().available / 2**30
        lanes_now, working = {}, set()
        for c in me.children():
            try:
                lanes_now[c.pid] = (c, c.memory_info().private / 2**30)
                cpu = sum(c.cpu_times()[:2])
            except (psutil.Error, AttributeError):
                continue
            seen, grew = cpu_seen.get(c.pid, (0.0, 0.0))
            if cpu - seen > 0.5:
                grew = time.time()
            cpu_seen[c.pid] = (cpu, grew)
            # a lane that computed within the last minute: a lane paging under pressure computes in bursts, and resumed
            # beside it on one quiet tick the others thrashed it (deep14); an idle pool worker computes for minutes none
            if time.time() - grew < LANE_QUIET_S:
                working.add(c.pid)
        active = {pid: v for pid, v in lanes_now.items() if pid not in paused}
        # only a lane computing is ever suspended: an idle pool worker waits for its next lane holding the queue's
        # lock, and suspended there it blocked every other worker's next lane (deep15)
        computing = {pid: v for pid, v in active.items() if pid in working}
        # the critical path first: the lane with the most work left (its own estimate, `_lane_left`) is kept and resumed
        # first; ranked by memory, the national study paused its 24-item SIM-DO lane for its SIH lane and then resumed
        # the small SIA lane, and the longest lane waited past the hour (2026-10-13). Memory breaks ties.
        left = _lanes_left(decl.study)

        def rank(pid):
            return (left.get(pid, 0.0), lanes_now.get(pid, (None, 0.0))[1])
        if avail < LANE_PRESSURE_GB and len(computing) > 1:
            keep = max(computing, key=rank)
            for pid, (proc, gb) in computing.items():
                if pid != keep and gb > 1.0:
                    try:
                        proc.suspend()
                        paused[pid] = proc
                        log(f"study {decl.study}: {avail:.1f} GB available: lane {pid} ({gb:.1f} GB) paused beside "
                            f"lane {keep} ({active[keep][1]:.1f} GB)")
                    except psutil.Error:
                        continue
        elif paused:
            # the smallest paused lane, once its own memory fits beside the floor: resumed at the floor alone, two 11 GB
            # lanes took turns pausing each other (the survey, 2026-10-11)
            # or when no other lane computes: the pool's idle workers had counted as active, and deep8 waited with
            # two lanes paused for 10 GB that nothing running would free (2026-10-12)
            fits = [p for p in paused if _may_resume(avail, lanes_now.get(p, (None, 0.0))[1], bool(working - set(paused)))]
            pid = max(fits, key=rank) if fits else max(paused, key=rank)
            if fits:
                try:
                    paused.pop(pid).resume()
                    log(f"study {decl.study}: {avail:.1f} GB available: lane {pid} resumed")
                except psutil.Error:
                    pass

    def new_pool():
        # a fresh process per lane: a finished lane's worker kept its 9.7 GB while it waited for the next (deep15)
        return cf.ProcessPoolExecutor(max_workers=lanes, mp_context=mp.get_context("spawn"), max_tasks_per_child=1)

    # a worker that dies (a hard crash: CUDA starting while a killed run's memory was still held, deep13) breaks the
    # whole pool, and every lane after it had run in this process, one after another; the pool is made anew and each
    # lane it held resubmitted once, and only a lane that fails again, or raises, runs here
    pool, broken, retried = new_pool(), False, set()
    try:
        while pending or running:
            balance()
            free_gb = room()
            while not broken and not paused and pending and len(running) < lanes and (
                    not running or free_gb >= max(LANE_FREE_GB, need[pending[0][0].dataset])):
                gpu_busy = any(dev == "cuda" for dev, _ in running.values())
                device = "cuda" if gpu and not gpu_busy else "cpu"
                group = pending.pop(0)
                log(f"study {decl.study}: lane for {group[0].dataset} ({len(group)} items) on {device}, "
                    f"{free_gb:.1f} GB of room, {need[group[0].dataset]:.1f} GB expected")
                try:
                    running[pool.submit(_run_group, decl.study, group, others, device, per_lane)] = (device, group)
                except cf.process.BrokenProcessPool:
                    pending.insert(0, group)
                    broken = True
                free_gb = room()
            done, _ = cf.wait(list(running), timeout=10, return_when=cf.FIRST_COMPLETED) if running else (set(), set())
            for f in done:
                _device, group = running.pop(f)
                try:
                    steps.update(f.result())
                except cf.process.BrokenProcessPool:
                    broken = True
                    if group[0].dataset in retried:
                        log(f"study {decl.study}: the lane of {group[0].dataset} broke its pool again: run here")
                        lost.append(group)
                    else:
                        retried.add(group[0].dataset)
                        pending.insert(0, group)
                        log(f"study {decl.study}: the lane of {group[0].dataset} broke its pool: resubmitted to a new one")
                except Exception as exc:  # noqa: BLE001 - a lane that raised: its group runs again below, in this process
                    log(f"study {decl.study}: the lane of {group[0].dataset} failed ({type(exc).__name__}): run again here")
                    lost.append(group)
            if broken and not running:
                pool.shutdown(wait=False, cancel_futures=True)
                pool, broken = new_pool(), False
                paused.clear()
    finally:
        for proc in paused.values():         # never leave a lane suspended: the pool waits on it at shutdown
            with contextlib.suppress(psutil.Error):
                proc.resume()
        pool.shutdown(wait=True)
    for group in lost:
        steps.update(_run_group(decl.study, group, others, None, None))
    return steps


def _study_key(key: dict) -> dict:
    """A study-level stored table's key with what every one of them depends on beside its inputs: the study's area and
    the replicate scale. Five keys had neither, so a study of Rio Grande do Sul and one of Brazil with the same topic
    read each other's relations, cohorts, determinants and expectation tables (the review of the study, 2026-10-14)."""
    return {**key, "area": sorted(config.study_area() or []), "nulls": config.replicates(1000, floor=1) / 1000}


def _plan(it: Item, others: list | None = None):
    """The `update` plan of one item: its system with the readers its depth adds, at the study's ``q`` (`Item.q`)."""
    from . import update

    return update.Plan(years=it.years, systems=[update.System(it.dataset, it.event, it.blocks, nodes=it.nodes,
                                                              mentions=it.mentions, source=it.source, extract=it.extract,
                                                              fields=it.field_list, **it.readers)],
                       relations=False, triage=it.triage, report=None, questions=it.questions, q=it.q,
                       # the held-out later years read prospectively as well: their events against fits on the years
                       # before (BPA for an outbreak), so an event of the later years is discovered, not only replicated;
                       # read retrospectively, B1 learns a statewide one as normal (Porto Alegre's 2024 floods were found
                       # by no discovery, the review of the RS slices, 2026-10-13)
                       extra={"corroborators": others or [],
                              **({"confirm_last": it.confirm_last, "prospective": it.confirm_last} if it.confirm_last else {})})


def _session(it: Item, source: dict | None = None):
    from . import tools

    return tools.Session(it.dataset, it.event, it.years, "contiguity", source=dict(it.source or {} if source is None else source))


def _fields_of(it: Item) -> list[tuple[str, dict | None]]:
    """Every field an item's run fitted, as (name, reader): its primary counts, then each reader its depth added
    (`update.system_readers`, the list `update.run` fits and asks)."""
    from . import update

    plan = _plan(it)
    try:
        extra = [(name, src) for name, src, _ in update.system_readers(plan.systems[0], plan, list(it.blocks))]
    except Exception as exc:  # noqa: BLE001 - readers that cannot be listed leave the primary field; said by the caller
        return [("", None), ("!", {"error": f"{type(exc).__name__}: {exc}"})]
    return [("", None)] + extra


def _study_nodes(it: Item, s) -> list[str]:
    """The topic's field nodes in an item: its seed nodes, or the event type's own field."""
    return list(it.nodes) if it.nodes else ["*"]


class _Lap(dict):
    """Seconds per product, each the time since the previous lap: the products phase took 19 of the smoke study's 32
    minutes and nothing said which product (2026-10-12)."""

    def __init__(self):
        super().__init__()
        self._t = time.time()
        self.failed: dict[str, str] = {}
        self.gaps: dict[str, str] = {}          # what could not be read, by design or by data (not a failure)

    def __call__(self, name: str) -> None:
        now = time.time()
        self[name] = round(self.get(name, 0.0) + now - self._t, 1)
        self._t = now

    def guard(self, name: str, fn, default, log):
        """One product run in isolation: an exception is logged and recorded (`provenance.json`'s products_failed, which
        `body` counts as a failed step), the product's empty ``default`` written, and the others still run. One late
        error had dropped the report, the README and the provenance after hours of lanes (the review, 2026-10-14)."""
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - recorded and said, never silent
            self.failed[name] = f"failed: {type(exc).__name__}: {exc}"
            log(f"study: product {name} failed: {type(exc).__name__}: {exc}")
            return default


def _write_products(decl: Declaration, scope: Scope, out: Path, log, lap: _Lap | None = None) -> dict[str, str]:
    """Findings, descriptive tables, every field's expectations, figures, the report; each product's seconds into
    ``lap``. Returns the folder's tables (each a table of study.duckdb)."""
    import duckdb

    lap = _Lap() if lap is None else lap

    names = gateway.municipality_names()
    rows, desc, figs, groups, places, quality, trends, seasons, measures = [], [], [], [], [], [], [], [], []
    expected: list[pa.Table] = []       # every field's observed and expected per municipality and period
    standards: dict[str, tuple] = {}    # each direct standardisation's standard: its bands and weights
    figure_rows: list[dict] = []        # what each figure file shows (the audit read hashed names, 2026-10-14)
    code_rows: list[dict] = []          # the topic's events by code
    series = {}          # each primary field's observed and expected by place and period: the related fields' reading
    # the register's current answers by field, once: each field had scanned all of them (65,725 SIM-DO answers in
    # the national register, times every field of the study; the review of the study, 2026-10-14)
    by_field: dict[str, list] = {}
    for x in leads.Register().current():
        if x.fields and x.kind == "answer" and x.status != "retired":
            by_field.setdefault(x.fields[0], []).append(x)
    # a year whose monthly files the lake holds fewer than twelve of is a part of a year (SIA's ATD began in August
    # 2014): its estimates say so, and no trend or season reads it (it had read as a halving, the SIA audit, 2026-10-14)
    files = lap.guard("sources", lambda: _publications(scope, log), None, log)
    partial = _partial_years(files)
    for it in (i for i in scope.items if i.status == "in"):
        for name, src in _fields_of(it):
            if name == "!":
                log(f"study: {it.dataset}: its readers could not be listed: {src['error']}")
                continue
            try:
                s = _session(it, src)
            except LookupError as exc:
                log(f"study: {it.dataset} {name}: {exc}")
                continue
            for node in _study_nodes(it, s):
                try:
                    f = s.expectations.field(node)
                    sv = config.on_cpu_if_cuda_fails(s.surprise, node, "B1")
                except Exception as exc:  # noqa: BLE001 - a field that could not be read is a note in the report
                    log(f"study: {it.dataset} {name} {node}: {type(exc).__name__}: {exc}")
                    continue
                # a share's name is COLUMN=value: named as the source labels it ("Critério de Confirmação: Laboratorial (1)")
                shown = _group_text(it, [name]) if name and "=" in name and " " not in name else name
                label = (gateway.split_event(f.label)[0] if f.label else node) + _codes_text(it) + (f" — {shown}" if shown else "") + _link_text(it)
                # the field's observed and expected per municipality and period, into the folder's one table keyed
                # by field: a file per field named by dataset and reader had given the SIM-DO counts, their
                # CAUSABAS_O field and their linked share one name, the last written kept (the paper audit, 2026-10-14)
                expected.append(_expectation_table(sv, names, f.id, label, s.expectations.model(f.block)))
                support = (src or {}).get("support") if name and str(name).startswith("support:") else None
                # Brazil's and the macro-regions' cells, once a field: its reference rates and its municipalities'
                # ratios to Brazil read them
                refs = lap.guard(f"reference {f.id}", lambda it=it, s=s, f=f: _reference_cells(
                    it, s, f, s.expectations.model(f.block).data), [], log) if not name else []
                rows_ = _descriptive(it, s, f, label, refs=refs, support=bool(support), standards=standards) + \
                    (_race_rates(it, s, f, label) if not name else []) + \
                    (lap.guard(f"proportional {f.id}", lambda it=it, label=label, f=f: _proportional(it, f, label), [],
                               log) if not name else [])
                _mark_years(rows_, it, partial)          # provisional and partial years: no trend reads them
                # the share placed, for the counts and for each other place they are read at: a place of infection
                # or of care left blank for 35-44 % of gestational cases makes its rates lower bounds (the review);
                # each year's share placed is a completeness row ("events placed"), once
                if (not name or support) and (not it.source or (it.source or {}).get("codes")
                                              or (it.source or {}).get("source") == "code_list"):
                    _allocation(it, list(it.years), support=support, lost=quality,
                                base={"dataset": it.dataset, "field": f.id, "label": label})
                # guarded as every product: an unguarded trend error had ended a slice's whole study (2026-10-14)
                trends.extend(lap.guard(f"trends {f.id}", lambda rows_=rows_: _apc(rows_), [], log))
                for r in rows_:                     # the cells the trends read, never a column of the table
                    r.pop("_cells", None)
                    r.pop("_std", None)
                desc.extend(rows_)
                # the field's own answers, on the item's years (each reader is its own field: counts, mentions, an
                # interval, a composition's share)
                rows.extend({**_finding(x, it, label, names), "_event": it.event,
                             "_places": [int(q) for q in x.locus.get("places") or []],
                             "_groups": [str(g) for g in x.locus.get("groups") or []],
                             "_train_last": x.train_last,
                             "_institutions": sorted({str(i) for i in x.locus.get("institutions") or []}
                                                     | ({str(f_)} if (f_ := _one_institution(x)) else set()))}
                            for x in by_field.get(f.id, ())
                            if list(x.provenance.get("years") or []) == list(it.years)
                            and int(x.provenance.get("nulls") or 1000) == config.replicates(1000))
                # a count field's series and map: a linked share's or a share's events are trials, not a rate per
                # person-year (its "per 100,000" map and its series had been drawn empty, and counted as figures)
                if not name and s.expectations.model(f.block).data.n is None:
                    mine = lap.guard(f"places {f.id}", lambda it=it, s=s, f=f, label=label, sv=sv, refs=refs: _places(
                        it, s, f, label, sv, names, refs), [], log)
                    places += mine
                    held = lap.guard(f"persons {f.id}", lambda it=it, s=s, f=f, label=label, mine=mine: _distinct_persons(
                        it, s, f, label, mine), [], log)
                    _mark_years(held, it, partial)
                    places += [r for r in held if r["section"] == "municipalities"]
                    desc.extend(r for r in held if r["section"] == "rates")
                    trends.extend(lap.guard(f"person trends {f.id}", lambda held=held: _apc(
                        [r for r in held if r["section"] == "rates"]), [], log))
                    seasons += lap.guard(f"seasons {f.id}", lambda it=it, s=s, f=f, label=label: _seasons(
                        it, s, f, label, skip={y for (ds, y) in partial if ds == it.dataset}), [], log)
                    measures += lap.guard(f"measures {f.id}", lambda it=it, f=f, label=label: _measures(it, f, label, log),
                                          [], log)
                    if decl.choice("persons"):
                        measures += lap.guard(f"follow-up {f.id}", lambda it=it, f=f, label=label: _followup(
                            it, f, label, log), [], log)
                    code_rows += lap.guard(f"codes {f.id}", lambda it=it, f=f, label=label: _codes(it, f, label), [], log)
                    try:                   # B0 beside B1: a finding's O/E is against its own tier's expectation
                        mu0 = s.surprise(node, "B0").mu
                    except Exception:  # noqa: BLE001 - a field with no B0: its B0 findings' O/E are said missing
                        mu0 = None
                    # a prospective tier's surprise on demand (the session keeps it): a BP finding's O/E reads it
                    series[f.id] = (label, it.dataset, np.asarray(sv.places), np.asarray(sv.years), sv.y, sv.mu, mu0,
                                    lambda tier, last, s=s, node=node: s.surprise(node, tier, last))
                    figs.append(_series_figure(out, sv, f, label, it, session=s))
                    if figs[-1]:
                        figure_rows.append({"file": f"figures/{Path(figs[-1]).name}", "kind": "series", "field": f.id,
                                            "label": label, "dataset": it.dataset,
                                            "shows": "the field's events in the whole area each year with their exact "
                                                     "95 % interval, and what the earlier years expected of the later "
                                                     "(tier BP, 90 % band); event counts, not rates"})
                    try:
                        d = s.expectations.model(f.block).data
                        expo = dict(zip(np.asarray(d.places).tolist(), d.N.sum(axis=(1, 2)).tolist(), strict=True))
                        smooth = {int(r["place"]): r["estimate"] for r in mine if r["measure"] == "smoothed_smr"
                                  and r.get("period_kind") == "period"}
                        figs.append(_map_figure(out, sv, f, label, it, [r for r in rows if r["field"] == f.id], expo,
                                                str(d.population), smooth))
                        if figs[-1]:
                            figure_rows.append({"file": f"figures/{Path(figs[-1]).name}", "kind": "map", "field": f.id,
                                                "label": label, "dataset": it.dataset,
                                                "shows": "left: the crude rate over the period by state (by health "
                                                         "region in a one-state study); middle: each municipality's "
                                                         "standardised ratio against the area's own age-sex rates, "
                                                         "smoothed by empirical Bayes (estimates.parquet, "
                                                         "municipalities, smoothed_smr); right, exploratory: each "
                                                         "municipality's standardised departure from tier B1 (observed "
                                                         "minus expected over its sd), the findings' places outlined"})
                    except Exception as exc:  # noqa: BLE001 - a map that cannot be drawn is a note; the tables stand
                        log(f"study: {it.dataset} {node} map: {type(exc).__name__}: {exc}")
                    lap("fields: tables, figures, maps")
                    groups.extend(_groups(it, s, f, label, log))
                    lap("fields: groups")
    related = lap.guard("related", lambda: _related(rows, series), [], log)
    pq.write_table(_rows_table(related) if related else pa.table({"finding": pa.array([], pa.string())}),
                   out / "related.parquet")
    lap("related")
    assoc = lap.guard("associated", lambda: _associated(decl, scope, log), [], log)
    lap("associated")
    chosen = decl.choice("relations")
    rel = lap.guard("relations", lambda: _relations(scope, decl, log), [], log) if "fields" in chosen else []
    lap("relations")
    rel += lap.guard("determinants", lambda: _determinants(scope, decl, log), [], log) if "contexts" in chosen else []
    lap("determinants")
    rel += lap.guard("screen", lambda: _screen(scope, decl, log), [], log) if "screen" in chosen else []
    lap("screen")
    pq.write_table(_rows_table(rel) if rel else pa.table({"field": pa.array([], pa.string())}),
                   out / "relations.parquet")
    lap.guard("institutions", lambda: (_institution_facts(rows, log), _institution_explains(rows),
                                       _recording_groups(rows)), None, log)
    lap("institutions")
    persons = lap.guard("persons", lambda: _persons(decl, scope, log), [], log) if decl.choice("persons") else []
    # a cohort-year that could not be scanned (its link runs not stored) is a gap of the study, in provenance beside the
    # failures: a note inside persons.parquet alone read as "no failure" (the second audit, 2026-10-14)
    for r in persons:
        if str(r.get("note") or "").startswith(("not scanned", "no year")):
            lap.gaps[f"persons {r.get('cohort')} {r.get('year') or ''}".strip()] = str(r["note"])
    lap("persons")
    pq.write_table(_rows_table(persons) if persons else pa.table({"outcome": pa.array([], pa.string())}),
                   out / "persons.parquet")
    captured = lap.guard("capture", lambda: _capture(decl, scope, log), [], log) if decl.choice("persons") else []
    lap("capture")
    pq.write_table(_rows_table(captured) if captured else pa.table({"population": pa.array([], pa.string())}),
                   out / "capture.parquet")
    profile = lap.guard("context profiles", lambda: _context_profiles(decl, scope, rows, log), [], log)
    covariates = lap.guard("contexts", lambda: _context_table(decl, scope, places, names, log), [], log)
    ecological = lap.guard("ecological", lambda: _ecological(places, covariates, log), [], log) if covariates else []
    places += lap.guard("spatial autocorrelation", lambda: _spatial_autocorrelation(places, decl.q, log), [], log)
    lap("context profiles")
    pq.write_table(_rows_table(profile) if profile else pa.table({"finding": pa.array([], pa.string())}),
                   out / "context_profile.parquet")
    lap.guard("stories", lambda: _stories([r for r in rows if r.get("class") == "signal"
                                           and "quality:" not in str(r.get("label"))]), None, log)  # `story` saved
    lap("stories")
    for r in rows:
        r.pop("_places", None)
        r.pop("_groups", None)
        r.pop("_train_last", None)
        r.pop("_institutions", None)
        r.pop("_event", None)
    findings = _rows_table(rows) if rows else pa.table({"id": pa.array([], pa.string())})
    pq.write_table(findings, out / "findings.parquet")
    linkage = lap.guard("linkage", lambda: _linkage(scope), [], log)
    pq.write_table(_rows_table(linkage) if linkage else pa.table({"link": pa.array([], pa.string())}),
                   out / "linkage.parquet")
    quality += lap.guard("quality", lambda: _quality(scope, groups, log), [], log)
    if standards:
        pq.write_table(pa.Table.from_pylist([{"standard": name, "sex": sex, "age_band": band, "weight": float(w)}
                                             for name, (bands, wts) in standards.items()
                                             for i, (sex, band) in enumerate((sx, b) for sx in ("male", "female")
                                                                             for b in bands)
                                             for w in [wts[i]]]), out / "standard.parquet")
    for fid in dict.fromkeys(r["field"] for r in desc if r["measure"] == "standardised_rate"):
        drawn = lap.guard(f"rate figure {fid}", lambda fid=fid: _rate_figure(out, fid, desc, trends), None, log)
        if drawn:
            figure_rows.append(drawn)
    if figure_rows:
        pq.write_table(_rows_table(figure_rows), out / "figures.parquet")
    if files is not None and files.num_rows:
        pq.write_table(files, out / "sources.parquet")
    lap.guard("geometry", lambda: _geometry(out, places), None, log)
    # every descriptive number as one schema (MEASURES): ten tables, each with its own columns, had grown one audit at a
    # time (docs/plans/study-estimates.md)
    est = [*desc, *trends, *places, *seasons, *code_rows, *groups, *quality, *measures, *assoc, *covariates,
           *ecological]
    pq.write_table(_estimates_table(est), out / "estimates.parquet")
    lap("places and quality")
    hyp = lap.guard("hypotheses", lambda: _hypotheses(decl, scope), [], log)
    pq.write_table(_rows_table(hyp) if hyp else pa.table({"hypothesis": pa.array([], pa.string())}),
                   out / "hypotheses.parquet")
    lap("hypotheses")
    if expected:
        pq.write_table(pa.concat_tables(expected, promote_options="permissive"), out / "expectations.parquet")
    db = out / "study.duckdb"
    tmp_db = out / f"study.{os.getpid()}.duckdb.tmp"
    tmp_db.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp_db))       # built aside, then moved in: a notebook holding the old one open had failed it
    # every table of the folder, the expectations included, as a table of the database's own: views read paths, which
    # DuckDB resolves from the reader's directory (relative) or this machine's (absolute), so a folder sent to a
    # researcher opened nothing (2026-10-14); a list kept by hand had left associated and hypotheses out
    out = out.resolve()
    tables = sorted(out.glob("*.parquet"))
    for path in tables:
        con.execute(f"CREATE TABLE {path.stem} AS SELECT * FROM read_parquet('{path.as_posix()}')")
    if (out / "estimates.parquet").exists():
        # the wide shapes a paper's tables read, as views over estimates: one row per field, place, stratum and period
        con.execute(f"CREATE VIEW rates AS {RATES_VIEW}")
        con.execute(f"CREATE VIEW municipalities AS {MUNICIPALITIES_VIEW}")
    con.close()
    try:
        os.replace(tmp_db, db)
    except PermissionError as exc:
        lap.failed["tables"] = f"failed: study.duckdb is held open elsewhere ({exc}); the new one is {tmp_db.name}"
        log(f"study: {lap.failed['tables']}")
    lap("tables")

    lap.guard("report", lambda: _report(decl, scope, out, rows, desc, [f for f in figs if f], hyp, rel, persons,
                                        captured, quality, trends, linkage, assoc, est), None, log)
    lap("report")
    lap.guard("methods", lambda: (out / "METHODS.md").write_text(_methods_markdown(decl, scope, desc, linkage),
                                                                encoding="utf-8"), None, log)
    lap.guard("codebook", lambda: _codebook(decl, scope, out), None, log)
    lap("codebook")
    return {path.stem: path.name for path in tables}


def _when(text: Any) -> list[int]:
    """The years a hypothesis's ``when`` covers: ``2018``, ``2018-03``, ``2018-01..2018-06``, ``2016..2018``."""
    parts = str(text).split("..")
    first, last = int(parts[0][:4]), int(parts[-1][:4])
    return list(range(first, last + 1))


def _when_months(text: Any) -> list[int]:
    """The months (YYYYMM) a ``when`` written in months covers (``2018-01..2018-06``, ``2024-05``); [] for years."""
    parts = [x.strip() for x in str(text).split("..")]
    if not all(len(x) >= 7 and x[4] == "-" for x in parts):
        return []
    first, last = int(parts[0][:4]) * 12 + int(parts[0][5:7]) - 1, int(parts[-1][:4]) * 12 + int(parts[-1][5:7]) - 1
    return [(m // 12) * 100 + m % 12 + 1 for m in range(first, last + 1)]


def _hypothesis_readers(scope: Scope):
    """(item, reader, support) for every read item at its residence and, for a field read at the residence by its own
    counts or a code set, at each other place it declares (`fields.support_sources`, the item's codes kept). A ratio or
    a linked share is read at the residence only: its denominator is the residence's."""
    for it in (i for i in scope.items if i.status == "in"):
        yield it, it.source, "residence"
        if it.source and ("population" in it.source or it.source.get("source") == "linked"):
            continue
        try:
            supports = fields.support_sources(it.dataset, it.event, list(it.years))
            span = {r["column"]: (r.get("first_year"), r.get("last_year")) for r in gateway.roles(it.dataset)}
        except Exception:  # noqa: BLE001 - a source whose supports cannot be listed is tested at its residence
            continue
        for name, src in supports:
            lo, hi = span.get(src["support"], (None, None))
            if (lo and int(lo) > it.years[-1]) or (hi and int(hi) < it.years[0]):
                continue                    # a column of another layout generation (DOFET's MUNIOCOR, before 1996)
            yield it, {**src, **(it.source or {}), "support": src["support"]}, name.removeprefix("support:")


#: the years before a hypothesis's window its prospective expectation is trained on, at least
HYPOTHESIS_TRAIN = 3


def _relation_hypothesis(h: dict, decl: Declaration, scope: Scope) -> list[dict]:
    """A declared relation (``component: relation``): the ``leader`` (a dataset, its event's every notification, or
    ``dataset:event``) precedes the topic's field by the ``lags`` window (first, last, in months), in the
    ``macro``-regions (1-5: read over their states, the study's area or not: an ecological relation needs many places)
    over the ``when`` years, the topic's expectation trained up to ``train_last`` (the year before ``when`` unless
    declared). One test (`tools.lagged_effect`: a distributed lag against tier BPA, p from the leader's circular
    shifts), and the same for the ``control`` (ICD-10 codes on the field's own reader, an outcome of the same recording
    the leader should not move); the answer is specific when the control's is not. Zika -> microcephaly had been one row
    among hundreds; on B1 innovations its evidence moved with the area the fields were fitted on (B1 learns a region's
    wave as its course), and its coarse lag profile was Down syndrome's too (evaluation 2026-10-14)."""
    from . import tools

    grain = "month"
    lo, hi = (int(x) for x in (h.get("lags") or [1, 3]))
    years = _when(h.get("when")) if h.get("when") else list(decl.years)
    leader_ds, _, leader_ev = str(h["leader"]).partition(":")
    leader_ev = leader_ev or gateway.event_types(leader_ds)[0]["name"]
    macro = [int(m) for m in h.get("macro") or []] or None
    name = h.get("note") or f"{leader_ds} leads the topic by {lo}-{hi} {grain}s"
    out = []
    for it in (i for i in scope.items if i.status == "in" and not i.count_only and not (i.source or {}).get("population")):
        node = _study_nodes(it, None)[0]
        base = {"hypothesis": name, "component": "relation", "source": it.dataset, "support": "",
                "field_reader": json.dumps(it.source or {"nodes": it.nodes}), "places": f"macro-regions {macro or 'all'}",
                "years": f"{years[0]}-{years[-1]}"}
        if not set(years) <= set(it.years):
            out.append({**base, "answer": f"not testable: {it.dataset} holds {it.years[0]}-{it.years[-1]}"})
            continue
        control = [str(c).upper().replace(".", "") for c in (h.get("control") or {}).get("icd10") or []]
        tests = [("topic", node, it.source)]
        if control:
            ctl = (dict(it.source or {}), control[0]) if (it.source or {}).get("source") == "code_list" else                 ({**(it.source or {}), "codes": control}, "*")
            tests.append(("control", ctl[1], ctl[0]))
        verdict = {}
        train_last = int(h.get("train_last") or years[0] - 1)
        # the declared macro-regions' states as the area of the test, the study's own area restored after
        saved = os.environ.get("PEGASUS_AREA")
        if macro:
            os.environ["PEGASUS_AREA"] = ",".join(str(u) for u in range(11, 54) if u // 10 in macro)
        try:
            for role, node_, src in tests:
                try:
                    res = tools.lagged_effect((leader_ds, leader_ev, "*"), (it.dataset, it.event, node_),
                                              sorted({*it.years, *years}), train_last, (lo, hi), sources=[None, src])
                except Exception as exc:  # noqa: BLE001 - a relation that cannot be read is said, never "not supported"
                    out.append({**base, "support": role, "answer": f"not read: {type(exc).__name__}: {exc}"})
                    continue
                verdict[role] = bool(res["p"] <= decl.q and res["effect"] > 0)
                out.append({**base, "support": role, "tier": f"BPA trained to {train_last}; distributed lag over "
                            f"{res['units']} immediate regions, {res['months'][0]}-{res['months'][1]}; p from "
                            f"{res['shifts']} circular shifts of the leader", "effect": res["rr"],
                            "effect_unit": f"rate ratio per unit of log incidence, lags {lo}-{hi} {grain}s",
                            "low": res["low"], "high": res["high"], "p": res["p"],
                            "answer": "supported" if verdict[role] else "not supported"})
        finally:
            if saved is None:
                os.environ.pop("PEGASUS_AREA", None)
            else:
                os.environ["PEGASUS_AREA"] = saved
        if "topic" in verdict and "control" in verdict:
            out.append({**base, "support": "specificity", "answer":
                        "specific: the control outcome does not follow the leader" if verdict["topic"] and not verdict["control"]
                        else "not specific: the control outcome follows the leader too (a recording change timed with it)"
                        if verdict["topic"] else "not supported for the topic"})
    return out


def _hypotheses(decl: Declaration, scope: Scope) -> list[dict]:
    """The declared hypotheses (ARCHITECTURE §7.7, version 1): each tested once, at its locus, in every source of the
    scope whose years and places hold it; its own test, not a member of a discovery family. A level or transient
    hypothesis is tested against what was expected before it happened: the prospective alarm tier (BPA, `surprise`),
    trained on the source's years before the window and extrapolated, whose flat history takes no past epidemic as
    normal. B1, fitted on the window's own years, learns the event as normal: Porto Alegre's leptospirosis in the
    May 2024 floods, a statewide rise absorbed by the year's effect, read "not supported" (2026-10-12). With fewer
    than `HYPOTHESIS_TRAIN` years before the window the test falls back to B1 and says so.
    level and transient: observed against expected over the locus, the upper tail of the sum under its negative
    binomial (moments of the cells' predictive), the rate ratio with an exact Poisson interval; step: the ratio of
    observed to expected after the declared year against before it.

    Each source is tested at the residence and at every other place it declares (`fields.support_sources`: the place of
    care, of infection, of notification): an outbreak's tests are billed where they were done, and SIA's consolidated
    production names no patient's residence (Santa Maria 2018: 2-8 serology tests a month by residence, 1,100 rising
    to 4,613 by the establishment's municipality)."""
    from scipy import stats

    out = []
    for h in decl.hypotheses:
        if str(h.get("component")) == "relation":
            out += _relation_hypothesis(h, decl, scope)
            continue
        comp, places = str(h.get("component", "transient")), [int(p) for p in (h.get("where") or [])]
        years = _when(h.get("when"))
        for it, reader, support in _hypothesis_readers(scope):
            base = {"hypothesis": h.get("note") or json.dumps(h, ensure_ascii=False), "component": comp,
                    "source": it.dataset, "support": support, "field_reader": json.dumps(reader or {"nodes": it.nodes}),
                    "places": ", ".join(map(str, places)), "years": f"{years[0]}-{years[-1]}"}
            if comp == "step":
                needed = [y for y in it.years if y < years[0]]
                if not needed or not set(years) & set(it.years):
                    out.append({**base, "answer": f"not testable: {it.dataset} holds {it.years[0]}-{it.years[-1]}"})
                    continue
            elif not set(years) <= set(it.years):
                out.append({**base, "answer": f"not testable: {it.dataset} holds {it.years[0]}-{it.years[-1]}, "
                                              f"the hypothesis {years[0]}-{years[-1]}"})
                continue
            before = [y for y in it.years if y < years[0]]
            tier = "BPA" if comp != "step" and len(before) >= HYPOTHESIS_TRAIN else "B1"
            # the grain the test reads: an annual study reads a window of months as its whole years
            grain = (f"tier {tier} (trained on {before[0]}-{before[-1]})" if tier == "BPA" else
                     f"tier B1 ({len(before)} years before the window, fewer than {HYPOTHESIS_TRAIN})"
                     if comp != "step" else "tier B1")
            if str(h.get("when", "")).count("-") >= 2 and "year" in (decl.grain or ["year"]):
                grain += f"; at the annual grain, {h.get('when')} read as {years[0]}-{years[-1]} whole"
            base["tier"] = grain
            months = _when_months(h.get("when")) if comp != "step" else []
            sv = None
            if months and tier == "BPA":
                # a window of months read in months: the monthly series of the hypothesis's states, against its
                # prospective expectation (Porto Alegre's May-July 2024 floods had been read as the whole of 2024);
                # the states' own monthly fit (`config.study_area`), the national one would cost every place's months
                saved = os.environ.get("PEGASUS_AREA")
                states = sorted({(p // 100000 if p > 999999 else p // 10000) for p in places}) if places else []
                try:
                    if states and decl.where in (None, "BR"):
                        os.environ["PEGASUS_AREA"] = ",".join(str(x) for x in states)
                    sm = _session(it, {**(reader or {}), "grain": "month"})
                    sv = sm.expectations.prospective(_study_nodes(it, None)[0], before[-1], purpose="alarm")
                    base["tier"] = (f"tier BPA, monthly (trained on {before[0]}-{before[-1]}), "
                                    f"{months[0] // 100}-{months[0] % 100:02d}..{months[-1] // 100}-{months[-1] % 100:02d}")
                except Exception as exc:  # noqa: BLE001 - the annual reading stands, and says why
                    base["tier"] += f"; the monthly series could not be read ({type(exc).__name__}): annual"
                    sv = None
                finally:
                    if saved is None:
                        os.environ.pop("PEGASUS_AREA", None)
                    else:
                        os.environ["PEGASUS_AREA"] = saved
            try:
                if sv is None:
                    ss = _session(it, reader)
                    node = _study_nodes(it, None)[0]
                    sv = (ss.expectations.prospective(node, before[-1], purpose="alarm") if tier == "BPA"
                          else ss.surprise(node, "B1"))
            except Exception as exc:  # noqa: BLE001 - said in the answer
                out.append({**base, "answer": f"not read: {type(exc).__name__}: {exc}"})
                continue
            # IBGE codes: the fit's places are six-digit; a declared seven-digit code drops its check digit
            pl6 = [p // 10 if p > 999999 else p for p in places]
            rows_u = np.isin(np.asarray(sv.places), pl6) if places else np.ones(len(sv.places), bool)
            if not rows_u.any():
                out.append({**base, "answer": "not testable: none of the places is in the fit"})
                continue
            yrs = np.asarray(sv.years)
            from . import surprise as surprise_

            cv = surprise_.field_cell_variance(sv)

            def window(sel_t, sv=sv, rows_u=rows_u, cv=cv):
                # a window's variance under the field's predictive: each cell's, and twice the covariances of a place's
                # cells over the periods of the window (the field's measured serial correlation, `sv.noise`); summed as
                # independent cells, a window of several years was too narrow, its p too small (the review of the study)
                Y = float(sv.y[np.ix_(rows_u, sel_t)].sum())
                M = float(sv.mu[np.ix_(rows_u, sel_t)].sum())
                V = float(cv[np.ix_(rows_u, sel_t)].sum())
                for k in range(1, int(sel_t.sum())):
                    if abs(sv.noise.corr(k)) < 1e-4:
                        break
                    both = sel_t[:-k] & sel_t[k:]
                    if both.any():
                        V += 2.0 * float(surprise_.field_lag_covariance(sv, k)[np.ix_(rows_u, both)].sum())
                return Y, M, max(V, M)

            monthly = bool(yrs.size) and int(yrs.max()) > 9999
            inside = np.isin(yrs, months) if monthly else np.isin(yrs, years)
            Y, M, V = window(inside)
            if comp == "step":
                Yb, Mb, Vb = window(yrs < years[0])
                after = np.isin(yrs, [y for y in yrs if y >= years[0]])
                Ya, Ma, Va = window(after)
                ratio = (Ya / Ma) / (Yb / Mb) if Ma > 0 and Mb > 0 and Yb > 0 else None
                # the log ratio's standard error by the delta method on the model's variances (overdispersion and the
                # serial correlation included); 1/Y + 1/Y had been Poisson's alone
                se = np.sqrt(Va / max(Ma, 1e-9) ** 2 + Vb / max(Mb, 1e-9) ** 2)
                p = float(stats.norm.sf(np.log(ratio) / se)) if ratio else None
                out.append({**base, "observed": Ya, "expected": Ma, "effect": ratio, "effect_unit": "ratio of O/E after to before",
                            "low": float(ratio * np.exp(-1.96 * se)) if ratio else None,
                            "high": float(ratio * np.exp(1.96 * se)) if ratio else None, "p": p,
                            "answer": "tested"})
                continue
            if M <= 0:
                out.append({**base, "answer": "not testable: no expected events at the locus"})
                continue
            if support == "residence" and comp != "step":
                # the expectation of the window scaled by the change in the share of the field's events placed at all
                # (`_allocation`): a recording change, not the place's events, had read as the hypothesis
                shares = _allocation(it, sorted(set(before) | set(years)))
                was = [shares[y] for y in before if y in shares]
                now = [shares[y] for y in years if y in shares]
                if was and now and min(was) > 0:
                    k = float(np.mean(now)) / float(np.mean(was))
                    base = {**base, "allocated_before": float(np.mean(was)), "allocated_window": float(np.mean(now))}
                    M, V = M * k, V * k * k
            size = M ** 2 / max(V - M, 1e-9)                      # the sum's NB by moments (Poisson when V = M)
            pval = float(stats.nbinom.sf(Y - 1, size, size / (size + M))) if V > M * 1.0001 else                 float(stats.poisson.sf(Y - 1, M))
            lo = stats.chi2.ppf(0.025, 2 * Y) / 2 / M if Y > 0 else 0.0
            hi = stats.chi2.ppf(0.975, 2 * Y + 2) / 2 / M
            out.append({**base, "observed": Y, "expected": M, "effect": Y / M, "effect_unit": "rate ratio",
                        "low": float(lo), "high": float(hi), "p": pval, "answer": "tested"})
    seen, kept = set(), []
    for r in out:                          # a source read under several readers says "not testable" once
        k = (r["hypothesis"], r["source"], r["support"], r["field_reader"], r.get("answer") if r.get("p") is None else id(r))
        if k not in seen:
            seen.add(k)
            kept.append(r)
    out = kept
    # each hypothesis is its own family (its own budget, ARCHITECTURE §7.7): Holm over the sources that test it
    for hyp in {r["hypothesis"] for r in out}:
        tested = sorted((r for r in out if r["hypothesis"] == hyp and r.get("p") is not None), key=lambda r: r["p"])
        running = 0.0
        for k, r in enumerate(tested):
            running = max(running, min(1.0, (len(tested) - k) * r["p"]))
            r["p_holm"] = running
            r["answer"] = "supported" if running <= decl.q else "not supported at q"
    return out


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_").lower()


#: what y and mu are, by the field's model (`monolith.model_class`): a count field's are events; a mark's are on its
#: model's own scale, which the table says on every row
EXPECTATION_SCALES = {
    "events": "events",
    "share": "empirical logit of the share: log((k + 1/2) / (n - k + 1/2)) of the n events, k of them marked",
    "count": "log of the mean count per event (a count-valued mark: ICU days of the admissions that used ICU)",
    "": "mean of the log of the mark per event (a positive measure: its geometric mean on the log scale)"}


def _expectation_table(sv, names: dict, field_id: str, label: str, model=None) -> pa.Table:
    """Observed against expected per municipality and period, with the surprise, the field, its scale and the place's
    names. A mark's cells carry their events (``n``), and a share's its observed and expected share, where y and mu are
    the empirical logit and its expectation (the audit read a linked share's logits as negative events, 2026-10-14)."""
    t = sv.table()
    u = [str(x) for x in t.column("u").to_pylist()]
    rows = t.num_rows
    mark = sv.extras.get("kind") == "mark"
    family = (getattr(model, "family", "") or "") if mark else "events"
    n = np.asarray(sv.extras["events"], dtype=float).ravel() if mark and "events" in sv.extras else np.full(rows, np.nan)
    y = np.asarray(t.column("y").to_numpy(zero_copy_only=False), dtype=float)
    mu = np.asarray(t.column("mu").to_numpy(zero_copy_only=False), dtype=float)
    observed = expected = np.full(rows, np.nan)
    if family == "share":
        # k from the empirical logit: e^y = (k + 1/2) / (n - k + 1/2)
        with np.errstate(invalid="ignore", over="ignore", divide="ignore"):
            k = (np.exp(y) * (n + 0.5) - 0.5) / (1.0 + np.exp(y))
            observed = np.where(n > 0, k / n, np.nan)
            expected = 1.0 / (1.0 + np.exp(-mu))
    return pa.table({"field": pa.array([field_id] * rows), "label": pa.array([label] * rows),
                     "scale": pa.array([EXPECTATION_SCALES.get(family, EXPECTATION_SCALES[""])] * rows),
                     "u": t.column("u"),
                     "municipality": pa.array([(names.get(c) or {}).get("name") for c in u]),
                     "state": pa.array([(names.get(c) or {}).get("uf_sigla") for c in u]),
                     **{c: t.column(c) for c in t.column_names if c != "u"},
                     "n": pa.array(n, pa.float64()), "observed_share": pa.array(observed, pa.float64()),
                     "expected_share": pa.array(expected, pa.float64())})


#: the population account's race slices by the label a source gives its race codes (labels, never code numbers: SIH's
#: 03 is parda and 04 amarela, SIM's, SINAN's and SINASC's the reverse)
ACCOUNT_RACE = {"branca": "branca", "preta": "preta", "amarela": "amarela", "parda": "parda", "indigena": "indigena"}


def _race_rates(it: Item, s, f, label: str) -> list[dict]:
    """A person-year field's standardised ratio by race, with its exact Poisson interval: each race's events (the
    subject's declared race, `gateway._strata`; each code mapped to the population account's race slice by its label,
    never its number) against those expected of its population at the field's own age-sex rates (indirect
    standardisation, the rates of each year's cells over every race): the tensor's race slices (tools.RACE_POPULATION)
    in the model's cells. A crude rate per all-age person-years of a race confounds race with age (P37.1's newborn
    admissions over each race's whole population, the first reading, 2026-10-13); the ratio does not. Fields rated per
    other events (the agravos: a birth's race is the mother's), and fields read collapsed (no age-sex cells), have none.
    Events of no recorded race are in no race's ratio."""
    import unicodedata

    from scipy.stats import chi2

    from . import monolith, tools

    d = s.expectations.model(f.block).data
    if _births_field(it) or d.n is not None or str(d.population).startswith("events:") or (it.source or {}).get("population")             or d.key.get("collapse"):
        return []
    column = gateway._strata(it.dataset, it.event).get("race")
    if not column:
        return []
    leaves = [d.leaves.index(c) for c in s.expectations.registry.leaves(f.node) if c in d.leaves]
    sel_e = np.isin(d.e, leaves)
    if np.unique(d.g[sel_e]).size <= 1:
        return []
    try:
        y, _, values = s.by_composition(f.node, column)
        import pegasus_data as pg

        labels = pg.levels(it.dataset, column, [v for v in values if v not in ("not recorded", "value missing")],
                           root=config.data_root())
    except Exception:  # noqa: BLE001 - a field whose race cannot be read has no race ratios; its shares say why
        return []

    def plain(x):
        return unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode().strip().lower()
    U, T, G = d.N.shape
    nB = G // 2
    edges = gateway.age_edges(d.population, it.dataset, it.event)
    if len(edges) != nB:
        return []
    # the field's rate in each year and age-sex cell, over every race (the place's events summed)
    yg = np.zeros((U, T, G))
    np.add.at(yg, (d.u[sel_e], d.t[sel_e], d.g[sel_e]), d.y[sel_e])
    N = d.N.astype(float)
    rate = np.divide(yg.sum(0), N.sum(0), out=np.zeros((T, G)), where=N.sum(0) > 0)          # [T, G]
    years = [int(x) for x in np.asarray(d.years)]
    races = {k: ACCOUNT_RACE.get(plain(labels.get(v, ""))) for k, v in enumerate(values)}
    races = {k: r for k, r in races.items() if r}
    # what the source says of its race column (pegasus_data's role note: SIH's code 04), on every row it makes
    note = next((r.get("note") for r in gateway.roles(it.dataset) if r.get("column") == column), None)
    expected = {}
    for k, race in races.items():
        tab = gateway._tensor_population(years, tools.RACE_POPULATION, race)
        u = monolith.positions(np.asarray(d.places), tab.column("u").to_numpy())
        t = np.searchsorted(np.asarray(years), tab.column("year").to_numpy())
        g = (tab.column("sex").to_numpy().astype(np.int64) - 1) * nB + monolith.age_band(tab.column("age").to_numpy(), edges)
        ok = (u >= 0) & (t < len(years)) & (g >= 0) & (g < G)
        expected[k] = np.zeros((U, T))
        np.add.at(expected[k], (u[ok], t[ok]), tab.column("n").to_numpy()[ok] * rate[t[ok], g[ok]])
    out = []
    for k, race in races.items():
        v = values[k]
        for ti, year in enumerate(years):
            for level, unit, sel in [(*_whole(), np.ones(U, bool))] +                     _levels_below(np.asarray(d.places)):
                # the expectation of the events whose race is recorded: each race's share of the population's expected
                # events times them (the unrecorded had lowered every race's ratio alike)
                recorded = float(sum(y[sel, ti, j].sum() for j in races))
                total_ex = float(sum(expected[j][sel, ti].sum() for j in races))
                ev = float(y[sel, ti, k].sum())
                ex = float(expected[k][sel, ti].sum()) * (recorded / total_ex if total_ex > 0 else 0.0)
                if ex <= 0:
                    continue
                lo = chi2.ppf(0.025, 2 * ev) / 2 if ev > 0 else 0.0
                hi = chi2.ppf(0.975, 2 * ev + 2) / 2
                out.append(_estimate_row(
                    "rates", "smr", {"field": f.id, "label": f"{label} — race: {labels.get(v, v)}", "dataset": it.dataset,
                                     "geography": level, "place": unit, **_period(year, None), "note": note},
                    variable="race", value=race, estimate=ev / ex, low=lo / ex, high=hi / ex,
                    interval="exact Poisson, expectation fixed", numerator=ev, denominator=ex,
                    denominator_kind="expected events (age-sex indirect, population account)",
                    comparator="every race at the field's age-sex rates"))
    return out


def _allocation(it: Item, years: list[int], support: str | None = None, lost: list | None = None,
                base: dict | None = None) -> dict[int, float]:
    """Each year's share of the field's events, nationally, that its counts can place (a residence, a sex, an age): the
    rest are unallocated and in no rate. A rate series whose share moves reads a recording change: SIA-PA's toxoplasma
    serology by residence rose 65-fold in Rio Grande do Sul over 2014-2023 while the tests billed stayed near five million
    a year, its consolidated production (no patient, no residence) giving way to individual records: 0.15 % of the
    tests placed in 2014, 9.7 % in 2023 (2026-10-13). The field's own codes for a code set. ``lost``, when given,
    receives the completeness rows the shares are made of (estimates.parquet, completeness): each reason the events were not placed,
    Brazil's events with no residence for an area, and the share placed."""
    import pyarrow.compute as pc

    src = it.source or {}
    codes = list(fields.codes_of(src, it.nodes))
    listed = fields.classifier_of(it.dataset, it.event, src, primary=False)
    listed = listed if isinstance(listed, tuple) else None
    out, keep = {}, lost
    base = base or {"dataset": it.dataset}
    ec_codes = tuple(codes) if it.extract else ()
    for y in years:
        try:
            # the rates' own cells (residence, sex and age): counted by residence alone, a certificate with no sex or
            # age was "placed" and in no rate (Alagoas 2016: 1,504 placed, 1,503 rated; the paper audit, 2026-10-14)
            area_ = tuple(sorted(config.study_area())) if config.study_area() else None
            # a code list's events by each category they carry, as its field counts them
            ec = (gateway.code_list_counts(it.dataset, it.event, int(y), list(listed), area=area_) if listed else
                  gateway.event_counts(it.dataset, it.event, int(y), classifier=src.get("classifier"),
                                       codes=tuple(codes) if it.extract else (), support=support, area=area_))
        except Exception:  # noqa: BLE001 - a year that cannot be counted has no share
            continue
        tabs = [ec.counts, ec.unallocated]
        if codes:
            def mine(t):
                hit = pc.starts_with(t.column("code"), codes[0])
                for c in codes[1:]:
                    hit = pc.or_(hit, pc.starts_with(t.column("code"), c))
                return t.filter(pc.fill_null(hit, False))
            tabs = [mine(t) if "code" in t.column_names else t for t in tabs]
        placed = float(pc.sum(tabs[0].column("y")).as_py() or 0)
        un = tabs[1]
        brazil = pc.ends_with(un.column("reason"), " (Brazil)") if un.num_rows else None
        lost = float(pc.sum(un.filter(pc.invert(brazil)).column("y")).as_py() or 0) if un.num_rows else 0.0
        share = placed / (placed + lost) if placed + lost > 0 else None
        if keep is not None and un.num_rows:
            mine_lost = un.filter(pc.invert(brazil)).group_by("reason").aggregate([("y", "sum")])
            for reason, n in zip(mine_lost.column("reason").to_pylist(), mine_lost.column("y_sum").to_pylist(),
                                 strict=True):
                keep.append(_indicator({**base, **_period(int(y), None)}, f"events not placed: {reason}",
                                       float(n or 0), placed + lost))
        if share is not None and config.study_area() is not None and support is None:
            # an area's residence share is Brazil's (a record with no residence is never knowably the area's): the
            # area's own share by sex and age times the national share placed at a residence, where the area's placed
            # events had been divided by its own unallocated plus Brazil's blanks (the review of the study, 2026-10-14)
            column = listed or fields.classifier_of(it.dataset, it.event, src)
            try:
                tot, nowhere = gateway.event_totals(it.dataset, it.event, int(y), column, codes=ec_codes), \
                    gateway.unplaced(it.dataset, it.event, int(y), column)
            except Exception:  # noqa: BLE001 - a national total that cannot be read leaves the area's own share
                tot = nowhere = None
            if tot is not None:
                tabs2 = [mine(t) for t in (tot, nowhere)] if codes else [tot, nowhere]
                total = float(pc.sum(tabs2[0].column("y")).as_py() or 0)
                blank = float(pc.sum(tabs2[1].column("y")).as_py() or 0) if tabs2[1].num_rows else 0.0
                share = share * (1.0 - blank / total) if total > 0 else share
                if keep is not None and total > 0:
                    keep.append(_indicator({**base, **_period(int(y), None)}, "Brazil's events with no residence "
                                           "recorded (none is knowably the area's)", blank, total))
                    # and those with a residence but no sex, age or valid municipality: in no reference rate of Brazil
                    # (descriptive's level reference), which is total - blank - these (the audit, 2026-10-14)
                    try:
                        national = (gateway.code_list_counts(it.dataset, it.event, int(y), list(listed)).counts
                                    if listed else gateway.event_counts(it.dataset, it.event, int(y),
                                                                        classifier=src.get("classifier"),
                                                                        codes=ec_codes).counts)
                        placed_br = float(pc.sum((mine(national) if codes else national).column("y")).as_py() or 0)
                    except Exception:  # noqa: BLE001 - Brazil's placed events unreadable: the row is not written
                        placed_br = None
                    if placed_br is not None:
                        rest = max(total - blank - placed_br, 0.0)
                        keep.append(_indicator({**base, **_period(int(y), None)}, "Brazil's events with a residence "
                                               "but no sex, age or valid municipality (in no reference rate)", rest,
                                               total))
        if share is not None:
            out[int(y)] = share
            if keep is not None:
                keep.append(_indicator({**base, **_period(int(y), None)}, "events placed (residence, sex and age): "
                                       "the share every rate counts", placed, None, share=share))
    return out


def _apc_adjusted(y: np.ndarray, n: np.ndarray) -> tuple[float, float, float] | None:
    """The age-sex-adjusted log-linear slope of a series and its variance: counts y[t, g] (years × sex-age cells) ~
    Poisson(n[t, g] exp(a_g + b·x_t)), each cell's level profiled out (closed form given b), b by Newton on the profile;
    the variance widened by the year-level Pearson dispersion (quasi-Poisson, never below Poisson's), the trend's own
    lack of fit. None when the years cannot identify it."""
    keep = (y.sum(0) > 0) & (n.sum(0) > 0)
    y, n = y[:, keep], n[:, keep]
    T = y.shape[0]
    if T < 3 or y.shape[1] == 0 or int((y.sum(1) > 0).sum()) < 3:
        return None
    x = np.arange(T, dtype=float) - (T - 1) / 2
    b = 0.0
    for _ in range(100):
        e = n * np.exp(b * x)[:, None]
        a = np.log(y.sum(0) / np.maximum(e.sum(0), 1e-300))          # each cell's level given b
        mu = e * np.exp(a)[None, :]
        score = float(((y - mu) * x[:, None]).sum())
        sx = (mu * x[:, None]).sum(0)
        info = float((mu * (x ** 2)[:, None]).sum() - (sx ** 2 / np.maximum(mu.sum(0), 1e-300)).sum())
        if not info > 0:
            return None
        step = score / info
        b += step
        if abs(step) < 1e-12:
            break
    yt, mt = y.sum(1), mu.sum(1)
    disp = max(float(((yt - mt) ** 2 / np.maximum(mt, 1e-300)).sum() / (T - 2)), 1.0)
    return b, disp / info, disp


def _apc(rows: list[dict]) -> list[dict]:
    """Each series' annual percent change (the crude rates of one field, geography, place, unit and stratum over the
    years), two ways: crude, a Poisson regression of the events on the year with the denominator as offset; and,
    where the rates carry their sex-age cells, age-sex adjusted (`_apc_adjusted`): an ageing population read as a rising
    risk in the crude one (Alagoas's infarction admissions: crude 5.6 %, adjusted about 2.6 %, the review of the study,
    2026-10-14). Each slope's interval is widened by the year-level Pearson dispersion (quasi-Poisson; never below
    Poisson's) and read on Student's t with T − 2 degrees of freedom, the dispersion being estimated (1.96 had made a
    ten-year interval 1.18 times too narrow). APC = 100 (e^b − 1). Provisional years are left out. Then joinpoint
    regression of the crude and of the directly standardised rate. A race's standardised ratio is a series too (is the
    disparity changing?): its events over its expected events, in the ratio's own unit. Returns the trends' estimates."""
    from scipy.stats import t as student

    series: dict[tuple, list[dict]] = {}
    for r in rows:
        if r["measure"] in ("crude_rate", "smr", "person_rate") and r["period_kind"] == "year" and not r.get("provisional") \
                and not r.get("partial") and r.get("denominator"):
            series.setdefault((r["field"], r["geography"], r["place"], r.get("unit") or "standardised ratio (observed "
                               "over expected)", r.get("stratum"), r.get("value"), r["measure"]), []).append(r)
    out = []
    for (field_, level, place, unit, group, _, _), rs in series.items():
        rs = sorted(rs, key=lambda r: r["first"])
        t = np.array([float(r["first"]) for r in rs])
        y = np.array([float(r["numerator"]) for r in rs])
        n = np.array([float(r["denominator"]) for r in rs])
        if len(rs) < 3 or int((y > 0).sum()) < 3 or (n <= 0).any():
            continue                       # a slope needs events in three years at least (one event read 9e16 %/year)
        x = t - t.mean()
        b0, b1 = np.log(y.sum() / n.sum()), 0.0
        for _ in range(50):                                   # Newton on the Poisson log-likelihood
            mu = n * np.exp(b0 + b1 * x)
            g = np.array([(y - mu).sum(), ((y - mu) * x).sum()])
            h = np.array([[mu.sum(), (mu * x).sum()], [(mu * x).sum(), (mu * x * x).sum()]])
            step = np.linalg.solve(h, g)
            b0, b1 = b0 + step[0], b1 + step[1]
            if np.abs(step).max() < 1e-10:
                break
        mu = n * np.exp(b0 + b1 * x)
        disp = max(float(((y - mu) ** 2 / np.maximum(mu, 1e-300)).sum() / (len(rs) - 2)), 1.0)
        with np.errstate(invalid="ignore"):
            var = float(np.linalg.pinv(h)[1, 1] * disp)
        if not np.isfinite(b1) or not var > 0:
            continue                       # a series whose slope the years cannot identify (events in one year only)
        se = var ** 0.5
        dof = len(rs) - 2
        q975 = float(student.ppf(0.975, dof))
        events = float(y.sum())
        # a trend is its own row of estimates.parquet (trends): its percentage had been written in the rate columns of
        # the descriptive table, said only by the text of `per` (2026-10-14)
        # each row its own unit (an APC is % a year, a count of joinpoints a count); the series' rate is the variable
        base = {"field": field_, "label": rs[0]["label"], "dataset": rs[0]["dataset"], "geography": level,
                "place": place, "stratum": group, "variable": f"{rs[0]['measure'].replace('_', ' ')} {unit}",
                "value": rs[0].get("value"), "denominator_kind": rs[0].get("denominator_kind")}
        whole = {**base, "period_kind": "period", "first": int(t[0]), "last": int(t[-1])}

        def slope(model: str, b: float, sd: float, dispersion: float, whole=whole, q975=q975, df=dof,
                  events=events) -> list[dict]:
            return [_estimate_row("trends", "apc", {**whole, "model": model, "unit": "% a year"}, estimate=100 * np.expm1(b),
                                  low=100 * np.expm1(b - q975 * sd), high=100 * np.expm1(b + q975 * sd), interval="t",
                                  p=float(2 * student.sf(abs(b / sd), df)), numerator=events),
                    _estimate_row("trends", "dispersion", {**whole, "model": model}, estimate=dispersion)]
        out += slope("crude", b1, se, disp)
        # the adjusted model reads a series' sex-age cells: a rate of one cell (per live birth: births carry no sex or
        # age) has none to adjust for, and its (1, 1) cells had crashed the products of every perinatal field (the
        # slice gate, 2026-10-14)
        cells = [r.get("_cells") for r in rs]
        if all(c is not None and np.ndim(c[0]) == 1 and np.size(c[0]) > 1 for c in cells):
            adj = _apc_adjusted(np.array([c[0] for c in cells], dtype=float), np.array([c[1] for c in cells], dtype=float))
            if adj is not None and np.isfinite(adj[0]) and adj[1] > 0:
                out += slope("age-sex adjusted", adj[0], adj[1] ** 0.5, adj[2])
        # joinpoint regression on the crude rate and on the directly standardised rate (the series a paper's trend
        # figure draws): a log-linear slope over a series that jumps and plateaus had been the only trend, and the
        # adjusted model's slope is not the standardised series' (the paper audit, 2026-10-14). The fitted rates on the
        # series' own scale: a perinatal series' crude rate is per 1,000 live births, and its fitted rates had been per
        # 100,000 under that unit (2026-10-14); the standardised rate is per 100,000 already
        first = {"smr": "joinpoint: standardised ratio", "person_rate": "joinpoint: person rate"}.get(
            rs[0]["measure"], "joinpoint: crude rate")
        inputs = [(first, np.log(y / n) if (y > 0).all() else None, y, float(rs[0].get("per") or 1.0))]
        std = [r.get("_std") for r in rs]
        if all(x is not None and x.get("estimate") and x.get("variance") for x in std):
            dsr = np.array([x["estimate"] for x in std], dtype=float)
            dvar = np.array([x["variance"] for x in std], dtype=float)
            if np.isfinite(dsr).all() and (dsr > 0).all() and np.isfinite(dvar).all() and (dvar > 0).all():
                inputs.append(("joinpoint: standardised rate", np.log(dsr), dsr ** 2 / dvar, 1.0))
        for model, logr, w, scale in inputs:
            jp = _joinpoint(t, logr, np.asarray(w, dtype=float), seed=config.seed(field_, level, place, group, model)) \
                if logr is not None else None
            if jp is None:
                continue
            # the standardised series is its own variable and unit (per 100,000): it had carried the crude series'
            # name, an AAPC of the standardised rate labelled "crude rate" (2026-10-14)
            std_ = model == "joinpoint: standardised rate"
            common = {**base, "model": model, **({"variable": "directly standardised rate per 100,000 person-years"}
                                                  if std_ else {})}
            unit_ = "per 100,000 person-years" if std_ else unit
            for i, sg in enumerate(jp["segments"]):
                seg = {**common, "segment": str(i + 1)}
                a = _apc_interval(sg["b"], sg["se"], jp["df"])
                out.append(_estimate_row("trends", "apc", {**seg, "period_kind": "segment", "first": int(sg["first"]),
                                                            "last": int(sg["last"]), "unit": "% a year"},
                                         estimate=a["apc"], low=a["apc_low"], high=a["apc_high"], interval="t",
                                         p=a["p"], numerator=events))
                for fit, yr in ((sg["fit_first"], sg["first"]), (sg["fit_last"], sg["last"])):
                    out.append(_estimate_row("trends", "fitted_rate", {**seg, "period_kind": "year", "first": int(yr),
                                                                        "last": int(yr), "unit": unit_},
                                             estimate=scale * fit))
            aapc = {**common, "segment": "AAPC", "period_kind": "period", "first": int(t[0]), "last": int(t[-1])}
            a = _apc_interval(jp["aapc"][0], jp["aapc"][1], jp["df"])
            out += [_estimate_row("trends", "aapc", {**aapc, "unit": "% a year"}, estimate=a["apc"], low=a["apc_low"],
                                  high=a["apc_high"], interval="t", p=a["p"], numerator=events),
                    _estimate_row("trends", "dispersion", aapc, estimate=jp["scale"]),
                    _estimate_row("trends", "joinpoints", {**aapc, "unit": "joinpoints"}, estimate=jp["joinpoints"],
                                  p=jp["p"], note=", ".join(str(int(v)) for v in jp["years"]) or None)]
    return out


def _apc_interval(b: float, se: float, df: int) -> dict:
    """An annual percent change from a log-linear slope, with its t interval and two-sided p."""
    from scipy.stats import t as student

    q = float(student.ppf(0.975, df))
    return {"apc": 100 * float(np.expm1(b)), "apc_low": 100 * float(np.expm1(b - q * se)),
            "apc_high": 100 * float(np.expm1(b + q * se)),
            "p": float(2 * student.sf(abs(b / se), df)) if se > 0 else None}


def _joinpoint_max(n: int) -> int:
    """The most joinpoints a series of n points may hold: the NCI Joinpoint program's default by the number of points."""
    return 0 if n < 7 else 1 if n < 12 else 2 if n < 17 else 3 if n < 22 else 4 if n < 27 else 5


def _joinpoint(x: np.ndarray, logr: np.ndarray, w: np.ndarray, permutations: int = 4499, alpha: float = 0.05,
               seed: int = 0) -> dict | None:
    """Joinpoint regression (Kim, Fay, Feuer & Midthune 2000; the NCI Joinpoint program's defaults): the log rate
    segmented-linear in the year by weighted least squares, each year weighted by the inverse variance of its log rate
    and the scale estimated; joinpoints at observed years, at least two years between a joinpoint and an end or another
    joinpoint; their number chosen by Kim's sequence of permutation tests (each at alpha over the number of tests, the
    residuals of the smaller model permuted); each segment's annual percent change with its t interval on n - 2k - 2
    degrees of freedom; and the average annual percent change of the whole series (the segments' slopes weighted by their
    lengths, its variance by the delta method). None when a year has no weight (a log rate of no events)."""
    import itertools

    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 3 or not (np.isfinite(logr).all() and np.isfinite(w).all() and (w > 0).all()):
        return None
    sw = np.sqrt(w)
    xc = x - x.mean()

    def placements(k: int) -> list[tuple]:
        return [c for c in itertools.combinations(range(2, n - 2), k)
                if all(b - a >= 3 for a, b in zip(c, c[1:], strict=False))]

    def design(c: tuple) -> np.ndarray:
        return np.column_stack([np.ones(n), xc, *[np.maximum(x - x[j], 0.0) for j in c]]) * sw[:, None]

    def best(k: int, Y: np.ndarray) -> tuple[np.ndarray, list[tuple]]:
        cs = placements(k)
        sse = np.empty((len(cs), Y.shape[1]))
        for i, c in enumerate(cs):
            q, _ = np.linalg.qr(design(c))
            proj = q.T @ Y
            sse[i] = (Y * Y).sum(0) - (proj * proj).sum(0)
        return np.maximum(sse.min(0), 0.0), [cs[i] for i in sse.argmin(0)]

    kmax = _joinpoint_max(n)
    while kmax and not placements(kmax):
        kmax -= 1
    yt = (sw * logr)[:, None]
    rng = np.random.default_rng(seed)
    a, b, p_last = 0, kmax, None
    while a < b:
        s_a, c_a = best(a, yt)
        s_b, _ = best(b, yt)
        stat = (s_a[0] - s_b[0]) / max(s_b[0], 1e-300)
        xa = design(c_a[0])
        fit = xa @ np.linalg.lstsq(xa, yt[:, 0], rcond=None)[0]
        res = yt[:, 0] - fit
        Y = fit[:, None] + res[rng.random((n, permutations)).argsort(0)]
        n_a, _ = best(a, Y)
        n_b, _ = best(b, Y)
        null = (n_a - n_b) / np.maximum(n_b, 1e-300)
        p_last = float((1 + (null >= stat - 1e-12).sum()) / (1 + permutations))
        if p_last < alpha / kmax:
            a += 1
        else:
            b -= 1
    k = a
    sse, cs = best(k, yt)
    c = cs[0]
    X = design(c)
    beta = np.linalg.lstsq(X, yt[:, 0], rcond=None)[0]
    df = max(n - 2 - 2 * k, 1)
    scale = float(sse[0]) / df
    cov = scale * np.linalg.pinv(X.T @ X)
    edges = [0, *c, n - 1]
    fitted = np.column_stack([np.ones(n), xc, *[np.maximum(x - x[j], 0.0) for j in c]]) @ beta      # the log rate
    segments, la = [], np.zeros(len(beta))
    for i in range(k + 1):
        lv = np.zeros(len(beta))
        lv[1], lv[2:2 + i] = 1.0, 1.0
        first, last = x[edges[i]], x[edges[i + 1]]
        segments.append({"first": first, "last": last, "b": float(lv @ beta),
                         "se": float(np.sqrt(max(lv @ cov @ lv, 0.0))),
                         "fit_first": float(np.exp(fitted[edges[i]])), "fit_last": float(np.exp(fitted[edges[i + 1]]))})
        la = la + (last - first) / (x[-1] - x[0]) * lv
    return {"joinpoints": k, "years": [x[j] for j in c], "p": p_last, "df": df, "scale": scale,
            "segments": segments, "aapc": (float(la @ beta), float(np.sqrt(max(la @ cov @ la, 0.0))))}


def _descriptive(it: Item, s, f, label: str, refs: list | None = None, support: bool = False,
                 standards: dict | None = None) -> list[dict]:
    """Counts, crude and directly age–sex-standardised rates per 100,000 by year, nationally and by state, from the
    fitted block's own cells (the population of the model's exposure; the standard is Brazil's 2010 population). Each
    crude rate carries its exact Poisson 95% interval (Garwood), the exposure held fixed; a ratio field's rate is per
    denominator event (``per``), its "population" the denominator's events. ``refs`` (`_reference_cells`) adds
    Brazil's and the macro-regions' rows, each by sex and age as the area's, and every standardised rate its ratio to
    Brazil's; ``support`` says a field read at the place of occurrence or care is rated on that place's residents;
    ``standards`` receives the standard used (standard.parquet)."""
    from scipy.stats import chi2

    m = s.expectations.model(f.block)
    d = m.data
    if d.n is not None:
        return _descriptive_cells(it, s, f, label, d)
    leaves = [d.leaves.index(c) for c in s.expectations.registry.leaves(f.node) if c in d.leaves]
    U, T, G = d.N.shape
    y = np.zeros((U, T, G))
    sel = np.isin(d.e, leaves)
    np.add.at(y, (d.u[sel], d.t[sel], d.g[sel]), d.y[sel])
    N = d.N.astype(float)
    # a fixed, named standard (Brazil's 2010 population by sex and age band, of the field's own population source): the
    # area's own pooled structure had been the standard, under a codebook saying "national", so a state-year's rate
    # changed with the period and compared with nothing (the review of the study, 2026-10-14)
    std, std_name = _standard(str(d.population), tuple(gateway.age_edges(d.population, it.dataset, it.event)),
                              it.dataset, N.shape[2])
    if std is None:
        std = N.sum(axis=(0, 1))
        std = std / std.sum() if std.sum() > 0 else std
        std_name = f"the study's own population, {int(np.asarray(d.years)[0])}-{int(np.asarray(d.years)[-1])}"
    out: list[dict] = []
    # the exposure the block was fitted on: person-years, or other events (a declared ratio, or the event type's
    # declared denominator: live births), reported per 1,000 of them
    ratio = str(d.population).startswith("events:")
    per, scale = ((f"1,000 {_exposure_text(d.population)}", 1e3) if ratio
                  else ("100,000 person-years", 1e5))
    if support and not ratio:
        # events at the place they occurred or were cared for, over that place's residents: an occurrence ratio, not a
        # risk (the audit read it as a rate per person-year of the people at risk, 2026-10-14)
        per = "100,000 person-years of the place's residents (events where they occurred: not a risk)"
    edges_ = gateway.age_edges(d.population, it.dataset, it.event)
    if standards is not None and std_name and std is not None and len(std) == 2 * len(edges_):
        standards[std_name] = (_band_labels(edges_), std)

    period = f"{int(np.asarray(d.years)[0])}-{int(np.asarray(d.years)[-1])}"
    # what the denominator is (estimates' ``denominator_kind``): person-years of residents, another field's events, or
    # the residents of the place an event occurred at
    kind = (_exposure_text(d.population) if ratio else
            "person-years of the place's residents (events where they occurred: not a risk)" if support else
            "person-years")

    def row(level: str, unit: str, t: int | None, yy: np.ndarray, nn: np.ndarray, group: str | None = None,
            std_g: np.ndarray | None = None) -> list[dict]:
        base = {"field": f.id, "label": label, "dataset": it.dataset, "geography": level, "place": unit,
                "stratum": group, **_period(int(np.asarray(d.years)[t]) if t is not None else None,
                                            None if t is not None else period)}
        out_ = _rated(base, float(yy.sum()), float(nn.sum()), per, scale, kind, cells=(yy, nn))
        sg = std if group is None else std_g
        if not ratio and float(nn.sum()) and sg is not None and yy.shape == sg.shape:
            # direct standardisation with the gamma interval of Fay & Feuer (1997): the standardised rate is a weighted
            # sum of Poisson counts, w_g = std_g / n_g; a sex's rate on the standard's ages of that sex
            with np.errstate(divide="ignore", invalid="ignore"):
                rate_g = np.where(nn > 0, yy / nn, 0.0)
                w = np.where(nn > 0, sg / nn, 0.0)
            dsr, var = float((w * yy).sum()), float((w * w * yy).sum())
            wm = float(w[nn > 0].max()) if (nn > 0).any() else 0.0
            low = chi2.ppf(0.025, 2 * dsr * dsr / var) * var / (2 * dsr) if dsr > 0 and var > 0 else 0.0
            vh = var + wm * wm
            high = chi2.ppf(0.975, 2 * (dsr + wm) ** 2 / vh) * vh / (2 * (dsr + wm)) if vh > 0 else None
            sr = _estimate_row("rates", "standardised_rate", base, estimate=1e5 * float((rate_g * sg).sum()),
                               low=1e5 * float(low), high=1e5 * float(high) if high else None,
                               interval="gamma (Fay & Feuer 1997)", denominator=float(nn.sum()),
                               denominator_kind=kind, per=1e5, unit="per 100,000 person-years",
                               standard=std_name if group is None else f"{std_name}: its ages, both sexes pooled",
                               variance=1e10 * var)
            out_.append(sr)
            out_[-2]["_std"] = sr              # the crude rate's standardised twin: the joinpoint of the series reads it
        return out_

    below = _levels_below(np.asarray(d.places))
    # a field whose events are live births is a birth prevalence: its person-year rows would be the mother's sex and age
    # over women's person-years (every event "female", the SINASC audit, 2026-10-14); only its rates per live births
    births_field = _births_field(it)
    # each year, then the whole period (a paper's table gives the period's rates beside the yearly series; they had to
    # be summed by hand from the yearly rows, 2026-10-14)
    for t in [] if births_field else [*range(T), None]:
        ys, ns = (y[:, t], N[:, t]) if t is not None else (y.sum(1), N.sum(1))
        out += row(*_whole(), t, ys.sum(0), ns.sum(0))
        for level, unit, sel_u in below:
            out += row(level, unit, t, ys[sel_u].sum(0), ns[sel_u].sum(0))
    # an area's reference: Brazil's and its macro-regions' rates of the same field, standardised to the same standard,
    # each year and over the period (an area's rate compared with nothing had been the folder's only rate, 2026-10-14)
    references = [] if ratio else list(refs or [])
    for unit, yr_, nr_ in [] if births_field else references:
        for t in [*range(T), None]:
            yy, nn = (yr_[t], nr_[t]) if t is not None else (yr_.sum(0), nr_.sum(0))
            out += row("reference", unit, t, yy, nn)
    if not ratio and not births_field and G >= 4 and G % 2 == 0:
        # rates by sex and by age band, for the whole: the risk a paper's first tables give (the case-mix shares say
        # nothing about it), each with its exact interval and its own trend (`_apc`)
        nB = G // 2
        edges = gateway.age_edges(d.population, it.dataset, it.event)
        bands = _band_labels(edges) if len(edges) == nB else [str(k) for k in range(nB)]
        # and by sex within each age band: the age-specific curves of each sex a paper plots
        groups = [("sex: male", slice(0, nB)), ("sex: female", slice(nB, G))] + \
            [(f"age {bands[k]}", [k, nB + k]) for k in range(nB)] + \
            [(f"sex: {sx}, age {bands[k]}", [k + off]) for sx, off in (("male", 0), ("female", nB)) for k in range(nB)]
        # each sex's standardised rate on one age standard, the standard's ages of both sexes pooled: on each sex's
        # own ages, male 52.4 and female 38.6 could not be divided (the third audit: 1.36, against 1.65 on one standard)
        ages = (std[:nB] + std[nB:G]) if std is not None else None
        common = ages / ages.sum() if ages is not None and ages.sum() > 0 else None
        std_of = {"sex: male": common, "sex: female": common}
        for t in [*range(T), None]:
            ys, ns = (y[:, t], N[:, t]) if t is not None else (y.sum(1), N.sum(1))
            for name, cells in groups:
                yy, nn = ys[:, cells].sum(0), ns[:, cells].sum(0)
                out += row(*_whole(), t, yy, nn, group=name, std_g=std_of.get(name))
            # Brazil's and the macro-regions' by sex and age: the age-specific curves a paper compares (the audit found
            # the reference by year only, 2026-10-14)
            for unit, yr_, nr_ in references:
                yr0, nr0 = (yr_[t], nr_[t]) if t is not None else (yr_.sum(0), nr_.sum(0))
                for name, cells in groups:
                    cells_ = cells if isinstance(cells, slice) else np.asarray(cells)
                    out += row("reference", unit, t, np.atleast_1d(yr0[cells_]), np.atleast_1d(nr0[cells_]),
                               group=name, std_g=std_of.get(name))
    if (not ratio or births_field) and _birth_related(it, d):
        # a perinatal or pregnancy field's rate is per live births, the convention of infant and maternal mortality
        # (RIPSA C.1, C.3): congenital toxoplasmosis' deaths had been given per 100,000 person-years of everyone
        # (2026-10-12); the person-year rows stay, the model's own exposure
        B = _births(d)

        def per_births(level, unit, t, sel_u):        # one cell: births carry no sex or age
            yy, bb = (y[sel_u, t], B[sel_u, t]) if t is not None else (y[sel_u].sum(1), B[sel_u].sum(1))
            base = {"field": f.id, "label": label, "dataset": it.dataset, "geography": level, "place": unit,
                    "stratum": None, **_period(int(np.asarray(d.years)[t]) if t is not None else None,
                                               None if t is not None else period)}
            # the count is the person-year rows' already, but for a births field, which has none
            return _rated(base, float(yy.sum()), float(bb.sum()), "1,000 live births", 1e3, "live births",
                          cells=(yy.sum(keepdims=True), bb.sum(keepdims=True)), count=births_field)
        for t in [*range(T), None]:
            out += per_births(*_whole(), t, np.ones(U, bool))
            for level, unit, sel_u in below:
                out += per_births(level, unit, t, sel_u)
        # Brazil's and the macro-regions' (and the region's without the area) per live births: what an area's birth
        # prevalence is compared with
        rb = _reference_births([int(x) for x in np.asarray(d.years)], [k for k, *_ in references])
        for unit, yr_, _ in references:
            for t in [*range(T), None]:
                ev_ = float(yr_[t].sum()) if t is not None else float(yr_.sum())
                bb = float(rb[unit][t]) if t is not None else float(rb[unit].sum())
                base = {"field": f.id, "label": label, "dataset": it.dataset, "geography": "reference", "place": unit,
                        "stratum": None, **_period(int(np.asarray(d.years)[t]) if t is not None else None,
                                                   None if t is not None else period)}
                out += _rated(base, ev_, bb, "1,000 live births", 1e3, "live births", count=births_field)
    _ratio_to_brazil(out)
    return out


def _rated(base: dict, events: float, pop: float, per: str, scale: float, kind: str, cells=None,
           count: bool = True) -> list[dict]:
    """A count (unless another row of the same events has it: ``count``) and, over its denominator, the crude rate with
    its exact Poisson 95 % interval (Garwood), the denominator fixed; ``cells`` (the sex-age events and denominators)
    kept for the age-sex adjusted trend, never written."""
    from scipy.stats import chi2

    out = [_estimate_row("rates", "count", base, estimate=events)] if count else []
    if pop:
        lo = chi2.ppf(0.025, 2 * events) / 2 if events > 0 else 0.0
        hi = chi2.ppf(0.975, 2 * events + 2) / 2
        out.append(_estimate_row("rates", "crude_rate", base, estimate=scale * events / pop, low=scale * lo / pop,
                                 high=scale * hi / pop, interval="exact Poisson (Garwood), denominator fixed",
                                 numerator=events, denominator=pop, denominator_kind=kind, per=scale,
                                 unit=f"per {per}", _cells=cells))
    return out


def _reference_births(years: list[int], units: list[str]) -> dict[str, np.ndarray]:
    """Live births by year of each reference unit of `_reference_cells` (Brazil, a macro-region by its digit, the region
    without the area)."""
    t = gateway.population(years, source=BIRTHS)
    u = t.column("u").to_numpy().astype(np.int64)
    yr = t.column("year").to_numpy().astype(np.int64)
    n = np.nan_to_num(t.column("n").to_numpy(zero_copy_only=False).astype(float))
    pos = np.searchsorted(np.asarray(years), yr)
    ok = np.isin(yr, years)
    out = {}
    for k in units:
        m = ok.copy()
        if k != "BR":
            m &= u // 100000 == int(k.split()[0])
            if k.endswith("without the area"):
                m &= ~config.in_area(u)
        out[k] = np.bincount(pos[m], weights=n[m], minlength=len(years))[:len(years)]
    return out


def _distinct_persons(it: Item, s, f, label: str, places: list[dict]) -> list[dict]:
    """A field's distinct persons where its source identifies its subject (`gateway.person_identifier`): each year, for
    the whole, each unit below it and each municipality, the persons and their rate per 100,000 residents (the treated
    prevalence: dialysis is a prevalent cohort, read as authorisations it had no patient, the SIA audit, 2026-10-14);
    over the period, the persons once. ``places`` (the municipalities' estimates) give each municipality's residents."""
    if gateway.person_identifier(it.dataset, it.event) is None:
        return []
    d = s.expectations.model(f.block).data
    if d.n is not None or str(d.population).startswith("events:"):
        return []
    import pyarrow.compute as pc

    src = it.source or {}
    classifier = fields.classifier_of(it.dataset, it.event, src)
    codes = fields.codes_of(src, it.nodes) or tuple(str(c) for c in s.expectations.registry.leaves(f.node)
                                                    if f.node != "*")
    area = tuple(sorted(config.study_area())) if config.study_area() else None
    years = [int(y) for y in np.asarray(d.years)]
    U = len(d.places)
    places_ = np.asarray(d.places, dtype=np.int64)
    N = d.N.astype(float).sum(2)                                 # [U, T]: residents' person-years
    pairs, every = {}, []
    for y in years:
        t = gateway.person_places(it.dataset, it.event, y, classifier if codes else None, codes, area)
        t = t.filter(pc.is_in(t.column("u"), value_set=pa.array(places_.astype(np.int32))))
        pairs[y] = t
        every.append(t.column("person"))
    out = []
    period = f"{years[0]}-{years[-1]}"
    levels = [(*_whole(), np.ones(U, bool)), *_levels_below(places_)]
    for level, unit, sel in levels:
        members = pa.array(places_[sel].astype(np.int32))
        for k, y in enumerate([*years, None]):
            if y is None:
                ts = [pairs[z].filter(pc.is_in(pairs[z].column("u"), value_set=members)) for z in years]
                n_p = len(set().union(*(set(x.column("person").to_pylist()) for x in ts))) if ts else 0
                base = {"field": f.id, "label": label, "dataset": it.dataset, "geography": level, "place": unit,
                        **_period(None, period)}
                out.append(_estimate_row("rates", "persons", base, estimate=float(n_p)))
                continue
            t = pairs[y].filter(pc.is_in(pairs[y].column("u"), value_set=members))
            n_p = len(set(t.column("person").to_pylist()))
            pop = float(N[sel, k].sum())
            base = {"field": f.id, "label": label, "dataset": it.dataset, "geography": level, "place": unit,
                    **_period(y, None)}
            out.append(_estimate_row("rates", "persons", base, estimate=float(n_p)))
            out += _person_rate("rates", base, n_p, pop)
    for ui, u in enumerate(places_):
        for k, y in enumerate(years):
            t = pairs[y].filter(pc.equal(pairs[y].column("u"), int(u)))
            n_p = t.num_rows
            row = next((r for r in places if r["measure"] == "count" and str(r["place"]) == str(int(u))
                        and r["period_kind"] == "year" and r["first"] == y), None)
            base = {"field": f.id, "label": label, "dataset": it.dataset, "geography": "municipality",
                    "place": int(u), **({k_: row.get(k_) for k_ in ("place_name", "state", "health_region",
                                                                   "health_macroregion")} if row else {}),
                    **_period(y, None)}
            out.append(_estimate_row("municipalities", "persons", base, estimate=float(n_p)))
            out += _person_rate("municipalities", base, n_p, float(N[ui, k]))
    return out


def _person_rate(section: str, base: dict, persons: float, pop: float) -> list[dict]:
    """Distinct persons per 100,000 residents' person-years, with the exact Poisson interval, the denominator fixed."""
    from scipy.stats import chi2

    if pop <= 0:
        return []
    lo = chi2.ppf(0.025, 2 * persons) / 2 if persons > 0 else 0.0
    hi = chi2.ppf(0.975, 2 * persons + 2) / 2
    return [_estimate_row(section, "person_rate", base, estimate=1e5 * persons / pop, low=1e5 * lo / pop,
                          high=1e5 * hi / pop, interval="exact Poisson (Garwood), denominator fixed", numerator=persons,
                          denominator=pop, denominator_kind="person-years", per=1e5,
                          unit="persons per 100,000 person-years")]


def _ratio_to_brazil(rows: list[dict]) -> None:
    """Each standardised rate's ratio to Brazil's of the same period and stratum, with its 95 % interval on the log scale
    from the two gamma variances (Brazil holds the area, so the interval is conservative): what a paper states as "x
    times the national rate" (the audit derived it by hand, 2026-10-14); and an area's against the rest of its region
    (no shared events: the two independent variances), when the area lies in one region. Appended to ``rows``."""
    std = [r for r in rows if r["measure"] == "standardised_rate" and r.get("estimate") and r.get("variance")]

    def key(r):
        return r["period_kind"], r["first"], r["last"], r.get("stratum")

    def ratio(r: dict, b: dict, comparator: str) -> dict:
        lr = float(np.log(r["estimate"] / b["estimate"]))
        se = float(np.sqrt(r["variance"] / r["estimate"] ** 2 + b["variance"] / b["estimate"] ** 2))
        base = {k: v for k, v in r.items() if k not in ("measure", "section", "variance", "denominator", "per", "unit",
                                                          "low", "high", "interval", "estimate")}
        return _estimate_row("rates", "rate_ratio", base, estimate=float(np.exp(lr)),
                             low=float(np.exp(lr - 1.96 * se)), high=float(np.exp(lr + 1.96 * se)),
                             interval="log-normal, two gamma variances", comparator=comparator)

    ref = {key(r): r for r in std if r["geography"] == "reference" and r["place"] == "BR"}
    rests = {r["place"] for r in std if r["geography"] == "reference" and str(r["place"]).endswith("without the area")}
    rest = {key(r): r for r in std if r["geography"] == "reference" and r["place"] in rests} if len(rests) == 1 else {}
    out = []
    for r in std:
        b = ref.get(key(r))
        if b is not None and b is not r:
            out.append(ratio(r, b, "Brazil"))
        c = rest.get(key(r))
        if c is not None and r["geography"] != "reference":
            out.append(ratio(r, c, "the region without the area"))
    rows.extend(out)


@functools.lru_cache(maxsize=32)
def _standard(population: str, edges: tuple | list, dataset: str, cells: int) -> tuple[np.ndarray | None, str]:
    """The standard population of a direct standardisation: Brazil's population of 2010 by sex and the field's age bands,
    from the field's own population source, as weights over the model's sex-age cells; (None, "") when that source has
    no 2010 or the cells do not match. Fixed across studies, periods and areas, so every standardised rate compares."""
    from . import monolith

    edges = list(edges)
    try:
        pop = gateway.population([2010], source=population if not population.startswith("events:") else None,
                                 dataset=dataset)
    except Exception:  # noqa: BLE001 - a source with no 2010: the caller falls back to the study's own, and says so
        return None, ""
    nB = len(edges)
    if 2 * nB != cells or pop.num_rows == 0:
        return None, ""
    g = (pop.column("sex").to_numpy().astype(int) - 1) * nB + monolith.age_band(pop.column("age").to_numpy(), edges)
    w = np.bincount(g, weights=pop.column("n").to_numpy().astype(float), minlength=cells)[:cells]
    if w.sum() <= 0:
        return None, ""
    return w / w.sum(), f"Brazil, 2010 ({population}), by sex and age band"


def _reference_cells(it: Item, s, f, d) -> list[tuple[str, np.ndarray, np.ndarray]]:
    """An area study's reference populations, Brazil and each macro-region the area lies in: their events of the field
    and person-years by year and sex-age cell ([T, G] each, the model's cells). The events are Brazil's `event_counts`
    (cached, shared by every area study and by the national totals an allocation share reads), each code cut to the
    block's width and kept when it is one of the field's leaves, as the model assembles its own; the person-years are
    the field's own population source. Nothing for a national study, a collapsed field, a monthly one, or one rated per
    other events."""
    import pyarrow.compute as pc

    from . import monolith

    area = config.study_area()
    years = np.asarray(d.years).astype(np.int64)
    if area is None or d.key.get("collapse") or years.max() > 9999 or str(d.population).startswith(("events:", "hybrid")):
        return []
    src = it.source or {}
    cols = fields.classifier_of(it.dataset, it.event, src, primary=False)
    U, T, G = d.N.shape
    nB = G // 2
    edges = list(gateway.age_edges(d.population, it.dataset, it.event))
    if G < 4 or len(edges) != nB:
        return []
    leaves = [str(c) for c in s.expectations.registry.leaves(f.node) if c in d.leaves]
    if not leaves and f.node != "*":
        return []
    width = max(len(str(c)) for c in d.leaves)
    subset = [str(x) for x in src.get("codes") or []]
    codes = tuple(subset) if it.extract else ()
    regions = sorted({int(str(int(a))[0]) for a in area})
    # Brazil, each macro-region the area lies in, and that region without the area: the comparison a paper makes (the
    # area against the rest of its region), which a total holding the area blurs (the paper audit, 2026-10-14)
    units = [("BR", None, False)] + [(f"{r} {REGIONS.get(r, '')}".strip(), r, False) for r in regions] + \
        [(f"{r} {REGIONS.get(r, '')} without the area".strip(), r, True) for r in regions]
    ev = {k: np.zeros((T, G)) for k, *_ in units}
    py = {k: np.zeros((T, G)) for k, *_ in units}
    for t, yr in enumerate(years):
        # a code list's events by each category they carry, as its field counts them (`gateway.code_list_counts`)
        c = (gateway.code_list_counts(it.dataset, it.event, int(yr), list(cols)).counts if isinstance(cols, tuple)
             else gateway.event_counts(it.dataset, it.event, int(yr), classifier=cols, codes=codes).counts)
        if subset:
            # the item's code set first, as the assembly cuts its block (`monolith._assemble`'s ``of_subset``): a code
            # set's field is its block's whole (node *), and Brazil's every death had been its reference (2026-10-14)
            hit = pc.starts_with(c.column("code"), subset[0])
            for x in subset[1:]:
                hit = pc.or_(hit, pc.starts_with(c.column("code"), x))
            c = c.filter(pc.fill_null(hit, False))
        if f.node != "*":
            c = c.filter(pc.fill_null(pc.is_in(pc.utf8_slice_codeunits(c.column("code"), 0, width),
                                               value_set=pa.array(leaves, pa.string())), False))
        u = c.column("u").to_numpy().astype(np.int64)
        cell = (c.column("sex").to_numpy().astype(np.int64) - 1) * nB + monolith.age_band(c.column("age").to_numpy(), edges)
        y = c.column("y").to_numpy().astype(float)
        for k, r, rest in units:
            m = np.ones(len(u), bool) if r is None else (u // 100000 == r)
            if rest:
                m &= ~config.in_area(u)
            ev[k][t] = np.bincount(cell[m], weights=y[m], minlength=G)[:G]
    pop = gateway.population([int(x) for x in years], source=str(d.population), dataset=it.dataset)
    u = pop.column("u").to_numpy().astype(np.int64)
    t_of = monolith.positions(years, pop.column("year").to_numpy())
    cell = (pop.column("sex").to_numpy().astype(np.int64) - 1) * nB + monolith.age_band(pop.column("age").to_numpy(), edges)
    n = pop.column("n").to_numpy().astype(float)
    ok = t_of >= 0
    for k, r, rest in units:
        m = ok & (np.ones(len(u), bool) if r is None else (u // 100000 == r))
        if rest:
            m &= ~config.in_area(u)
        py[k] = np.bincount(t_of[m] * G + cell[m], weights=n[m], minlength=T * G)[:T * G].reshape(T, G)
    return [(k, ev[k], py[k]) for k, *_ in units]


@functools.lru_cache(maxsize=256)
def _area_events(dataset: str, event: str, year: int, classifier: str | None, area) -> tuple[np.ndarray, np.ndarray]:
    """Every event of the type in the area (or Brazil) in ``year`` by code (codes, events): those the counts placed and
    those lost for the area's own reasons (not Brazil's blank residences), from `gateway.event_counts` (the read the
    model made). The denominator of a proportional share and of the ill-defined-cause share."""
    import pyarrow.compute as pc

    ec = gateway.event_counts(dataset, event, int(year), classifier=classifier, area=area)
    un = ec.unallocated.filter(pc.invert(pc.ends_with(ec.unallocated.column("reason"), " (Brazil)")))
    both = [ec.counts.select(["code", "y"]), un.select(["code", "y"])]
    code = np.array([str(x or "") for t_ in both for x in t_.column("code").to_pylist()], dtype=object)
    n = np.concatenate([x.column("y").to_numpy(zero_copy_only=False).astype(float) for x in both])
    return code, n


@functools.cache
def _icd_ancestors() -> dict[str, list[tuple[str, str]]]:
    """Each ICD-10 category's ancestors, nearest first, as (code, label): I21 -> (I20-I25, ischaemic heart diseases),
    (IX, the circulatory chapter). From the canonical tree (`gateway.code_tree`)."""
    rows = {r["code"]: r for r in gateway.code_tree("ICD10").to_pylist()}
    out = {}
    for code, r in rows.items():
        if r.get("level") != "category":
            continue
        chain, p = [], r.get("parent")
        while p and p in rows:
            chain.append((p, rows[p]["label"]))
            p = rows[p].get("parent")
        out[code] = chain
    return out


#: the measures an estimate can be, each defined once (estimates.parquet's ``measure``; the codebook prints them)
MEASURES = {
    "count": "events (or records) counted; no interval",
    "crude_rate": "events per `per` units of the denominator (`denominator_kind`), exact Poisson interval (Garwood) "
                  "with the denominator fixed",
    "standardised_rate": "directly age-sex-standardised rate per `per` person-years to `standard`, gamma interval (Fay & "
                         "Feuer 1997)",
    "rate_ratio": "a standardised rate over `comparator`'s of the same period and stratum, log-normal interval from "
                  "the two gamma variances",
    "smr": "observed over expected events at `comparator`'s rates (indirect standardisation), exact Poisson interval "
           "with the expectation fixed; p two-sided exact, q Benjamini-Hochberg over the municipalities",
    "proportion": "numerator over denominator, exact (Clopper-Pearson) interval",
    "case_fatality": "the topic's records whose outcome is death from the event (the codes pegasus_data declares fatal "
                     "on the outcome column, `variable`) over all its records, as the Ministry of Health's letalidade "
                     "and TabNet's in-hospital mortality define it; exact (Clopper-Pearson) interval; the records whose "
                     "outcome is not recorded in `note`",
    "case_fatality_adjusted": "a year's case fatality at the period's own case mix of age band and sex (marginal "
                              "standardisation of a binomial regression on year, age band and sex; interval from "
                              "2,000 draws of its coefficients)",
    "case_fatality_trend": "the odds of death from the event multiplied per year, adjusted for age band and sex "
                           "(binomial regression, Wald interval)",
    "mortality_after": "the persons dead of any cause within `variable`'s days of their first admission with the "
                       "topic's codes in the period, over those followed that long: a record linkage to the death "
                       "certificates (pegasus_data's cohort link), its false-match rate at that horizon and its verdict "
                       "in `model`, the deaths less the link's coincidences (its shifted-date control) in `note`; exact "
                       "interval, linkage error not in it",
    "expected": "events expected (`model`), no interval",
    "model_rate": "the hierarchical model's expected events per `per` person-years (tier B1)",
    "persons": "distinct persons among the events, by the source's registry identifier of its subject (the CNS): each "
               "once in a place and year, once over the period in the period's row (no interval)",
    "person_rate": "distinct persons in the year per `per` residents' person-years: the treated prevalence, exact "
                   "Poisson interval (Garwood) with the denominator fixed",
    "mean": "mean of the valid values", "sd": "standard deviation of the valid values",
    "quantile": "a quantile of the valid values (`value`: its probability)",
    "median": "the median of the records' values (a mark: a stay, an interval)",
    "seasonal_index": "a month's rate over the year's (a year's rows) or over the geometric mean of the twelve, each year "
                      "its own level (the period's rows: quasi-Poisson regression on year and month, days as offset)",
    "seasonality_f": "the twelve month effects' joint F statistic (p its p)",
    "uniformity_chi2": "Pearson's chi-square of a year's months against their days, 11 degrees of freedom (p its p)",
    "peak_day": "one harmonic's peak, day of the year (`note`: as a date), delta-method interval",
    "peak_to_trough": "one harmonic's peak-to-trough rate ratio, delta-method interval",
    "apc": "annual percent change: 100 (exp(b) - 1) of a log-linear slope (`model`; a joinpoint `segment`), t interval",
    "aapc": "average annual percent change over the series (joinpoint: the segments' slopes weighted by their lengths)",
    "fitted_rate": "a joinpoint model's fitted rate at a segment's end, in `unit` (`first` = `last` its year)",
    "dispersion": "the trend model's scale (Pearson dispersion, or the joinpoint's residual variance)",
    "joinpoints": "the number of joinpoints chosen (`p`: the permutation p of the last test; `note`: their years)",
    "lift": "the records with a code among those with the topic over those of the same sex and ten-year band without "
            "it (associated causes), with p and Benjamini-Hochberg q",
    "context": "a context's value in a municipality (`unit` over `denominator_kind`), the year it was read from in `note`",
    "association": "a field's standardised ratio multiplied per standard deviation of a context across the municipalities "
                   "(`note`: the SD), from the ecological regression (`model`: alone, or with the other contexts): "
                   "negative binomial, offset the events expected at the area's own age-sex rates, Wald interval "
                   "robust to clustering by health region; an association between places, never an individual effect",
    "smoothed_smr": "a municipality's standardised ratio (against the area's own age-sex rates) shrunk toward the area's by "
                    "empirical Bayes (Poisson-gamma, Marshall 1991): the posterior mean and its 95 % interval, what a map "
                    "of a rare event draws where a crude ratio of a small place is noise",
    "moran_global": "global Moran's I of the municipalities' smoothed standardised ratios over the period (row-standardised "
                    "contiguity; p one-sided from 999 permutations): whether neighbouring municipalities' ratios resemble "
                    "each other",
    "lisa": "a municipality's local Moran (LISA, Anselin 1995) of its smoothed standardised ratio: `value` its quadrant "
            "(high-high, low-low, high-low, low-high) where its p from 9,999 permutations passes the study's false-discovery level "
            "across the municipalities (q, Benjamini-Hochberg), else not significant; `estimate` the local I",
    "moran_i": "Moran's I of the ecological regression's Pearson residuals on the municipalities' contiguity (p: "
               "one-sided, 999 permutations): spatial dependence the model leaves",
}


def _period(year, period) -> dict:
    """An estimate's time, explicit: a year is first = last; a whole period its first and last year; never a null
    standing for "the whole" (the audit summed both, 2026-10-14)."""
    if year is not None and str(year) not in ("", "nan", "None"):
        y = int(year)
        return {"period_kind": "month" if y > 9999 else "year", "first": y, "last": y}
    if period:
        a, _, b = str(period).partition("-")
        return {"period_kind": "period", "first": int(a), "last": int(b or a)}
    return {"period_kind": None, "first": None, "last": None}


#: estimates.parquet's columns by type: a column holds one type whatever the producer (a municipality's code beside "BR"
#: in ``place`` had failed the table, 2026-10-14); the private ones (``_``) are the producers' and never written
ESTIMATE_TEXT = ("section", "measure", "field", "label", "dataset", "model", "segment", "variable", "variable_label",
                 "value", "value_label", "partial",
                 "interval", "denominator_kind", "unit", "geography", "place", "place_name", "state", "health_region",
                 "health_macroregion", "period_kind", "stratum", "comparator", "standard", "note")
ESTIMATE_NUMBER = ("estimate", "low", "high", "p", "q", "numerator", "denominator", "per", "variance")
ESTIMATE_INT = ("first", "last", "month")


#: study.duckdb's view of the rates as a paper's table reads them (and the report's): one row per field, place, stratum and
#: period, the count, the crude and the standardised rate with their intervals, the ratio to Brazil
RATES_VIEW = """SELECT field, label, dataset, geography, place, stratum, period_kind, first, last, denominator_kind,
        max(numerator) FILTER (WHERE measure = 'crude_rate') AS events,
        max(estimate) FILTER (WHERE measure = 'crude_rate') AS crude_rate,
        max(low) FILTER (WHERE measure = 'crude_rate') AS crude_low,
        max(high) FILTER (WHERE measure = 'crude_rate') AS crude_high,
        max(estimate) FILTER (WHERE measure = 'standardised_rate') AS standardised_rate,
        max(low) FILTER (WHERE measure = 'standardised_rate') AS standardised_low,
        max(high) FILTER (WHERE measure = 'standardised_rate') AS standardised_high,
        max(estimate) FILTER (WHERE measure = 'rate_ratio' AND comparator = 'Brazil') AS ratio_to_brazil,
        max(low) FILTER (WHERE measure = 'rate_ratio' AND comparator = 'Brazil') AS ratio_to_brazil_low,
        max(high) FILTER (WHERE measure = 'rate_ratio' AND comparator = 'Brazil') AS ratio_to_brazil_high,
        max(denominator) FILTER (WHERE measure = 'crude_rate') AS denominator,
        max(unit) FILTER (WHERE measure = 'crude_rate') AS unit
    FROM estimates WHERE section = 'rates' AND measure IN ('crude_rate', 'standardised_rate', 'rate_ratio')
    GROUP BY ALL"""
#: and of the municipalities: rates, the standardised ratios against Brazil and the area, the model's rate
MUNICIPALITIES_VIEW = """SELECT field, label, dataset, place AS u, place_name AS municipality, state, health_region,
        health_macroregion, period_kind, first, last,
        max(estimate) FILTER (WHERE measure = 'count') AS events,
        max(estimate) FILTER (WHERE measure = 'crude_rate') AS crude_rate,
        max(low) FILTER (WHERE measure = 'crude_rate') AS crude_low,
        max(high) FILTER (WHERE measure = 'crude_rate') AS crude_high,
        max(estimate) FILTER (WHERE measure = 'smr' AND comparator LIKE 'Brazil%') AS smr_brazil,
        max(low) FILTER (WHERE measure = 'smr' AND comparator LIKE 'Brazil%') AS smr_brazil_low,
        max(high) FILTER (WHERE measure = 'smr' AND comparator LIKE 'Brazil%') AS smr_brazil_high,
        max(q) FILTER (WHERE measure = 'smr' AND comparator LIKE 'Brazil%') AS smr_brazil_q,
        max(estimate) FILTER (WHERE measure = 'smr' AND comparator LIKE 'the area%') AS smr_area,
        max(low) FILTER (WHERE measure = 'smr' AND comparator LIKE 'the area%') AS smr_area_low,
        max(high) FILTER (WHERE measure = 'smr' AND comparator LIKE 'the area%') AS smr_area_high,
        max(q) FILTER (WHERE measure = 'smr' AND comparator LIKE 'the area%') AS smr_area_q,
        max(estimate) FILTER (WHERE measure = 'smoothed_smr') AS smoothed_smr,
        max(value) FILTER (WHERE measure = 'lisa') AS lisa_cluster,
        max(low) FILTER (WHERE measure = 'smoothed_smr') AS smoothed_smr_low,
        max(high) FILTER (WHERE measure = 'smoothed_smr') AS smoothed_smr_high,
        max(estimate) FILTER (WHERE measure = 'model_rate') AS model_rate
    FROM estimates WHERE section = 'municipalities' GROUP BY ALL"""


def _estimates_table(rows: list[dict]) -> pa.Table:
    """estimates.parquet: every column of the schema, typed, whatever the producers emitted (a folder without ratios had
    no ``comparator``, and its views' SQL failed, 2026-10-14); a row's private keys (``_``) never written."""
    cols = [*ESTIMATE_TEXT, *ESTIMATE_NUMBER, *ESTIMATE_INT, "provisional"]
    types = {**{c: pa.string() for c in ESTIMATE_TEXT}, **{c: pa.float64() for c in ESTIMATE_NUMBER},
             **{c: pa.int64() for c in ESTIMATE_INT}, "provisional": pa.bool_()}
    # each row its id, so a paper's number cites its row (the audits numbered them themselves)
    return pa.table({"id": pa.array(range(1, len(rows) + 1), pa.int64()),
                     **{c: pa.array([r.get(c) for r in rows], types[c]) for c in cols}})


def _estimate_row(section: str, measure: str, base: dict, **row) -> dict:
    """One estimate row, typed and refused when incomplete: a measure of the vocabulary; an interval names its method; a
    rate names its denominator and scale; every column of its one type (`ESTIMATE_TEXT`, `ESTIMATE_NUMBER`,
    `ESTIMATE_INT`), an unknown one refused."""
    if measure not in MEASURES:
        raise ValueError(f"estimate: no measure {measure!r}")
    out = {"section": section, "measure": measure, **base, **row}
    if (out.get("low") is not None or out.get("high") is not None) and not out.get("interval"):
        raise ValueError(f"estimate {section}/{measure}: an interval without its method")
    if measure in ("crude_rate", "standardised_rate", "model_rate") and not (out.get("denominator_kind") and out.get("per")):
        raise ValueError(f"estimate {section}/{measure}: a rate without its denominator or scale")
    for k, v in out.items():
        if v is None or k.startswith("_") or k == "provisional":
            continue
        if k in ESTIMATE_TEXT:
            out[k] = str(v)
        elif k in ESTIMATE_NUMBER:
            out[k] = float(v)
        elif k in ESTIMATE_INT:
            out[k] = int(v)
        else:
            raise ValueError(f"estimate {section}/{measure}: no column {k!r}")
    return out


def _mark_years(rows: list[dict], it: Item, partial: dict) -> None:
    """A year's estimates marked as the source says of the year: ``provisional``, not final yet (pegasus_data's
    ``final_after_years``: SINAN's notifications are closed over three years; RS's 2023 congenital records had no
    closing date, the review, 2026-10-13), and ``partial``, a part of a year (`_partial_years`). No trend reads either."""
    final = ((gateway.event_type(it.dataset, it.event) or {}).get("source_notes") or {}).get("final_after_years")
    for r in rows:
        if r["period_kind"] != "year":
            continue
        if final:
            r["provisional"] = int(r["first"]) > int(time.strftime("%Y")) - int(final)
        if why := partial.get((it.dataset, r["first"])):
            r["partial"] = why


def _partial_years(files: pa.Table | None) -> dict[tuple[str, int], str]:
    """(dataset, year) -> why the year is a part of one: a source published by month (its files have a competence)
    whose year the lake holds fewer than twelve months of. A year's rate would compare a part with wholes."""
    out: dict[tuple[str, int], str] = {}
    if files is None or not files.num_rows:
        return out
    t = files.select(["dataset", "year", "competence", "in_lake"]).to_pylist()
    monthly = {r["dataset"] for r in t if r["competence"]}
    held: dict[tuple[str, int], set] = {}
    for r in t:
        if r["dataset"] in monthly and r["in_lake"] and r["competence"]:
            held.setdefault((r["dataset"], int(r["year"])), set()).add(str(r["competence"]))
    for (ds, y), months in held.items():
        if len(months) < 12:
            out[(ds, y)] = f"{len(months)} of 12 months published and held ({min(months)}-{max(months)})"
    return out


def _publications(scope: Scope, log) -> pa.Table | None:
    """Every published file the study's sources were read from (pegasus_data `publications`: the server path, state,
    year and competence, the size and date the server listed, the digest and rows of the bytes decoded, when and from
    where they were fetched, and the source's own status, preliminary or final), and every file listed for those years
    the lake does not hold, with why: what a methods section cites and a reader re-checks against the server (the
    audit could check nothing, 2026-10-14). Every state's files of an area study: a record is filed by its place of
    care, so a resident cared for elsewhere is in another state's file."""
    import pegasus_data as pg

    years: dict[str, set[int]] = {}
    for it in (i for i in scope.items if i.status == "in" and i.years):
        years.setdefault(it.dataset, set()).update(int(y) for y in it.years)
    parts = []
    for ds, ys in years.items():
        try:
            t = pg.publications(ds, sorted(ys), root=config.data_root())
        except Exception as exc:  # noqa: BLE001 - a source whose files cannot be listed: said, the others written
            log(f"study: sources {ds}: {type(exc).__name__}: {exc}")
            continue
        parts.append(t)
    return pa.concat_tables(parts, promote_options="permissive") if parts else None


def _population_text(population: str) -> str | None:
    """What the population series is, as the documents that produce it say (pegasus_data `curation/populations.yml`):
    producer, vintage, reference date, years, method, limitations and the documents."""
    from pegasus_data.sources.ibge import series_documentation

    doc = series_documentation(str(population).split("+")[0].split(":")[0])
    if not doc:
        return None

    def flat(v) -> str:
        return "; ".join(" ".join(str(x).split()) for x in v) if isinstance(v, (list, tuple)) else " ".join(str(v).split())
    parts = [f"{k.replace('_', ' ')}: {flat(doc[k])}" for k in ("producer", "vintage", "reference_date", "years", "method",
                                                                "limitations", "documents") if doc.get(k)]
    return f"The population ({doc.get('title') or population}). " + ". ".join(parts) + "."


def _codes(it: Item, f, label: str) -> list[dict]:
    """A code set's events in the area by each code it holds, labelled (pegasus_data's codelist of the column), per year
    and over the period: every category (three characters: I21, I22) and every code as the source records it (I21.0 to
    I21.9), each with its share of the topic's events and its exact interval. Every event counted, placed or not, as the
    proportional measures. A paper splits acute myocardial infarction by subtype and gives the share unspecified (I21.9);
    the folder had the topic as one count (the audit, 2026-10-14)."""
    import pegasus_data as pg

    src = it.source or {}
    codes = [str(c).upper() for c in src.get("codes") or []]
    if not codes or src.get("source") or it.count_only:
        return []
    et = gateway.event_type(it.dataset, it.event) or {}
    classifier = src.get("classifier") or next((c["column"] for c in et.get("classifiers") or []
                                                if c.get("role") == "primary"), None)
    area = tuple(sorted(config.study_area())) if config.study_area() else None
    level, unit = _whole()
    per_year: dict[int, dict[str, float]] = {}
    for y in it.years:
        try:
            code, n = _area_events(it.dataset, it.event, int(y), classifier, area)
        except Exception:  # noqa: BLE001 - a year that cannot be counted has no rows (the rates say why)
            continue
        acc: dict[str, float] = {}
        for c, k in zip(code, n, strict=True):
            c = str(c).upper()
            if any(c.startswith(x) for x in codes):
                for key in dict.fromkeys([c[:3], c]):
                    acc[key] = acc.get(key, 0.0) + float(k)
        per_year[int(y)] = acc
    years = sorted(per_year)
    if not years:
        return []
    every = sorted({c for v in per_year.values() for c in v})
    try:
        labels = pg.levels(it.dataset, classifier, every, root=config.data_root())
    except Exception:  # noqa: BLE001 - codes without labels are given as codes, said by the empty label
        labels = {}
    out = []
    for y in [*years, None]:
        acc = per_year[y] if y is not None else {c: sum(per_year[z].get(c, 0.0) for z in years) for c in every}
        total = sum(v for c, v in acc.items() if len(c) == 3)
        for c in every:
            k = acc.get(c, 0.0)
            base = {"field": f.id, "label": label, "dataset": it.dataset, "geography": level, "place": unit,
                    "variable": classifier, "value": c, "value_label": labels.get(c),
                    "note": "category" if len(c) == 3 else "code",
                    **_period(y, None if y is not None else f"{years[0]}-{years[-1]}")}
            pr = _proportion(k, total)
            out += [_estimate_row("codes", "count", base, estimate=k),
                    _estimate_row("codes", "proportion", base, estimate=pr["proportion"], low=pr["proportion_low"],
                                  high=pr["proportion_high"], interval="Clopper-Pearson", numerator=k,
                                  denominator=total, denominator_kind="the topic's events (its categories)")]
    return out


def _proportional(it: Item, f, label: str) -> list[dict]:
    """A code set's share of the events it belongs among (proportional mortality, morbidity): of each ICD-10 ancestor
    of its codes (I21-I22: the ischaemic heart diseases, chapter IX) and of all the source's events, in the area, each
    year and over the period, with its exact (Clopper-Pearson) interval. Every event counted, placed or not (a share is
    no rate: no denominator of persons). A paper states "acute myocardial infarction caused N % of deaths"; the folder
    had no such row (2026-10-14)."""
    src = it.source or {}
    codes = [str(c) for c in src.get("codes") or []]
    et = gateway.event_type(it.dataset, it.event) or {}
    classifier = src.get("classifier") or next((c["column"] for c in et.get("classifiers") or []
                                                if c.get("role") == "primary"), None)
    structure = next((c.get("structure") for c in et.get("classifiers") or [] if c.get("column") == classifier), None)
    if not codes or src.get("source") or it.count_only or structure != "ICD10":
        return []
    anc = _icd_ancestors()
    mine = {a for c in codes for a in anc.get(c[:3], [])}
    if any(len(c) < 3 for c in codes):
        return []
    area = tuple(sorted(config.study_area())) if config.study_area() else None
    level, unit = _whole()
    per_year: dict[int, dict[str, tuple[float, float]]] = {}
    for y in it.years:
        try:
            code, n = _area_events(it.dataset, it.event, int(y), classifier, area)
        except Exception:  # noqa: BLE001 - a year that cannot be counted has no share (the rates say why)
            continue
        cat = np.array([c[:3] for c in code], dtype=object)
        topic = np.zeros(len(code), bool)
        for c in codes:
            topic |= np.array([x.startswith(c) for x in code], dtype=bool)
        k = float(n[topic].sum())
        shares = {"all the source's events": (k, float(n.sum()))}
        for a, a_label in sorted(mine):
            inside = np.array([any(x == a for x, _ in anc.get(c, [])) for c in cat], dtype=bool)
            shares[f"{a_label} ({a})"] = (k, float(n[inside].sum()))
        per_year[int(y)] = shares
    out = []
    years = sorted(per_year)
    for y in [*years, None]:
        for name in (per_year[years[0]] if years else {}):
            k, tot = (per_year[y][name] if y is not None else
                      tuple(sum(per_year[z][name][i] for z in years) for i in range(2)))
            if tot <= 0:
                continue
            pr = _proportion(k, tot)
            out.append(_estimate_row("rates", "proportion", {"field": f.id, "label": label, "dataset": it.dataset,
                                                             "geography": level, "place": unit, **_period(
                                                                 y, None if y is not None else f"{years[0]}-{years[-1]}")},
                                     estimate=pr["proportion"], low=pr["proportion_low"], high=pr["proportion_high"],
                                     interval="Clopper-Pearson", numerator=k, denominator=tot, denominator_kind=name))
    return out


def _measures(it: Item, f, label: str, log) -> list[dict]:
    """Every measure and interval the source declares, on the field's own events in the area (`gateway.mark_values`,
    one filtered scan a year): per year and over the period, the events, those with a valid value, those not recorded
    (a declared missing code) and those out of the declared domain, and the mean, standard deviation, quartiles and 90th
    percentile of the valid values; an interval in days from the event's own date (plus one: a same-day date is 1).
    A measure the models do not read (an administrative fact: a value paid) is described all the same: a paper reports
    the length of stay and the cost of the topic's admissions, which the folder did not hold (2026-10-14)."""
    from . import fields as fields_

    src = it.source or {}
    codes = fields_.codes_of(src, it.nodes)
    if src.get("source") not in (None, "code_list") or it.count_only or (not codes and config.study_area() is None):
        return []           # a linked share or a second coding; a whole type nationally is described by its readers
    et = gateway.event_type(it.dataset, it.event) or {}
    if et.get("weight") or et.get("grid"):
        return []
    classifier = fields_.classifier_of(it.dataset, it.event, src)
    specs = []
    for d in fields_.declared(it.dataset):
        if d.kind == "measure":
            lo, hi = d.domain if d.domain else (0.0, float("inf"))
            specs.append({"measure": d.column, "measure_name": d.name, "kind": "measure", "anchor": None,
                          "lo": lo, "hi": hi, "missing": [str(x) for x in d.missing]})
        elif d.kind == "interval" and not d.reason:
            try:
                iv = fields_.interval_source(it.dataset, it.event, d.column, int(it.years[-1]))
            except (ValueError, LookupError):
                continue
            specs.append({"measure": iv["mark"], "measure_name": f"days from {iv['anchor']} to {d.name}",
                          "kind": "interval", "anchor": iv["anchor"], "sign": iv.get("sign", 1), "lo": 1.0,
                          "hi": float("inf"), "missing": []})
    area = tuple(sorted(config.study_area())) if config.study_area() else None
    if not specs:
        return _ages(it, f, label, classifier, area) + _case_fatality(it, f, label, classifier, area, log)
    columns = tuple(dict.fromkeys(c for sp in specs for c in (sp["measure"], sp["anchor"]) if c))
    vals: dict[tuple[str, int], np.ndarray] = {}
    counts: dict[tuple[str, int], tuple[int, int, int]] = {}
    import duckdb

    for y in it.years:
        try:
            t = gateway.mark_values(it.dataset, it.event, int(y), columns, classifier, codes, area)
        except Exception as exc:  # noqa: BLE001 - a year that cannot be read is said, the others described
            log(f"study: measures {it.dataset} {y}: {type(exc).__name__}: {exc}")
            continue
        con = duckdb.connect()
        con.register("r", t)
        for sp in specs:
            if sp["measure"] not in t.column_names or (sp["anchor"] and sp["anchor"] not in t.column_names):
                continue
            raw = f'trim(CAST("{sp["measure"]}" AS VARCHAR))'
            # a decimal comma read as a decimal point ("12,5": TRY_CAST had made it outside the domain)
            value = (f"CAST({int(sp['sign'])} * date_diff('day', {gateway._date_sql(sp['anchor'])}, "
                     f"{gateway._date_sql(sp['measure'])}) + 1 AS DOUBLE)" if sp["anchor"]
                     else f"TRY_CAST(replace({raw}, ',', '.') AS DOUBLE)")
            # a declared missing code, and a blank, are not recorded (a blank had counted as outside the domain, the
            # SINASC audit's measures, 2026-10-14); a value IN an empty list is never true, so no code, no clause
            miss = ", ".join("'" + m.replace("'", "''") + "'" for m in sp["missing"])
            is_miss = f"({raw} IS NULL OR {raw} = ''" + (f" OR {raw} IN ({miss})" if miss else "") + ")"
            r = con.execute(f"""SELECT count(*) AS events, count(*) FILTER (WHERE {is_miss}) AS not_recorded,
                    list(m) FILTER (WHERE m IS NOT NULL AND NOT ({is_miss}) AND m >= {sp['lo']}
                                    AND m <= {sp['hi'] if sp['hi'] != float('inf') else 1e300}) AS v
                FROM (SELECT {raw} AS mraw_, {value} AS m, * FROM r)""").fetchone()
            v = np.asarray(r[2] or [], dtype=float)
            vals[(sp["measure"], int(y))] = v
            counts[(sp["measure"], int(y))] = (int(r[0]), int(r[1]), int(r[0]) - int(r[1]) - len(v))
        con.close()
    out = _ages(it, f, label, classifier, area) + _case_fatality(it, f, label, classifier, area, log)
    period = f"{min(it.years)}-{max(it.years)}"
    for sp in specs:
        years = sorted(y for (m, y) in vals if m == sp["measure"])
        for y in [*years, None]:
            v = vals[(sp["measure"], y)] if y is not None else np.concatenate([vals[(sp["measure"], z)] for z in years]) \
                if years else np.array([])
            ev, nr, ob = counts[(sp["measure"], y)] if y is not None else tuple(
                sum(counts[(sp["measure"], z)][k] for z in years) for k in range(3))
            if not ev:
                continue
            q = np.percentile(v, [25, 50, 75, 90]) if len(v) else [None] * 4
            out += _measure_rows({"field": f.id, "label": label, "dataset": it.dataset, "variable": sp["measure"],
                                  "variable_label": sp["measure_name"], **_period(y, None if y is not None else period)},
                                 sp["kind"], len(v), nr, ob, float(v.mean()) if len(v) else None,
                                 float(v.std(ddof=1)) if len(v) > 1 else None, q, _median_ci(v))
    return out


def _measure_rows(base: dict, kind: str, n: float, not_recorded: float | None, out_of_domain: float | None,
                  mean: float | None, sd: float | None, q: list, median_ci: tuple | None = None) -> list[dict]:
    """A measure's description as estimates: its valid, not-recorded and out-of-domain counts, mean (with its t
    interval), sd and quantiles (the median with its order-statistic interval, ``median_ci``)."""
    from scipy.stats import t as student

    base = {**base, "geography": _whole()[0], "unit": {"interval": "days", "age": "years"}.get(kind)}
    out = []
    for what, k in (("valid", n), ("not recorded", not_recorded), ("outside the domain", out_of_domain)):
        if k is not None:
            out.append(_estimate_row("measures", "count", {**base, "value": what}, estimate=float(k)))
    for meas, x, val in (("mean", mean, None), ("sd", sd, None), *(("quantile", v, p) for v, p in
                                                                   zip(q, ("0.25", "0.5", "0.75", "0.9"), strict=True))):
        if x is None:
            continue
        ci = {}
        if meas == "mean" and sd is not None and n > 1:
            h = float(student.ppf(0.975, n - 1)) * sd / np.sqrt(n)
            ci = {"low": x - h, "high": x + h, "interval": "t on the valid values"}
        elif val == "0.5" and median_ci is not None:
            ci = {"low": median_ci[0], "high": median_ci[1], "interval": "exact order statistics (binomial)"}
        out.append(_estimate_row("measures", meas, {**base, **({"value": val} if val else {})}, estimate=float(x), **ci))
    return out


def _median_ci(v: np.ndarray) -> tuple[float, float] | None:
    """The median's exact distribution-free 95 % interval: the order statistics the binomial(n, 1/2) brackets."""
    from scipy.stats import binom

    n = len(v)
    if n < 6:
        return None
    a = np.sort(v)
    lo = int(binom.ppf(0.025, n, 0.5))
    hi = int(binom.isf(0.025, n, 0.5))
    return float(a[max(lo - 1, 0)]), float(a[min(hi, n - 1)])


#: the case fatalities a run has written, by (dataset, event read, codes, area, years): a notification's and its confirmed
#: cases' items read the same cases, written once
_CASE_FATALITY_DONE: set = set()


def _case_fatality(it: Item, f, label: str, classifier: str | None, area, log) -> list[dict]:
    """The topic's case fatality from its own records' outcome: every column whose role pegasus_data declares ``fatal``
    codes for (SIH's death flag, SINAN's evolution: the codes of death from the event; ``fatal_other`` those of death
    from another cause) read on the field's events in the area (`gateway.mark_values`), with their age and sex. Per
    year and over the period: deaths from the event over all records (the Ministry of Health's letalidade, TabNet's
    in-hospital mortality), by sex and by age band, with exact intervals; the share dead of other causes; the records
    not recorded said. Then adjusted: a binomial regression of death on year, age band and sex (bands merged upward
    until each holds a death and a survivor, the partition from the data), each year's case fatality at the period's
    case mix (marginal standardisation, interval from 2,000 coefficient draws), and the adjusted odds ratio per year.
    A paper on admissions or notifications reports how many died; the folder had held it only as one value of a case
    mix's column, unadjusted (2026-10-14). Its denominator is the cases: a notification's case fatality is read on
    the source's confirmed cases (the event whose status confirms one), every leptospirosis death being a confirmed
    case's (11 % of them, against 2 % of the notifications, pegasus_data 2026-10-14); a run writes each once."""
    import duckdb
    import pandas as pd
    import statsmodels.api as sm
    from scipy.stats import beta

    cols = [r for r in gateway.roles(it.dataset) if r.get("fatal")]
    if not cols:
        return []
    event = it.event
    if not (gateway.event_type(it.dataset, event) or {}).get("status"):
        confirmed = [e["name"] for e in gateway.event_types(it.dataset) if e.get("status") and e.get("kind") == "case"]
        event = confirmed[0] if confirmed else event
    on = "" if event == it.event else f", on the {event}s (confirmed) of its notifications"
    key = (it.dataset, event, tuple(sorted(fields.codes_of(it.source or {}, it.nodes))), area, tuple(it.years))
    if key in _CASE_FATALITY_DONE:
        return []
    _CASE_FATALITY_DONE.add(key)
    out = []
    period = f"{min(it.years)}-{max(it.years)}"
    edges = [int(x) for x in gateway.age_edges(dataset=it.dataset, event=it.event)]
    bands = _band_labels(edges)
    codes = fields.codes_of(it.source or {}, it.nodes)

    def cp(k: float, n: float) -> tuple[float, float]:
        return (float(beta.ppf(0.025, k, n - k + 1)) if k > 0 else 0.0,
                float(beta.ppf(0.975, k + 1, n - k)) if k < n else 1.0)

    def inlist(raw: str, vals: list[str]) -> str:
        return "(" + raw + " IN (" + ", ".join("'" + v.replace("'", "''") + "'" for v in vals) + "))" if vals else "FALSE"
    for role in cols:
        col = role["column"]
        fatal, other = [str(c) for c in role["fatal"]], [str(c) for c in role.get("fatal_other") or []]
        missing = [str(c) for c in role.get("missing") or []]
        frames = []
        for y in it.years:
            try:
                strata = gateway._strata(it.dataset, event, int(y))
                use = tuple(c for c in (col, strata.get("age"), strata.get("sex")) if c)
                t = gateway.mark_values(it.dataset, event, int(y), use, classifier if codes else None, codes, area)
            except Exception as exc:  # noqa: BLE001 - a year that cannot be read is said, the others described
                log(f"study: case fatality {it.dataset} {col} {y}: {type(exc).__name__}: {exc}")
                continue
            if col not in t.column_names:
                continue
            raw = 'trim(CAST("' + col + '" AS VARCHAR))'
            age = "NULL"
            if strata.get("age") and strata["age"] in t.column_names:
                x = 'trim(CAST("' + strata["age"] + '" AS VARCHAR))'
                am = [str(c) for c in strata.get("age_missing") or ()]
                age = (f"CASE WHEN {inlist(x, am)} THEN NULL ELSE floor(TRY_CAST({x} AS DOUBLE)) END" if am
                       else f"floor(TRY_CAST({x} AS DOUBLE))")
            sex = gateway._sex_sql(strata, it.dataset, t) if strata.get("sex") in t.column_names else "NULL"
            con = duckdb.connect()
            con.register("r", t)
            frames.append(con.execute(f"""SELECT {int(y)} AS year,
                    CASE WHEN {inlist(raw, fatal)} THEN 1 WHEN {inlist(raw, other)} THEN 2
                         WHEN {raw} IS NULL OR {raw} = '' OR {inlist(raw, missing)} THEN 9 ELSE 0 END AS o,
                    {age} AS age, {sex} AS sex FROM r""").df())
            con.close()
        if not frames:
            continue
        d = pd.concat(frames, ignore_index=True)
        d["band"] = np.searchsorted(edges, d["age"].astype(float).fillna(-1).to_numpy(), side="right") - 1
        base = {"field": f.id, "label": label, "dataset": it.dataset, "variable": col,
                "variable_label": (role.get("name") or col) + on, "geography": _whole()[0], "place": _whole()[1]}

        def crude(sel, extra: dict, y, d=d, base=base, other=other) -> None:
            g = d[sel]
            n, k, k2, nr = len(g), int((g["o"] == 1).sum()), int((g["o"] == 2).sum()), int((g["o"] == 9).sum())
            if n == 0:
                return
            row = {**base, **extra, **_period(y, None if y is not None else period),
                   "note": f"{nr} of {n} records with the outcome not recorded" if nr else None}
            lo, hi = cp(k, n)
            out.append(_estimate_row("case fatality", "case_fatality", {**row, "value_label": "death from the event"},
                                     estimate=k / n, low=lo, high=hi, interval="Clopper-Pearson", numerator=k,
                                     denominator=n, denominator_kind="records", unit="proportion"))
            if other:
                lo, hi = cp(k2, n)
                out.append(_estimate_row("case fatality", "proportion", {**row, "value_label": "death from another cause"},
                                         estimate=k2 / n, low=lo, high=hi, interval="Clopper-Pearson", numerator=k2,
                                         denominator=n, denominator_kind="records", unit="proportion"))
        for y in [*sorted(d["year"].unique()), None]:
            sel = d["year"] == y if y is not None else pd.Series(True, index=d.index)
            crude(sel, {}, None if y is None else int(y))
            if y is None:
                for sx, nm in ((1, "male"), (2, "female")):
                    crude(sel & (d["sex"] == sx), {"stratum": f"sex: {nm}"}, None)
                for b in sorted(d.loc[d["band"] >= 0, "band"].unique()):
                    crude(sel & (d["band"] == b), {"stratum": f"age band: {bands[int(b)]}"}, None)
        # adjusted: the records with an outcome, an age and a sex; bands merged upward until each has both outcomes
        m = d[(d["o"] != 9) & (d["band"] >= 0) & d["sex"].isin([1, 2])].copy()
        m["dead"] = (m["o"] == 1).astype(float)
        years_ = sorted(int(v) for v in m["year"].unique())
        if len(years_) < 2 or m["dead"].sum() < 10:
            continue
        merged: dict[int, int] = {}
        cur: list[int] = []
        for b in sorted(int(v) for v in m["band"].unique()):
            cur.append(b)
            g = m[m["band"].isin(cur)]
            if 0 < g["dead"].sum() < len(g):
                merged.update(dict.fromkeys(cur, cur[0]))
                cur = []
        last = max(merged.values()) if merged else (cur[0] if cur else 0)
        merged.update(dict.fromkeys(cur, last))        # the oldest bands without both outcomes join the last group
        m["grp"] = m["band"].map(merged)
        groups = sorted(m["grp"].unique())
        cells = m.groupby(["year", "grp", "sex"]).agg(n=("dead", "size"), k=("dead", "sum")).reset_index()

        def design(c, trend: bool, years_=years_, groups=groups) -> np.ndarray:
            parts = [np.ones(len(c))]
            parts += ([c["year"].to_numpy(float) - years_[0]] if trend
                      else [(c["year"] == yy).to_numpy(float) for yy in years_[1:]])
            parts += [(c["grp"] == gg).to_numpy(float) for gg in groups[1:]]
            parts.append((c["sex"] == 2).to_numpy(float))
            return np.column_stack(parts)
        try:
            y2 = np.column_stack([cells["k"], cells["n"] - cells["k"]]).astype(float)
            fit = sm.GLM(y2, design(cells, False), family=sm.families.Binomial()).fit()
            trend = sm.GLM(y2, design(cells, True), family=sm.families.Binomial()).fit()
        except Exception as exc:  # noqa: BLE001 - an unfittable adjustment is said; the crude rows stand
            log(f"study: case fatality {it.dataset} {col}: adjustment: {type(exc).__name__}: {exc}")
            continue
        mix = m.groupby(["grp", "sex"]).size().reset_index(name="w")
        w = (mix["w"] / mix["w"].sum()).to_numpy()
        rng = np.random.default_rng(config.seed(f.id, col, "case fatality"))
        draws = rng.multivariate_normal(np.asarray(fit.params), np.asarray(fit.cov_params()), size=2000)
        note = (f"{len(m)} records with an outcome, an age and a sex; age bands merged to {len(groups)} groups; "
                "standard: the period's case mix")
        model = "binomial regression on year, age band and sex; marginal standardisation"
        for yy in years_:
            X = design(mix.assign(year=yy), False)
            p_hat = float((w / (1 + np.exp(-X @ np.asarray(fit.params)))).sum())
            sims = (w[None] / (1 + np.exp(-draws @ X.T))).sum(1)
            out.append(_estimate_row("case fatality", "case_fatality_adjusted",
                                     {**base, **_period(yy, None), "value_label": "death from the event", "note": note},
                                     estimate=p_hat, low=float(np.percentile(sims, 2.5)),
                                     high=float(np.percentile(sims, 97.5)), interval="2,000 coefficient draws",
                                     unit="proportion", model=model))
        b, se = float(trend.params[1]), float(trend.bse[1])
        out.append(_estimate_row("case fatality", "case_fatality_trend",
                                 {**base, **_period(None, period), "value_label": "death from the event", "note": note},
                                 estimate=float(np.exp(b)), low=float(np.exp(b - 1.96 * se)),
                                 high=float(np.exp(b + 1.96 * se)), p=float(trend.pvalues[1]), interval="Wald",
                                 unit="odds ratio per year", model="binomial regression on year (linear), age band "
                                 "and sex"))
    return out


#: the follow-up horizons a study reports, in days after the first admission
FOLLOWUP_DAYS = (30, 365)


def _followup(it: Item, f, label: str, log) -> list[dict]:
    """Mortality after the first admission with the topic's codes (`FOLLOWUP_DAYS`), from pegasus_data's cohort link
    (`linked_deaths`: each person's first admission of the period to a death certificate of any cause, its false-match
    rate and verdict by horizon). Over the period and by the year of the first admission, the persons dead within the
    horizon over those followed that long, with exact intervals; a horizon whose link is not viable is said, never
    estimated. The area's states' files are read (SIH's are cut by the hospital's state) and the area's residents
    kept: a resident admitted in another state is not followed, which the note says."""
    import pegasus_data as pg
    import pyarrow.compute as pc
    from pegasus_data.linkage.followup import cohort_link
    from scipy.stats import beta

    src = it.source or {}
    codes = list(fields.codes_of(src, it.nodes))
    if not codes or it.count_only or src.get("population") or src.get("support"):
        return []
    ds = gateway.data_code(it.dataset)
    try:
        cohort_link(ds)                  # the source has a declared cohort link, or no follow-up
    except LookupError:
        return []
    area = config.study_area()
    states = sorted({int(u) if int(u) < 100 else int(u) // 10000 for u in area}) if area else None
    strata = gateway._strata(it.dataset, gateway.split_event(it.event)[0])
    residence = next((r["role"] for r in gateway.roles(it.dataset) if r["column"] == strata.get("residence")), None)
    try:
        fu = pg.linked_deaths(ds, codes, years=list(it.years), geography=[str(x) for x in states] if states else "BR",
                              match="any" if src.get("source") == "code_list" else "principal",
                              roles=[residence] if residence else [], root=config.data_root())
    except Exception as exc:  # noqa: BLE001 - a follow-up that cannot be linked is said; the case fatality stands
        log(f"study: follow-up {it.dataset} {codes}: {type(exc).__name__}: {exc}")
        return []
    t = fu.table
    keep = None
    if area and residence and residence in t.column_names:
        u = pc.cast(pc.utf8_slice_codeunits(pc.cast(t.column(residence), pa.string()), 0, 6), pa.int64())
        keep = pa.array(config.in_area(np.nan_to_num(u.to_numpy(zero_copy_only=False).astype(float), nan=0)
                                       .astype(np.int64)))
    origin_year = pc.year(t.column("origin")).to_numpy(zero_copy_only=False)
    period = f"{min(it.years)}-{max(it.years)}"
    q = fu.quality
    base = {"field": f.id, "label": label, "dataset": it.dataset, "geography": _whole()[0], "place": _whole()[1],
            "value_label": "death of any cause", "denominator_kind": "persons followed",
            "unit": "proportion"}
    out = []
    for d in FOLLOWUP_DAYS:
        try:
            flags = fu.died_within(d)
        except Exception as exc:  # noqa: BLE001 - a horizon the link does not support (not viable, past its window)
            log(f"study: follow-up {it.dataset} {d} days: {type(exc).__name__}: {exc}")
            continue
        h = fu.horizon(d)
        died = pc.fill_null(flags, False).to_numpy(zero_copy_only=False)
        followed = pc.is_valid(flags).to_numpy(zero_copy_only=False)
        if keep is not None:
            mine = keep.to_numpy(zero_copy_only=False)
            died, followed = died & mine, followed & mine
        whole = fu.mortality(d)
        share_false = (whole["died"] - whole["died_corrected"]) / whole["died"] \
            if whole.get("died_corrected") is not None and whole["died"] else None
        model = (f"record linkage to the death certificates ({q['link']}); false-match rate at {h['days']} days "
                 f"{h['chance_percent']} %; verdict {h['verdict']}")
        for y in [*sorted({int(v) for v in origin_year[followed]} & {int(x) for x in it.years}), None]:
            sel = followed if y is None else followed & (origin_year == y)
            n, k = int(sel.sum()), int((died & sel).sum())
            if not n:
                continue
            lo = float(beta.ppf(0.025, k, n - k + 1)) if k > 0 else 0.0
            hi = float(beta.ppf(0.975, k + 1, n - k)) if k < n else 1.0
            note = (f"{k * (1 - share_false):.0f} deaths less the link's coincidences ({k * (1 - share_false) / n:.1%})"
                    if share_false is not None else None)
            if area and y is None:
                note = (note + "; " if note else "") + "the area's residents admitted in its own states' hospitals"
            out.append(_estimate_row("case fatality", "mortality_after",
                                     {**base, "variable": f"death within {d} days of the first admission",
                                      **_period(y, None if y is not None else period), "note": note, "model": model},
                                     estimate=k / n, low=lo, high=hi, interval="Clopper-Pearson (linkage error not in "
                                     "it)", numerator=k, denominator=n))
    return out


def _ages(it: Item, f, label: str, classifier: str | None, area) -> list[dict]:
    """The age at the event of the field's events in the area, from its own records (`gateway.mark_values`: the age and
    sex columns of the topic's records, filtered in the lake), per year and over the period, for everyone and by sex:
    the first line of a paper's table 1 (mean age, its standard deviation and quartiles). The counts' single years are
    capped at the population's open band (80: `gateway.MAX_AGE`), and the deaths of the old had a top-coded mean and
    quartiles (the paper audit, 2026-10-14); the age is read here as the counts read it, uncapped (the counts' own
    expression is in every stored count's key)."""
    import duckdb

    src = it.source or {}
    codes = fields.codes_of(src, it.nodes)
    acc: dict[tuple, list[np.ndarray]] = {}
    for y in it.years:
        try:
            strata = gateway._strata(it.dataset, it.event, int(y))
            if not strata.get("age"):
                return []
            cols = tuple(c for c in (strata["age"], strata.get("sex")) if c)
            t = gateway.mark_values(it.dataset, it.event, int(y), cols, classifier if codes else None, codes, area)
        except Exception:  # noqa: BLE001 - a year that cannot be read has no age row (the rates say why)
            continue
        x = f'trim(CAST("{strata["age"]}" AS VARCHAR))'
        missing = ", ".join("'" + str(c).replace("'", "''") + "'" for c in strata.get("age_missing") or ())
        age_sql = f"CASE WHEN {x} IN ({missing}) THEN NULL ELSE floor(TRY_CAST({x} AS DOUBLE)) END" if missing \
            else f"floor(TRY_CAST({x} AS DOUBLE))"
        con = duckdb.connect()
        con.register("r", t)
        a = con.execute(f"""SELECT {age_sql} AS age, {gateway._sex_sql(strata, it.dataset, t)} AS sex FROM r
                            WHERE {age_sql} IS NOT NULL AND {age_sql} >= 0""").fetchnumpy()
        age = np.asarray(a["age"], dtype=float)
        sex = np.nan_to_num(np.asarray(a["sex"], dtype=float), nan=0).astype(int)
        n = np.ones(len(age))
        for key, m in ((None, np.ones(len(age), bool)), (1, sex == 1), (2, sex == 2)):
            acc.setdefault((int(y), key), []).append(np.stack([age[m], n[m]]))
    out = []
    period = f"{min(it.years)}-{max(it.years)}"
    years = sorted({y for y, _ in acc})
    for sx in (None, 1, 2):
        for y in [*years, None]:
            parts = acc.get((y, sx), []) if y is not None else [a for z in years for a in acc.get((z, sx), [])]
            if not parts:
                continue
            a, w = np.concatenate(parts, axis=1)
            if w.sum() <= 0:
                continue
            order = np.argsort(a)
            a, w = a[order], w[order]
            cum = np.cumsum(w) / w.sum()
            q = [float(a[min(np.searchsorted(cum, p), len(a) - 1)]) for p in (0.25, 0.5, 0.75, 0.9)]
            mean = float((a * w).sum() / w.sum())
            sd = float(np.sqrt((w * (a - mean) ** 2).sum() / max(w.sum() - 1, 1)))
            out += _measure_rows({"field": f.id, "label": label, "dataset": it.dataset, "variable": "age",
                                  "variable_label": "age at the event, years" + {None: "", 1: " (male)",
                                                                                 2: " (female)"}[sx],
                                  **_period(y, None if y is not None else period)},
                                 "age", float(w.sum()), None, None, mean, sd, q)
    return out


def _seasons(it: Item, s, f, label: str, skip: set | frozenset = frozenset()) -> list[dict]:
    """A count field by the month of its events' own dates (`gateway.monthly_counts`, the study's area), over the period
    and each year: events, the days of those months, events per day, and the seasonal index (a month's events per day
    over the period's) with its exact interval, the period's daily rate fixed; over the period, Pearson's test of the
    months' events against their days (no seasonality: each day alike). What a paper's seasonality figure and sentence
    read; the folder had years only (2026-10-14). Each code cut as the model cuts its block (the item's code set, then
    the field's leaves); events dated outside the item's years are not counted here."""
    import calendar

    import pyarrow.compute as pc
    from scipy.stats import chi2

    d = s.expectations.model(f.block).data
    if d.n is not None:
        return []
    src = it.source or {}
    subset = [str(x) for x in src.get("codes") or []]
    leaves = [str(c) for c in s.expectations.registry.leaves(f.node) if c in d.leaves]
    width = max(len(str(c)) for c in d.leaves) if d.leaves else 0
    area = tuple(sorted(config.study_area())) if config.study_area() else None
    years = [int(y) for y in it.years if int(y) not in skip]       # a partial year has no season of its own
    if not years:
        return []
    ev = np.zeros((len(years), 12))
    for y in years:
        cls = fields.classifier_of(it.dataset, it.event, src, primary=False)
        c = gateway.monthly_counts(it.dataset, it.event, y, classifier=cls, area=area,
                                   codes=tuple(subset) if subset and not isinstance(cls, (list, tuple)) else ()).counts
        if subset:
            hit = pc.starts_with(c.column("code"), subset[0])
            for x in subset[1:]:
                hit = pc.or_(hit, pc.starts_with(c.column("code"), x))
            c = c.filter(pc.fill_null(hit, False))
        if f.node != "*" and leaves:
            c = c.filter(pc.fill_null(pc.is_in(pc.utf8_slice_codeunits(c.column("code"), 0, width),
                                               value_set=pa.array(leaves, pa.string())), False))
        yr = c.column("year").to_numpy().astype(int)
        mo = c.column("month").to_numpy().astype(int)
        n = c.column("y").to_numpy().astype(float)
        ok = np.isin(yr, years) & (mo >= 1) & (mo <= 12)
        np.add.at(ev, (np.searchsorted(years, yr[ok]), mo[ok] - 1), n[ok])
    days = np.array([[calendar.monthrange(y, m)[1] for m in range(1, 13)] for y in years], dtype=float)
    out = []
    period = f"{years[0]}-{years[-1]}"
    try:
        date_column = gateway._when(it.dataset)
    except LookupError:
        date_column = None

    def rows(e: np.ndarray, dd: np.ndarray, year: int | None) -> list[dict]:
        tot, td = float(e.sum()), float(dd.sum())
        if tot <= 0:
            return []
        rate = tot / td
        exp = rate * dd
        stat = float(((e - exp) ** 2 / exp).sum())
        p = float(chi2.sf(stat, 11))
        lo = np.where(e > 0, chi2.ppf(0.025, 2 * e) / 2, 0.0) / exp
        hi = chi2.ppf(0.975, 2 * e + 2) / 2 / exp
        base = {"field": f.id, "label": label, "dataset": it.dataset, "geography": _whole()[0],
                "variable": date_column, "model": "the year's own months against their days", **_period(year, None)}
        out_ = [_estimate_row("seasonality", "uniformity_chi2", base, estimate=stat, p=p)]
        for m in range(12):
            out_ += [_estimate_row("seasonality", "count", {**base, "month": m + 1}, estimate=float(e[m]),
                                   denominator=float(dd[m]), denominator_kind="days"),
                     _estimate_row("seasonality", "seasonal_index", {**base, "month": m + 1},
                                   estimate=float(e[m] / exp[m]), low=float(lo[m]), high=float(hi[m]),
                                   interval="exact Poisson, the year's daily rate fixed")]
        return out_

    out += _seasonal_model(ev, days, {"field": f.id, "label": label, "dataset": it.dataset, "geography": _whole()[0],
                                      "variable": date_column, **_period(None, period)})
    for k, y in enumerate(years):
        out += rows(ev[k], days[k], y)
    return out


def _seasonal_model(ev: np.ndarray, days: np.ndarray, base: dict) -> list[dict]:
    """The period's seasonality by quasi-Poisson regression of the monthly counts (years x 12) on year and month, the
    days of each month as offset: each year its own level, so a trend or a jump between years is not read as season
    (the audit: a pooled index of a rising series, 2026-10-14). The month's index is its rate ratio to the geometric mean
    of the twelve (sum-to-zero contrasts), with its 95 % interval; the months' joint F test; and one harmonic fitted the
    same way, its peak month and peak-to-trough ratio with delta-method intervals (Stolwijk et al. 1999). The variance
    is scaled by the Pearson dispersion."""
    import statsmodels.api as sm
    from scipy.stats import f as fdist

    keep = ev.sum(1) > 0
    e, dd = ev[keep], days[keep]
    K = int(keep.sum())
    if K == 0 or e.sum() < 24:
        return []
    yv, off = e.ravel(), np.log(dd.ravel())
    yr = np.repeat(np.eye(K), 12, axis=0)
    mo = np.tile(np.vstack([np.eye(11), -np.ones((1, 11))]), (K, 1))           # sum-to-zero contrasts
    fit = sm.GLM(yv, np.hstack([yr, mo]), family=sm.families.Poisson(), offset=off).fit(scale="X2")
    b, cov = np.asarray(fit.params)[K:], np.asarray(fit.cov_params())[K:, K:]
    L = np.vstack([np.eye(11), -np.ones((1, 11))])
    est, se = L @ b, np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", L, cov, L), 0.0))
    df = max(int(fit.df_resid), 1)
    stat = float(b @ np.linalg.solve(cov, b)) / 11 if np.linalg.cond(cov) < 1e12 else float("nan")
    p_f = float(fdist.sf(stat, 11, df)) if np.isfinite(stat) else None
    theta = 2 * np.pi * (np.arange(12) + 0.5) / 12
    harm = np.tile(np.column_stack([np.cos(theta), np.sin(theta)]), (K, 1))
    h = sm.GLM(yv, np.hstack([yr, harm]), family=sm.families.Poisson(), offset=off).fit(scale="X2")
    (c, s_), hc = np.asarray(h.params)[K:], np.asarray(h.cov_params())[K:, K:]
    amp = float(np.hypot(c, s_))
    peak: list[dict] = []
    if amp > 0:
        g_amp = np.array([c, s_]) / amp
        g_phi = np.array([-s_, c]) / amp ** 2
        se_amp = float(np.sqrt(max(g_amp @ hc @ g_amp, 0.0)))
        se_phi = float(np.sqrt(max(g_phi @ hc @ g_phi, 0.0)))
        import datetime

        phi = float(np.arctan2(s_, c))
        # the peak as days from 1 January (a peak in "months" read a month off: 7.35 is 12 August, written up as July,
        # the second audit, 2026-10-14)
        day = (phi / (2 * np.pi)) % 1.0 * 365.25
        half = 1.96 * se_phi / (2 * np.pi) * 365.25
        base = {**base, "model": "quasi-Poisson regression on year and month (days as offset)"}
        peak = [_estimate_row("seasonality", "peak_day", base, estimate=day + 1, low=day + 1 - half,
                              high=day + 1 + half, interval="delta method", unit="day of the year",
                              note=(datetime.date(2001, 1, 1) + datetime.timedelta(days=int(day))).strftime("%d %B")),
                _estimate_row("seasonality", "peak_to_trough", base, estimate=float(np.exp(2 * amp)),
                              low=float(np.exp(2 * max(amp - 1.96 * se_amp, 0))),
                              high=float(np.exp(2 * (amp + 1.96 * se_amp))), interval="delta method")]
    base = {**base, "model": "quasi-Poisson regression on year and month (days as offset)"}
    out = [_estimate_row("seasonality", "seasonality_f", base, estimate=stat if np.isfinite(stat) else None, p=p_f),
           *(peak or [])]
    for m in range(12):
        out += [_estimate_row("seasonality", "count", {**base, "month": m + 1}, estimate=float(ev[:, m].sum()),
                              denominator=float(days[:, m].sum()), denominator_kind="days"),
                _estimate_row("seasonality", "seasonal_index", {**base, "month": m + 1}, estimate=float(np.exp(est[m])),
                              low=float(np.exp(est[m] - 1.96 * se[m])), high=float(np.exp(est[m] + 1.96 * se[m])),
                              interval="quasi-Poisson regression")]
    return out


def _link_text(it: Item) -> str:
    """A linked share's label: the share of the field's records paired with the partner's, and through which link (a
    linked share had the count field's own label, "hospitalisation: I21 ...", and read as admissions, 2026-10-14)."""
    src = it.source or {}
    if src.get("source") != "linked" or not src.get("link"):
        return ""
    spec = gateway.link_specs().get(src["link"])
    partner = (spec.right.dataset if src.get("side", "left") == "left" else spec.left.dataset) if spec else "partner"
    # the link's own description says which records it pairs: sih_deaths_to_sim pairs the admissions that ended in
    # death, so its share of a topic's admissions is their in-hospital deaths found in SIM, not death after admission
    # (the cohort of Alagoas's 2022 admissions: 159 linked, all among the 168 with MORTE = 1, 2026-10-14)
    what = gateway.link_description(src["link"])
    return f" — share paired with a {partner} record ({src['link']}" + (f": {what}" if what else "") + ")"


def _band_order(label: str) -> float:
    """An age band's label ("0", "1-4", "80+") as its lower edge; any other value after every band."""
    head = label.split("-")[0].rstrip("+").strip()
    return float(head) if head.isdigit() else float("inf")


def _band_labels(edges) -> list[str]:
    """Each age band's label from its lower edges: "0", "1-4", ..., "80+" (one labelling for every table: the rates had
    "0-0" where the case mix had "0", 2026-10-14)."""
    edges = [int(x) for x in edges]
    return [f"{lo}-{hi - 1}" if hi - 1 > lo else f"{lo}" for lo, hi in zip(edges[:-1], edges[1:], strict=True)] + \
        [f"{edges[-1]}+"]


def _area_text() -> str:
    """The study's area in words: Brazil, or each state by its abbreviation and each municipality by its name, with their
    IBGE codes (the methods had said "the area 27")."""
    area = config.study_area()
    if area is None:
        return "Brazil"
    names = gateway.municipality_names()
    out = []
    for a in sorted(int(x) for x in area):
        if a < 100:
            uf = next((v.get("uf_sigla") for k, v in names.items() if str(k).startswith(str(a)) and v), None)
            out.append(f"the state of {uf} (IBGE {a})" if uf else f"IBGE {a}")
        else:
            nm = (names.get(str(a)) or {}).get("name")
            out.append(f"{nm} (IBGE {a})" if nm else f"IBGE {a}")
    return ", ".join(out)


def _linkage(scope: Scope) -> list[dict]:
    """Every stored link run a linked field of the study read, one row per run: the records on each side, the pairs
    kept, the share linked, the false-match rate estimated from the placebo with its upper 95 % bound, the threshold,
    the verdict, and the agreement on each validation field (a field the linkage did not use is independent; one it
    used is circular): what a paper's linkage section reports (the RECORD statement), which the folder did not hold."""
    out, seen = [], set()
    for it in (i for i in scope.items if i.status == "in" and (i.source or {}).get("source") == "linked"):
        src = it.source or {}
        link, side = src.get("link"), src.get("side") or "left"
        if not link:
            continue
        for z in sorted({z for y in it.years for z in gateway.covering_runs(link, side, y)}):
            if (link, z) in seen:
                continue
            seen.add((link, z))
            rep = gateway.link_report(link, z)
            if not rep:
                out.append({"link": link, "run_year": z, "verdict": "not stored"})
                continue
            vals = rep.get("validations") or {}
            indep = [float(v["agreement_percent"]) for v in vals.values()
                     if isinstance(v, dict) and not v.get("circular") and v.get("agreement_percent") is not None]
            out.append({"link": link, "run_year": z, "method": rep.get("method"),
                        "left_records": rep.get("left_records"), "right_records": rep.get("right_records"),
                        "candidates": rep.get("candidates"), "threshold_bits": rep.get("threshold_bits"),
                        "pairs": rep.get("pairs"), "linked_share": rep.get("linked_share"),
                        "false_match_percent": rep.get("estimated_fdr_percent", rep.get("chance_percent")),
                        "false_match_upper95_percent": rep.get("fdr_upper95_percent", rep.get("chance_upper95_percent")),
                        "verdict": rep.get("verdict"),
                        "verdict_reasons": "; ".join(str(x) for x in rep.get("verdict_reasons") or []) or None,
                        "independent_agreement_percent": min(indep) if indep else None,
                        "validations": "; ".join(
                            f"{k}: {v.get('agreement_percent')} % of {v.get('pairs_compared')} pairs"
                            f"{' (circular)' if v.get('circular') else ' (independent)'}"
                            for k, v in vals.items() if isinstance(v, dict)) or None})
    return out


def _proportion(k: float, n: float) -> dict:
    """A proportion with its exact (Clopper-Pearson) 95 % interval, as estimates.parquet carries it."""
    from scipy.stats import beta

    if not n or n <= 0:
        return {"proportion": None, "proportion_low": None, "proportion_high": None}
    return {"proportion": k / n, "proportion_low": float(beta.ppf(0.025, k, n - k + 1)) if k > 0 else 0.0,
            "proportion_high": float(beta.ppf(0.975, k + 1, n - k)) if k < n else 1.0}


def _places(it: Item, s, f, label: str, sv, names: dict, refs: list | None = None) -> list[dict]:
    """A count field per municipality, each year and over the whole period: what a map, a spatial model or a table of
    places reads (the folder had maps as pictures, and per-place values only as views into the store, 2026-10-14).
    Events and denominator; the crude rate with its exact Poisson interval (Garwood); the events expected at the area's
    own age-sex rates of each year (indirect standardisation) and the standardised ratio with its exact interval, the
    expectation fixed (Breslow & Day 1987); the hierarchical model's expected events and rate (tier B1: the place's own
    level, its effect smoothed toward its neighbours); the municipality's name, state and, in an area study, health
    region and macro-region. With Brazil's cells (``refs``), the ratio against Brazil's age-sex rates of each year too,
    so a municipality compares with the nation and not only with its own area (whose ratio is 1 by construction); each
    period ratio's exact two-sided p and Benjamini-Hochberg q over the municipalities (the audit, 2026-10-14)."""
    from scipy.stats import chi2, poisson
    from scipy.stats import gamma as gamma_
    from statsmodels.stats.multitest import multipletests

    from . import monolith

    d = s.expectations.model(f.block).data
    if d.n is not None:
        return []
    leaves = [d.leaves.index(c) for c in s.expectations.registry.leaves(f.node) if c in d.leaves]
    U, T, G = d.N.shape
    y = np.zeros((U, T, G))
    sel = np.isin(d.e, leaves)
    np.add.at(y, (d.u[sel], d.t[sel], d.g[sel]), d.y[sel])
    N = d.N.astype(float)
    ratio = str(d.population).startswith("events:")
    per, scale = ((f"1,000 {_exposure_text(d.population)}", 1e3) if ratio
                  else ("100,000 person-years", 1e5))
    if _births_field(it):
        # a birth prevalence by municipality: its live births as the one cell (a birth has no sex or age of its own),
        # the area's and Brazil's rates per live birth as the expectations (the audit could map no prevalence)
        y, N = y.sum(2, keepdims=True), _births(d)[:, :, None]
        G = 1
        per, scale, ratio = "1,000 live births", 1e3, True
        refs = [(k, yb.sum(1, keepdims=True), _reference_births([int(x) for x in np.asarray(d.years)], [k])[k][:, None])
                for k, yb, _ in refs or [] if k == "BR"]
    with np.errstate(divide="ignore", invalid="ignore"):
        own = np.where(N.sum(0) > 0, y.sum(0) / N.sum(0), 0.0)           # [T, G]: the area's own rates of each year
    ex, ev, py = (N * own[None]).sum(2), y.sum(2), N.sum(2)              # [U, T]
    brazil = next(((yb, nb) for unit, yb, nb in refs or [] if unit == "BR"), None)
    if brazil is not None:
        with np.errstate(divide="ignore", invalid="ignore"):
            rb = np.where(brazil[1] > 0, brazil[0] / brazil[1], 0.0)       # [T, G]: Brazil's rates of each year
        exb = np.column_stack([(N * rb[None]).sum(2), (N * rb[None]).sum(2).sum(1)])
    else:
        exb = None
    places = np.asarray(d.places).astype(np.int64)
    years = np.asarray(d.years).astype(np.int64)
    # the B1 expectation on the model's years (a monthly surprise summed to its years)
    svy = np.asarray(sv.years).astype(np.int64)
    svy = svy // 100 if svy.max() > 9999 else svy
    mu = np.asarray(sv.mu, dtype=float)
    pos = monolith.positions(np.asarray(sv.places), places)
    md = np.full((U, T), np.nan)
    for k, yr in enumerate(years):
        cols = np.flatnonzero(svy == yr)
        if len(cols):
            md[:, k] = np.where(pos >= 0, mu[np.maximum(pos, 0)][:, cols].sum(1), np.nan)
    ev, py, ex, md = (np.column_stack([a, a.sum(1)]) for a in (ev, py, ex, md))   # the period as one more column
    lo = np.where(ev > 0, chi2.ppf(0.025, 2 * ev) / 2, 0.0)
    hi = chi2.ppf(0.975, 2 * ev + 2) / 2
    region = macro = None
    if config.study_area() is not None and len(places):
        try:
            region = gateway.regions(places, "health_region")
            macro = gateway.regions(places, "health_macroregion")
        except LookupError:
            pass                            # a municipality without the membership: no region written, never guessed

    def two_sided(o: float, e: float) -> float | None:
        return min(1.0, 2 * min(float(poisson.cdf(o, e)), float(poisson.sf(o - 1, e)))) if e > 0 else None
    p_int = [two_sided(float(ev[ui, T]), float(ex[ui, T])) for ui in range(U)]
    p_br = [two_sided(float(ev[ui, T]), float(exb[ui, T])) for ui in range(U)] if exb is not None else [None] * U

    def bh(ps: list) -> list:
        ok = [i for i, p in enumerate(ps) if p is not None]
        q = multipletests([ps[i] for i in ok], method="fdr_bh")[1] if ok else []
        out_ = [None] * len(ps)
        for i, v in zip(ok, q, strict=True):
            out_[i] = float(v)
        return out_
    q_int, q_br = bh(p_int), bh(p_br)
    # each period's empirical-Bayes prior for the municipalities' ratios (Marshall 1991): the gamma whose mean is the
    # area's ratio and whose variance is the ratios' spread beyond Poisson noise, a small place's ratio shrunk toward it
    prior = []
    for k in range(T + 1):
        o_, e_ = ev[:, k].astype(float), ex[:, k].astype(float)
        ok_ = e_ > 0
        m = float(o_[ok_].sum() / e_[ok_].sum()) if ok_.any() and e_[ok_].sum() > 0 else 0.0
        v = (float((e_[ok_] * (o_[ok_] / e_[ok_] - m) ** 2).sum() / e_[ok_].sum() - m / e_[ok_].mean())
             if ok_.sum() > 1 else 0.0)
        prior.append((m * m / v, m / v) if m > 0 and v > 0 else None)
    period = f"{int(years[0])}-{int(years[-1])}"
    kind = ("live births" if _births_field(it) else _exposure_text(d.population)
            if ratio else "person-years")
    exact = "exact Poisson, expectation fixed"
    out = []
    with np.errstate(divide="ignore", invalid="ignore"):
        for ui, u in enumerate(places):
            nm = names.get(str(int(u))) or {}
            for k in range(T + 1):
                pop, e, o, m = float(py[ui, k]), float(ex[ui, k]), float(ev[ui, k]), float(md[ui, k])
                lo_, hi_ = float(lo[ui, k]), float(hi[ui, k])
                base = {"field": f.id, "label": label, "dataset": it.dataset, "geography": "municipality",
                        "place": int(u), "place_name": nm.get("name"), "state": nm.get("uf_sigla"),
                        "health_region": None if region is None else str(region[ui]),
                        "health_macroregion": None if macro is None else str(macro[ui]),
                        **_period(int(years[k]) if k < T else None, None if k < T else period)}
                out.append(_estimate_row("municipalities", "count", base, estimate=o))
                if pop > 0:
                    out.append(_estimate_row("municipalities", "crude_rate", base, estimate=scale * o / pop,
                                             low=scale * lo_ / pop, high=scale * hi_ / pop,
                                             interval="exact Poisson (Garwood), denominator fixed", numerator=o,
                                             denominator=pop, denominator_kind=kind, per=scale, unit=f"per {per}"))
                # against the area's own age-sex rates of each year, and against Brazil's; over the period with the
                # exact two-sided p and the Benjamini-Hochberg q across the municipalities
                own_, brazil_ = (("the area's own rate per live birth", "Brazil's rate per live birth")
                                 if G == 1 else ("the area's own age-sex rates", "Brazil's age-sex rates"))
                for e_, p_, q_, comparator in ((e, p_int[ui], q_int[ui], own_),
                                               *(() if exb is None else ((float(exb[ui, k]), p_br[ui], q_br[ui],
                                                                          brazil_),))):
                    if e_ > 0:
                        out.append(_estimate_row("municipalities", "smr", base, estimate=o / e_, low=lo_ / e_,
                                                 high=hi_ / e_, interval=exact, p=p_ if k == T else None,
                                                 q=q_ if k == T else None, numerator=o, denominator=e_,
                                                 denominator_kind="expected events", comparator=comparator))
                if prior[k] is not None and e > 0:
                    a_, b_ = prior[k][0] + o, prior[k][1] + e
                    out.append(_estimate_row("municipalities", "smoothed_smr", base, estimate=a_ / b_,
                                             low=float(gamma_.ppf(0.025, a_, scale=1 / b_)),
                                             high=float(gamma_.ppf(0.975, a_, scale=1 / b_)),
                                             interval="gamma posterior (empirical Bayes)", numerator=o, denominator=e,
                                             denominator_kind="expected events", comparator=own_,
                                             model="empirical Bayes, Poisson-gamma (Marshall 1991)"))
                if np.isfinite(m):
                    out.append(_estimate_row("municipalities", "expected", base, estimate=m,
                                             model="hierarchical, tier B1"))
                    if pop > 0:
                        out.append(_estimate_row("municipalities", "model_rate", base, estimate=scale * m / pop,
                                                 denominator=pop, denominator_kind=kind, per=scale, unit=f"per {per}",
                                                 model="hierarchical, tier B1"))
    return out


#: IBGE's mesh quality for the folder's geometry and maps: "intermediaria" (the default "minima", for overview maps, drew a
#: municipality in about 12 vertices, which the third audit could not map, 2026-10-14)
MESH_QUALITY = "intermediaria"


def _geometry(out: Path, places: list[dict]) -> None:
    """The municipalities of the folder's places as GeoJSON (pegasus_data's IBGE mesh, simplified to about 100 m),
    keyed by ``u`` as estimates.parquet's municipalities (``place``): a map drawn from the tables needs no other file (the audit could not draw one)."""
    import pegasus_data as pg

    us = sorted({int(r["place"]) for r in places if r.get("place") is not None})
    if not us:
        return
    munis = pg.mesh("municipality", quality=MESH_QUALITY, root=config.data_root())
    munis["u"] = munis["code"].str[:6].astype(int)
    munis = munis[munis["u"].isin(us)].copy()
    names = gateway.municipality_names()
    munis["municipality"] = [(names.get(str(u)) or {}).get("name") for u in munis["u"]]
    munis["state"] = [(names.get(str(u)) or {}).get("uf_sigla") for u in munis["u"]]
    munis["geometry"] = munis.geometry.simplify(0.0001, preserve_topology=True)
    (out / "municipalities.geojson").write_text(munis[["u", "code", "municipality", "state", "geometry"]].to_json(),
                                                encoding="utf-8")


def _quality(scope: Scope, groups: list[dict], log) -> list[dict]:
    """The records' completeness beside the allocation's rows (`_allocation`): for a source classified by ICD-10, the
    share of all its events in the area with an ill-defined cause (R00-R99, the cause-of-death quality indicator; for
    admissions, an ill-defined principal diagnosis), each year; and for each composition column the share of the field's
    events with the value not recorded, each year and over the period. Each share with its exact interval."""
    out = []
    area = tuple(sorted(config.study_area())) if config.study_area() else None
    cats = {str(r["code"])[:3] for r in gateway.code_tree("ICD10").to_pylist() if r.get("level") == "category"}
    done = set()
    for it in (i for i in scope.items if i.status == "in" and i.years):
        if (it.dataset, it.event) in done:
            continue
        done.add((it.dataset, it.event))
        et = gateway.event_type(it.dataset, it.event) or {}
        primary = next((c for c in et.get("classifiers") or [] if c.get("role") == "primary"), None)
        if not primary or primary.get("structure") != "ICD10":
            continue
        for y in it.years:
            try:
                code, n = _area_events(it.dataset, it.event, int(y), None, area)
            except Exception as exc:  # noqa: BLE001 - a year that cannot be counted has no quality row, said
                log(f"study: quality {it.dataset} {y}: {type(exc).__name__}: {exc}")
                continue
            ill = np.array([str(x or "")[:1] == "R" for x in code], dtype=bool)
            k, tot = float(n[ill].sum()), float(n.sum())
            # and those with no code of the tree at all (blank, '000'): a topic read on a column most records leave
            # empty is a recording-defined part of them (SIA's ATD: 88 % of its authorisations, 2026-10-14)
            none_ = np.array([str(x or "").strip()[:3].upper() not in cats for x in code], dtype=bool)
            out.append(_indicator({"dataset": it.dataset, "label": f"every {it.event} of the source",
                                   **_period(int(y), None)},
                                  f"no ICD-10 code on {primary['column']} (blank or none of the tree)",
                                  float(n[none_].sum()), tot))
            out.append(_indicator({"dataset": it.dataset, "label": f"every {it.event} of the source",
                                   **_period(int(y), None)},
                                  f"ill-defined causes (ICD-10 R00-R99) on {primary['column']}", k, tot))
            out += _garbage_rows(it, int(y), code, n, primary["column"], log)
    # the system's coverage of its events in the area's states (pegasus_data's system_completeness: SIM and SINASC by
    # state and year, the published ratio to 2011 and a calibrated extension): what separates a recording change from a
    # real one (the audit had only a 2004 national figure, 2026-10-14)
    states = sorted({int(a) if a < 100 else int(a) // 10000 for a in (config.study_area() or [])})
    for ds in dict.fromkeys(i.dataset for i in scope.items if i.status == "in" and i.years):
        system = gateway.completeness_system(ds)
        if system is None:
            continue
        years = sorted({int(y) for i in scope.items if i.dataset == ds and i.status == "in" for y in i.years})
        try:
            kap = gateway.completeness(system).to_pylist()
        except Exception as exc:  # noqa: BLE001 - a series that cannot be read leaves no row, said
            log(f"study: quality: {system} completeness: {type(exc).__name__}: {exc}")
            continue
        for r in kap:
            if int(r["year"]) in years and (not states or int(r["uf"]) in states):
                k, sd = float(r["kappa"]), float(r["s"] or 0.0)
                out.append(_indicator(
                    {"dataset": ds, "label": f"{system} in state {int(r['uf'])}", **_period(int(r["year"]), None)},
                    f"coverage of the state's {system} events (pegasus_data system_completeness: the published ratio "
                    "to 2011, a calibrated extension after; 95 % interval from the source's 80 %)", None, None,
                    share=k, low=float(np.exp(np.log(k) - 1.96 * sd)) if k > 0 else None,
                    high=min(1.0, float(np.exp(np.log(k) + 1.96 * sd))) if k > 0 else None,
                    interval="log-normal from the source's 80 % interval"))
    whole = _whole()[0]
    blank: dict[tuple, list[float]] = {}
    one: dict[tuple, set] = {}
    # the case mix's shares of the whole (`_groups`), sex and age band apart (the model's own cells: always recorded)
    for g in groups:
        if g["measure"] != "proportion" or g["geography"] != whole or g["variable"] in ("sex", "age band"):
            continue
        name = g.get("variable_label") or g["variable"]
        when = (g["period_kind"], g["first"], g["last"])
        if g["period_kind"] == "period" and float(g.get("numerator") or 0) > 0:
            one.setdefault((g["dataset"], g["field"], g["label"], name, when, float(g.get("denominator") or 0.0)),
                           set()).add(str(g.get("value_label") or g.get("value")))
        acc = blank.setdefault((g["dataset"], g["field"], g["label"], when, name),
                               [0.0, float(g.get("denominator") or 0.0)])
        if str(g.get("value")) in ("not recorded", "value missing"):
            acc[0] += float(g.get("numerator") or 0.0)
    for (ds, fid, label, (kind, first, last), name), (k, tot) in blank.items():
        out.append(_indicator({"dataset": ds, "field": fid, "label": label, "period_kind": kind, "first": first,
                               "last": last}, f"not recorded: {name}", k, tot))
    # a column with one value on every record of the period carries no information here, whatever its label says (SIH's
    # GESTRISCO "Sim" on every admission, men's included; the audit, 2026-10-14)
    for (ds, fid, label, name, (kind, first, last), tot), values in one.items():
        # (a column not recorded on every record is its not-recorded row's 100 %, said once)
        if len(values) == 1 and tot > 0 and not values & {"not recorded", "value missing"}:
            out.append(_indicator({"dataset": ds, "field": fid, "label": label, "period_kind": kind, "first": first,
                                   "last": last},
                                  f"one value on every record: {name} = {next(iter(values))} (no information)", tot,
                                  tot))
    return out


def _indicator(base: dict, indicator: str, k: float | None, n: float | None, share: float | None = None,
               low: float | None = None, high: float | None = None, interval: str | None = None) -> dict:
    """A completeness indicator as an estimate: ``k`` of ``n`` with its Clopper-Pearson interval, or a share computed
    elsewhere with its own interval (named)."""
    if share is None and n:
        pr = _proportion(k or 0.0, n)
        share, low, high, interval = pr["proportion"], pr["proportion_low"], pr["proportion_high"], "Clopper-Pearson"
    return _estimate_row("completeness", "proportion", {**base, "geography": base.get("geography") or _whole()[0]},
                         variable=indicator, estimate=share, low=low, high=high,
                         interval=interval if low is not None or high is not None else None,
                         numerator=k, denominator=n, denominator_kind="events" if n is not None else None)


@functools.cache
def _garbage_levels(edition: str = "GBD2019") -> dict[str, int]:
    """Each garbage code of a published list (pegasus_data `garbage_codes`) and its GBD level (the lowest where a code is
    in two packages; 0 where the edition prints none), as the list spells them: a category of three characters, or a code
    as SIM writes it. Read exactly: a subcode the list omits is not its category's (I42.2, hypertrophic cardiomyopathy, is
    no garbage code though I42.9 is; reading by category had put Alagoas's 2014 share at 44.9 % for 44.3 %)."""
    import pegasus_data as pg

    out: dict[str, int] = {}
    for r in pg.garbage_codes(edition).to_pylist():
        lv = int(r["level"]) if r.get("level") is not None else 0
        c = str(r["code"]).upper()
        prev = out.get(c)
        out[c] = lv if not prev else (min(prev, lv) if lv else prev)
    return out


def _garbage_rows(it: Item, year: int, code: np.ndarray, n: np.ndarray, column: str, log) -> list[dict]:
    """One year's share of the area's events (placed or not) whose code is a garbage code of the GBD 2019 list
    (`_garbage_levels`), at every level and at each, of the whole source and of the ICD-10 chapter of the topic's codes:
    what tells a coding shift from a change in the condition (the paper audits, 2026-10-14). A code the list does not
    hold is not asserted useful: the list is a claim about its own codes."""
    try:
        levels = _garbage_levels()
    except Exception as exc:  # noqa: BLE001 - no list: no rows, said
        log(f"study: garbage codes: {type(exc).__name__}: {exc}")
        return []
    lv = np.array([levels.get(str(x or "").upper(), -1) for x in code])
    anc = _icd_ancestors()
    topic = [str(c).upper() for c in (it.source or {}).get("codes") or []]
    chapters = {anc[c[:3]][-1] for c in topic if anc.get(c[:3])}          # (code, label) of the outermost ancestor
    scopes = [("every event of the source", np.ones(len(code), bool))]
    for a, a_label in sorted(chapters):
        inside = np.array([any(x == a for x, _ in anc.get(str(c or "")[:3], [])) for c in code], dtype=bool)
        scopes.append((f"{a_label} ({a})", inside))
    out = []
    cite = "GBD 2019 list, Johnson et al. 2021, pegasus_data garbage_codes"
    for name, m in scopes:
        tot = float(n[m].sum())
        if tot <= 0:
            continue
        for which, sel in [("every level", lv >= 0), *((f"level {k}", lv == k) for k in (1, 2, 3, 4)),
                           ("level not given by the list", lv == 0)]:
            k = float(n[m & sel].sum())
            out.append(_indicator({"dataset": it.dataset, "label": name, **_period(year, None)},
                                  f"garbage codes on {column}, {which} ({cite})", k, tot))
    return out


def _methods(decl: Declaration, scope: Scope, desc: list[dict],
             linkage: list[dict] | None = None) -> list[tuple[str, list[str]]]:
    """The study's methods as a paper states them, written from what this run read and computed (design, sources and
    their case definitions, the population and the standard, every estimator and interval, the models, the questions
    and their error control, what the sources say of themselves), as (heading, paragraphs): METHODS.md and the report's
    section 6 are this one text (`_methods_markdown`, `_limitations`). Assembled from declarations and the run's own
    tables, never written by hand (ARCHITECTURE §2.4, BACKLOG 1.8)."""
    now = int(time.strftime("%Y"))
    read = [i for i in scope.items if i.status == "in" and i.years]
    area = _area_text()
    standards = sorted({str(r["standard"]) for r in desc if r.get("standard")})
    pers = sorted({str(r["unit"])[len("per "):] for r in desc if r["measure"] == "crude_rate" and r.get("unit")})
    design = [f"Population-based descriptive and ecological study of {area}, {decl.years[0]}-{decl.years[-1]}, on "
              "Brazil's national health information systems (DATASUS), read from the public files of each year (each "
              "file's server, path, digest and dates in sources.parquet, `served_by` naming a mirror where one served "
              "it). Events "
              "are attributed to the municipality of residence: every state's files are read and the records whose "
              "residence lies in the area kept, so a resident cared for in another state is counted, and a field read at "
              "another place (of care, of infection) says so in its label.",
              f"Denominators: {'; '.join(pers) or 'none'}. Rates per person-years use the resident population of the "
              "field's population source by municipality, sex, age and year; a source that declares other events as its "
              "denominator (live births) is rated per 1,000 of them."]
    for population in sorted({str(config.population_source())}):
        try:
            text = _population_text(population)
        except Exception:  # noqa: BLE001 - an undocumented series is said so
            text = None
        design.append(text or f"The population {population}: no document describing it has been read (pegasus_data).")
    design.append("Files read: sources.parquet, one row per published file of each source and year (server path, state, "
                  "competence, the size and date the server listed, the digest and rows of the bytes decoded, the "
                  "source's status), with the files listed and not held and why.")
    sources = []
    for it in read:
        src = it.source or {}
        et = gateway.event_type(it.dataset, it.event) or {}
        st = et.get("status") or {}
        what = ", ".join(str(c) for c in src.get("codes") or []) or "every event"
        on = src.get("classifier") or next((c["column"] for c in et.get("classifiers") or []
                                            if c.get("role") == "primary"), "its primary classifier")
        kind = (f"share linked across {src.get('link')}" if src.get("source") == "linked"
                else "second coding, counted and described only" if it.count_only else "counts")
        try:
            when = gateway._when(it.dataset)
        except LookupError:
            when = None
        try:
            import pegasus_data as pg

            facts = pg.dataset_facts(it.dataset)
        except Exception:  # noqa: BLE001 - a dataset pegasus_data does not document: the event type's grain
            facts = {}
        row_is = facts.get("what_one_row_is") or et.get("grain") or "one event"
        line = (f"{it.dataset} ({it.event}; one row is {row_is}), {min(it.years)}-"
                f"{max(it.years)}: {what} on {on} ({kind}); a year's events are those of the files published for "
                "that year" + (f", a month's those whose {when} falls in it (estimates.parquet, seasonality), so a year's months "
                               "need not sum to its published count" if when else ""))
        if st:
            line += f"; counted where {st['column']} is {', '.join(st['values'])}"
        sources.append(line + f". Why read: {it.reason}.")
    measures = [
        "Crude rates with exact Poisson 95 % intervals (Garwood), the denominator fixed; per year, over the whole period, "
        "for the whole and for each region, state and (an area) health macro-region and health region.",
        f"Direct standardisation by sex and age band to {'; '.join(standards) or 'the study population'}, with the gamma "
        "interval of Fay & Feuer (1997); rates by sex, by age band and by sex within each age band, with exact "
        "intervals.",
        "Annual percent change of each series, crude and age-sex adjusted: a Poisson log-linear model of the counts on "
        "the year, each sex-age cell its own level in the adjusted model, person-years as offset; the variance widened "
        "by the year-level Pearson dispersion (quasi-Poisson, in `dispersion`) and the interval read on Student's t "
        "with T - 2 degrees of freedom; APC = 100 (exp(b) - 1), with the slope's two-sided p (estimates.parquet, trends). "
        "Joinpoint regression (Kim et al. 2000, the NCI Joinpoint program's defaults) of the crude and of the directly "
        "standardised rate: log rate segmented-linear in the year by weighted least squares (weights the inverse "
        "variance of each year's log rate), joinpoints at observed years at least two years from an end or another "
        "joinpoint, their number by Kim's permutation tests (4,499 permutations, alpha 0.05 over the tests), each "
        "segment's APC and the whole series' average APC (AAPC) with t intervals. Provisional years (a source not yet "
        "final) are left out of every trend.",
        "Measures (estimates.parquet, measures): every quantity and interval the source declares on the topic's own events (a "
        "length of stay, a value paid), per year and over the period: mean, standard deviation, quartiles and 90th "
        "percentile of the valid values, with the counts not recorded and outside the declared domain.",
        "Seasonality (estimates.parquet, seasonality): the events by the month of their own dates (the column named in date_column). "
        "Over the period, a quasi-Poisson regression of the monthly counts on year and month with the month's days as "
        "offset, so neither a trend nor a jump between years reads as season: each month's rate ratio to the geometric "
        "mean of the twelve with its 95 % interval, the months' joint F test, and one harmonic's peak month and "
        "peak-to-trough ratio with delta-method intervals; each year, its months' events per day against the year's "
        "(exact intervals) and Pearson's chi-square (11 degrees of freedom).",
        "Case mix: every recorded variable of the events, as counts and shares with Clopper-Pearson intervals, per year "
        "and over the period; 'not recorded' and 'value missing' are values, kept.",
        "Race: each declared race's standardised ratio (estimates.parquet, rates, measure smr, variable race): its "
        "events against those expected of its population at the field's own age-sex rates of each year (indirect "
        f"standardisation), the populations by race of pegasus_data's population account ({tools_race_population()}: "
        "municipal population by single age, sex and race, with intervals); events of no recorded race are in no ratio, "
        "so a race recorded on few events (SIH before 2020) gives ratios that measure its recording.",
        f"Persons (persons.parquet): the cohort scan reads the study's last {PERSON_YEARS} years whose link runs are "
        "stored; a year that cannot be scanned is listed in provenance.json's products_gaps.",
        "Municipalities (estimates.parquet, municipalities; boundaries in municipalities.geojson, IBGE's mesh of intermediate quality): crude rates; the "
        "standardised ratio against the area's own age-sex rates of each year (indirect standardisation, 1 for the "
        "area by construction) and against Brazil's, each with its exact interval, the expectation fixed, and over the "
        "period its exact two-sided p and Benjamini-Hochberg q across the municipalities; for maps, the ratio against "
        "the area smoothed by empirical Bayes (Poisson-gamma, Marshall 1991: the gamma prior's mean the area's ratio, "
        "its variance the ratios' spread beyond Poisson noise by the method of moments, each year and the period apart), "
        "the posterior mean with its 95 % gamma interval, so a small municipality's ratio is shrunk toward the area's "
        "in proportion to its noise; the hierarchical model's expected events. Spatial autocorrelation of the smoothed "
        "ratios: global Moran's I (999 permutations) and the local Moran (LISA, Anselin 1995; 9,999 permutations) on "
        "row-standardised contiguity (esda); a municipality's quadrant (high-high, low-low, high-low, low-high) where its local p "
        "passes the study's q after Benjamini-Hochberg across the municipalities.",
        "Comparison with Brazil: every directly standardised rate's ratio to Brazil's of the same year and stratum, "
        "with a 95 % interval from the two gamma variances on the log scale (Brazil includes the area, so the interval "
        "is conservative); Brazil's and each macro-region's rates by sex, by age band and by sex within each age band "
        "(estimates.parquet, rates, geography reference); the standard's weights in standard.parquet.",
        "Case fatality (estimates.parquet, case fatality; where a source's outcome column has the codes of death "
        "declared, pegasus_data roles `fatal`): the topic's records whose outcome is death from the event over all its "
        "records (letalidade; in-hospital mortality for admissions), by year, sex and age band, with Clopper-Pearson "
        "intervals, the records with no outcome recorded counted in the denominator and said; deaths from another "
        "cause apart. Adjusted for age and sex by a binomial regression on year, age band and sex (adjacent bands "
        "merged until each holds a death and a survivor), each year at the period's case mix (marginal "
        "standardisation, interval from 2,000 draws of the coefficients), and its trend as the odds ratio per year. "
        "Where persons are read and pegasus_data declares a cohort link for the source, mortality after the first "
        "admission with the topic's codes in the period: each person's first admission linked to a death certificate of "
        "any cause (deterministic passes on birth date, sex and residence), the persons dead within 30 days and within a "
        "year over those followed that long, with exact intervals, each horizon's false-match rate from the link's "
        "shifted-date control and its verdict; a horizon whose link is not viable is not estimated.",
        "Associated causes (multiple-cause analysis, where a source carries every certificate line or diagnosis): each "
        "ICD-10 category named beside the topic on its own records, its share with a Clopper-Pearson interval and its "
        "ratio to the records of the same sex and ten-year age band without the topic.",
        "Proportional measures (estimates.parquet, rates, measure proportion): a code set's events over every event of each "
        "ICD-10 ancestor of its codes (its group, its chapter) and of the whole source, in the area, placed or not, with "
        "Clopper-Pearson intervals.",
        "Completeness (estimates.parquet, completeness): the share of the events placed by residence, sex and age, every reason the "
        "rest were not, the share of ill-defined causes (R00-R99) and of garbage codes (the GBD 2019 list, Johnson et al. "
        "2021, every level and by level, of the source and of the topic's ICD-10 chapter), each variable's share not "
        "recorded (the codes "
        "pegasus_data declares missing for that column), a column with one value on every record, and, for SIM and "
        "SINASC, the system's coverage of the state's events by year (pegasus_data system_completeness: the published "
        "ratio to 2011, a calibrated extension after it, its interval from the source's own 80 % interval)."]
    questions = decl.choice("questions")
    models = [
        "Expected counts: a hierarchical model per block of codes, Poisson with negative-binomial dispersion (NB-P), "
        "place effects smoothed over the municipalities' adjacency (ICAR), time courses per group, and a robust refit "
        "in which outlying cells are replaced by their expectation; a dispersion estimate on its Poisson bound is "
        "replaced by its lower 95 % profile-likelihood limit. Tiers: B0, the whole's rates without place effects "
        "(Brazil's, or the area's in an area study); B1, each place's own level; BP, fitted on earlier years only.",
        f"Questions asked of each field: {', '.join(questions) if questions else 'every question'} (excess, steps, "
        "trend changes, spatial and space-time clusters, shares). Monte Carlo tests on each method's own number of "
        "replicate worlds" + ("" if float(decl.choice("nulls")) == 1.0 else f" times {decl.choice('nulls'):g}")
        + ", stopped sequentially (Besag & Clifford 1991). False-discovery rate at q = "
        f"{decl.q}: Benjamini-Bogomolov across the fields asked, Benjamini-Hochberg within each selected field.",
        "Each finding is a statistical departure from expectation, not a causal claim. Its reading is classed by its "
        "own evidence (signal; a recording, denominator or system explanation; noise when its exact interval holds 1) "
        "and given with its observed-over-expected ratio and exact interval (findings.parquet)."]
    notes = []
    seen = set()
    for it in read:
        if (it.dataset, it.event) in seen:
            continue
        seen.add((it.dataset, it.event))
        et = gateway.event_type(it.dataset, it.event) or {}
        sn, ex = et.get("source_notes") or {}, et.get("exposure") or {}
        cite = f" ({sn['source']})" if sn.get("source") else ""
        try:
            import pegasus_data as pg

            facts = pg.dataset_facts(it.dataset)
        except Exception:  # noqa: BLE001 - nothing documented: nothing quoted
            facts = {}
        if facts.get("known_biases"):
            notes.append(f"{it.dataset}: known biases: {' '.join(str(facts['known_biases']).split())} (pegasus_data)")
        notes += [f"{it.dataset}: {' '.join(str(g).split())} (pegasus_data)" for g in facts.get("gotchas") or ()]
        if sn.get("definition"):
            notes.append(f"{it.dataset}: definition: {sn['definition']}{cite}")
        if sn.get("valid_from") and min(it.years) < sn["valid_from"]:
            notes.append(f"{it.dataset}: valid from {sn['valid_from']}; earlier years are read but are not the "
                         f"source's own{cite}")
        if sn.get("final_after_years"):
            prelim = [y for y in it.years if y > now - sn["final_after_years"]]
            if prelim:
                notes.append(f"{it.dataset}: {prelim[0]}-{prelim[-1]} preliminary (a year is final "
                             f"{sn['final_after_years']} years later){cite}")
        notes += [f"{it.dataset}: known error: {x}{cite}" for x in sn.get("known_errors") or ()]
        notes += [f"{it.dataset}: limitation: {x}{cite}" for x in sn.get("limitations") or ()]
        if ex:
            notes.append(f"{it.dataset}: rates per {ex.get('per', 1):g} {' + '.join(ex['events'])}: {ex['evidence']}")
    readers = sorted(decl.choice("readers"))
    linked = []
    for link in dict.fromkeys(r["link"] for r in linkage or []):
        rs = [r for r in linkage or [] if r["link"] == link and r.get("pairs") is not None]
        missing = [r["run_year"] for r in linkage or [] if r["link"] == link and r.get("pairs") is None]
        if not rs:
            linked.append(f"{link}: no stored run ({', '.join(map(str, missing))}); its linked shares are not given.")
            continue

        def span(k, rs=rs):
            v = [float(r[k]) for r in rs if r.get(k) is not None]
            return f"{min(v):.2f}-{max(v):.2f}" if v else "not measured"
        method = sorted({str(r.get("method")) for r in rs})
        linked.append(
            f"{link} ({', '.join(method)}; {gateway.link_description(link) or 'no description'}), runs "
            f"{rs[0]['run_year']}-{rs[-1]['run_year']}: "
            f"{sum(int(r['pairs'] or 0) for r in rs):,} pairs; false-match rate {span('false_match_percent')} % "
            f"(upper 95 % bound up to {span('false_match_upper95_percent').split('-')[-1]} %); agreement on independent "
            f"validation fields {span('independent_agreement_percent')} %; verdicts "
            f"{', '.join(sorted({str(r.get('verdict')) for r in rs}))}"
            + (f"; runs not stored: {', '.join(map(str, missing))}" if missing else "") + " (linkage.parquet).")
    if linked:
        linked.insert(0, "Probabilistic record linkage (pegasus_data, ADR-0111): the chance agreement of each compared "
                         "field from random pairs; its agreement for the same person from leave-one-field-out anchor "
                         "pairs, each state's pooled with the nation's; candidates from several blocking keys, each "
                         "scored as the sum of its fields' log-likelihood ratios in bits; a placebo in which every date of "
                         "one side is rotated by half a year inside the other side's period gives the pairs expected by "
                         "chance, and the threshold is where the estimated false-match rate (placebo pairs over real pairs "
                         "above it) is within the link's target; pairs resolved one to one by descending score. A run is "
                         "validated on fields the linkage did not use (independent) and on fields it did (circular).")
    return [("Design and population", design),
            ("Sources and case definition", sources),
            ("Descriptive measures", measures),
            *([("Record linkage", linked)] if linked else []),
            *([("Ecological analysis", [
                "Each count field's events over the period in each municipality regressed on the declared contexts "
                "(estimates.parquet, associations): negative binomial (NB2; its dispersion estimated once, by maximum "
                "likelihood on the field's null model, every regression a GLM at it), offset the log of the events expected at "
                "the area's own age-sex rates, so a coefficient multiplies the standardised ratio; each context "
                "standardised across the municipalities (a ratio per standard deviation, the SD in `note`), each alone "
                "(with its Benjamini-Hochberg q across the field's contexts) and then together, the contexts left after "
                "dropping, one at a time, the one of largest variance inflation until none exceeds 5 (those dropped "
                "named in `model`); a context is modelled where nine municipalities in ten hold its value. Wald intervals robust "
                "to clustering by health region (sandwich; heteroskedasticity-robust under ten regions, or where the joint "
                "model has as many parameters as regions); an estimate without a finite interval is not written. Moran's I of "
                "the joint model's Pearson residuals on the municipalities' contiguity, its one-sided p from 999 "
                "permutations, says the spatial dependence the model leaves. The associations are between places "
                "(ecological), never effects on persons."])] if decl.contexts else []),
            ("Exploratory signal detection (hypothesis-generating)",
             ["The scans below suggest where and when to look; they confirm nothing. A hypothesis they raise is tested "
              "by declaring it in the study (its own test, its own error control), and is reported as the study's "
              "result only then.", *models,
              f"Fields read at depth {decl.depth}: counts" + "".join(f", {r}" for r in readers) + "."]),
            ("What the sources say of themselves", notes or ["No source of this study declares notes."]),
            ("Reproducibility",
             [f"PegaSUS code {config.code_version()}, data {config.data_version()} (pegasus_data), written "
              f"{time.strftime('%Y-%m-%d')}. scope.yml says what was read and why and what was left out; provenance.json "
              "every step and its time; README.md every table's columns; study.duckdb every table as a table of its "
              "own; figures.parquet what each figure shows; municipalities.geojson the places' boundaries."])]


def tools_race_population() -> str:
    """The population account the race ratios read (`tools.RACE_POPULATION`)."""
    from . import tools

    return gateway.TENSOR.get(tools.RACE_POPULATION, (tools.RACE_POPULATION,))[0]


def _methods_markdown(decl: Declaration, scope: Scope, desc: list[dict], linkage: list[dict] | None = None) -> str:
    """METHODS.md: `_methods` as Markdown, the text a paper's methods section is written from."""
    lines = [f"# Methods: {decl.study}", ""]
    for head, paras in _methods(decl, scope, desc, linkage):
        lines += [f"## {head}", ""] + [f"- {x}" for x in paras] + [""]
    return "\n".join(lines)


def _exposure_text(population: str) -> str:
    """A denominator of other events as a reader names it: "live births" for SINASC's births, else each event type's
    name ("SIM-DOFET:death events")."""
    named = {BIRTHS[len("events:"):]: "live births"}
    return " + ".join(named.get(p, f"{p} events") for p in str(population)[len("events:"):].split(";"))


def _births_field(it: Item) -> bool:
    """Whether the field's events are live births themselves (SINASC's: a newborn's anomaly), not deaths or admissions
    around birth: its rates are per live births only, its strata the mother's."""
    return f"events:{it.dataset}:{gateway.split_event(it.event)[0]}" == BIRTHS


def _birth_related(it: Item, d) -> bool:
    """Whether a count field is rated per live births: its events are births themselves (SINASC's: an anomaly is a birth
    prevalence, and microcephaly had been rated per person-years of every resident, 2026-10-14), or they belong to
    pregnancy or the perinatal period: its codes all in ICD-10 chapter XV (O00–O99) or XVI (P00–P96), or its events
    mostly at age 0 (the model's newborn exposure, `monolith.default_population`)."""
    if _births_field(it):
        return True
    codes = [str(c) for c in ((it.source or {}).get("codes") or it.nodes or [])]
    icd = (it.source or {}).get("structure", "ICD10") == "ICD10" and all(c[:1].isalpha() for c in codes)
    return str(d.population).startswith("hybrid") or bool(codes and icd and all(c[:1] in "OP" for c in codes))


#: the live births a perinatal or a birth field is rated per (SINASC's declaration)
BIRTHS = "events:SINASC-DN:birth"


def _births(d) -> np.ndarray:
    """Live births (SINASC) per place and year of a block's lattice, [U, T]; sex and age summed."""
    import pyarrow.compute as pc

    years = [int(x) for x in np.asarray(d.years)]
    t = gateway.population(years, source=BIRTHS)
    u = t.column("u").to_numpy().astype(np.int64)
    yr = t.column("year").to_numpy().astype(np.int64)
    n = pc.fill_null(t.column("n"), 0.0).to_numpy()
    places = np.asarray(d.places, dtype=np.int64)
    order = np.argsort(places)
    i = np.searchsorted(places[order], u).clip(0, len(places) - 1)
    keep = (places[order][i] == u) & np.isin(yr, years)
    B = np.zeros((len(places), len(years)))
    np.add.at(B, (order[i[keep]], np.searchsorted(np.asarray(years), yr[keep])), n[keep])
    return B


def _states_besides_whole(state: np.ndarray) -> list:
    """The states whose rows the descriptive tables write beside the whole: none when the area is one state (its rows
    would repeat the area's), and in an area only the states it holds whole: a municipality's area wrote a row "state
    43" holding one municipality's events (the review of the study, 2026-10-14)."""
    area = config.study_area()
    states = list(np.unique(state))
    if area is None:
        return states
    whole_states = {int(a) for a in area if int(a) < 100}
    kept = [st for st in states if int(st) in whole_states]
    return [] if len(states) == 1 and kept == states else kept


#: IBGE's macro-regions, the first digit of a state's code: how Brazil's epidemiology reports between the nation and
#: its states (a paper's North-to-South gradient had no row of its own)
REGIONS = {1: "Norte", 2: "Nordeste", 3: "Sudeste", 4: "Sul", 5: "Centro-Oeste"}


#: the health system's own regionalisation, written below an area's states: how a state's epidemiology reports (its
#: macro-regions and the CIR's health regions), pegasus_data's memberships (`gateway.regions`)
HEALTH_LEVELS = (("health_macroregion", "health macro-region"), ("health_region", "health region"))


def _levels_below(places: np.ndarray) -> list[tuple[str, str, np.ndarray]]:
    """The geographies below the whole a descriptive table writes, each (level, unit, mask over ``places``, the
    municipality of each element): the macro-regions when the study spans more than one, then the states (none when
    the area is one state), then, for a declared area, its health macro-regions and health regions (`HEALTH_LEVELS`):
    a state's profile tabulates its regions, where Alagoas's infarction study had the state's rows alone (2026-10-13).
    Brazil's own study stops at the states; its municipalities are the findings' and maps'."""
    places = np.asarray(places).astype(np.int64)
    state = places // 10000
    region = state // 10
    out = []
    if len(np.unique(region)) > 1:
        out += [("region", f"{int(rg)} {REGIONS.get(int(rg), '')}".strip(), region == rg) for rg in np.unique(region)]
    out += [("state", str(int(st)), state == st) for st in _states_besides_whole(state)]
    if config.study_area() is None or not len(places):
        return out
    uniq, inv = np.unique(places, return_inverse=True)
    for classification, level in HEALTH_LEVELS:
        try:
            unit = gateway.regions(uniq, classification)[inv]
        except LookupError:
            continue                    # a municipality without the membership: the level is not written, never guessed
        for code in np.unique(unit):
            sel = unit == code
            out.append((level, _region_label(classification, str(code), int(places[sel][0])), sel))
    return out


@functools.cache
def _region_label(classification: str, code: str, member: int) -> str:
    """A health region's or macro-region's name, from one of its municipalities' memberships (pegasus_data)."""
    import pegasus_data as pg

    m = pg.memberships(str(member)).get(classification)
    return f"{code} {m.member_label}" if m is not None else code


def _whole() -> tuple[str, str]:
    """The level and unit of the study's whole: Brazil's, or its declared area's (`config.study_area`). An area study's
    total was written as "national, BR", the same numbers as its state's rows: the area labelled as Brazil (2026-10-12)."""
    area = config.study_area()
    return ("national", "BR") if area is None else ("area", "+".join(str(a) for a in sorted(area)))


def _sex_age(it: Item, s, f, label: str) -> list[dict]:
    """The field's events by sex and by age band (the model's own cells: events with both recorded), by year, for the
    whole and each state, each value's share with its exact interval: the case mix a paper's first table gives, which
    the groups table held for the source's other columns only (2026-10-12). Bands are the population source's."""
    from scipy.stats import beta

    d = s.expectations.model(f.block).data
    # the cells are the subject's sex and age only for a person-year field read whole: a field read collapsed holds every
    # event in its first cell, and one rated per births in the births' cells (the newborn's), so gestational cases read
    # as 100 % male at age 0 (the review of the RS slice, 2026-10-13)
    if d.n is not None or d.key.get("collapse") or str(d.population).startswith("events:"):
        return []
    births_field = _births_field(it)         # a birth's cells are its mother's: her age band, no sex
    G = d.N.shape[2]
    nB = G // 2
    if nB < 2:
        return []                                          # a collapsed field: no sex or age cells
    edges = gateway.age_edges(d.population, it.dataset, it.event)
    if len(edges) != nB:
        return []
    leaves = [d.leaves.index(c) for c in s.expectations.registry.leaves(f.node) if c in d.leaves]
    sel = np.isin(d.e, leaves)
    if np.unique(d.g[sel]).size <= 1:
        return []                          # one cell holds every event: no sex or age is recorded in them
    yg = np.zeros(d.N.shape)
    np.add.at(yg, (d.u[sel], d.t[sel], d.g[sel]), d.y[sel])
    by_sex = yg.reshape(*yg.shape[:2], 2, nB).sum(3)       # [U, T, 2]: sex 1, 2
    by_age = yg.reshape(*yg.shape[:2], 2, nB).sum(2)       # [U, T, nB]
    bands = _band_labels(edges)
    state = np.asarray(d.places) // 10000
    geo = [(*_whole(), np.ones(len(state), bool))] + _levels_below(np.asarray(d.places))
    yrs = np.asarray(d.years)
    out = []
    for by, by_name, arr, values in ((() if births_field else (("sex", "Sexo", by_sex, [("1", "Masculino"),
                                                                                       ("2", "Feminino")]),))
                                     + (("mother's age band" if births_field else "age band",
                                         "Faixa etária da mãe (anos)" if births_field else "Faixa etária (anos)",
                                         by_age, [(b, b) for b in bands]),)):
        for t, year in [*enumerate(yrs), (None, None)]:        # each year, then the whole period
            for level, unit, rows_u in geo:
                obs = arr[rows_u, t].sum(0) if t is not None else arr[rows_u].sum((0, 1))
                tot = float(obs.sum())
                if tot <= 0:
                    continue
                for k, (v, vl) in enumerate(values):
                    if obs[k] <= 0:
                        continue
                    o = float(obs[k])
                    out.append(_estimate_row(
                        "case mix", "proportion",
                        {"field": f.id, "label": label, "dataset": it.dataset, "geography": level, "place": unit,
                         "variable": by, "variable_label": by_name, "value": v, "value_label": vl,
                         **_period(int(year) if year is not None else None,
                                   None if year is not None else f"{int(yrs[0])}-{int(yrs[-1])}")},
                        estimate=o / tot, low=float(beta.ppf(0.025, o, tot - o + 1)),
                        high=float(beta.ppf(0.975, o + 1, tot - o)) if o < tot else 1.0, interval="Clopper-Pearson",
                        numerator=o, denominator=tot, denominator_kind="the field's events with sex and age"))
    return out


def _groups(it: Item, s, f, label: str, log) -> list[dict]:
    """A count field split by each composition column (`tools.Session.by_composition`), observed and expected by value,
    nationally and by state per year: the expectation is the place's observed events at its own usual mix of the value (race: at its population's)."""
    if (it.source or {}).get("population"):
        return []
    out = []
    places = np.asarray(s.expectations.model(f.block).data.places)
    years = np.asarray(s.expectations.model(f.block).data.years)
    from scipy.stats import beta

    from . import tools

    names = {d.column: d.name for d in fields.declared(it.dataset)}
    geo = [(*_whole(), np.ones(len(places), bool))] + _levels_below(places)     # once: every column and year reads it
    for column in tools.group_columns(it.dataset, it.event):
        try:
            y, mu, values = config.on_cpu_if_cuda_fails(s.by_composition, f.node, column)
        except Exception as exc:  # noqa: BLE001 - a column that cannot be split is a note, the others are written
            log(f"study: {it.dataset} {f.node} by {column}: {type(exc).__name__}: {exc}")
            continue
        # labelled as a finding's text labels them (`gateway.value_labels`, one table chosen on the column's values in
        # the study's area and years, kept for the process): two paths had labelled the same values, one on this
        # split's values only, where a subset can choose another table (2026-10-14)
        try:
            vl = gateway.value_labels(it.dataset, it.event, column, tuple(int(x) for x in it.years))
        except Exception:  # noqa: BLE001 - a column no table decodes: its values as recorded, said undecoded
            vl = {}
        shown = {v: (vl[str(v)] if str(v) in vl else (str(v) if str(v) in ("not recorded", "value missing")
                                                       else f"{v} (undecoded)")) for v in values}
        # each year, then the whole period: a paper's first table is the period's case mix, with its intervals
        for t, year in [*enumerate(years), (None, None)]:
            for level, unit, sel in geo:
                obs = y[sel, t].sum(0) if t is not None else y[sel].sum((0, 1))
                exp = mu[sel, t].sum(0) if t is not None else mu[sel].sum((0, 1))
                # each value's share of the field's events, with its exact (Clopper–Pearson) interval: a case mix is
                # described by proportions, and the table gave counts against a model's expectation only (2026-10-12).
                # One vectorised call per level and year: per value, 138,612 calls took 113 s of a study (2026-10-14)
                tot = float(obs.sum())
                with np.errstate(invalid="ignore", divide="ignore"):
                    lo = np.where(obs > 0, beta.ppf(0.025, obs, tot - obs + 1), 0.0) if tot else None
                    hi = np.where(obs < tot, beta.ppf(0.975, obs + 1, tot - obs), 1.0) if tot else None
                when = _period(int(year) if year is not None else None,
                               None if year is not None else f"{int(years[0])}-{int(years[-1])}")
                for k, v in enumerate(values):
                    if not (obs[k] > 0 or exp[k] > 0):
                        continue
                    base = {"field": f.id, "label": label, "dataset": it.dataset, "geography": level, "place": unit,
                            "variable": column, "variable_label": names.get(column, "race"), "value": v,
                            "value_label": shown[v], **when}
                    if tot:
                        out.append(_estimate_row("case mix", "proportion", base, estimate=float(obs[k]) / tot,
                                                 low=float(lo[k]), high=float(hi[k]), interval="Clopper-Pearson",
                                                 numerator=float(obs[k]), denominator=tot,
                                                 denominator_kind="the field's events"))
                    out.append(_estimate_row("case mix", "expected", base, estimate=float(exp[k]),
                                             unit="events", model="the place-year's events at the place's own mix "
                                             "of the column in its other years (race: at its population's mix)"))
    out.extend(_sex_age(it, s, f, label))
    return out


def _related(rows: list[dict], series: dict) -> list[dict]:
    """Related-field consistency (ARCHITECTURE §9, BACKLOG 7.4): every other primary field of the study read at a
    finding's places and years, observed against expected (B1), with its exact Poisson 95% interval on the observed
    count over the expected. A congenital excess beside a gestational one at the same places is consistent; beside none
    it asks why. Each row names the related fields whose interval excludes 1 (``related``)."""
    from scipy.stats import chi2

    out = []
    for r in rows:
        places = set(r.get("_places") or [])
        if not places or not r.get("first_year"):
            continue
        lo_y, hi_y = int(r["first_year"]), int(r["last_year"] or r["first_year"])
        notes = []
        for fid, (label, dataset, pl, yrs, y, mu, mu0, prospective) in series.items():
            ui = np.flatnonzero(np.isin(pl, list(places)))
            year_of = yrs // 100 if yrs.max() > 9999 else yrs          # YYYYMM periods at the monthly grain
            ti = np.flatnonzero((year_of >= lo_y) & (year_of <= hi_y))
            if not len(ui) or not len(ti):
                continue
            o, e_ = float(y[np.ix_(ui, ti)].sum()), float(mu[np.ix_(ui, ti)].sum())
            if fid == r["field"] and str(r.get("tier")) == "B0":
                # a B0 finding (a cluster, a level, a group) departs from national rates without place effects: its O/E
                # is against them; read against B1, a region persistently 13x the national rate read as 1.05, its own
                # usual level (the review of the RS slice, 2026-10-13)
                e_ = float(mu0[np.ix_(ui, ti)].sum()) if mu0 is not None else float("nan")
            if fid == r["field"] and str(r.get("tier", "")).startswith("BP"):
                # a prospective finding departs from an expectation fitted on the years before its window; B1, fitted
                # on every year, absorbs it (Alagoas: "q 2.6e-5, O/E 1.00 [0.95, 1.05]", 2026-10-14): its O/E is
                # against its own tier's expectation, read from the training fit (its observed count only when that
                # cannot be read)
                r["observed"] = o
                try:
                    bp = prospective(str(r["tier"]), int(r["_train_last"]))
                    by = np.asarray(bp.years)
                    by = by // 100 if by.max() > 9999 else by
                    bu = np.flatnonzero(np.isin(np.asarray(bp.places), list(places)))
                    bt = np.flatnonzero((by >= lo_y) & (by <= hi_y))
                    o_bp, e_bp = float(np.asarray(bp.y)[np.ix_(bu, bt)].sum()), float(np.asarray(bp.mu)[np.ix_(bu, bt)].sum())
                except Exception:  # noqa: BLE001 - a training fit that cannot be read leaves the observed count alone
                    continue
                if e_bp > 0:
                    r["observed"], r["expected"], r["excess"] = o_bp, e_bp, o_bp - e_bp
                    r["ratio"] = o_bp / e_bp
                    r["ratio_low"] = (chi2.ppf(0.025, 2 * o_bp) / 2 if o_bp > 0 else 0.0) / e_bp
                    r["ratio_high"] = chi2.ppf(0.975, 2 * o_bp + 2) / 2 / e_bp
                continue
            if fid == r["field"]:
                # the finding's own burden (BACKLOG 7.3): its field's events at its locus against the expectation. A
                # group answer's effect is its group's, against the place's own mix: the field's totals beside it read
                # as its counts (Santa Maria 2019: "effect 0.0057, observed 118, expected 20"), so they are the locus's
                if r.get("groups"):
                    r["locus_observed"], r["locus_expected"] = o, e_
                else:
                    r["observed"], r["expected"], r["excess"] = o, e_, o - e_
                # every finding's interpretable estimate beside its method's effect (often a model statistic: a
                # cluster's level, a step): its locus's observed over expected, with the exact Poisson interval of a
                # standardised ratio, the expected held fixed (Breslow & Day 1987; no finding had an interval,
                # 2026-10-12)
                if e_ > 0:
                    # a group finding's own estimate is its group's effect; the locus's O/E is all the field's events
                    # there, named apart (it had been the row's `ratio` beside the group's effect: "below expectation,
                    # O/E 2.35", the review of the study, 2026-10-14)
                    tag = "locus_ratio" if r.get("groups") else "ratio"
                    r[tag], r[f"{tag}_low"] = o / e_, (chi2.ppf(0.025, 2 * o) / 2 if o > 0 else 0.0) / e_
                    r[f"{tag}_high"] = chi2.ppf(0.975, 2 * o + 2) / 2 / e_
                continue
            if e_ <= 0:
                continue
            low = (chi2.ppf(0.025, 2 * o) / 2 if o > 0 else 0.0) / e_
            high = chi2.ppf(0.975, 2 * o + 2) / 2 / e_
            out.append({"finding": r["id"], "related_field": fid, "label": label, "dataset": dataset,
                        "observed": o, "expected": e_, "ratio": o / e_, "low": low, "high": high})
            if low > 1 or high < 1:
                notes.append(f"{label} ({dataset}) {o / e_:.2f} [{low:.2f}, {high:.2f}]")
        r["related"] = "; ".join(notes[:4]) or None
    return out


def _relations(scope: Scope, decl: Declaration, log) -> list[dict]:
    """Relations among the topic's fields (ARCHITECTURE §8.1, acceptance item 4; BACKLOG 3.5 the estimator): each read
    event type's own field and each code set of the topic's own codes (its admissions, its deaths), so whether the
    systems move together is asked. They are estimated jointly (`tools.relate`: one map over graph bands and lags, one
    BH) over each window of years at least two of them share: the years every field holds, and the longest span two or
    more hold; pairwise, the national study's code sets made hundreds of separate estimates (2026-10-13). Related codes'
    fields have their own table; ratios, linked shares and supports are other questions. Every row is kept,
    ``reported`` marking those at q; a study with none says why."""
    from . import tools

    fields_ = []
    for it in (i for i in scope.items if i.status == "in" and not i.reason.startswith("related code")):
        src = it.source or {}
        if src and (set(src) - {"codes", "classifier", "structure"} or not src.get("codes")):
            continue
        for node in _study_nodes(it, None):
            f = (it.dataset, it.event, node, frozenset(it.years), src or None)
            if all((g[0], g[2], json.dumps(g[4], sort_keys=True)) != (f[0], f[2], json.dumps(f[4], sort_keys=True))
                   for g in fields_):
                fields_.append(f)
    # the windows: the years every field holds, and the longest span shared by two fields or more
    windows = []
    if fields_:
        windows.append(frozenset.intersection(*(f[3] for f in fields_)))
        shared = [f[3] for f in fields_ if sum(f[3] <= g[3] for g in fields_) >= 2]
        if shared:
            windows.append(max(shared, key=len))
    out = []
    for w in dict.fromkeys(w for w in windows if len(w) >= 4):
        years = sorted(w)
        members = [f for f in fields_ if w <= f[3]]
        if len(members) < 2 or len({f[0] for f in members}) < 2:
            continue
        key = {"what": "study_relations", "fields": [list(f[:3]) + [f[4]] for f in members], "years": years,
               "q": decl.q, "data": config.data_version(), "code": config.code_key(tools.relate)}
        key = _study_key(key)
        hit = store.get_table("study_table", key)
        if hit is not None:
            rows = hit.to_pylist()
        else:
            try:
                rows = config.on_cpu_if_cuda_fails(tools.relate, [f[:3] for f in members], years, q=decl.q,
                                                   sources=[f[4] for f in members], log=log)
            except Exception as exc:  # noqa: BLE001 - a window that cannot be read is said, the other runs
                log(f"study: relations {years[0]}-{years[-1]}: {type(exc).__name__}: {exc}")
                out.append({"pair": None, "reported": False, "years": f"{years[0]}-{years[-1]}",
                            "note": f"failed: {type(exc).__name__}: {exc}"})
                continue
            rows = [{k: v for k, v in r.items() if not isinstance(v, (dict, list))} for r in rows]
            store.put_table("study_table", key, _rows_table(rows) if rows else pa.table({"p": pa.array([], pa.float64())}))
        out += [{**r, "pair": f"{r.get('leader')} ~ {r.get('field')}", "years": f"{years[0]}-{years[-1]}"}
                for r in rows if r.get("field") is not None]
    if not out:
        out.append({"pair": None, "reported": False, "note": f"no relation computed among {len(fields_)} fields: no two "
                    "of different sources share four years, or none could be read (said above)"})
    return out


def _determinants(scope: Scope, decl: Declaration, log) -> list[dict]:
    """The topic's fields against every time-varying context (ARCHITECTURE §8.2, acceptance item 4): each primary field
    with all the scope's rated contexts jointly, over graph bands and lags (`tools.determinants`), cached as a study
    table; rows are associations with their adjustment set, never effects."""
    from . import tools

    left: list = []
    contexts = gateway.rated(scope.contexts, left)
    for name, why in left:
        log(f"study: determinants: context {name} left out: {why}")
    out = []
    for it in (i for i in scope.items if i.status == "in" and "population" not in (i.source or {})):
        for node in _study_nodes(it, None):
            if len(it.years) < 4:
                continue
            x = (it.dataset, it.event, node)
            key = {"what": "study_determinants", "x": list(x), "source": it.source, "years": it.years,
                   "contexts": contexts, "q": decl.q,
                   "data": config.data_version(), "code": config.code_key(tools.determinants)}
            key = _study_key(key)
            hit = store.get_table("study_table", key)
            if hit is not None:
                rows = hit.to_pylist()
            else:
                try:
                    rows = config.on_cpu_if_cuda_fails(tools.determinants, x, contexts, list(it.years), q=decl.q,
                                                       log=log, source=it.source)
                except Exception as exc:  # noqa: BLE001 - a field that cannot be related is said, the others run
                    log(f"study: determinants of {x}: {type(exc).__name__}: {exc}")
                    continue
                flat = [{k: v for k, v in r.items() if not isinstance(v, (dict, list))} for r in rows]
                store.put_table("study_table", key, _rows_table(flat) if flat else pa.table({"p": pa.array([], pa.float64())}))
            out += [{**{k: v for k, v in r.items() if not isinstance(v, (dict, list))},
                     "pair": f"{r.get('field')} ~ {r.get('leader')}", "years": f"{it.years[0]}-{it.years[-1]}"}
                    for r in rows if r.get("field") is not None]
    # the place-level layer (§8.2 "cross-sectionally"): every topic field's place effect against the contexts in one
    # map, marginal and conditional on the others, Moran null (`dependency.field_map`)
    from . import dependency

    topic = [(it.dataset, it.event, node, it.source, list(it.years))
             for it in scope.items if it.status == "in" and "population" not in (it.source or {}) and len(it.years) >= 4
             for node in _study_nodes(it, None)]
    key = {"what": "study_field_map", "fields": topic, "contexts": contexts, "data": config.data_version(),
           "code": config.code_key(dependency.field_map)}
    key = _study_key(key)
    hit = store.get_table("study_table", key)
    if hit is not None:
        rows = hit.to_pylist()
    else:
        try:
            rows = config.on_cpu_if_cuda_fails(dependency.field_map, topic, contexts)
        except Exception as exc:  # noqa: BLE001 - the layer that cannot run is said; the time-varying rows stand
            log(f"study: place-level determinants: {type(exc).__name__}: {exc}")
            rows = []
        store.put_table("study_table", key, _rows_table(rows) if rows else pa.table({"p": pa.array([], pa.float64())}))
    out += [{"support": "between places", "field": r["x"], "leader": r["y"], "lag": 0, "rho": r.get("rho"),
             "p": r.get("p"), "reported": bool(r.get("admitted")), "partial": r.get("rho_c"),
             "pair": f"{r['x']} ~ {r['y']}", "years": "study period"} for r in rows if r.get("x")]
    return out


def _screen(scope: Scope, decl: Declaration, log) -> list[dict]:
    """The data-space screen (ARCHITECTURE §8.3, BACKLOG 10.1), at exhaustive depth: every system the store has fitted
    over the topic's years (the window chosen to read the most data), read with the topic's own systems (`tools.relation_survey`: the
    relation estimator over graph bands and lags, one BH over everything), so a field anywhere in the data that moves with the
    topic is found without being named. The relations involving a topic field are kept; each is a lead, never a cause."""
    from . import store, tools

    topic = [i for i in scope.items if i.status == "in" and not i.source]
    if not topic:
        return []
    topic_years = sorted(set.intersection(*(set(i.years) for i in topic)))
    if len(topic_years) < 4:
        log(f"study: screen: the topic's systems share {len(topic_years)} years; four are needed")
        return [{"pair": None, "screen": True, "reported": False,
                 "note": f"not run: the topic's systems share {len(topic_years)} years; four are needed"}]
    # every system the store has fitted over at least four of the topic's years; the window is the run of the topic's
    # years from its first that maximises systems × years read (the fits on it are made on demand)
    # each block's stored fits: read over a fit's own years and cut to the window (`surprise.window`), a fit on the
    # window's years alone is never made (the screen had asked every stored block for one)
    cover: dict[tuple[str, str, str], set[int]] = {}
    fits: dict[tuple[str, str, str], list[list[int]]] = {}
    # the fits the study can load: its own area's (an area study read Brazil's 577 stored blocks, none loadable under
    # its area, and fitted each on demand, unpriced: the slice past its cap, 2026-10-12)
    area = sorted(config.study_area() or []) or None
    for m in store.manifests("monolith"):
        k = m["key"]
        if k.get("codes") or k.get("source") or not k.get("block") or not k.get("event") or (k.get("area") or None) != area:
            continue
        cover.setdefault((k["dataset"], k["event"], k["block"]), set()).update(k.get("years") or [])
        fits.setdefault((k["dataset"], k["event"], k["block"]), []).append(sorted(k.get("years") or []))
    best = (0, topic_years[:4])
    for e in range(3, len(topic_years)):
        window = topic_years[:e + 1]
        n = sum(1 for ys in cover.values() if set(window) <= ys)
        best = max(best, (n * len(window), window))
    years = best[1]
    plan: dict[tuple, set[str]] = {}
    for it in topic:
        plan.setdefault((it.dataset, it.event, tuple(it.years)), set()).update(it.blocks)
    topic_keys = {(i.dataset, i.event) for i in topic}
    for (ds, ev, block), _ys in cover.items():
        if (ds, ev) in topic_keys:
            continue
        held = [f for f in fits[(ds, ev, block)] if set(years) <= set(f)]
        if held:
            plan.setdefault((ds, ev, tuple(min(held, key=len))), set()).add(block)
    spec = [(ds, ev, sorted(bl), list(ys)) for (ds, ev, ys), bl in plan.items()]
    log(f"study: screen over {len(spec)} systems, {sum(len(b) for *_, b in spec)} blocks, {years[0]}-{years[-1]}")
    try:
        found = tools.relation_survey(spec, years, q=decl.q, log=log)
    except Exception as exc:  # noqa: BLE001 - the screen failing leaves the study's own relations; a failure row
        # the gate reads (`body`): a crash caught and logged had let two slices pass with no screen (2026-10-12)
        log(f"study: screen: {type(exc).__name__}: {exc}")
        return [{"pair": None, "screen": True, "reported": False, "note": f"failed: {type(exc).__name__}: {exc}"}]
    mine = {f"{i.dataset}:{i.event}:" for i in topic}
    out = []
    for x in found:
        if not any(f.startswith(tuple(mine)) for f in x.fields):
            continue
        out.append({"pair": " ~ ".join(x.fields), "support": x.locus.get("band") or x.locus.get("scale"),
                    "lag": x.locus.get("lag"), "rho": float(x.effect), "p": float(x.p), "q": float(x.q),
                    "reported": True, "screen": True, "years": f"{years[0]}-{years[-1]}"})
    if not out:
        # the screen ran and found nothing with a topic field at q: said, a row the body reads (an empty result had read
        # as a screen never run, 2026-10-13)
        out.append({"pair": None, "screen": True, "reported": False,
                    "note": f"screened {len(spec)} systems, {sum(len(b) for *_, b in spec)} blocks, {years[0]}-{years[-1]}: "
                            f"no relation with a topic field at q {decl.q:g}"})
    return out


def _institution_explains(rows: list[dict]) -> None:
    """A finding of a source at a place and period where an establishment of that source stepped up (an institution
    finding: a unit that began notifying, a ward that opened) is read as recording, not as the events: its class
    becomes "system", the institution named in its reason (São Leopoldo's health secretariat went from 0 notifications
    in 2021 to 81 in 2022, and the region's excess, schooling and autochthony findings there read as signals, the RS
    slice's review, 2026-10-13). Above-expectation findings only; the institution finding itself keeps its class."""
    steps = [r for r in rows if str(r.get("question")) == "institution" and r.get("first_year")]
    for r in rows:
        if str(r.get("question")) == "institution" or r.get("class") != "signal" or (r.get("ratio") or 0) <= 1:
            continue
        mine = set(r.get("_places") or [])
        for st in steps:
            if (st["dataset"] == r["dataset"] and mine & set(st.get("_places") or [])
                    and int(st["first_year"]) <= int(r.get("last_year") or 0)
                    and int(r.get("first_year") or 0) <= int(st.get("last_year") or st["first_year"])):
                r["class_reason"] = (f"an establishment stepped up there in {st['first_year']} (institution finding "
                                     f"{st['id']}): recording, not the events; was signal ({r.get('class_reason')})")
                r["class"] = "system"
                break


def _recording_groups(rows: list[dict]) -> None:
    """A group finding whose groups are a column's missing levels ("not recorded", "value missing") departs in the
    records' completeness, not in the events: its class becomes "system", the reason said, the column's completeness in
    estimates.parquet's completeness (Inhapi's "Necrópsia: not recorded" and "Recebeu assistência médica: not recorded" had led the
    Alagoas study's first story as signals, 2026-10-14)."""
    for r in rows:
        groups = r.get("_groups") or []
        if r.get("class") != "signal" or not groups:
            continue
        levels = {str(g).partition("=")[2] for g in groups}
        if levels <= {"not recorded", "value missing"}:
            r["class_reason"] = (f"the group is its column's {' and '.join(sorted(levels))} level: the records' "
                                 f"completeness, not the events (estimates.parquet); was signal ({r.get('class_reason')})")
            r["class"] = "system"


def _institution_facts(rows: list[dict], log) -> None:
    """A finding concentrated in an establishment is an institutional finding, read with the establishment's facts
    (ARCHITECTURE §9.1, BACKLOG 7.1): each institution's CNES registration at the finding's first and last year (name,
    type, care level, SUS link, beds, obstetric centre, neonatal unit; `gateway.establishment_facts`), absent in the
    first year meaning it opened within the finding. Written to ``institution_facts`` on the row."""
    def short(v) -> str:
        v = str(v or "")
        return v.rsplit(" (", 1)[0] if v.endswith(")") else v

    for r in rows:
        codes = r.get("_institutions") or []
        if not codes or not r.get("last_year"):
            continue
        try:
            last = gateway.establishment_facts(codes, int(r["last_year"]))
            first = gateway.establishment_facts(codes, int(r["first_year"])) if r.get("first_year") else last
        except Exception as exc:  # noqa: BLE001 - facts that cannot be read leave the finding without them, said
            log(f"study: establishment facts {codes}: {type(exc).__name__}: {exc}")
            continue
        parts = []
        for c in codes:
            f_ = last.get(c)
            if f_ is None:
                parts.append(f"{c}: not registered in {r['last_year']}")
                continue
            beds = sum(int(x) for x in (f_.get("QTLEITP1"), f_.get("QTLEITP2")) if str(x or "").isdigit())
            parts.append(f"{short(f_.get('CNES'))} ({c}), {short(f_.get('CODUFMUN'))}: {short(f_.get('TP_UNID'))}; "
                         f"{short(f_.get('VINC_SUS'))}; {beds} beds; obstetric centre {short(f_.get('CENTROBS'))}; "
                         f"neonatal unit {short(f_.get('CENTRNEO'))}"
                         + ("" if c in first else f"; opened after {r['first_year']}"))
        r["institution_facts"] = " | ".join(parts) or None
        r["institution_volume"] = _institution_volume(r, codes, log)


@functools.lru_cache(maxsize=64)
def _facility_volume(dataset: str, event: str, year: int) -> dict[str, int]:
    """Each facility's events of every code in a year (`facility.facility_cube` summed over residence and code), once a
    process: every finding row had read the national cube and filtered it per code (31.8 s of the leptospirosis slice,
    the review of the study, 2026-10-14)."""
    from . import facility

    t = facility.facility_cube(dataset, event, year).group_by("facility").aggregate([("y", "sum")])
    return dict(zip([str(f) for f in t.column("facility").to_pylist()], [int(v or 0) for v in t.column("y_sum").to_pylist()],
                    strict=True))


def _institution_volume(r: dict, codes: list[str], log) -> str | None:
    """Each institution's events of every code, the year before the finding and in its last (`_facility_volume`): a
    ward whose whole activity grew reads as a departure of any one code there (BACKLOG 7.1's other-chapter volume)."""
    dataset, event = r.get("dataset"), r.get("_event")
    first, last = r.get("first_year"), r.get("last_year")
    if not (dataset and event and first and last):
        return None
    published = gateway.published_years(dataset)
    base = int(first) - 1 if int(first) - 1 in published else int(first)
    try:
        volume = {y: _facility_volume(dataset, event, y) for y in sorted({base, int(last)})}
    except Exception as exc:  # noqa: BLE001 - a volume that cannot be read leaves the finding without it, said
        log(f"study: institution volume {dataset} {codes}: {type(exc).__name__}: {exc}")
        return None
    parts = []
    for c in codes:
        n = {y: v.get(str(c), 0) for y, v in volume.items()}
        ratio = f" (×{n[int(last)] / n[base]:.2f})" if n.get(base) else ""
        parts.append(f"{c}: {n[base]:,} {event} events of every code in {base}, {n[int(last)]:,} in {last}{ratio}")
    return " | ".join(parts) or None


def _context_table(decl: Declaration, scope: Scope, places: list[dict], names: dict, log) -> list[dict]:
    """Every context of the scope (pegasus_data's declared fields over their declared denominators,
    `gateway.context_value`) per municipality of the study's places, each year and over the period: the covariates an
    ecological model of the rates reads beside estimates.parquet's municipalities. A context without a value for a place-year is an empty
    value, never zero."""
    us = sorted({int(r["place"]) for r in places if r.get("place") is not None})
    if not us or not scope.contexts:
        return []
    arr = np.asarray(us, dtype=np.int64)
    period = f"{decl.years[0]}-{decl.years[-1]}"
    out: list[dict] = []
    left: list = []
    spec_of = gateway.declared_fields()
    for entry in gateway.rated(scope.contexts, left):
        name = gateway.context_name(entry)
        numerators, _, over, declared = gateway._context_entry(entry)
        spec = spec_of.get(numerators[0]) or {}
        unit_ = str(spec.get("unit") or "")
        about = {"variable": name, "unit": unit_ if (" per " in unit_ or " over " in unit_) else
                 f"{unit_} per {'resident' if over == 'population' else over}",
                 "denominator_kind": "residents" if over == "population" else over,
                 "value_label": " ".join(str(spec.get("what") or "").split()) or None}
        held = ", ".join(str(x) for x in declared)
        for y in [*decl.years, None]:
            window = list(decl.years) if y is None else [int(y)]
            inside = [x for x in declared if window[0] <= x <= window[-1]]
            read = inside or [min(declared, key=lambda x: (abs(x - window[-1]), -x))] if declared else []
            try:
                v, _ = gateway.context_value(entry, window, arr)
            except Exception as exc:  # noqa: BLE001 - a context without data for a year: no row, said
                log(f"study: context {name} {y or period}: {type(exc).__name__}: {exc}")
                continue
            note = (f"read from {', '.join(str(x) for x in read) or 'no year'} (the source holds {held}); "
                    f"{spec.get('source')}")
            for u, val in zip(us, np.asarray(v, dtype=float), strict=True):
                nm = names.get(str(u)) or {}
                out.append(_estimate_row("contexts", "context", {
                    "geography": "municipality", "place": u, "place_name": nm.get("name"), "state": nm.get("uf_sigla"),
                    "per": 1.0,
                    **_period(y, None if y is not None else period), **about, "note": note},
                    estimate=float(val) if np.isfinite(val) else None))
    for name_, why in left:
        log(f"study: context {name_} left out: {why}")
    return out


def _spatial_autocorrelation(places: list[dict], q_level: float, log) -> list[dict]:
    """Global Moran's I and the local Moran (LISA) of each count field's municipal smoothed standardised ratios over
    the period (`places`' smoothed_smr), on the municipalities' contiguity, row-standardised; 999 permutations (esda);
    each municipality's quadrant where its local p passes ``q_level`` after Benjamini-Hochberg across the
    municipalities, else not significant. A municipality without a neighbour among the study's is left out. What a
    spatial paper reports beside its map: whether high ratios cluster, and where."""
    import esda
    import libpysal
    from statsmodels.stats.multitest import multipletests

    from . import graphs

    by: dict[str, dict] = {}
    for r in places:
        if r["measure"] == "smoothed_smr" and r.get("period_kind") == "period" and r.get("estimate") is not None:
            f = by.setdefault(r["field"], {"label": r.get("label"), "dataset": r.get("dataset"), "v": {}, "name": {}})
            f["v"][int(r["place"])] = float(r["estimate"])
            f["name"][int(r["place"])] = (r.get("place_name"), r.get("state"))
    out = []
    for fid, f in by.items():
        us = np.array(sorted(f["v"]), dtype=np.int64)
        if len(us) < 30:
            continue
        e = graphs.edges(us, "contiguity")
        neighbours = {i: [] for i in range(len(us))}
        for i, j in e:
            neighbours[int(i)].append(int(j))
            neighbours[int(j)].append(int(i))
        keep = [i for i in range(len(us)) if neighbours[i]]
        if len(keep) < 30:
            continue
        index = {old: new for new, old in enumerate(keep)}
        w = libpysal.weights.W({index[i]: [index[j] for j in neighbours[i] if j in index] for i in keep},
                               silence_warnings=True)
        w.transform = "r"
        y = np.array([f["v"][int(us[i])] for i in keep])
        seed = config.seed(fid, "lisa") % (2**32)
        try:
            np.random.seed(seed)            # esda's global Moran draws its permutations from numpy's global state
            mg = esda.Moran(y, w, permutations=999)
            # 9,999 permutations: at 999 a local p cannot fall under 0.001, and Benjamini-Hochberg over 497 places then
            # passes none (leptospirosis' cases in RS, 2026-10-15)
            ml = esda.Moran_Local(y, w, permutations=9999, seed=seed)
        except Exception as exc:  # noqa: BLE001 - a field whose autocorrelation cannot be computed is said
            log(f"study: spatial autocorrelation {fid}: {type(exc).__name__}: {exc}")
            continue
        base = {"field": fid, "label": f["label"], "dataset": f["dataset"], "geography": "municipality",
                "period_kind": "period"}
        out.append(_estimate_row("municipalities", "moran_global", {**base, "geography": _whole()[0],
                                 "place": _whole()[1], "model": "row-standardised contiguity, 999 permutations"},
                                 estimate=float(mg.I), p=float(mg.p_sim), denominator=float(len(y)),
                                 denominator_kind="municipalities"))
        qs = multipletests(ml.p_sim, method="fdr_bh")[1]
        quad = {1: "high-high", 2: "low-high", 3: "low-low", 4: "high-low"}
        for k, i in enumerate(keep):
            u = int(us[i])
            nm, st = f["name"].get(u, (None, None))
            out.append(_estimate_row("municipalities", "lisa", {**base, "place": u, "place_name": nm, "state": st,
                                     "value": quad[int(ml.q[k])] if qs[k] <= q_level else "not significant",
                                     "model": "local Moran on row-standardised contiguity, 9,999 permutations"},
                                     estimate=float(ml.Is[k]), p=float(ml.p_sim[k]), q=float(qs[k])))
    return out


def _ecological(places: list[dict], contexts: list[dict], log) -> list[dict]:
    """The ecological association of each count field with the study's contexts, as a paper relating rates to place
    characteristics declares it: the municipalities' events over the period, negative-binomial (NB2) regression with
    the events expected at the area's own age-sex rates as offset (the coefficients act on the standardised ratio), each
    context standardised across the municipalities (a ratio per standard deviation); each context alone, then all
    those with values in nine places of ten together (complete cases, a variance inflation over 5 said); Wald intervals
    robust to clustering by health region (sandwich; heteroskedasticity-robust under ten regions); Moran's I of the
    full model's Pearson residuals on contiguity with its permutation p. Associations between places, never effects on
    persons (the ecological fallacy). The contexts had been collected per municipality and related to nothing (three
    paper audits, 2026-10-14)."""
    import statsmodels.api as sm

    from . import graphs

    ctx: dict[str, dict[int, float]] = {}
    about: dict[str, dict] = {}
    for r in contexts:
        if r.get("period_kind") == "period" and r.get("estimate") is not None and r.get("place") is not None:
            ctx.setdefault(r["variable"], {})[int(r["place"])] = float(r["estimate"])
            about.setdefault(r["variable"], {"unit": r.get("unit"), "label": r.get("value_label")})
    if not ctx:
        return []
    fields_: dict[str, dict] = {}
    for r in places:
        if r.get("period_kind") != "period":
            continue
        fid, u = r["field"], int(r["place"])
        f = fields_.setdefault(fid, {"label": r.get("label"), "dataset": r.get("dataset"), "y": {}, "e": {}, "region": {}})
        if r["measure"] == "count":
            f["y"][u] = float(r["estimate"])
            f["region"][u] = r.get("health_region") or r.get("state")
        elif r["measure"] == "smr" and str(r.get("comparator", "")).startswith("the area"):
            f["e"][u] = float(r["denominator"])
    out = []
    for fid, f in fields_.items():
        us = np.array(sorted(u for u in f["y"] if f["e"].get(u, 0) > 0), dtype=np.int64)
        if len(us) < 20:
            log(f"study: ecological {fid}: {len(us)} municipalities with an expectation, fewer than 20: not modelled")
            continue
        y = np.array([f["y"][u] for u in us])
        off = np.log(np.array([f["e"][u] for u in us]))
        groups = np.unique([str(f["region"].get(u)) for u in us], return_inverse=True)[1]
        usable = {}
        for name, vals in ctx.items():
            v = np.array([vals.get(int(u), np.nan) for u in us])
            ok = np.isfinite(v)
            if ok.mean() >= 0.9 and np.nanstd(v) > 0:
                usable[name] = v
        if not usable:
            continue
        base = {"field": fid, "label": f["label"], "dataset": f["dataset"], "geography": "municipality",
                "period_kind": "period"}

        # the field's dispersion once, from its null model (the expected events alone): every regression of it is
        # then a negative-binomial GLM at that dispersion, fitted by IRLS. A maximum-likelihood fit of the
        # dispersion in each of sixty regressions had failed to converge on wide designs and its Newton fallback
        # held the suicide study's products for half an hour (2026-10-15)
        try:
            null = sm.NegativeBinomial(y, np.ones((len(y), 1)), offset=off, loglike_method="nb2").fit(disp=0,
                                                                                                    maxiter=200)
            alpha = float(null.params[-1])
        except Exception:  # noqa: BLE001 - the moments' estimate where the null's likelihood will not fit
            alpha = float("nan")
        if not np.isfinite(alpha) or alpha <= 0:
            mu0 = np.exp(off) * y.sum() / np.exp(off).sum()
            alpha = max(float(((y - mu0) ** 2 - mu0).sum() / (mu0 ** 2).sum()), 1e-8)
        family_ = f"negative binomial (dispersion {alpha:.3g}, from the field's null model)"

        def fit(names: list[str], usable=usable, y=y, off=off, groups=groups, robust_only=False, alpha=alpha,
                family_=family_):
            Z = np.column_stack([(usable[n] - np.nanmean(usable[n])) / np.nanstd(usable[n]) for n in names])
            ok = np.isfinite(Z).all(1)
            X = sm.add_constant(Z[ok], has_constant="add")
            g = groups[ok]
            # cluster-robust where there are ten regions and more of them than parameters
            cov = ({"cov_type": "cluster", "cov_kwds": {"groups": g}}
                   if len(np.unique(g)) >= max(10, len(names) + 2) and not robust_only else {"cov_type": "HC1"})
            res = sm.GLM(y[ok], X, family=sm.families.NegativeBinomial(alpha=alpha), offset=off[ok]).fit(**cov)
            return res, ok, cov["cov_type"], family_

        def rows(res, names, ok, kind, cov_type, base=base, usable=usable, fid=fid) -> list[dict]:
            got = []
            for k, name in enumerate(names, start=1):
                b, se, p = float(res.params[k]), float(res.bse[k]), float(res.pvalues[k])
                if not (np.isfinite(b) and np.isfinite(se) and se > 0 and np.isfinite(np.exp(b + 1.96 * se))):
                    log(f"study: ecological {fid} {name} ({kind}): no finite interval, not written")
                    continue
                got.append(_estimate_row(
                    "associations", "association", {**base, "variable": name, "value_label": about[name]["label"],
                                                    "note": f"1 SD = {np.nanstd(usable[name]):.4g} "
                                                            f"{about[name]['unit'] or ''}".strip()},
                    estimate=float(np.exp(b)), low=float(np.exp(b - 1.96 * se)), high=float(np.exp(b + 1.96 * se)),
                    interval=f"Wald, {'cluster-robust by health region' if cov_type == 'cluster' else 'HC1'}", p=p,
                    denominator=float(ok.sum()), denominator_kind="municipalities", model=kind))
            return got
        alone = []
        for name in usable:
            try:
                res, ok, ct, fam = fit([name])
            except Exception as exc:  # noqa: BLE001 - a context that cannot be fitted alone is said, the others go on
                log(f"study: ecological {fid} {name}: {type(exc).__name__}: {exc}")
                continue
            alone += rows(res, [name], ok, f"{fam}, offset the expected events: alone", ct)
        # each context alone is one test among the field's contexts: its Benjamini-Hochberg q across them
        if alone:
            from statsmodels.stats.multitest import multipletests

            for r_, q_ in zip(alone, multipletests([r_["p"] for r_ in alone], method="fdr_bh")[1], strict=True):
                r_["q"] = float(q_)
        out += alone
        # the joint model's contexts: none redundant (dropped one at a time by the largest variance inflation until
        # none exceeds 5, the usual rule), and fewer parameters than the clusters a robust covariance is taken over
        names = list(usable)
        complete = np.isfinite(np.column_stack([usable[n] for n in names])).all(1)
        dropped: list[str] = []
        if len(names) > 1:
            # first the contexts that are combinations of others (a temperature, its monthly maximum and minimum):
            # a rank-revealing QR keeps an independent set; a pseudo-inverse's inflations had looked finite on a
            # singular design and the joint fit had no interval (leptospirosis in RS, 2026-10-15)
            from scipy.linalg import qr

            Z = np.column_stack([usable[n] for n in names])[complete]
            Zs = (Z - Z.mean(0)) / np.where(Z.std(0) > 0, Z.std(0), 1.0)
            _, R, piv = qr(Zs, mode="economic", pivoting=True)
            rank = int((np.abs(np.diag(R)) > 1e-6 * np.abs(R[0, 0])).sum())
            dropped += [names[i] for i in sorted(piv[rank:])]
            names = [names[i] for i in sorted(piv[:rank])]
        while len(names) > 1:
            Z = np.column_stack([usable[n] for n in names])[complete]
            Zs = (Z - Z.mean(0)) / np.where(Z.std(0) > 0, Z.std(0), 1.0)
            try:
                vif = np.diag(np.linalg.inv(np.corrcoef(Zs, rowvar=False)))
            except np.linalg.LinAlgError:
                vif = np.full(len(names), np.inf)
            worst = int(np.argmax(np.where(np.isfinite(vif), vif, np.inf)))
            if np.isfinite(vif[worst]) and vif[worst] <= 5:
                break
            dropped.append(names.pop(worst))
        clusters = len(np.unique(groups[complete]))
        if len(names) > 1 and len(us) > len(names) + 10:
            try:
                res, ok, ct, fam = fit(names, robust_only=len(names) + 2 > clusters)
            except Exception as exc:  # noqa: BLE001 - the joint model that cannot be fitted is said
                log(f"study: ecological {fid} joint: {type(exc).__name__}: {exc}")
                continue
            kind = (f"{fam}, offset the expected events: with the {len(names) - 1} other contexts"
                    + (f"; left out of it as combinations of the others or for a variance inflation over 5: "
                       f"{', '.join(dropped)}" if dropped else ""))
            out += rows(res, names, ok, kind, ct)
            # spatial dependence the joint model leaves: Moran's I of its Pearson residuals on contiguity
            r = np.asarray(res.resid_pearson)
            e = graphs.edges(us[ok], "contiguity")
            if len(e):
                def moran(v: np.ndarray, e=e) -> float:
                    v = v - v.mean()
                    return float(len(v) / (2 * len(e)) * 2 * (v[e[:, 0]] * v[e[:, 1]]).sum() / (v @ v))
                obs = moran(r)
                rng = np.random.default_rng(config.seed(fid, "moran"))
                null = np.array([moran(rng.permutation(r)) for _ in range(999)])
                out.append(_estimate_row("associations", "moran_i", {**base, "model": kind},
                                         estimate=obs, p=float((1 + (null >= obs).sum()) / 1000),
                                         denominator=float(ok.sum()), denominator_kind="municipalities"))
    return out


def _context_profiles(decl: Declaration, scope: Scope, rows: list[dict], log) -> list[dict]:
    """Every finding's context profile (ARCHITECTURE §9, BACKLOG 7.2): for each context of the scope (pegasus_data's
    declared fields, each over its declared denominator, `gateway.context_value`), the mean over the finding's places
    in the study's period and its percentile among Brazil's municipalities. Each finding row also names its three most
    extreme contexts (``context``). A context that cannot be read is skipped and logged, never zero."""

    if not rows or not scope.contexts:
        return []
    pop = gateway.population(decl.years[-1:]).group_by("u").aggregate([("n", "sum")])
    places = np.asarray(pop.column("u").to_numpy())
    index = {int(u): i for i, u in enumerate(places)}
    # a context is a rate over its declared denominator; a count with none would rank places by size alone (every
    # capital at p100), so size enters once, as the residents
    values = {"population (residents)": np.asarray(pop.column("n_sum").to_numpy(), dtype=float)}
    left: list = []
    for entry in gateway.rated(scope.contexts, left):
        name = gateway.context_name(entry)
        try:
            v, _ = gateway.context_value(entry, list(decl.years), places)
        except Exception as exc:  # noqa: BLE001 - a context without data for the period is skipped, said
            log(f"study: context {name}: {type(exc).__name__}: {exc}")
            continue
        if np.isfinite(v).sum() >= min(100, max(10, len(places) // 2)):
            values[name] = v
        else:
            log(f"study: context {name}: {int(np.isfinite(v).sum())} of {len(places)} places hold a value: left out")
    for name_, why in left:
        log(f"study: context {name_} left out: {why}")
    out = []
    ranked = {name: np.sort(v[np.isfinite(v)]) for name, v in values.items()}

    def percentile(a: np.ndarray, m: float) -> float:
        """scipy's percentileofscore of ``m`` in ``a`` (kind "rank": ties count half), on ``a`` sorted once a context:
        it had ranked the whole context again for every finding (the review of the study, 2026-10-14)."""
        left, right = int(np.searchsorted(a, m, "left")), int(np.searchsorted(a, m, "right"))
        return (left + right + (1 if right > left else 0)) * 50.0 / len(a)

    for r in rows:
        idx = [index[u] for u in r.get("_places") or [] if u in index]
        if not idx:
            continue
        extreme = []
        for name, v in values.items():
            here = v[idx]
            if not np.isfinite(here).any():
                continue
            m = float(np.nanmean(here))
            pct = percentile(ranked[name], m)
            out.append({"finding": r["id"], "context": name, "value": m, "percentile": pct,
                        "places_with_value": int(np.isfinite(here).sum()), "places": len(idx)})
            extreme.append((abs(pct - 50.0), name, pct))
        r["context"] = "; ".join(f"{n} p{p:.0f}" for _, n, p in sorted(extreme, reverse=True)[:3]) or None
    return out


def _descriptive_cells(it: Item, s, f, label: str, d) -> list[dict]:
    """A measure's, an interval's or a share's field by year, nationally and by state (ARCHITECTURE §6.4):
    - a positive measure or an interval: the records' own median and 90th percentile (`gateway.mark_quantiles`; an
      interval's mark is days + 1, given in days);
    - a count-valued measure: the mean per event;
    - a share (n events, y the share): the share with its exact (Clopper–Pearson) 95% interval."""
    from scipy.stats import beta

    kind = (s.source or {}).get("source", "events")
    days = 1.0 if (s.source or {}).get("anchor") else 0.0
    leaves = [d.leaves.index(c) for c in s.expectations.registry.leaves(f.node) if c in d.leaves]
    sel = np.isin(d.e, leaves)
    t_of, n, y = d.t[sel], d.n[sel].astype(float), d.y[sel].astype(float)
    src = s.source or {}
    # the node's codes (a whole tree's field reads every event)
    codes = [] if f.node == "*" else list(s.expectations.registry.leaves(f.node))
    quant: dict[int, dict] = {}
    out = []

    period = f"{int(np.asarray(d.years)[0])}-{int(np.asarray(d.years)[-1])}"

    def row(level: str, unit: str, t: int | None, keep: np.ndarray) -> list[dict]:
        nn = float(n[keep].sum())
        base = {"field": f.id, "label": label, "dataset": it.dataset, "geography": level, "place": unit,
                **_period(int(np.asarray(d.years)[t]) if t is not None else None, None if t is not None else period)}
        if nn <= 0:
            return [_estimate_row("rates", "count", base, estimate=nn)]
        if kind == "mark":
            # the records' own median and 90th percentile (`gateway.mark_quantiles`), never the log moments' exp(mean)
            year = int(np.asarray(d.years)[t])
            if year not in quant:
                quant[year] = {int(r["state"]): r for r in gateway.mark_quantiles(
                    it.dataset, it.event, year, src["mark"], tuple(src["bounds"]), src.get("classifier"),
                    tuple(src.get("missing") or ()), src.get("anchor"), int(src.get("sign", 1)), tuple(codes)).to_pylist()}
            # a median per state or Brazil: a region's or a several-state area's is not read (int("43+42") had raised)
            q = quant[year].get(0 if unit == "BR" else int(unit) if str(unit).isdigit() else None)
            if q is None:
                return [_estimate_row("rates", "count", base, estimate=nn)]
            valued = {"denominator": float(q["n"]), "denominator_kind": "records with a valid value",
                      "unit": "days" if days else None}
            return [_estimate_row("rates", "median", base, estimate=q["q50"] - days, **valued),
                    _estimate_row("rates", "quantile", base, value="0.9", estimate=q["q90"] - days, **valued)]
        if kind == "count":
            return [_estimate_row("rates", "mean", base, estimate=float((n[keep] * y[keep]).sum() / nn), denominator=nn,
                                  denominator_kind="the field's events")]
        k = float((n[keep] * y[keep]).sum())
        return [_estimate_row("rates", "proportion", base, estimate=k / nn,
                              low=float(beta.ppf(0.025, k, nn - k + 1)) if k > 0 else 0.0,
                              high=float(beta.ppf(0.975, k + 1, nn - k)) if k < nn else 1.0, interval="Clopper-Pearson",
                              numerator=k, denominator=nn, denominator_kind="the field's events")]

    below = _levels_below(np.asarray(d.places)[d.u[sel]])
    # each year, then the period (a median is read per year only: no period row for a mark)
    for t in [*range(len(d.years)), *([None] if kind != "mark" else [])]:
        at = t_of == t if t is not None else np.ones(len(t_of), bool)
        out += row(*_whole(), t, at)
        for level, unit, sel_u in below:
            out += row(level, unit, t, at & sel_u)
    if src.get("source") == "linked":
        out += _link_sensitivity_rows(it, f, label, [r for r in out if r["geography"] == _whole()[0]
                                                     and r["measure"] == "proportion"])
    return out


def _link_sensitivity_rows(it: Item, f, label: str, whole: list[dict]) -> list[dict]:
    """A same-event link's share among the topic's records it can pair: those meeting its side's condition (its
    ``where``, and the validations that event must pass on this side: sih_deaths_to_sim pairs admissions that ended in
    death with certificates of deaths in hospital). On the admissions' side it is the link's sensitivity for the topic;
    on the certificates' the share of the topic's hospital deaths with an SUS admission ending in death. The linked
    share over every record had been called the sensitivity (the audit: 14 % of all admissions, 88 % of those that
    ended in death, 2026-10-14)."""
    from scipy.stats import beta

    src = it.source or {}
    eligible = _link_eligible(it, [int(r["first"]) for r in whole if r["period_kind"] == "year"])
    if not eligible:
        return []
    cond = gateway.link_side_condition(src["link"], src.get("side") or "left")
    out = []
    for r in whole:
        n = (float(sum(eligible.values())) if r["period_kind"] != "year" else float(eligible.get(int(r["first"]), 0.0)))
        k = float(r.get("numerator") or 0.0)
        if n <= 0:
            continue
        kk = min(k, n)
        base = {c: r.get(c) for c in ("field", "dataset", "geography", "place", "period_kind", "first", "last")}
        out.append(_estimate_row("rates", "proportion", {**base, "label": label,
                                                         "stratum": f"records the link can pair ({cond})"},
                                 estimate=k / n, low=float(beta.ppf(0.025, kk, n - kk + 1)) if kk > 0 else 0.0,
                                 high=float(beta.ppf(0.975, kk + 1, n - kk)) if kk < n else 1.0,
                                 interval="Clopper-Pearson", numerator=k, denominator=n,
                                 denominator_kind="the records the link can pair (on this side: its sensitivity for "
                                                  "the topic)"))
    return out


def _link_eligible(it: Item, years: list[int]) -> dict[int, float]:
    """The item's records (its codes, the area's residents) that meet its link side's condition, each year: read as the
    link reads its side (pegasus_data's role tables of the national year, the condition over role names)."""
    from dataclasses import replace

    from pegasus_data.linkage.engine import Side, _side_table

    src = it.source or {}
    link, side = src.get("link"), src.get("side") or "left"
    spec = gateway.link_specs().get(link or "")
    cond = gateway.link_side_condition(link, side) if spec is not None else ""
    if not cond:
        return {}
    sd = spec.left if side == "left" else spec.right
    by_column = {r["column"]: r["role"] for r in gateway.roles(sd.dataset)}
    home = by_column.get(gateway._strata(sd.dataset)["residence"])
    coded = by_column.get(src.get("classifier") or "")
    codes = [str(c).upper() for c in src.get("codes") or []]
    if not home or (codes and not coded):
        return {}
    where = cond + ("" if not codes else " AND (" + " OR ".join(
        f"starts_with(upper(trim(CAST(\"{coded}\" AS VARCHAR))), '{c}')" for c in codes) + ")")
    out = {}
    area = config.study_area()
    for y in years:
        t = _side_table(replace(Side(sd.dataset), where=where), [home], period=int(y), geography="BR")
        u = [str(v or "")[:6] for v in t.column(home).to_pylist()]
        keep = config.in_area(np.array([int(c) if c.isdigit() else -1 for c in u])) if area is not None \
            else np.ones(len(u), bool)
        out[int(y)] = float(keep.sum())
    return out


def _finding(x: leads.Lead, it: Item, label: str, names: dict) -> dict:
    places = [str(p) for p in (x.locus.get("places") or [])]
    years = x.locus.get("years") or []
    tri = x.robustness.get("triage") or {}
    corr = (x.replications or {}).get("corroboration") or {}
    return {
        "id": x.id, "component": questions.components(x.estimand, x.provenance.get("methods")), "question": x.estimand,
        "field": x.fields[0], "label": label, "dataset": it.dataset, "tier": x.tier,
        "places": ", ".join(places[:20]) + (f" (+{len(places) - 20})" if len(places) > 20 else ""),
        "place_names": ", ".join(f"{(names.get(p) or {}).get('name', p)}/{(names.get(p) or {}).get('uf_sigla', '')}"
                                 for p in places[:8]) + (f" (+{len(places) - 8})" if len(places) > 8 else ""),
        "n_places": len(places), "groups": _group_text(it, x.locus.get("groups") or []) or None,
        "first_year": int(years[0]) if years else None,
        "last_year": int(years[-1]) if years else None,
        "effect": float(x.effect), "effect_unit": x.scale.replace("_", " "),
        "interval_low": float(x.interval[0]) if x.interval else None,
        "interval_high": float(x.interval[1]) if x.interval else None,
        "q": float(x.q), "family": x.family, "methods": ", ".join(sorted(x.provenance.get("methods") or []))
        if isinstance(x.provenance.get("methods"), list) else str(x.provenance.get("methods") or ""),
        "class": tri.get("class"), "class_reason": tri.get("reason"), "class_grade": tri.get("grade"),
        "replication": x.replication, "corroborated": bool(corr.get("ok")), "corroboration": _corroboration_text(corr),
        "status": x.status, **(_COMPOSITION if x.locus.get("groups_by") and x.locus.get("groups_by") != gateway._strata(
            it.dataset, it.event).get("race") else _reliability(x.provenance.get("methods") or [x.estimand]))}


def _group_text(it: Item, groups: list[str]) -> str:
    """A finding's groups as a reader names them: "Evolução do Caso: Vivo (1)" for "EVOLUCAO=1", the code kept beside
    its label (`gateway.value_labels`, weighed on every value the column holds over the item's years); a code no table
    decodes stays a code, said undecoded."""
    out = []
    for g in groups:
        column, _, value = str(g).partition("=")
        if not value:
            out.append(str(g))
            continue
        try:
            name = gateway.column_name(it.dataset, column)
            labels = gateway.value_labels(it.dataset, it.event, column, tuple(int(y) for y in it.years))
        except Exception:  # noqa: BLE001 - a column pegasus_data cannot describe is named as recorded
            name, labels = column, {}
        if value in ("not recorded", "value missing") or value in labels:
            shown = f"{labels[value]} ({value})" if value in labels else value
        else:
            shown = f"{value} (undecoded)"
        out.append(f"{name}: {shown}")
    return ", ".join(out)


#: a non-race composition's group answer: read against the place's own mix in its other years (`tools.own_mix`), so it
#: needs no population and does not restate demography (OPEN_QUESTIONS 17). Its null is its own (`Session.composition_null`:
#: 4 of 210 column-worlds with any finding, 1.9 %, within q), not the generic `group_disparity` record, whose worlds
#: hold no compositions. The race stratum is read against the place's own population by race and keeps that record
_COMPOSITION = {"uncalibrated": False, "reliability": "a composition read against the place's own usual mix (leave-one-"
                "year-out, shrunk to its state's and Brazil's); null worlds: findings in 4 of 210 column-worlds (1.9 %)"}


@functools.cache
def _method_records() -> dict:
    """The methods' records (`tools.method_status`: null worlds, planted signals), read once per study."""
    from . import tools

    return tools.method_status()


def _reliability(methods) -> dict:
    """A finding's methods as measured on null worlds: ``uncalibrated`` when every method that raised it finds
    departures in null worlds beyond its error rate (calibrated False), with the measured share in ``reliability``. A
    finding is never removed for it (validation characterises, it does not gate): the report says it, and a story made
    only of such findings ranks after the others. `group_disparity` had findings in 60 of 125 null worlds (STATUS),
    and the survey printed 107 of its answers as signals (2026-10-11)."""
    from .harness import GRID_NOT_JUDGED

    names = [m.strip() for m in (methods if isinstance(methods, list) else str(methods).replace("+", ",").split(",")) if m]
    # a method no drawn world can judge has no null-world record to go by (its stored one read real records inside the
    # worlds: `institution_step`'s 20 of 20 were real steps)
    recs = [(m, {} if m in GRID_NOT_JUDGED else _method_records().get(m) or {}) for m in names]
    bad = [(m, r) for m, r in recs if r.get("calibrated") is False]
    if not bad or len(bad) < len(recs):
        return {"uncalibrated": False, "reliability": None}
    return {"uncalibrated": True, "reliability": "; ".join(
        f"{m}: findings in {r.get('null_worlds_with_findings')} of {r.get('null_worlds')} null worlds" for m, r in bad)}


def _figure_name(it: Item, f, kind: str) -> str:
    """A field's own figure file: its dataset, its codes and a digest of the field's identity. Named by dataset and node,
    every code set of a dataset (node *) wrote one file, each over the last (the slice's SIH P37.1, B58 and H32)."""
    import hashlib

    codes = "_".join((it.source or {}).get("codes") or it.nodes or [])[:40]
    return f"{_slug(f'{it.dataset}_{codes}' if codes else it.dataset)}_{hashlib.sha1(f.id.encode()).hexdigest()[:8]}_{kind}.png"


def _series_figure(out: Path, sv, f, label: str, it: Item, session=None) -> str | None:
    """The field's national series: the observed events with their exact Poisson 95 % interval, and what was expected
    of the later years from the earlier ones (the prospective tier, BP: fitted on the years up to the item's held-out
    later years, `Item.confirm_last`, and extrapolated), with its 90 % band. B1, fitted on every year with each year's
    effect, reproduces the national totals by construction: drawn as "expected", it tracked the observations 1:1 and
    tested nothing (author, 2026-10-13). A series too short to hold years out is drawn observed only, and says so."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import stats

    years = np.asarray(sv.years)
    obs = sv.y.sum(0)
    lo = np.where(obs > 0, stats.chi2.ppf(0.025, 2 * obs) / 2, 0.0)
    hi = stats.chi2.ppf(0.975, 2 * obs + 2) / 2
    figs = out / "figures"
    figs.mkdir(exist_ok=True)
    name = _figure_name(it, f, "series")
    fig, ax = plt.subplots(figsize=(7, 3.2), dpi=110)
    note = ""
    if session is not None and it.confirm_last:
        try:
            bp = session.expectations.prospective(f.id.split(":")[-1] if f.id.split(":")[-1] in
                                                  session.expectations.registry.level else f.node, it.confirm_last)
            by = np.asarray(bp.years)
            mu = bp.mu.sum(0)
            var = (bp.mu + np.where(np.isfinite(bp.phi), bp.mu ** 2 / np.where(np.isfinite(bp.phi), bp.phi, 1.0), 0.0)).sum(0)
            z = stats.norm.ppf(0.95)
            ax.fill_between(by, np.maximum(mu - z * np.sqrt(var), 0), mu + z * np.sqrt(var), alpha=0.25,
                            label=f"expected from {int(years[0])}-{it.confirm_last}, 90 %")
            ax.plot(by, mu, lw=1.5, label="expected (prospective)")
            ax.axvline(it.confirm_last + 0.5, color="grey", lw=0.8, ls=":")
        except Exception as exc:  # noqa: BLE001 - a field with no prospective tier (a measure, a share): observed only
            note = f"no prospective expectation: {type(exc).__name__}"
    else:
        note = "too few years to hold any out: observed only"
    ax.errorbar(years, obs, yerr=[obs - lo, hi - obs], fmt="o-", lw=1.5, capsize=2, label="observed, exact 95 %")
    ax.set_title(f"{label} — {it.dataset}" + (f"\n({note})" if note else ""), fontsize=9)
    ax.set_ylabel("events")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(figs / name)
    plt.close(fig)
    return f"figures/{name}"


def _rate_figure(out: Path, field_id: str, desc: list[dict], trends: list[dict]) -> dict | None:
    """A count field's rates as a paper draws them: (a) the directly standardised rate per year with its 95 % interval,
    for the study's whole and its references (Brazil, the region without the area), the whole's average annual percent
    change from the joinpoint model in the legend; (b) the rates by age band of each sex over the period, on a log
    scale. Drawn from the rows estimates.parquet carries (rates, trends), so every point is one of them."""
    import hashlib

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    whole = _whole()[0]
    rows = [r for r in desc if r["field"] == field_id and r.get("unit") == "per 100,000 person-years"]
    series: dict[str, list[dict]] = {}
    for r in rows:
        if r["measure"] == "standardised_rate" and r["period_kind"] == "year" and r.get("stratum") is None \
                and (r["geography"] == whole or (r["geography"] == "reference" and (
                    r["place"] == "BR" or str(r["place"]).endswith("without the area")))):
            name = "the area" if r["geography"] == whole and whole == "area" else \
                "Brazil" if r["place"] == "BR" else str(r["place"]).split(" ", 1)[-1]
            series.setdefault(name, []).append(r)
    if not series:
        return None
    label, dataset = rows[0]["label"], rows[0]["dataset"]
    aapc = next((t for t in trends if t["field"] == field_id and t["geography"] == whole and t.get("stratum") is None
                 and t.get("model") == "joinpoint: standardised rate" and t["measure"] == "aapc"), None)
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(11, 3.8), dpi=110)
    for name, rs in series.items():
        rs = sorted(rs, key=lambda r: r["first"])
        x = [r["first"] for r in rs]
        y = [r["estimate"] for r in rs]
        lo = [r.get("low") or v for r, v in zip(rs, y, strict=True)]
        hi = [r.get("high") or v for r, v in zip(rs, y, strict=True)]
        text = name
        if aapc is not None and name == ("the area" if whole == "area" else "Brazil"):
            text += f" (AAPC {aapc['estimate']:.1f} %, {aapc['low']:.1f} to {aapc['high']:.1f})"
        ax.plot(x, y, "o-", lw=1.5, ms=3, label=text)
        ax.fill_between(x, lo, hi, alpha=0.2)
    ax.set_ylabel("standardised rate per 100,000")
    ax.set_title("(a) directly standardised rate, 95 % interval", fontsize=9)
    ax.legend(fontsize=7, frameon=False)
    for sx in ("male", "female"):
        rs = [r for r in rows if r["measure"] == "crude_rate" and r["geography"] == whole and r["period_kind"] == "period"
              and str(r.get("stratum") or "").startswith(f"sex: {sx}, age ")]
        if not rs:
            continue
        bands = [str(r["stratum"]).split(", age ")[1] for r in rs]
        y = [r.get("estimate") or np.nan for r in rs]
        lo = [r.get("low") or np.nan for r in rs]
        hi = [r.get("high") or np.nan for r in rs]
        pos = np.arange(len(bands))
        bx.plot(pos, y, "o-", lw=1.5, ms=3, label=sx)
        bx.fill_between(pos, lo, hi, alpha=0.2)
        bx.set_xticks(pos, bands, rotation=60, fontsize=7)
    bx.set_yscale("log")
    bx.set_ylabel("rate per 100,000 person-years")
    bx.set_title("(b) by age band and sex over the period, exact 95 %", fontsize=9)
    bx.legend(fontsize=7, frameon=False)
    fig.suptitle(f"{label} — {dataset}", fontsize=9)
    fig.tight_layout()
    (out / "figures").mkdir(exist_ok=True)
    name = f"{_slug(dataset)}_{hashlib.sha1(field_id.encode()).hexdigest()[:8]}_rates.png"
    fig.savefig(out / "figures" / name)
    plt.close(fig)
    return {"file": f"figures/{name}", "kind": "rates", "field": field_id, "label": label, "dataset": dataset,
            "shows": "(a) the standardised rate per year with its 95 % interval for the whole and its references, the "
                     "whole's AAPC (joinpoint) in the legend; (b) the rates by age band of each sex over the period, log "
                     "scale; every point a row of estimates.parquet (rates)"}


def _map_figure(out: Path, sv, f, label: str, it: Item, findings: list[dict], expo: dict, population: str = "",
                smooth: dict | None = None) -> str | None:
    """Three maps of the field over the study's years: each state's rate (events per exposure: per 100,000 person-years,
    or per denominator event for a ratio; by health region in a one-state study); each municipality's smoothed
    standardised ratio (``smooth``: the empirical-Bayes ratio against the area's own age-sex rates, the map a paper
    draws); and, exploratory, each municipality's standardised departure from B1, the places of the field's findings
    outlined (pegasus_data's IBGE meshes, `pg.mesh`)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    import pegasus_data as pg

    places = np.asarray(sv.places)
    obs, mu = sv.y.sum(1), sv.mu.sum(1)
    ratio = str(population).startswith("events:")
    n_of = np.array([expo.get(int(p), 0.0) for p in places])
    states = pg.mesh("state", quality=MESH_QUALITY, root=config.data_root())
    munis = pg.mesh("municipality", quality=MESH_QUALITY, root=config.data_root())
    munis["u"] = munis["code"].str[:6].astype(int)
    st = places // 10000
    scale = 1e3 if ratio else 1e5
    area = config.study_area()
    if area is not None:
        # an area study draws its own places: Brazil's 5,570 municipalities, all but the area's grey, took 9 s a map
        # (Alagoas's infarction study, 2026-10-14)
        munis = munis[config.in_area(munis["u"].to_numpy())]
        states = states[states["code"].astype(int).isin(np.unique(st).tolist())]
    one_state = area is not None and len(np.unique(st)) == 1
    if one_state:
        # one state: its rate by health region (the descriptive tables' level), each municipality drawn in its region's
        region = gateway.regions(places, "health_region")
        rate_of = {}
        for code in np.unique(region):
            sel = region == code
            n = float(n_of[sel].sum())
            rate_of[code] = float(obs[sel].sum()) / n * scale if n else np.nan
        munis["rate"] = munis["u"].map(dict(zip(places.tolist(), [rate_of[r] for r in region], strict=True)))
        rated, level = munis, "health region"
    else:
        by_state = {}
        for k in np.unique(st):
            sel = st == k
            n = float(n_of[sel].sum())
            by_state[str(int(k))] = float(obs[sel].sum()) / n * scale if n else np.nan
        states["rate"] = states["code"].map(by_state)
        rated, level = states, "state"
    # the standardised departure over the years, (O − E)/sd with the NB variance: a small place's ratio is mostly noise
    var = (sv.mu + np.where(np.isfinite(sv.phi), sv.mu ** 2 / np.where(np.isfinite(sv.phi), sv.phi, 1.0), 0.0)).sum(1)
    zd = np.where(var > 0, (obs - mu) / np.sqrt(np.maximum(var, 1e-12)), np.nan)
    munis["z"] = munis["u"].map(dict(zip(places.tolist(), zd.tolist(), strict=True)))
    flagged = {int(p) for r in findings for p in str(r.get("places") or "").replace(" (+", ",").split(",")
               if p.strip().isdigit()}
    figs = out / "figures"
    figs.mkdir(exist_ok=True)
    name = _figure_name(it, f, "map")
    fig, (a1, a3, a2) = plt.subplots(1, 3, figsize=(15, 4.6), dpi=110)
    munis["smoothed"] = munis["u"].map(smooth or {})
    if munis["smoothed"].notna().any():
        hi_ = float(np.nanpercentile(munis["smoothed"], 98))
        munis.plot(column="smoothed", ax=a3, cmap="RdBu_r", norm=mcolors.TwoSlopeNorm(1.0, min(0.99, float(
            np.nanmin(munis["smoothed"]))), max(1.01, hi_)), legend=True, missing_kwds={"color": "#eee"},
                   legend_kwds={"shrink": 0.6, "label": "standardised ratio (empirical Bayes)"})
        states.boundary.plot(ax=a3, color="#555", linewidth=0.3)
    a3.set_title("standardised ratio against the area, smoothed", fontsize=9)
    rated.plot(column="rate", ax=a1, cmap="YlOrRd", legend=True, missing_kwds={"color": "#eee"},
               legend_kwds={"shrink": 0.6, "label": "per 1,000 denominator events" if ratio else "per 100,000"})
    if one_state:
        states.boundary.plot(ax=a1, color="#555", linewidth=0.3)
    # the field's label over the figure: in the first panel's title it ran across the second (2026-10-14)
    fig.suptitle(label if len(label) <= 140 else label[:137] + "...", fontsize=10)
    a1.set_title(f"crude rate by {level}, {sv.years[0]}–{sv.years[-1]}", fontsize=9)
    munis.plot(column="z", ax=a2, cmap="RdBu_r", norm=mcolors.TwoSlopeNorm(0.0, -4.0, 4.0), legend=True,
               missing_kwds={"color": "#eee"}, legend_kwds={"shrink": 0.6, "label": "(observed − expected) / sd",
                                                            "extend": "both"})
    outlined = munis[munis["u"].isin(flagged)]
    if len(outlined):
        outlined.boundary.plot(ax=a2, color="black", linewidth=0.6)
    states.boundary.plot(ax=a2, color="#555", linewidth=0.3)
    a2.set_title(f"exploratory: departure from B1; {len(outlined)} with findings outlined", fontsize=9)
    for ax in (a1, a2, a3):
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(figs / name)
    plt.close(fig)
    return f"figures/{name}"


# ---------------------------------------------------------------------- the report


def _report(decl: Declaration, scope: Scope, out: Path, rows: list[dict], desc: list[dict], figs: list[str],
            hyp: list[dict] | None = None, relations: list[dict] | None = None, persons: list[dict] | None = None,
            captured: list[dict] | None = None, completeness: list[dict] | None = None,
            trends: list[dict] | None = None, linkage: list[dict] | None = None,
            associated: list[dict] | None = None, estimates: list[dict] | None = None) -> None:
    """`report.html`: the study's results in a paper's order (ARCHITECTURE §3.5), from the folder's own tables: the
    summary of what was estimated; descriptive epidemiology (rates, trends, places, case fatality); analytic results
    (ecological associations, declared hypotheses, persons); data quality; then the exploratory signals, labelled
    hypothesis-generating (they suggest where to look, they confirm nothing); scope, methods, provenance. It had
    opened on the scans' findings, the study read as a dossier of signals (the author, 2026-10-14)."""
    from pegasus_data.linkage.engine import CAUTION, VIABLE

    e = html.escape
    read = [i for i in scope.items if i.status == "in"]
    # a quality field's departures are the data's, not the disease's: their own section (ARCHITECTURE §9.1, BACKLOG 7.5)
    quality = [r for r in rows if "quality:" in str(r.get("label"))]
    rows = [r for r in rows if "quality:" not in str(r.get("label"))]
    signal = [r for r in rows if r.get("class") == "signal"]
    institutional = [r for r in rows if r.get("class") == "facility" or r.get("institution_facts")]
    other = [r for r in rows if r.get("class") not in ("signal", "facility", "noise") and not r.get("institution_facts")]
    noise = [r for r in rows if r.get("class") == "noise"]
    rank = sorted(signal, key=lambda r: (r["q"], -abs(np.log(r["ratio"])) if r.get("ratio") and r["ratio"] > 0 else 0))
    # the stories the products numbered on every place of each locus (`story`), not recomputed on the written list
    numbered: dict[int, list[dict]] = {}
    for r in signal:
        if r.get("story") is not None:
            numbered.setdefault(int(r["story"]), []).append(r)
    stories = [sorted(numbered[k], key=lambda r: (bool(r.get("uncalibrated")), r["q"])) for k in sorted(numbered)]

    def table(rs: list[dict], cols: list[tuple[str, str]], cap: int = 40, where: str = "findings.parquet") -> str:
        head = "".join(f"<th>{e(c)}</th>" for _, c in cols)
        body = "".join("<tr>" + "".join(f"<td>{e(_fmt(r.get(k)))}</td>" for k, _ in cols) + "</tr>" for r in rs[:cap])
        more = f"<p class=more>{len(rs) - cap} more in {e(where)}</p>" if len(rs) > cap else ""
        return f"<table><tr>{head}</tr>{body}</table>{more}"

    import duckdb

    nat: list[dict] = []
    if desc:                            # the rates as the view `rates` shapes them, the whole and the references' periods
        con = duckdb.connect()
        con.register("estimates", _estimates_table(desc))
        cur = con.execute(f"""SELECT * FROM ({RATES_VIEW}) WHERE stratum IS NULL
            AND (geography = '{_whole()[0]}' OR (geography = 'reference' AND period_kind = 'period'))
            ORDER BY field, geography, place, period_kind DESC, first""")
        nat = [dict(zip([c[0] for c in cur.description], r, strict=True)) for r in cur.fetchall()]
    trend_rows = [r for r in trends or [] if not r.get("stratum") and r["measure"] in ("apc", "aapc")]
    # the associated causes that are leads: q at most the study's and records naming both at least `cooccur.MIN_BOTH`
    from . import cooccur

    shares = {(r["dataset"], r["variable"], r["value"]): r for r in associated or [] if r["measure"] == "proportion"}
    leads = [{"code": r["value"], "label": r.get("value_label"), "dataset": r["dataset"], "recorded_on": r["variable"],
              "with_code": r["numerator"], "expected": r["denominator"],
              "share": shares.get((r["dataset"], r["variable"], r["value"]), {}).get("estimate"),
              "lift": r["estimate"], "lift_low": r["low"], "lift_high": r["high"], "q": r["q"]}
             for r in associated or [] if r["measure"] == "lift" and r.get("q") is not None and r["q"] <= decl.q
             and (r.get("numerator") or 0) >= cooccur.MIN_BOTH]
    sources = sorted({i.dataset for i in read})
    level, unit = _whole()
    est_ = estimates or []
    fatality = [r for r in est_ if r.get("section") == "case fatality" and not r.get("stratum")
                and r["measure"] in ("case_fatality", "case_fatality_adjusted", "case_fatality_trend", "mortality_after")]
    ecological = [r for r in est_ if r.get("section") == "associations" and r["measure"] == "association"
                  and "with the" in str(r.get("model"))] or \
        [r for r in est_ if r.get("section") == "associations" and r["measure"] == "association"]
    moran = [r for r in est_ if r.get("section") == "associations" and r["measure"] == "moran_i"]
    smoothed = sorted((r for r in est_ if r.get("section") == "municipalities" and r["measure"] == "smoothed_smr"
                       and r.get("period_kind") == "period" and (r.get("low") or 0) > 1),
                      key=lambda r: -(r.get("low") or 0))
    # the summary's fields: the topic's own readers, not an alternative support (a place of occurrence) or a race
    whole = [r for r in nat if r.get("geography") == level and r.get("period_kind") == "period"
             and "support=" not in str(r.get("field"))]
    moran_g = [r for r in est_ if r.get("measure") == "moran_global"]
    lisa_n: dict[tuple, int] = {}
    for r in est_:
        if r.get("measure") == "lisa" and r.get("value") != "not significant":
            lisa_n[(r["field"], r["value"])] = lisa_n.get((r["field"], r["value"]), 0) + 1
    aapc = [r for r in trend_rows if r["measure"] == "aapc"]
    cf_period = [r for r in fatality if r["measure"] == "case_fatality" and r.get("period_kind") == "period"]
    # Table 1: each primary field's events by its characteristics over the period, at the study's whole
    first = {"sex": 0, "age band": 1, "mother's age band": 1}
    table1 = sorted(
        ({**r, "characteristic": r.get("variable_label") or r.get("variable"), "category": r.get("value_label") or
          r.get("value"), "n": r.get("numerator"), "pct": 100 * r["estimate"],
          "pct_low": None if r.get("low") is None else 100 * r["low"],
          "pct_high": None if r.get("high") is None else 100 * r["high"]}
         for r in est_ if r.get("section") == "case mix" and r["measure"] == "proportion"
         and r.get("period_kind") == "period" and r.get("geography") == level and "support=" not in str(r["field"])),
        key=lambda r: (str(r["field"]), first.get(str(r.get("variable")), 2 if "RACA" in str(r.get("variable")) else 3),
                       str(r.get("variable")),
                       # an age band in age order ("5-9" after "1-4"), a not-recorded value last; else by count
                       (_band_order(str(r.get("category"))) if "age band" in str(r.get("variable")) else -(r["n"] or 0))))

    def num(x, k=1) -> str:
        return "–" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:,.{k}f}"
    summary = (
        [f"<li>{e(r['label'])} ({e(r['dataset'])}), {r['first']}–{r['last']}: {num(r.get('events'), 0)} events, "
         f"{num(r.get('crude_rate'), 2)} {e(str(r.get('unit') or ''))} (95 % {num(r.get('crude_low'), 2)}–"
         f"{num(r.get('crude_high'), 2)})"
         + (f"; age-sex standardised {num(r.get('standardised_rate'), 2)} per 100,000" if r.get('standardised_rate')
            is not None else "") + "</li>" for r in whole]
        + [f"<li>{e(r['label'])}: {e(str(r.get('variable') or ''))}, average annual percent change "
           f"{num(r['estimate'], 1)} % (95 % {num(r['low'], 1)} to {num(r['high'], 1)}), {r['first']}–{r['last']}</li>"
           for r in aapc if r.get("place") == unit and r.get("value") is None and "support=" not in str(r["field"])]
        + [f"<li>{e(r['label'])}: case fatality {num(100 * r['estimate'], 1)} % (95 % {num(100 * r['low'], 1)}–"
           f"{num(100 * r['high'], 1)}), {num(r['numerator'], 0)} of {num(r['denominator'], 0)}</li>" for r in cf_period]
        + [f"<li>{len(smoothed)} municipalities whose smoothed standardised ratio lies above 1 (95 % interval)</li>"]
        + ([f"<li>{len([r for r in ecological if r.get('p') is not None and r['p'] < decl.q])} ecological "
            f"associations with p below {decl.q} (of {len(ecological)} in the joint models)</li>"] if ecological else []))
    parts = [f"<h1>{e(decl.study)}</h1>",
             f"<p class=meta>{e(_area_text())} · depth {e(decl.depth)} · period "
             f"{decl.years[0]}–{decl.years[-1]} · q {decl.q} · written {time.strftime('%Y-%m-%d %H:%M')}</p>",
             "<h2>1. Summary</h2>",
             f"<p>{len(sources)} sources read ({e(', '.join(sources))}) in {len(read)} fields.</p>",
             "<ul>" + "".join(summary) + "</ul>",
             # the counts as they are: sources are datasets (fields are items), and a noise finding (an exact interval
             # holding 1) is no recording explanation (731 of Alagoas's 751 "explained" findings were noise; the
             # review of the study, 2026-10-14)
             f"<p>Exploratory signal detection (section 5, hypothesis-generating): {len(rows)} findings, {len(signal)} "
             f"unexplained by recording, {len(other)} with a recording, denominator or system explanation, {len(noise)} "
             f"within chance, in {len(stories)} stories.</p>",
             "<h2>2. Descriptive epidemiology</h2>",
             table(nat, [("label", "field"), ("dataset", "source"), ("place", "where"), ("first", "from"),
                         ("last", "to"), ("events", "events"), ("crude_rate", "rate"), ("crude_low", "95% from"),
                         ("crude_high", "to"), ("unit", "per"), ("standardised_rate", "standardised /100k"),
                         ("standardised_low", "95% from"), ("standardised_high", "to")], cap=80,
                   where="estimates.parquet, section rates (with sex, age, region rows and the standard population named; view rates)"),
             "<h3>Trends</h3>"
             + (table(trend_rows,
                      [("label", "field"), ("dataset", "source"), ("place", "where"), ("model", "model"),
                       ("segment", "segment"), ("first", "from"), ("last", "to"), ("estimate", "APC %"),
                       ("low", "95% from"), ("high", "to"), ("p", "p")], cap=40,
                      where="estimates.parquet, section trends (by sex and age band too)") if trends else "<p>No series long enough.</p>"),
             "".join(f"<img src='{e(f)}' alt=''>" for f in figs),
             "<h3>Table 1. Characteristics of the events</h3><p>Each field's events over the period by the "
             "characteristics its records carry: n, % and the exact (Clopper-Pearson) interval; a value not recorded "
             "is its own category.</p>"
             + (table(table1, [("label", "field"), ("characteristic", "characteristic"), ("category", "category"),
                               ("n", "n"), ("pct", "%"), ("pct_low", "95% from"), ("pct_high", "to")], cap=150,
                      where="estimates.parquet, section case mix (by year and region too)")
                if table1 else "<p>No characteristic is recorded on the topic's events.</p>"),
             "<h3>Municipalities</h3><p>The municipalities whose smoothed standardised ratio (empirical Bayes, against "
             "the area's own age-sex rates) lies above 1 over the period, the lower bound first.</p>"
             + table(smoothed, [("label", "field"), ("place_name", "municipality"), ("numerator", "events"),
                                ("denominator", "expected"), ("estimate", "smoothed ratio"), ("low", "95% from"),
                                ("high", "to")], cap=25, where="estimates.parquet, section municipalities (view "
                                                                "municipalities)"),
             "".join(f"<p>{e(str(r['label']))}: global Moran's I of the smoothed ratios {num(r['estimate'], 3)} "
                     f"(p {num(r['p'], 3)}, {num(r['denominator'], 0)} municipalities); local clusters at q {decl.q}: "
                     + (", ".join(f"{v} {lisa_n[(r['field'], v)]}" for v in ("high-high", "low-low", "high-low",
                                                                             "low-high") if (r['field'], v) in lisa_n)
                        or "none") + " (estimates.parquet, measure lisa; view municipalities, lisa_cluster)</p>"
                     for r in moran_g),
             "<h3>Case fatality</h3>"
             + (table(fatality, [("label", "field"), ("dataset", "source"), ("variable", "outcome"),
                                 ("measure", "measure"), ("first", "from"), ("last", "to"), ("numerator", "deaths"),
                                 ("denominator", "records"), ("estimate", "estimate"), ("low", "95% from"),
                                 ("high", "to"), ("p", "p"), ("note", "note")], cap=60,
                      where="estimates.parquet, section case fatality (by sex and age band too)")
                if fatality else "<p>No source read declares the fatal codes of its outcome.</p>"),
             "<h2>3. Analytic results</h2>",
             "<h3>Ecological associations</h3><p>Each field's standardised ratio across the municipalities against "
             "the contexts, per standard deviation, all contexts together (negative binomial, offset the expected "
             "events, intervals robust to clustering by health region): associations between places, never effects "
             "on persons.</p>"
             + (table(ecological, [("label", "field"), ("variable", "context"), ("note", "per"), ("estimate", "ratio"),
                                   ("low", "95% from"), ("high", "to"), ("p", "p"), ("denominator", "municipalities")],
                      cap=60, where="estimates.parquet, section associations (each context alone too)")
                + "".join(f"<p>{e(r['label'])}: Moran's I of the residuals {num(r['estimate'], 3)} (p {num(r['p'], 3)})"
                          "</p>" for r in moran)
                if ecological else "<p>No context declared, or none held by nine municipalities in ten.</p>"),
             "<h3>Declared hypotheses</h3>",
             table(hyp or [], [("hypothesis", "hypothesis"), ("source", "source"), ("support", "place"),
                               ("field_reader", "field"), ("years", "years"), ("observed", "observed"),
                               ("expected", "expected"), ("effect", "effect"), ("low", "95 % low"),
                               ("high", "95 % high"), ("p", "p"), ("p_holm", "p (Holm, over its sources)"),
                               ("answer", "answer")], cap=60) if decl.hypotheses else "<p>None declared.</p>",
             "<h3>Persons</h3><p>The cohort scan over linked persons (ARCHITECTURE §7.8): each attribute of the "
             "persons of a source against each outcome they reach, on their own record or through the viable links "
             "of any route, adjusted for age, sex and place; linkage uncertainty by plausible link sets.</p>"
             + (table(sorted([r for r in persons if r.get("q") is not None], key=lambda r: r["q"]),
                      [("cohort", "persons"), ("year", "year"), ("outcome", "outcome"), ("attribute", "attribute"),
                       ("level", "level"), ("reference", "against"), ("rr", "RR"), ("low", "95 % from"), ("high", "to"),
                       ("q", "q")], cap=40)
                + "".join(f"<p>{e(r['cohort'])} {r.get('year') or ''}: {e(r['note'])}</p>" for r in persons if r.get("note"))
                if persons else f"<p>{'Not read (persons: false).' if not decl.choice('persons') else 'No source read holds persons on a usable link.'}</p>"),
             "<h2>4. Data quality</h2>",
             "<h3>Completeness of the records</h3>"
             + (table(completeness, [("dataset", "source"), ("label", "field"), ("first", "from"), ("last", "to"),
                                     ("variable", "indicator"), ("numerator", "events"), ("denominator", "of"),
                                     ("estimate", "share"), ("low", "95% from"), ("high", "to")], cap=60, where="estimates.parquet, section completeness")
                if completeness else "<p>No completeness measure was written.</p>"),
             "<h3>Completeness across systems</h3>"
             + (table(captured, [("population", "population"), ("lists", "lists"), ("years", "years"),
                                 ("patterns", "persons by list (1 on it, 0 not)"), ("observed", "observed"),
                                 ("estimate", "estimated"), ("low", "95 % from"), ("high", "to"), ("model", "model"),
                                 ("completeness", "each list's share"), ("note", "rests on")], cap=10)
                + "<p>Every estimate assumes the links find every pair: a pair a link misses (SINAN carries an age, "
                  "not a birth date, for the link to match) raises the estimate, and lists that record the same "
                  "persons more often than chance lower it.</p>"
                if any(r.get("patterns") for r in captured or []) else f"<p>{e(_capture_note(scope))}</p>"),
             "<h3>Where the recording departs</h3><p>Places and periods where a column's blank or 'ignored' share "
             "departs from its expectation: where the records of this topic are least complete, and where a recording "
             "practice changed.</p>",
             table(quality, [("label", "column"), ("dataset", "source"), ("component", "component"),
                             ("place_names", "places"), ("first_year", "from"), ("last_year", "to"), ("effect", "effect"),
                             ("q", "q")], cap=30) if quality else "<p>No quality departure at this depth.</p>",
             "<h2>5. Exploratory signal detection (hypothesis-generating)</h2><p>Departures of the observed events from "
             "a hierarchical model's expectation, searched over places, periods, groups and establishments under "
             "false-discovery control. They point at where to look; none is a confirmed excess or a causal claim, and "
             "a hypothesis they suggest is tested by declaring it (section 3).</p>",
             "".join(_story_html(k, st, e) for k, st in enumerate(stories[:15], 1)),
             (f"<p class=more>{len(stories) - 15} more stories in findings.parquet (column story)</p>"
              if len(stories) > 15 else ""),
             "<h3>Every signal finding</h3>",
             table(rank, [("label", "field"), ("dataset", "source"), ("component", "component"),
                          ("place_names", "places"), ("groups", "group"), ("first_year", "from"), ("last_year", "to"),
                          ("effect", "effect"), ("effect_unit", "unit"), ("q", "q"), ("replication", "replication"),
                          ("corroborated", "corroborated"), ("related", "related fields there (O/E, 95%)"),
                          ("context", "context (national percentile)")], cap=20),
             "<h3>Institutional findings</h3><p>Departures concentrated in one establishment: often real (a referral "
             "centre, a new service, a screening programme), read with the establishment's registration.</p>",
             table(institutional, [("label", "field"), ("dataset", "source"), ("component", "component"),
                                   ("first_year", "from"), ("last_year", "to"), ("effect", "effect"), ("q", "q"),
                                   ("institution_facts", "establishment (CNES)"),
                                   ("institution_volume", "its whole activity")], cap=30),
             "<h3>Findings with a recording, denominator or system explanation</h3>",
             table(other, [("label", "field"), ("dataset", "source"), ("component", "component"),
                           ("place_names", "places"), ("first_year", "from"), ("last_year", "to"), ("effect", "effect"),
                           ("class", "class"), ("class_reason", "why")], cap=30),
             "<h3>Relations among the study's fields</h3><p>Fields whose departures move together, at which spatial "
             "scale and lag (the joint model over graph bands; a relation is statistical, never causal by itself).</p>",
             (table(sorted([r for r in (relations or []) if r.get("reported")], key=lambda r: r.get("p", 1)),
                    [("pair", "fields"), ("support", "scale"), ("lag", "lag"), ("rho", "ρ"), ("direct", "direct"),
                     ("p", "p"), ("years", "years")], cap=25) if relations else "<p>No pair of fields shares four years.</p>"),
             "<h2>6. Scope</h2>", "<ul>" + "".join(
                 f"<li><b>{e(i.dataset)}</b> ({e(gateway.split_event(i.event)[0])}), {i.years[0]}–{i.years[-1]}: {e(i.reason)}"
                 + (f" — {e(i.note)}" if i.note else "") + "</li>" for i in read) + "</ul>",
             "<h3>Deferred</h3><ul>" + "".join(f"<li>{e(i.dataset)}: {e(i.note)}</li>"
                                               for i in scope.items if i.status != "in") + "</ul>",
             "<h3>Codes found with the topic's on the same records</h3>"
             + (table(sorted(leads, key=lambda r: -r["lift"]),
                      [("code", "code"), ("label", "condition"), ("dataset", "source"), ("recorded_on", "on"),
                       ("with_code", "records with both"), ("expected", "expected"), ("share", "share of the topic's"),
                       ("lift", "lift"), ("lift_low", "95% from"), ("lift_high", "to"), ("q", "q")], cap=25,
                      where="estimates.parquet, section associated causes")
                if leads else "<p>None at q.</p>"),
             "<h3>Person paths</h3><p>Declared record links between the sources read (no name is published: pairs "
             "are found on birth date, sex, residence and dates). A link is read only where its negative control, the "
             f"same key shifted, finds few pairs by chance (viable at most {VIABLE[0]:g}% with {VIABLE[1]:g}% "
             f"agreement of its held-out fields, with caution at most {CAUTION[0]:g}% with {CAUTION[1]:g}%, on the "
             "95% upper bound); otherwise what it would answer is not answered here.</p>"
             + (table([{**p, "best": _best_run(p)} for p in scope.paths],
                      [("link", "link"), ("left", "from"), ("right", "to"), ("verdict", "verdict"),
                       ("best", "best stored run (period: pairs, chance %)"), ("what", "what it pairs")], cap=40)
                if scope.paths else "<p>No declared link touches the sources read.</p>"),
             "<h3>Medicines</h3><p>The treatments an official document gives for the topic's codes (pegasus_data "
             "<code>treatments.yml</code>), each read as a context of the topic through the declared fields that count "
             "it: retail sales are not the topic's count.</p>"
             + (table([{**m, "contexts": ", ".join(m["contexts"]) or "none declared"} for m in scope.medicines],
                      [("substance", "substance"), ("use", "use"), ("contexts", "read as"), ("catmat", "CATMAT (BNAFAR)"),
                       ("source", "source")], cap=20)
                + "".join(f"<p>{e(n)}</p>" for n in dict.fromkeys(m["note"] for m in scope.medicines if m["note"]))
                if scope.medicines else "<p>No treatment is declared for the topic's codes.</p>"),
             "<h3>Named by a seed and not read</h3><ul>" + "".join(
                 f"<li>{e(x['seed'])}: {e(x['why'])}</li>" for x in scope.excluded) + "</ul>",
             "<h2>7. Methods and limitations</h2>", _limitations(decl, scope, desc, linkage),
             "<h2>8. Provenance</h2><p>provenance.json; every table of the folder is a table of study.duckdb, which "
             "opens on any machine. <code>pegasus-core export</code> copies the folder (and writes CSV on request).</p>"]
    css = ("body{font-family:system-ui,sans-serif;max-width:1100px;margin:2em auto;padding:0 1em;color:#222}"
           "table{border-collapse:collapse;font-size:13px;margin:.5em 0}td,th{border-bottom:1px solid #ddd;"
           "padding:3px 8px;text-align:left}th{background:#f4f4f4}img{max-width:100%;margin:.5em 0}.meta,.more{color:#666}")
    (out / "report.html").write_text(f"<!doctype html><meta charset=utf-8><title>{e(decl.study)}</title><style>{css}"
                                     f"</style>{''.join(parts)}", encoding="utf-8")


def _best_run(path: dict) -> str:
    """A person path's stored run with the most pairs among its best verdict's, as 'period: pairs, chance %'."""
    rank = {"viable": 2, "use with caution": 1}
    runs = sorted(path["runs"], key=lambda r: (rank.get(r.get("verdict") or "", 0), r.get("pairs") or 0), reverse=True)
    if not runs:
        return "not run"
    r = runs[0]
    chance = r.get("chance_upper95_percent") if r.get("chance_upper95_percent") is not None else r.get("chance_percent")
    return f"{r['period']}: {r.get('pairs')} pairs" + (f", chance ≤ {chance:.1f}%" if chance is not None else "")


def _stories(rows: list[dict]) -> list[list[dict]]:
    """Findings grouped into stories (ARCHITECTURE §9): connected by a shared municipality and overlapping years, across
    fields, components and sources; each story's rows strongest first, the stories by their strongest q. Each row gets
    its story's number (``story``)."""
    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_place: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        # every place of the locus (`_places`): the written `places` holds the first 20, and findings sharing only a
        # later one were never one story (the review of the study, 2026-10-14)
        places = r.get("_places") or [p_.strip() for p_ in str(r.get("places") or "").replace(" (+", ",").split(",")
                                       if p_.strip().isdigit()]
        for p_ in places:
            by_place.setdefault(str(int(p_)), []).append(i)
    for idx in by_place.values():
        for i in idx:
            for j in idx:
                ri, rj = rows[i], rows[j]
                if i < j and (ri.get("first_year") or 0) <= (rj.get("last_year") or 9999) \
                        and (rj.get("first_year") or 0) <= (ri.get("last_year") or 9999):
                    parent[find(i)] = find(j)
    groups: dict[int, list[dict]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(find(i), []).append(r)
    # ranked by evidence (independent sources), burden (excess events at the stories' loci), then the strongest q
    # (ARCHITECTURE §9, BACKLOG 7.3)
    # a story whose findings all come from methods that fail their null worlds ranks after every other (`_reliability`)
    out = sorted((sorted(g, key=lambda r: (bool(r.get("uncalibrated")), r["q"])) for g in groups.values()),
                 key=lambda g: (all(r.get("uncalibrated") for r in g), -len({r["dataset"] for r in g}),
                                -sum(max(r.get("excess") or 0.0, 0.0) for r in g), g[0]["q"]))
    for k, g in enumerate(out, 1):
        for r in g:
            r["story"] = k
    return out


def _by_chapter(structure: str, codes: list[str]) -> dict[str, list[str]]:
    """Codes grouped by their chapter in the code tree ("02 Procedimentos com finalidade diagnostica"); a code the tree
    does not hold is its own group."""
    tree = {r["code"]: r for r in gateway.code_tree(structure).select(["code", "label", "level", "parent"]).to_pylist()}
    out: dict[str, list[str]] = {}
    for code in codes:
        x = code
        while x in tree and tree[x]["level"] != "chapter" and tree[x]["parent"]:
            x = tree[x]["parent"]
        key = f"{x} {tree[x]['label']}" if x in tree and tree[x]["level"] == "chapter" else code
        out.setdefault(key, []).append(code)
    return out


@functools.cache
def _tree_labels(structure: str) -> dict:
    return {r["code"]: r.get("label") or "" for r in gateway.code_tree(structure).select(["code", "label"]).to_pylist()}


def _code_structure(it: Item) -> str:
    """The code tree an item's codes belong to: its source's, else its classifier's, else its event's primary one
    (SIA-PA's serology codes are SIGTAP procedures, and were named from ICD-10's labels: none)."""
    src = it.source or {}
    if src.get("structure"):
        return src["structure"]
    cls = gateway.event_type(it.dataset, it.event).get("classifiers") or []
    own = [c for c in cls if c["column"] == src.get("classifier")] or [c for c in cls if c["role"] == "primary"]
    return (own[0].get("structure") if own else None) or "ICD10"


def _codes_text(it: Item) -> str:
    """A code set's codes as the field's name carries them (": B58 Toxoplasmose"): stories listed B58's and P37.1's
    admissions both as "hospitalisation" (2026-10-12)."""
    codes = (it.source or {}).get("codes") or []
    cond = gateway.split_event(it.event)[1]
    if cond:                     # a record condition's topic: its name and its clauses
        return f": {cond['name']} ({_condition_text(cond['clauses'])})"
    if not codes and not it.nodes and not it.source:
        # a notifiable agravo's own records: named by the condition its records carry (SINAN-DENG's A90), never by the
        # event alone ("case", "notification")
        try:
            held = gateway.condition_codes(it.dataset)
            labels = _tree_labels("ICD10") if held else {}
        except Exception:  # noqa: BLE001 - an agravo pegasus_data ties to no code: its dataset's name
            held, labels = [], {}
        top = sorted({c[:3] for c in held})[:2]
        # in parentheses: ": P37" is the perinatal fields' mark (`body`), and an agravo's notifications are not rated
        # per live birth
        return (" (" + ", ".join(f"{c} {labels[c]}" if labels.get(c) else c for c in top) + ")") if top \
            else f" ({it.dataset})"
    if not codes:
        return ""
    try:
        labels = _tree_labels(_code_structure(it))
    except Exception:  # noqa: BLE001 - a tree pegasus_data does not hold: the codes as recorded, said undecoded
        labels = {}
    shown = [f"{c} {labels[c]}" if labels.get(c) else f"{c} (undecoded)" for c in codes[:4]]
    # read on another classifier than the source's primary: said, or SIM's CAUSABAS_O read as CAUSABAS (the run of
    # 2026-10-14: two fields, one label, two figures indistinguishable)
    column = (it.source or {}).get("classifier")
    other = next((c for c in (gateway.event_type(it.dataset, it.event) or {}).get("classifiers") or []
                  if c.get("column") == column and c.get("role") != "primary"), None)
    on = (f" (on {column}, the {other.get('role')} coding" + (f" that {other['recodes']} recodes" if other.get("recodes")
                                                             else "") + ")") if other else ""
    return ": " + ", ".join(shown) + (f" (+{len(codes) - 4})" if len(codes) > 4 else "") + on


def _n(k: int, noun: str) -> str:
    return f"{k:,} {noun}" + ("" if k == 1 else "s")


def _direction(r: dict) -> str:
    """Whether a rate-ratio finding is above or below its expectation, in words (a deficit cluster read "effect 0.35
    rate ratio" with nothing saying it was one)."""
    if str(r.get("effect_unit")) != "rate ratio" or r.get("effect") is None:
        return ""
    return " (above expectation)" if float(r["effect"]) > 1 else " (below expectation)"


def _story_html(k: int, rows: list[dict], e) -> str:
    """One story: where, when, what departs, in how many fields and sources, and its strongest findings."""
    lead = rows[0]
    fields_ = sorted({r["label"] for r in rows})
    sources = sorted({r["dataset"] for r in rows})
    years = [y for r in rows for y in (r.get("first_year"), r.get("last_year")) if y]
    span = f"{min(years)}–{max(years)}" if years else ""
    def estimate(r: dict) -> str:
        if r.get("groups"):
            ci = (f" [{_fmt(r.get('interval_low'))}, {_fmt(r.get('interval_high'))}]"
                  if r.get("interval_low") is not None else "")
            there = (f"; all the field's events there: {_fmt(r.get('locus_observed'))} against "
                     f"{_fmt(r.get('locus_expected'))} expected" if r.get("locus_observed") is not None else "")
            return f", {e(str(r['effect_unit']))} {_fmt(r['effect'])}{ci}{there}"
        if r.get("ratio") is not None:
            return (f", observed {_fmt(r.get('observed'))} against {_fmt(r.get('expected'))} expected, "
                    f"O/E {_fmt(r.get('ratio'))} [{_fmt(r.get('ratio_low'))}, {_fmt(r.get('ratio_high'))}]")
        if str(r.get("tier", "")).startswith("BP"):
            ratio = (f", O/E {_fmt(r.get('ratio'))} [{_fmt(r.get('ratio_low'))}, {_fmt(r.get('ratio_high'))}]"
                     if r.get("ratio") is not None else "")
            return (f", observed {_fmt(r.get('observed'))} against {_fmt(r.get('expected'))} expected from the fit on "
                    f"the years before{ratio}" if r.get("expected") is not None else
                    f", {e(str(r['effect_unit']))} {_fmt(r['effect'])} against the expectation fitted on the years "
                    f"before (observed {_fmt(r.get('observed'))})")
        return f", {e(str(r['effect_unit']))} {_fmt(r['effect'])} (the method's statistic)"

    items = "".join(f"<li>{e(r['label'])} ({e(r['dataset'])}): {e(str(r['component']))}"
                    + (f" in {e(r['groups'])}" if r.get("groups") else "")
                    + _direction(r) + estimate(r)
                    + f", q {_fmt(r['q'])}"
                    + (", corroborated" if r.get("corroborated") else "")
                    + (f" (method not calibrated: {e(r['reliability'])})" if r.get("uncalibrated") else "") + "</li>"
                    for r in rows[:6])
    excess = sum(max(r.get("excess") or 0.0, 0.0) for r in rows)
    return (f"<h3>Story {k}: {e(lead.get('place_names') or 'the whole study area')}, {span}</h3><p>{_n(len(rows), 'finding')} in "
            f"{_n(len(fields_), 'field')} from {_n(len(sources), 'source')} ({e(', '.join(sources))})"
            + (f"; {excess:,.0f} events above expectation" if excess else "") + f".</p><ul>{items}</ul>")


def _limitations(decl: Declaration, scope: Scope, desc: list[dict], linkage: list[dict] | None = None) -> str:
    """The report's methods and limitations: `_methods`, the text METHODS.md holds, as HTML."""
    e = html.escape
    return "".join(f"<h3>{e(head)}</h3><ul>" + "".join(f"<li>{e(x)}</li>" for x in paras) + "</ul>"
                   for head, paras in _methods(decl, scope, desc, linkage))


#: Every column a study folder's tables carry: what it holds, its unit, how it was computed. `_codebook` writes them to
#: the folder's README.md and lists any column missing here as undocumented, which `body` refuses (a folder's numbers
#: were described only in the report's prose, 2026-10-12).
COLUMNS = {
    "field": "the field's id: dataset, event, classifier and codes or reader, block",
    "label": "the field's name as a reader reads it: event, codes with their labels, reader",
    "dataset": "the source (DATASUS system and series)",
    "level": "the row's geography: national (Brazil), area (the declared study area), region (IBGE macro-region), state "
             "(one the area holds whole), health macro-region or health region (the SUS regionalisation, an area's), "
             "or reference (an area study's comparison: Brazil, BR, and each macro-region the area lies in, the same "
             "field read nationally and standardised to the same standard)",
    "unit": "the geography's code: BR, the area's IBGE codes joined by +, the region's digit and name, the state's "
            "two-digit IBGE code, or the health (macro-)region's code and name",
    "year": "the year of the events (the event type's own date)",
    "events": "the field's events in the row's geography and year",
    "population": "the denominator: person-years of residents (POPSVS; with the account's age 0 for a newborn field), "
                  "or, for a standardised ratio by race, the events expected of that race's population at the field's "
                  "own age-sex rates; "
                  "or the events named in per",
    "per": "the denominator's unit: 100,000 person-years, 1,000 of the named events (live births: SINASC-DN), share, "
           "days, median (trends.parquet: the unit of the rates the trend is of)",
    "month": "the calendar month of the events' own dates (1-12)",
    "expectations.parquet:field": "the field (its id: dataset, event, reader and node); one field's rows per municipality "
                                   "and period, so filter on it",
    "expectations.parquet:scale": "what y and mu are: events for a count field; for a share the empirical logit of its k "
                                  "of n events; for another mark the mean log of the mark per event",
    "expectations.parquet:year": "the period (a year, or YYYYMM at the monthly grain)",
    "expectations.parquet:y": "the field's observed value in the municipality and period, on its scale (scale)",
    "expectations.parquet:mu": "its expectation there under the hierarchical model (tier B1: the place's own level and "
                               "the shared course), on the same scale",
    "expectations.parquet:phi": "a count field's negative-binomial dispersion under the predictive with the field's noise "
                                "structure: variance mu + mu^2/phi (infinite: Poisson); empty for a mark",
    "expectations.parquet:pit": "the randomised probability integral transform of the observed value under the "
                                "predictive (uniform on [0, 1] when the model holds)",
    "expectations.parquet:z": "the normal score of pit (standard normal when the model holds): the cell's surprise",
    "expectations.parquet:w": "the cell's weight in the scans: the inverse of its predictive variance (a count field's "
                              "mu / (1 + mu/phi))",
    "expectations.parquet:flags": "a bitmask: 1 events without person-years (denominator), 2 the field failed calibration "
                                  "at this tier, 8 no information (mu near 0, or no events for a mark), 16 a category "
                                  "the training fit never saw",
    "expectations.parquet:n": "a mark's events in the cell (a share's trials: its denominator); empty for a count field",
    "expectations.parquet:observed_share": "a share's observed share in the cell (k / n), from y and n; empty otherwise",
    "expectations.parquet:expected_share": "a share's expected share in the cell (the inverse logit of mu); empty "
                                           "otherwise",
    "measure": "the measure's column (an interval: its end date's column)",
    "measure_name": "the measure's name in the source's dictionary (an interval: the days from its start to it)",
    "kind": "measure (a declared quantity of the event), interval (days between two of its dates, plus one) or age (the "
            "subject's age at the event, from the counts' single years: events placed by sex and age only)",
    "mean": "mean of the valid values",
    "sd": "standard deviation of the valid values",
    "median": "median of the valid values",
    "seasonal_index": "a year's row: the month's events per day over the year's; the period's: the month's rate "
                      "ratio to the geometric mean of the twelve, each year its own level (1: no seasonality)",
    "uniformity_chi2": "Pearson's statistic of the twelve months' events against their days (11 degrees of freedom)",
    "link": "the link (pegasus_data's curation/links.yml)",
    "run_year": "the year of the stored national run (its scope may pad a side by neighbouring years)",
    "linkage.parquet:method": "the linkage method (probabilistic or deterministic)",
    "left_records": "the left side's records the run read",
    "right_records": "the right side's records the run read",
    "candidates": "candidate pairs scored",
    "threshold_bits": "the score above which a pair is kept (sum of log2 likelihood ratios)",
    "pairs": "pairs kept, one to one",
    "linked_share": "the share of the left side's records the national run paired (all records the side reads, every "
                    "cause); a topic's own sensitivity is in estimates.parquet, stratum 'records the link can pair'",
    "false_match_percent": "the false-match rate estimated from the placebo, in percent",
    "false_match_upper95_percent": "its upper 95 % bound",
    "linkage.parquet:verdict": "the run's verdict (viable, or why not)",
    "verdict_reasons": "the reasons a run is not viable",
    "independent_agreement_percent": "the lowest agreement among the validation fields the linkage did not use",
    "validations": "every validation: field, agreement and pairs compared, independent or circular",
    "apc": "annual percent change: 100 (e^b - 1) of the slope b",
    "apc_low": "lower 95 % bound of the APC: the slope's variance widened by the year-level Pearson dispersion "
               "(quasi-Poisson), on Student's t with T - 2 degrees of freedom",
    "apc_high": "upper 95 % bound of the APC, as apc_low",
    "dispersion": "the model's scale: a log-linear model's year-level Pearson dispersion (at least 1); a joinpoint "
                  "model's residual variance of the weighted log rates",
    "segment": "a joinpoint model's segment (1, 2, ...) or AAPC (the average annual percent change of the whole series); "
               "empty for the log-linear models",
    "joinpoints": "the number of joinpoints chosen (Kim's permutation tests)",
    "health_macroregion": "the municipality's health macro-region (SUS regionalisation), in an area study",
    "seasonality_f": "the period's joint F statistic of the twelve month effects (11 and the residual degrees of freedom)",
    "peak_day": "one harmonic's peak as a day of the year (1 = 1 January, 182 = 1 July)",
    "peak_to_trough": "one harmonic's peak-to-trough rate ratio",
    "standard.parquet:standard": "the standard population's name (as estimates.parquet's standard)",
    "standard.parquet:sex": "male or female",
    "standard.parquet:age_band": "the age band",
    "standard.parquet:weight": "the cell's weight (the weights of a standard sum to 1)",
    "sources.parquet:dataset": "the source (pegasus_data's name for it)",
    "sources.parquet:listed": "whether the catalog's last listing of the server holds the file",
    "sources.parquet:path": "the file's path on the DATASUS server",
    "sources.parquet:uf": "the state the file is published under (BR: national)",
    "sources.parquet:year": "the year the file is published under",
    "sources.parquet:competence": "a monthly file's month (YYYYMM); empty for an annual file",
    "sources.parquet:listed_size": "the file's size as the server listed it",
    "sources.parquet:listed_modified": "its modification date on the server as listed",
    "sources.parquet:listed_at": "when the catalog last listed it",
    "sources.parquet:in_lake": "whether the lake holds the file's records (False: listed, not read, see lake_note)",
    "sources.parquet:lake_note": "why a listed file is not held",
    "sources.parquet:blob_sha256": "the SHA-256 of the bytes decoded (the digest every record read from it carries)",
    "sources.parquet:rows_decoded": "the file's rows in the lake (every state's, for a national file)",
    "sources.parquet:decoded_at": "when the file was decoded",
    "sources.parquet:fetched_at": "when the bytes were fetched",
    "sources.parquet:served_by": "where from: the DATASUS server or a mirror",
    "sources.parquet:fetched_size": "the size of the bytes fetched",
    "sources.parquet:server_changed_since_fetch": "the server's listing differs from the one at the fetch: the file has "
                                                  "been rewritten since",
    "sources.parquet:status": "preliminary, final or undeclared (the source declares no finality rule)",
    "sources.parquet:status_basis": "the declaration behind the status",
    "figures.parquet:file": "the figure's file in the folder",
    "figures.parquet:kind": "series, map or rates",
    "figures.parquet:shows": "what the figure draws",
    "standard": "the standard population of the direct standardisation: Brazil's 2010 population by sex and age band of "
                "the field's own population source (fixed, so rates compare across studies, periods and areas)",
    "stratum": "a row's sex, age band, or sex within an age band (the whole's rates of each); empty for every person",
    "period": "the years a whole-period row sums (first-last); empty on a year's row",
    "u": "the municipality's IBGE code (6 digits)",
    "municipality": "the municipality's name (IBGE)",
    "state": "the municipality's state (abbreviation)",
    "health_region": "the municipality's health region (SUS regionalisation, CIR code), in an area study",
    "smr": "standardised ratio: events over expected_indirect",
    "model_rate": "expected_model over the population, per the row's per",
    "numerator": "the events the share or indicator counts (a linked share: the records paired)",
    "denominator": "the events it is a share of (empty when the share is a product of shares)",
    "proportion": "the indicator's share",
    "proportion_low": "lower 95 % bound of the share (Clopper-Pearson)",
    "proportion_high": "upper 95 % bound of the share (Clopper-Pearson)",
    "provisional": "true for a year the source declares not yet final (its notifications still being investigated "
                   "and closed): a fall in it may be the year still filling in",
    "id": "the finding's stable id in the register",
    "component": "the kind of departure (transient, level, trend, cluster, share, group, divergence)",
    "question": "the question that found it (excess, step, trend, cluster, propagation, share, institution, group, "
                "divergence)",
    "tier": "the expectation it departs from: B0 national rates without place effects; B1 the place's own model fitted on "
            "the same years (a local departure only); BP/BPA prospective, fitted on earlier years and extrapolated; cohort",
    "places": "IBGE municipality codes of the finding's locus (first 20)",
    "place_names": "the locus's municipality names",
    "n_places": "the number of municipalities in the locus",
    "groups": "the finding's population group (column: label (code)), if any",
    "first_year": "first year of the locus",
    "last_year": "last year of the locus",
    "effect": "the method's own statistic, in effect_unit: for a scan (cluster, excess level) the ratio of its scanned "
              "cells against the expectation raised by the minimum effect it tests, not the locus's observed over "
              "expected; read `ratio` and its interval for the size of the departure",
    "effect_unit": "the unit of effect",
    "interval_low": "lower 95 % bound of effect where the method gives one (see ratio_low otherwise)",
    "interval_high": "upper 95 % bound of effect where the method gives one",
    "q": "false-discovery-rate q value in its question family (Benjamini-Bogomolov over the fields asked, then "
         "Benjamini-Hochberg within each selected field); a scan's p comes from its null replicates drawn sequentially "
         "(Besag & Clifford: up to 200 at the standard depth, scaled by the study's `nulls`), from a Gumbel tail fitted to "
         "their maxima where none reached the observed: a q far below 1/200 is that tail extrapolated, read it as beyond "
         "every replicate, not as a precise probability (1e-83 on a cluster, the review, 2026-10-13)",
    "family": "the multiple-testing family q is adjusted in",
    "methods": "the methods the question used",
    "class": "recording class: signal (a change in the events), system (a change in recording), noise",
    "class_reason": "why the class was given",
    "class_grade": "the strength of the class's evidence",
    "replication": "replication on the held-out later years (R0 not tested; higher, replicated)",
    "corroborated": "whether an independent source shows the same departure",
    "corroboration": "the corroborating sources and their figures",
    "status": "the finding's register status (open, replicated, retired)",
    "uncalibrated": "true when the method's false-positive rate is not calibrated on null worlds",
    "reliability": "the method's measured reliability, or why none",
    "locus_observed": "a group finding's locus: all the field's events there",
    "locus_expected": "a group finding's locus: their expected count",
    "observed": "the field's events at the finding's locus (places and years)",
    "expected": "the expected count there under the model of the finding's tier (findings.parquet: `tier`; BP or BPA, a "
                "prospective finding: the fit on the years before its window, `train_last`): B1, fitted on "
                "the same years with each year's own effect, so it reads a departure of the place from its own level and "
                "from the shared course, never a rise every place shares (a national or statewide one is absorbed: those "
                "are read prospectively, hypotheses and series); B0, the whole's rates without place effects",
    "locus_ratio": "a group finding's locus: all the field's events there over their expected count (its own estimate "
                   "is `effect`)",
    "locus_ratio_low": "lower 95 % bound of locus_ratio, as ratio_low",
    "locus_ratio_high": "upper 95 % bound of locus_ratio, as ratio_low",
    "context_profile.parquet:context": "the context (water, sanitation, ...)",
    "context_profile.parquet:places": "how many places of the finding's locus the context was read at",
    "excess": "observed minus expected",
    "ratio": "observed over expected at the locus (a standardised ratio)",
    "ratio_low": "lower 95 % bound of ratio: exact Poisson, expected fixed (Breslow and Day 1987)",
    "ratio_high": "upper 95 % bound of ratio, as ratio_low",
    "related": "other fields departing at the same locus, with their ratio and interval",
    "context": "contexts (water, sanitation, ...) in which the locus stands out",
    "story": "the number of the story (findings of one place and period, read together in the report) it belongs to",
    "variable": "the column the field is split by",
    "recorded_on": "where on the records the codes are read together (a certificate's lines, an admission's diagnoses)",
    "value": "the column's code as recorded",
    "value_label": "the code's label from the source's dictionary; undecoded when none",
    "total": "the field's events in the row's geography and year (the share's denominator; by sex or age band, those "
             "with both recorded)",
    "share": "the proportion: events with the value (or persons with the outcome) over the total",
    "share_low": "lower 95 % bound: Clopper-Pearson; for persons, Rubin's rules over link draws (normal)",
    "share_high": "upper 95 % bound, as share_low",
    "finding": "the finding's id",
    "related_field": "the other field",
    "low": "lower 95 % bound",
    "high": "upper 95 % bound",
    "percentile": "the locus's percentile among places",
    "places_with_value": "places with a value of the context",
    "support": "the geography a relation is read at",
    "leader": "the leading series",
    "lag": "the lag, in periods",
    "rho": "correlation of the two series' departures",
    "z": "its z statistic",
    "p": "p value",
    "reported": "whether reported at the study's q",
    "pair": "the pair of fields",
    "years": "the years read",
    "partial": "the correlation partialled on the shared series",
    "screen": "true for a relation the data-space screen found (the topic against every block the store holds)",
    "cohort": "the persons scanned: source and role",
    "outcome": "the outcome linked to the person",
    "attribute": "the person's attribute contrasted",
    "reference": "the attribute's reference level",
    "rr": "rate ratio against the reference (Rubin's rules over link draws)",
    "persons.parquet:recording": "true when the level is a missing one (blank, not recorded): a difference in the "
                                 "records' completeness between persons with and without the outcome, not a risk",
    "persons": "persons in the cohort",
    "with_outcome": "persons with the outcome (mean over link draws)",
    "note": "why a value is absent, or what was tested",
    "capture": "the population counted across lists",
    "lists": "the sources linked as lists",
    "patterns": "persons by list pattern (1 on the list, 0 not)",
    "estimate": "estimated total: Chapman (1951) for two lists; log-linear chosen by AIC for three (Fienberg 1972)",
    "model": "the log-linear model chosen",
    "completeness": "each list's share of the estimated total",
    "hypothesis": "the declared hypothesis",
    "source": "the source tested",
    "field_reader": "the field's reader",
    "answer": "the answer: supported, not supported, or not testable and why",
    "p_holm": "p adjusted by Holm over the hypothesis's tests",
    "with_code": "the topic's records (in the area and years) that also name the category",
    "records_with_code": "every record of the area and years naming the category, the topic's or not",
    "topic_records": "the topic's records (in the area and years) the share is of: those naming a seed code on any of "
                     "the group's columns (a certificate's lines: the deaths the infarction took part in, beside those it "
                     "is the underlying cause of)",
    "lift_low": "lower 95 % bound of the lift (exact Poisson, the expected fixed)",
    "lift_high": "upper 95 % bound of the lift",
    "hypotheses.parquet:tier": "the expectation tested against: BPA (trained on the years before the window, extrapolated) or B1, and the grain",
    "institution_facts": "each establishment of an institutional finding: its CNES registration (name, type, care "
                         "level, SUS link, beds, obstetric centre, neonatal unit) at the finding's first and last year",
    "institution_volume": "each establishment's events of every code the year before the finding and in its last",
    # estimates.parquet: one schema for every descriptive number (MEASURES; docs/plans/study-estimates.md)
    "estimates.parquet:section": "the part of the analysis: rates, municipalities, seasonality, codes, case mix, "
                                 "completeness, measures, case fatality, trends, associated causes, contexts, "
                                 "associations (the ecological regression of the municipalities' events on the "
                                 "contexts)",
    "estimates.parquet:measure": "what the estimate is: one of the measures defined below the tables",
    "estimates.parquet:model": "the model behind the estimate: a trend's (crude or age-sex adjusted log-linear, "
                               "joinpoint of the crude or standardised rate), a season's method, the hierarchical tier",
    "estimates.parquet:variable": "what the estimate is of within the field: a case-mix or code column, a completeness "
                                  "indicator, a measure's column, a context, a season's date column, a race ratio",
    "estimates.parquet:variable_label": "the variable's name in the source's dictionary (a measure's, an interval's: the "
                                        "days from its start to its end; a context's: what pegasus_data declares it)",
    "estimates.parquet:value": "the variable's value the estimate is of: a code or category, a quantile's probability, a "
                               "measure's 'valid', 'not recorded' or 'outside the domain'",
    "estimates.parquet:estimate": "the estimate, in `unit` (a count: events or records)",
    "estimates.parquet:interval": "the 95 % interval's method (empty: the estimate has none)",
    "estimates.parquet:id": "the estimate's number in the folder, which a paper's number cites",
    "estimates.parquet:partial": "why the estimate's year is a part of one (a monthly source's year the lake holds "
                                 "fewer than twelve months of): never compare it with whole years; no trend reads it",
    "estimates.parquet:variance": "the estimate's variance on its own scale, where the method gives one (a standardised "
                                  "rate's, from its Poisson cells: what a pooled or compared rate needs)",
    "estimates.parquet:p": "the estimate's p (a test's or a ratio's; the measure says which)",
    "estimates.parquet:q": "Benjamini-Hochberg q over the estimate's family (the municipalities' ratios, the associated "
                           "categories)",
    "estimates.parquet:numerator": "the events (or records) the estimate counts",
    "estimates.parquet:denominator": "what it is over, of the kind `denominator_kind`",
    "estimates.parquet:denominator_kind": "the denominator's kind: person-years, live births, the field's events, "
                                          "expected events, days",
    "estimates.parquet:per": "a rate's scale: per this many units of the denominator",
    "estimates.parquet:unit": "the estimate's unit (a rate's 'per 100,000 person-years', days, years, a context's)",
    "estimates.parquet:geography": "the estimate's geography: national (Brazil), area (the declared study area), region, "
                                   "state, health macro-region or health region, municipality, or reference (an area "
                                   "study's comparison: Brazil and each macro-region the area lies in)",
    "estimates.parquet:place": "the geography's code: BR, the area's IBGE codes joined by +, a region's digit and name, "
                               "a state's two-digit code, a health (macro-)region's code and name, a municipality's "
                               "six-digit IBGE code",
    "estimates.parquet:place_name": "a municipality's name (IBGE)",
    "estimates.parquet:period_kind": "year (first = last), month, period (first to last, summed: never add it to its "
                                     "years) or segment (a joinpoint segment's years)",
    "estimates.parquet:first": "the estimate's first year",
    "estimates.parquet:last": "the estimate's last year",
    "estimates.parquet:comparator": "what a ratio is against: Brazil, the region without the area, the area's own or "
                                    "Brazil's age-sex rates",
    "estimates.parquet:note": "what the estimate needs read beside it: a peak's date, the joinpoints' years, a code's "
                              "level (category or code: never sum the two), a context's year and source",
    # a name that means another thing in one table
    "context_profile.parquet:value": "the context's value at the finding's locus",
    "capture.parquet:population": "what is counted: cases or deaths",
    "capture.parquet:observed": "persons on at least one list",
    "capture.parquet:years": "the years pooled",
    "hypotheses.parquet:places": "the hypothesis's municipalities (IBGE codes)",
    "hypotheses.parquet:allocated_before": "the mean share of the field's events placed at a residence in the years before "
                                           "the window (`allocated_share`); the expectation is scaled by window over before",
    "hypotheses.parquet:allocated_window": "the mean share of the field's events placed at a residence in the window",
    "hypotheses.parquet:years": "the hypothesis's years",
    "hypotheses.parquet:observed": "the field's events at the hypothesis's places and time",
    "hypotheses.parquet:expected": "their expected count under the model",
}


def _codebook(decl: Declaration, scope: Scope, out: Path) -> list[str]:
    """The folder's README.md: what each table holds, column by column (`COLUMNS`); each field the study read with its
    definition, case status, codes and denominator and their evidence (pegasus_data's event types); the code and data
    it was computed on. Returns the columns no entry describes."""
    lines = [f"# {decl.study}", "",
             f"Period {decl.years[0]}-{decl.years[-1]}, area {decl.where or 'BR'}, depth {decl.depth}; code "
             f"{config.code_version()}, data {config.data_version()}; written {time.strftime('%Y-%m-%d %H:%M')}.", "",
             "## Fields read", ""]
    seen = set()
    for it in (i for i in scope.items if i.status == "in"):
        key = (it.dataset, it.event, json.dumps(it.source, sort_keys=True, default=str))
        if key in seen or not it.years:
            continue
        seen.add(key)
        et = gateway.event_type(it.dataset, it.event) or {}
        st, ex, sn = et.get("status") or {}, et.get("exposure") or {}, et.get("source_notes") or {}
        src = it.source or {}
        # the item's reading: two items of one source had printed identical lines (the review of the study)
        how = (f" linked across {src['link']} ({src.get('side')} side)" if src.get("source") == "linked"
               else " (second coding: counted and described only)" if it.count_only else "")
        text = (f"- **{it.dataset} {it.event}**{_codes_text(it)} on {src.get('classifier') or 'the primary classifier'}"
                f"{how}, {min(it.years)}-{max(it.years)}: one row is {et.get('grain') or 'one event'}")
        if st:
            why = st.get("evidence") or et.get("evidence")
            text += f"; counted where {st['column']} is {', '.join(st['values'])}" + (f" ({why})" if why else "")
        if ex:
            text += f"; rates per {ex.get('per', 1):g} {' + '.join(ex['events'])} ({ex.get('evidence') or ''})"
        else:
            text += "; rates per 100,000 person-years of residents"
            codes = [str(c) for c in (it.source or {}).get("codes") or []]
            if codes and _code_structure(it) == "ICD10" and all(c[:1] in "OP" for c in codes):
                text += ", and per 1,000 live births (SINASC-DN), pregnancy and perinatal codes (RIPSA C.1, C.3)"
        if sn.get("definition"):
            text += f"; the source's definition: {sn['definition']}"
        lines.append(text)
    lines += ["", "## Tables", ""]
    missing = []
    for path in sorted(out.glob("*.parquet")):
        cols = pq.read_schema(path).names
        lines += [f"### {path.name} ({pq.read_metadata(path).num_rows:,} rows)", "", "| column | meaning |", "|---|---|"]
        for c in cols:
            meaning = COLUMNS.get(f"{path.name}:{c}") or COLUMNS.get(c)
            if meaning is None:
                missing.append(f"{path.name}:{c}")
            lines.append(f"| {c} | {meaning or 'UNDOCUMENTED'} |")
        lines.append("")
    if (out / "estimates.parquet").exists():
        lines += ["## The measures of estimates.parquet", "",
                  "Each row of estimates.parquet is one estimate: filter on `section` and `measure`. study.duckdb's "
                  "views `rates` and `municipalities` hold the wide shapes a paper's tables read.", "",
                  "| measure | what it is |", "|---|---|",
                  *(f"| {k} | {v} |" for k, v in MEASURES.items()
                    if k in set(pq.read_table(out / "estimates.parquet", columns=["measure"]).column(0).to_pylist())),
                  ""]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return missing


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        # three significant digits below a thousand, whole numbers with separators above ("1.61e+03" had been a count)
        return f"{v:.3g}" if abs(v) < 1e3 else f"{v:,.0f}"
    return str(v)


# ---------------------------------------------------------------------- export


def body(folder: str | Path) -> list[dict]:
    """The analytic body every study folder must hold, whatever its preset, area, period or topic (author, 2026-10-12:
    enough data and statistics for a thorough epidemiological analysis and a paper, produced reliably across all presets
    and scopes): each part present with content, or absent with a stated reason. What is required follows the folder's
    own declaration (`Declaration.choice`): no persons part where persons were not asked for. Each row: part, status
    (met / missing), evidence."""
    import yaml

    folder = Path(folder)
    out: list[dict] = []

    def part(name, ok, evidence):
        out.append({"part": name, "status": "met" if ok else "missing", "evidence": evidence})

    def table(name):
        path = folder / f"{name}.parquet"
        return pq.read_table(path).to_pandas() if path.exists() else None

    decl = load(folder / "study.yml")
    scope = yaml.safe_load((folder / "scope.yml").read_text(encoding="utf-8")) if (folder / "scope.yml").exists() else {}
    read = scope.get("read") or []
    unread = (scope.get("deferred") or []) + (scope.get("not_read") or [])
    part("scope", bool(read) and all((x.get("note") or x.get("why") or x.get("reason")) for x in unread),
         f"{len(read)} sources read with their reasons, {len(unread)} left out each with why")
    est = table("estimates")

    def section(name: str):
        return est[est["section"] == name] if est is not None and "section" in est else None
    desc = section("rates")
    counted = {x["dataset"] for x in read if (x.get("source") or {}).get("source") != "linked"}
    if desc is None or desc.empty:
        part("descriptive epidemiology", False, "no rates among the estimates")
    else:
        rated = desc[desc["estimate"].notna() & desc["low"].notna() & desc["high"].notna()]
        missing = sorted(d for d in counted if d not in set(rated["dataset"]))
        part("descriptive epidemiology", not missing,
             f"{len(rated)} estimates with 95 % intervals and their denominators "
             f"({', '.join(sorted(set(rated['measure'].astype(str))))[:120]})"
             + (f"; none for {missing}" if missing else ""))
        # the meaning of the numbers, not their presence (2026-10-12): an area's total is not Brazil's; a notified
        # condition with a confirmed-case event is rated on its cases; a pregnancy or perinatal field per live births
        whole = "national" if decl.where in (None, "BR") else "area"
        wrong = sorted(set(desc["geography"].dropna()) - {whole, "region", "state",
                                                          *(level for _, level in HEALTH_LEVELS),
                                                          *(["reference"] if whole == "area" else [])})
        part("descriptive: geography", not wrong, f"the whole at level {whole}" + (f"; also {wrong}" if wrong else ""))
        cased = sorted({x["dataset"] for x in read if x.get("event") == "case"})
        uncased = sorted({x["dataset"] for x in read if not x.get("source") and any(
            e.get("status") and e.get("kind") == "case" for e in gateway.event_types(x["dataset"]))} - set(cased))
        rated_cases = {d for d in cased if (desc["field"].astype(str).str.startswith(f"{d}:case:")).any()}
        part("descriptive: case definition", not uncased and rated_cases == set(cased),
             f"confirmed-case rates for {sorted(rated_cases) or 'no source'}"
             + (f"; read as notifications only: {uncased}" if uncased else "")
             + (f"; no case rate for {sorted(set(cased) - rated_cases)}" if set(cased) - rated_cases else ""))
        rates_ = desc[desc["measure"] == "crude_rate"]
        perinatal = rates_[rates_["label"].astype(str).str.contains(r": [OP]\d", regex=True)]
        births = perinatal[perinatal["denominator_kind"].astype(str).str.contains("birth")]
        part("descriptive: perinatal denominators", perinatal.empty or set(births["field"]) == set(perinatal["field"]),
             f"{births['field'].nunique()} of {perinatal['field'].nunique()} pregnancy or perinatal fields rated per live births")
    figs = sorted((folder / "figures").glob("*_series.png")) if (folder / "figures").exists() else []
    maps = sorted((folder / "figures").glob("*_map.png")) if (folder / "figures").exists() else []
    fields_read = [x for x in read if (x.get("source") or {}).get("source") != "linked"]
    part("figures", len(figs) >= len(fields_read) and len(maps) >= len(fields_read),
         f"{len(figs)} series and {len(maps)} maps for {len(fields_read)} fields read (each its own)")
    f = table("findings")
    if f is None:
        part("findings", False, "no findings table")
    else:
        named = f["place_names"].notna().mean() if len(f) else 1.0
        classed = f["class"].notna().mean() if len(f) else 1.0
        with_e = f[f["expected"].fillna(0) > 0] if "expected" in f else f.iloc[:0]
        intervals = (with_e["ratio_low"].notna().mean() if "ratio_low" in with_e and len(with_e) else
                     (1.0 if not len(with_e) else 0.0))
        # a recording class where the declaration triages its answers (a survey does not: said, not required)
        triaged = decl.choice("triage")
        part("findings", len(f) == 0 or (named > 0.95 and (classed > 0.9 or not triaged) and intervals > 0.99),
             f"{len(f)} findings, {classed:.0%} with a recording class" + ("" if triaged else " (triage: false)")
             + f", {named:.0%} with named places, {intervals:.0%} of those with an expectation with an O/E and its "
             "interval" + ("" if len(f) else " (none at q: said in the report)"))
    g = section("case mix")
    if g is not None and len(g):
        g = g[g["measure"] == "proportion"]
        ok = len(g) > 0 and g["estimate"].notna().mean() > 0.99 and g["low"].notna().mean() > 0.99
        # an undecoded value is shown as such, never guessed (CLAUDE.md §6): named here, not a threshold to fail on
        und = g[g["value_label"].astype(str).str.endswith("(undecoded)")] if "value_label" in g else g
        cols = sorted(set(und["dataset"].astype(str) + ":" + und["variable"].astype(str))) if len(und) else []
        part("groups", bool(ok), f"{len(g)} rows, shares with intervals {'present' if ok else 'missing'}; "
             f"{len(und) / max(len(g), 1):.0%} of values undecoded" + (f" ({', '.join(cols[:5])})" if cols else ""))
    rel = table("relations")
    if "screen" in decl.choice("relations"):
        sc = rel[rel["screen"].fillna(False).astype(bool)] if rel is not None and "screen" in rel else None
        bad = [] if sc is None or "note" not in sc else [n for n in sc["note"].dropna() if str(n).startswith("failed")]
        part("screen", sc is not None and len(sc) > 0 and not bad,
             f"{0 if sc is None else int(sc['pair'].notna().sum())} screened relations" + (f"; {bad[0][:120]}" if bad else ""))
    if "fields" in decl.choice("relations"):
        part("relations", rel is not None and len(rel) > 0, f"{0 if rel is None else len(rel)} relation rows")
    if decl.choice("persons"):
        pe, ca = table("persons"), table("capture")
        shares = 0 if pe is None or "share" not in pe else int(pe["share"].notna().sum())
        scanned = pe is not None and "note" in pe and pe["note"].astype(str).str.contains("contrasts over").any()
        part("persons", pe is not None and len(pe) > 0 and (shares > 0 or not scanned),
             f"{0 if pe is None else len(pe)} cohort rows, {shares} outcome proportions with intervals")
        part("completeness across systems", ca is not None and len(ca) > 0,
             f"{0 if ca is None else len(ca)} capture rows (estimates, overlaps or why none)")
    if "quality" in decl.choice("readers") and f is not None:
        q = f[f["label"].astype(str).str.contains("quality:", regex=False)] if len(f) else f
        qd = desc[desc["label"].astype(str).str.contains("—", regex=False)] if desc is not None else None
        # a code set's items read no quality field (they would read every event of the type, not the topic's): its
        # data quality is its own records' completeness by year, which the case mix gives (the SINASC study, 2026-10-14)
        comp = section("completeness")
        nr = 0 if comp is None else int((comp["variable"].astype(str).str.startswith("not recorded:")
                                         & (comp["period_kind"] == "year")).sum())
        part("data quality", (q is not None and len(q) > 0) or (qd is not None and len(qd) > 0) or nr > 0,
             f"{0 if q is None else len(q)} quality findings, {0 if qd is None else len(qd)} recorded shares by year, "
             f"{nr} of the topic's own variables not recorded by year")
    lk = table("linkage")
    if any((x.get("source") or {}).get("source") == "linked" for x in read):
        part("linkage", lk is not None and len(lk) > 0 and "pairs" in lk,
             f"{0 if lk is None else len(lk)} link runs described (pairs, false-match rate, validations)")
    tr = section("trends")
    tr = tr[tr["measure"].isin(["apc", "aapc"])] if tr is not None else None
    part("trends", tr is not None and ((len(tr) > 0 and tr["low"].notna().all()) or len(decl.years) < 3),
         f"{0 if tr is None else len(tr)} annual percent changes with intervals (crude and age-sex adjusted)")
    # where the topic's own records were described (`_measures`: not a whole type nationally), and the source's outcome
    # declares its fatal codes
    fatal = set()
    me_ = section("measures")
    for ds in counted & (set() if me_ is None else set(me_["dataset"])):
        try:
            if any(r.get("fatal") for r in gateway.roles(ds)):
                fatal.add(ds)
        except Exception:  # noqa: BLE001 - a dataset pegasus_data cannot describe declares no outcome
            pass
    if fatal:
        cf = section("case fatality")
        got = set() if cf is None else set(cf[cf["measure"] == "case_fatality"]["dataset"])
        part("case fatality", fatal <= got, f"case fatality for {sorted(got)}"
             + (f"; none for {sorted(fatal - got)}, whose outcome declares its fatal codes" if fatal - got else ""))
    me = section("measures")
    if any(x.get("dataset") for x in read):
        part("measures", me is not None, f"{0 if me is None else len(me)} measure rows (the topic's own quantities)")
    se = section("seasonality")
    part("seasons", se is not None and len(se) > 0 and se[se["measure"] == "seasonal_index"]["low"].notna().any(),
         f"{0 if se is None else len(se)} month rows (seasonal index with intervals, the test of uniformity)")
    pl = section("municipalities")
    part("places", pl is not None and (pl["measure"] == "crude_rate").any() and (pl["measure"] == "smr").any()
         and pl[pl["measure"] == "crude_rate"]["low"].notna().any() and (pl["measure"] == "smoothed_smr").any(),
         f"{0 if pl is None else len(pl)} municipality estimates (rates, standardised ratios, their empirical-Bayes "
         f"smoothing, model expectations with intervals) for "
         f"{0 if pl is None or 'field' not in pl else pl['field'].nunique()} count fields")
    cx = section("contexts")
    if cx is not None and len(cx) > 0:
        ec = section("associations")
        part("associations", ec is not None and (ec["measure"] == "association").any()
             and ec[ec["measure"] == "association"]["low"].notna().all(),
             f"{0 if ec is None else int((ec['measure'] == 'association').sum())} ecological associations of the "
             f"fields with {cx['variable'].nunique()} contexts, with intervals")
    qa = section("completeness")
    placed = set() if qa is None or "variable" not in qa else set(
        qa[qa["variable"].astype(str).str.startswith("events placed")]["dataset"])
    part("completeness", qa is not None and len(qa) > 0 and not (counted - placed),
         f"{0 if qa is None else len(qa)} completeness rows; placed share for {sorted(placed)}"
         + (f"; none for {sorted(counted - placed)}" if counted - placed else ""))
    if desc is not None and not desc.empty:
        part("descriptive: period", (desc["period_kind"] == "period").any(),
             f"{int((desc['period_kind'] == 'period').sum())} whole-period estimates")
    methods = folder / "METHODS.md"
    text = methods.read_text(encoding="utf-8") if methods.exists() else ""
    absent = sorted(d for d in counted if d not in text)
    part("methods", bool(text) and not absent, f"METHODS.md {'written' if text else 'missing'}"
         + (f"; no word of {absent}" if absent else ""))
    hyp = table("hypotheses")
    if decl.hypotheses:
        part("hypotheses", hyp is not None and len(hyp) > 0 and hyp["answer"].notna().all(),
             f"{0 if hyp is None else len(hyp)} answers to {len(decl.hypotheses)} declared hypotheses")
    readme = folder / "README.md"
    undocumented = [c for c in (readme.read_text(encoding="utf-8").splitlines() if readme.exists() else [])
                    if c.endswith("| UNDOCUMENTED |")]
    part("codebook", readme.exists() and not undocumented,
         "README.md describes every table's columns and every field's definition and denominator"
         if readme.exists() and not undocumented else f"README.md {'missing' if not readme.exists() else undocumented[:3]}")
    rep = folder / "report.html"
    text = rep.read_text(encoding="utf-8") if rep.exists() else ""
    sections = ["Summary", "Descriptive epidemiology", "Scope", "Methods and limitations", "Provenance"]
    part("report", all(x in text for x in sections), f"report.html, {len(text) // 1024} kB")
    prov = json.loads((folder / "provenance.json").read_text(encoding="utf-8")) if (folder / "provenance.json").exists() else {}
    # a step that raised, or a part of one recorded as failed (one field's fit, a link year, an extract)
    failed = [k for k, v in (prov.get("steps") or {}).items() if isinstance(v, dict) and "error" in v]
    failed += [f"{k}: {sub}" for k, v in (prov.get("steps") or {}).items() if isinstance(v, dict)
               for sub, w in v.items() if isinstance(w, str) and w.startswith("failed:")]
    failed += [f"product {k}: {w}" for k, w in (prov.get("products_failed") or {}).items()]
    part("every step ran", bool(prov) and not failed, f"{len(prov.get('steps') or {})} steps, {len(failed)} failed"
         + (" (products only: the lanes not run, their fits and answers as stored)" if prov.get("products_only") else "")
         + (f": {failed[0][:80]}" if failed else ""))
    return out


def audit(folder: str | Path) -> list[dict]:
    """A study folder against the win condition's acceptance items 1–10 (BACKLOG): each item met, partial or not met,
    with the evidence read from the folder's own files, so a study is certified by what it holds, not by a reading of
    its log. Item 8's export and item 10's machine are checked on the folder as it stands."""
    import yaml

    folder = Path(folder)

    def table(name):
        path = folder / f"{name}.parquet"
        return pq.read_table(path).to_pylist() if path.exists() else []

    scope = yaml.safe_load((folder / "scope.yml").read_text(encoding="utf-8")) if (folder / "scope.yml").exists() else {}
    prov = json.loads((folder / "provenance.json").read_text(encoding="utf-8")) if (folder / "provenance.json").exists() else {}
    read = scope.get("read") or []
    findings, relations, persons = table("findings"), table("relations"), table("persons")
    hyp, captured, profile = table("hypotheses"), table("capture"), table("context_profile")
    out: list[dict] = []

    def item(n, what, checks):
        met = [c for c, ok in checks if ok]
        missing = [c for c, ok in checks if not ok]
        out.append({"item": n, "what": what, "status": "met" if not missing else ("partial" if met else "not met"),
                    "evidence": "; ".join(met), "missing": "; ".join(missing)})

    def reads(ds, pred=lambda i: True):
        return [i for i in read if gateway.same_dataset(i["dataset"], ds) and pred(i)]

    sources = (i.get("source") or {} for i in read)
    sigtap = any(s_.get("structure") == "SIGTAP" for s_ in sources)
    contexts = [str(c) for c in scope.get("contexts") or []]
    decl = yaml.safe_load((folder / "study.yml").read_text(encoding="utf-8")) if (folder / "study.yml").exists() else {}
    agravos = [str(a).upper() for a in ((decl.get("topic") or {}).get("seeds") or {}).get("sinan") or []]
    item(1, "scope", [
        (f"every seeded agravo read ({', '.join(agravos) or 'none seeded'})",
         all(reads(f"SINAN-{a}") for a in agravos)),
        ("SIH with the codes in any diagnosis", any(i.get("mentions") or (i.get("source") or {}).get("classifier") in
                                                    ("DIAG_SECUN", "mentions:admission.diagnoses") for i in reads("SIHSUS-RD"))
         or any(r.get("dataset") in ("SIHSUS-RD", "SIH-RD") for r in scope.get("related_codes") or [])),
        ("SIM with them on any certificate line", any(i.get("mentions") for i in reads("SIM-DO"))
         or any(r.get("dataset") == "SIM-DO" and "mentions" in str(r.get("where")) for r in scope.get("related_codes") or [])),
        ("SINASC births with related anomalies", bool(reads("SINASC-DN"))),
        ("SIA serology procedures read", sigtap and bool(reads("SIASUS-PA") or reads("SIASUS-BI"))),
        (f"medicines {len(scope.get('medicines') or [])}", bool(scope.get("medicines"))),
        ("BNAFAR/SNGPC for them", any("sngpc" in c.lower() or "bnafar" in c.lower() for c in contexts)),
        ("SISAGUA among the contexts", any("sisagua" in c.lower() for c in contexts)),
        (f"related codes with strength {len(scope.get('related_codes') or [])}",
         any(r.get("lift") is not None for r in scope.get("related_codes") or [])),
        (f"person paths with viability {len(scope.get('person_paths') or [])}",
         any(p_.get("verdict") for p_ in scope.get("person_paths") or [])),
    ])
    fields_ = " ".join(str(f.get("field")) for f in findings) + " " + " ".join(json.dumps(i.get("source") or {}) for i in read)
    item(2, "fields", [
        ("counts", bool(read)),
        ("measures", "measure" in fields_ or any("measures" in (i.get("readers") or {}) for i in read)),
        ("compositions", "share" in fields_ or any("compositions" in (i.get("readers") or {}) for i in read)),
        ("infection away from residence", "away" in fields_),
        ("intervals", "interval" in fields_ or any("intervals" in (i.get("readers") or {}) for i in read)),
        ("ratios", "population" in fields_),
        ("linked shares", "linked" in fields_),
        ("a capture of TOXC × SIH × SIM", any(r.get("patterns") and str(r.get("lists", "")).count("×") >= 2 for r in captured)),
        ("quality fields", any("quality:" in str(f.get("label")) for f in findings)
         or any("quality" in (i.get("readers") or {}) for i in read)),
    ])
    asked = {f.get("question") for f in findings}
    item(3, "components", [
        (f"questions answered: {', '.join(sorted(a for a in asked if a))}", len(asked - {None}) >= 5),
        ("the declared hypothesis answered", any(h.get("answer") in ("supported", "not supported at q") for h in hyp)),
    ])
    ctx_rel = [r for r in relations if any(c.lower() in str(r.get("field", "")).lower() + str(r.get("leader", "")).lower()
                                           + str(r.get("pair", "")).lower() for c in contexts)]
    item(4, "relations", [
        (f"among fields: {len(relations)} rows", bool(relations)),
        (f"with contexts: {len(ctx_rel)} rows", bool(ctx_rel)),
        ("SISAGUA as a context with lags", any("sisagua" in json.dumps(r, default=str).lower() for r in ctx_rel)),
        ("the data-space screen", any(r.get("screen") for r in relations)),
    ])
    item(5, "persons", [
        (f"cohort contrasts {sum(1 for r in persons if r.get('rr') is not None)}", any(r.get("rr") is not None for r in persons)
         or any("contrasts" in str(r.get("note")) for r in persons)),
        (f"capture–recapture: {len([r for r in captured if r.get('estimate')])} populations estimated, "
         f"{len([r for r in captured if r.get('patterns') and not r.get('estimate')])} reported without a total for "
         "links not viable", any(r.get("patterns") for r in captured)),
    ])
    def share(k):
        return sum(1 for f in findings if f.get(k) not in (None, "", [], {})) / max(len(findings), 1)

    signals = [f for f in findings if f.get("class") == "signal"]
    asked_corr = sum(1 for f in signals if f.get("corroboration")) / max(len(signals), 1)
    item(6, "interpretation", [
        (f"recording class on {share('class'):.0%}", share("class") > 0.9),
        (f"graded {share('class_grade'):.0%}", share("class_grade") > 0.5),
        (f"replication on {share('replication'):.0%}", share("replication") > 0.9),
        (f"corroboration on {asked_corr:.0%} of the signals (only signals are asked)", asked_corr > 0.9),
        (f"context profiles {len(profile)}", bool(profile)),
        (f"stories {share('story'):.0%}", share("story") > 0),
        ("institutional findings with CNES facts", any(f.get("institution_facts") for f in findings)),
    ])
    # the folder's own tables as it writes them (estimates.parquet replaced descriptive and groups, 2026-10-14), and
    # the analytic body a paper is written from (`body`: every part met)
    files = ["findings", "estimates", "relations", "persons", "capture"]
    try:
        parts = body(folder) if (folder / "study.yml").exists() else []
    except (DeclarationError, OSError, KeyError) as exc:   # a folder whose declaration no longer loads: said
        parts = [{"part": "the declaration", "status": "missing", "evidence": f"{type(exc).__name__}: {exc}"[:200]}]
    gaps = [r["part"] for r in parts if r["status"] != "met"]
    item(7, "products", [(f"{f}.parquet", (folder / f"{f}.parquet").exists()) for f in files] + [
        ("figures", any((folder / "figures").glob("*.png")) if (folder / "figures").exists() else False),
        ("report.html", (folder / "report.html").exists()), ("METHODS.md", (folder / "METHODS.md").exists()),
        ("README.md (the codebook)", (folder / "README.md").exists()), ("provenance.json", bool(prov)),
        (f"the analytic body: {len(parts) - len(gaps)} of {len(parts)} parts met"
         + (f" (missing: {', '.join(gaps)})" if gaps else ""), bool(parts) and not gaps)])
    size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) / 2**20
    item(8, "storage", [(f"the folder holds {size:.1f} MB", size < 200), ("study.duckdb views", (folder / "study.duckdb").exists())])
    def places_of(f):
        # the findings table writes a finding's places as text ("431690, 430010 (+17)"), the register as a list
        raw = f.get("places") or []
        return {int(x) for x in (raw if isinstance(raw, list) else str(raw).replace("(", " ").replace(",", " ").split())
                if str(x).isdigit() and len(str(x)) == 6}

    # the declaration's documented events (its hypotheses): each found by discovery, a signal at one of its places
    # over its window, not only answered as a hypothesis
    events = []
    for h in decl.get("hypotheses") or []:
        where = {int(str(w)[:6]) for w in h.get("where") or [] if str(w)[:6].isdigit()}
        years = _when(h.get("when")) if h.get("when") else []
        hits = [f for f in findings if where & places_of(f) and f.get("class") == "signal" and years
                and (f.get("first_year") or 0) <= years[-1] and years[0] <= (f.get("last_year") or 9999)]
        label = h.get("note") or json.dumps(h, ensure_ascii=False)
        events.append((f"{label}: {len(hits)} signals by discovery "
                       + ", ".join(sorted({str(f.get('label'))[:40] for f in hits}))[:250], bool(hits)))
    item(9, "documented event", events or [("the declaration names no documented event (hypotheses)", False)])
    minutes = (prov.get("seconds") or 0) / 60
    est = prov.get("estimated_minutes") or scope.get("estimated_minutes")
    item(10, "cost", [(f"{minutes:.0f} min against an estimate of {est} made before running",
                       bool(prov) and est is not None and minutes <= float(est))])
    return out


def search(query: str, limit: int = 40) -> dict[str, list[dict]]:
    """What a study of ``query`` would seed on: the ICD-10 codes whose label holds it (pegasus_data `label_matches`,
    accents and case ignored; categories first), the SINAN agravos whose records carry one of those codes as their
    condition (pegasus_data `condition_codes`: the agravo's own ICD-10 code, not its name matched), and the declared
    context fields whose name or label holds it (`gateway.declared_fields`). The first step from a question to a
    declaration (`new`): a person picks the codes, nothing is chosen for them."""
    import unicodedata

    import pegasus_data as pg

    def plain(x: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", str(x).lower()) if unicodedata.category(c) != "Mn")

    terms = [t for t in str(query).split(",") if t.strip()]
    codes = pg.label_matches([t.strip() for t in terms])
    codes = sorted(codes, key=lambda r: (r["level"] != "chapter", r["level"] != "block", r["level"] != "category",
                                         r["code"]))
    cats = {r["code"] for r in codes if r["level"] in ("category", "subcategory")}
    t = pg.condition_codes(root=config.data_root())
    agravos: dict[str, set] = {}
    for d, c in zip(t.column("dataset").to_pylist(), t.column("code").to_pylist(), strict=True):
        c = str(c or "").replace(".", "").upper()
        if c and any(c.startswith(x[:3]) and (len(x) == 3 or c.startswith(x)) for x in cats):
            agravos.setdefault(str(d), set()).add(c)
    sinan = [{"sinan": d.split("-", 1)[-1].split("_", 1)[-1], "dataset": d, "codes": sorted(cs)}
             for d, cs in sorted(agravos.items()) if d.upper().startswith("SINAN")]
    words = [plain(x.strip()) for x in terms]
    contexts = []
    for name, spec in sorted(gateway.declared_fields().items()):
        text = plain(f"{name} {spec.get('label') or ''} {spec.get('description') or ''}")
        if any(w in text for w in words):
            contexts.append({"context": name, "label": spec.get("label") or spec.get("description") or ""})
    # the typed roles a term names, every served dataset's (what a record condition is written on)
    roles_ = {}
    for ds in sorted(gateway.event_datasets()):
        for r in gateway.roles(ds):
            text = plain(f"{r['role']} {r.get('name') or ''}")
            if r.get("kind") in ("number", "category", "date") and any(w in text for w in words):
                roles_.setdefault((ds, r["role"]), {"dataset": ds, "role": r["role"], "name": r.get("name") or "",
                                                    "kind": r["kind"], "column": r["column"]})
    return {"icd10": codes[:limit], "sinan": sinan, "contexts": contexts[:limit], "roles": list(roles_.values())[:limit]}


def parse_records(text: str, name: str, per: str | None = None) -> dict:
    """A records seed from one line: "DATASET[:event]: role op value [and role op value ...]" (ops <, <=, >, >=, ==;
    "role in a,b" for codes); numbers are read as numbers, codes as filed."""
    head, _, body = str(text).partition(": ")
    if not body:
        raise DeclarationError(f"--records {text!r}: write DATASET: role op value [and role op value]")
    ds, _, event = head.strip().partition(":")
    clauses = []
    for part in body.split(" and "):
        words = part.strip().split(None, 2)
        if len(words) == 3 and words[1] == "in":
            clauses.append({"role": words[0], "in": [w.strip() for w in words[2].split(",")]})
            continue
        if len(words) != 3 or words[1] not in ("<", "<=", ">", ">=", "=="):
            raise DeclarationError(f"--records clause {part!r}: role op value, op one of < <= > >= ==, or role in a,b")
        value = words[2]
        if value.lstrip("-").replace(".", "", 1).isdigit():     # a number; anything else a code as filed
            value = float(value) if "." in value else int(value)
        clauses.append({"role": words[0], "op": words[1], "value": value})
    return {"dataset": ds.strip(), **({"event": event.strip()} if event.strip() else {}), "name": name,
            "condition": clauses, **({"per": per} if per else {})}


def new(name: str, icd10: list[str] | None = None, sinan: list[str] | None = None, terms: list[str] | None = None,
        where: str = "BR", period: str = "2014-2023", depth: str = "standard", only: list[str] | None = None,
        contexts: list[str] | None = None, folder: str | Path = "studies", records: list[dict] | None = None) -> Path:
    """A study declaration written from its choices (ARCHITECTURE §3.1), every key commented with what it does and
    what to change, validated by `load` before it is kept: the step after `search`. A declaration whose problems
    `load` reports is not written."""
    if not (icd10 or sinan or terms or records):
        raise DeclarationError("a study needs seeds: --icd10 codes, --sinan agravos, --terms, or --records a condition "
                               "(`pegasus-core search`)")
    path = Path(folder) / f"{name}.yml"
    if path.exists():
        raise DeclarationError(f"{path} exists: choose another name, or edit it")
    seeds = {k: v for k, v in (("icd10", icd10), ("sinan", sinan), ("terms", terms)) if v}
    import json as json_

    def record_line(r: dict) -> str:
        return "      - " + json_.dumps(r, ensure_ascii=False)

    def flow(xs) -> str:
        return "[" + ", ".join(str(x) for x in xs) + "]"
    lines = [f"# {name}: written by `pegasus-core new`; every key is described in the README and ARCHITECTURE §3.1.",
             f"study: {name}",
             "topic:",
             "  seeds:                       # the topic: ICD-10 codes (any level), SINAN agravos, label terms",
             *(f"    {k}: {flow(v)}" for k, v in seeds.items()),
             *(["    records:", *(record_line(r) for r in records)] if records else []),
             *([f"  only: {flow(only)}             # the sources read (leave out to read every source holding the codes)"]
               if only else []),
             f"period: {period}               # first-last year",
             f"where: {where}                    # BR, states (AL or 27, several as a list) or municipality codes",
             f"depth: {depth}               # survey, standard, deep or exhaustive: presets of the choices below",
             "# related: 3                   # related codes read beside the topic's own, strongest first (0: none)",
             "# persons: true                # the cohort scan over linked persons (deep and exhaustive)",
             "# download: 10                 # gigabytes the study may download (years held in the lake are free)",
             (f"contexts: {flow(contexts)}" if contexts else
              "contexts: auto                 # municipal contexts related to the rates (auto: every declared one)"),
             "# hypotheses:                  # declared tests, e.g. an outbreak or a relation with its lags",
             "#   - {component: transient, where: [431690], when: 2018, note: a documented outbreak}",
             ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        load(path)
    except DeclarationError:
        path.unlink()
        raise
    return path


def export(folder: str | Path, to: str | Path, tables: list[str] | None = None, fmt: str = "parquet") -> Path:
    """A study folder copied elsewhere (ARCHITECTURE §3.6). It stands alone already: its tables are its own files and
    study.duckdb's own tables (2026-10-14: views had read this machine's paths); with ``fmt="csv"`` every table of the
    database (or ``tables``) is also written as CSV under tables/."""
    import duckdb

    folder, to = Path(folder), Path(to)
    shutil.copytree(folder, to, dirs_exist_ok=True)
    if fmt != "parquet":
        con = duckdb.connect(str(folder / "study.duckdb"), read_only=True)
        (to / "tables").mkdir(exist_ok=True)
        for (name,) in con.execute("SELECT table_name FROM duckdb_tables() WHERE NOT internal").fetchall():
            if tables and name not in tables:
                continue
            con.execute(f"COPY {name} TO '{(to / 'tables' / f'{name}.csv').as_posix()}' (FORMAT csv, HEADER)")
        con.close()
    return to
