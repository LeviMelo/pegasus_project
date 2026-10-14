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
SEED_SYSTEMS = ("icd10", "sinan", "terms")
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
PRESETS = {
    "survey": {"readers": [], "related": 0, "relations": ["fields"], "chapters": False, "persons": False,
               "replicate": False, "download": 2.0, "draws": 1, "related_questions": []},
    "standard": {"readers": list(READERS), "related": 3, "relations": ["fields"], "chapters": False, "persons": False,
                 "replicate": False, "download": 10.0, "draws": 1, "related_questions": []},
    "deep": {"readers": list(READERS), "related": 8, "relations": ["fields", "contexts"], "chapters": False,
             "persons": True, "replicate": True, "download": 40.0, "draws": 10, "related_questions": []},
    "exhaustive": {"readers": list(READERS), "related": 20, "relations": list(RELATIONS), "chapters": False,
                   "persons": True, "replicate": True, "download": float("inf"), "draws": 20,
                   "related_questions": []},
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
    questions: list[str] | None = None  # the questions asked of every field (None: all, `questions.QUESTIONS`)
    nulls: float = 1.0                   # replicate null worlds per test, as a factor on each method's own (`NULLS`)
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
    nulls = doc.get("nulls", "standard")
    if not (nulls in NULLS or (isinstance(nulls, (int, float)) and nulls > 0)):
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
    if problems:
        raise DeclarationError(f"{path}:\n  - " + "\n  - ".join(problems))
    return Declaration(study=str(doc["study"]), seeds={k: [str(c) for c in v] for k, v in seeds.items()}, years=years,
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
                       nulls=float(NULLS.get(nulls, nulls)) if nulls in NULLS or isinstance(nulls, (int, float)) else 1.0,
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
    extract: bool = False                # its codes read from an extract of the dataset, file by file (`_extract_or_lake`)
    confirm_last: int | None = None      # stage E's later years: its leads selected on the years up to it, tested after
    questions: list[str] | None = None   # the declaration's questions (None: every question)
    note: str = ""
    #: a second coding of the topic's own events (an alternative classifier of the primary's structure: SIM's cause
    #: before investigation): counted and described, asked nothing, given no supports or linked shares
    count_only: bool = False


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
    import pegasus_data as pg

    published = gateway.published_years(dataset)
    held = control.reserved(dataset)
    ys = [y for y in years if (not published or y in published) and (not held or y < min(held))]
    volume = _volumes(dataset, config.data_root())
    # read once per scope (`resolve` clears it): not across a run, whose `ensure_lake` extends the lake; per call, the
    # deep scope priced each related code in every served dataset by a fresh read
    if dataset not in _LAKE:
        _LAKE[dataset] = frozenset(pg.lake_coverage(dataset, root=config.data_root()))
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

    def per_item(dataset, years):
        total = 0.0
        for step in ("later_years", "triage", "prospective"):
            for pool in ([m for m in item_steps if m.get("step") == step and m.get("dataset") == dataset
                          and m.get("area") == area],
                         [m for m in item_steps if m.get("step") == step and m.get("dataset") == dataset],
                         [m for m in item_steps if m.get("step") == step]):
                if pool:
                    total += float(np.median([float(m["seconds"]) * len(years) / max(len(m.get("years") or [1]), 1)
                                              * size(tuple(area or ())) / size(tuple(m.get("area") or ()))
                                              for m in pool]))
                    break
        return total
    from .questions import QUESTIONS

    codes = [int(c) for c in gateway.municipality_names() if str(c).isdigit()]
    size = functools.cache(lambda area: max(int(config.in_area(codes, frozenset(area) if area else None).sum()), 1))

    def per_field(dataset, years):
        # a measurement scaled by years and by the places its area holds (a question's cost is per place and period:
        # Rio Grande do Sul's 497 municipalities against Brazil's 5,570)
        for pool in ([m for m in asked if m.get("dataset") == dataset and m.get("area") == area],
                     [m for m in asked if m.get("dataset") == dataset],
                     [m for m in asked if m.get("area") == area], asked):
            if pool:
                return float(np.median([float(m["seconds"]) * len(years) / max(len(m.get("years") or [1]), 1)
                                        * size(tuple(area or ())) / size(tuple(m.get("area") or ())) for m in pool]))
        # nothing measured yet: the leptospirosis slice's ~390 fields' fits and questions in Rio Grande do Sul, 9 years,
        # took ~33 min (2026-10-12), about 5 s each, scaled the same way; replaced by the store's own once one ran
        return 5.0 * len(years) / 9 * size(tuple(area or ())) / size((43,))
    for it in items:
        if it.status != "in" or not it.years:
            continue
        share = len(it.questions if it.questions is not None else decl.questions or QUESTIONS) / len(QUESTIONS)
        try:
            n = 1 + len(update.system_readers(_plan(it).systems[0], _plan(it), list(it.blocks)))
        except Exception:  # noqa: BLE001 - a reader list that cannot be built here is built (and fails) in the run
            n = 1
        fit = 0.0
        for block in it.blocks:
            # the nearest stored fit: same dataset and block, the same area and event first, scaled by years and
            # places (a national fit of 14 years, 354 s, had priced each of Rio Grande do Sul's fields)
            same = [m for m in fits if m["key"].get("dataset") == it.dataset and m["key"].get("block") == block]
            same = ([m for m in same if m["key"].get("area") == area and m["key"].get("event") == it.event]
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
        replicating = decl.choice("replicate") and len(it.years) >= 2 * LATER_YEARS + 2
        steps = per_item(it.dataset, it.years) if replicating else 0.0
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
                rows = cooccur.associated(it.dataset, it.event, list(it.years), list(cols), seeds)
            except Exception as exc:  # noqa: BLE001 - a source whose records cannot be read is said
                log(f"study: associated {it.dataset} {role}: {type(exc).__name__}: {exc}")
                continue
            out += [{"dataset": it.dataset, "where": role, "years": f"{min(it.years)}-{max(it.years)}", **r} for r in rows]
    return out


def _related_codes(decl: Declaration, items: list[Item], seeds: list[str], log) -> list[dict]:
    """The codes related to the seeds on the same records (BACKLOG 4.2, `cooccur.related_codes`), wherever a read item's
    records carry several codes (`fields.declared_mentions`: certificate lines, all diagnoses, anomaly lists), over the
    item's years in the lake; each with its strength (lift and interval) and FDR."""
    from . import cooccur

    if not seeds:
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
                rows = cooccur.related_codes(it.dataset, it.event, list(it.years), cols, seeds, q=decl.q)
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
            primary_structure = next((c.get("structure") for c in et.get("classifiers") or []
                                      if c.get("role") == "primary"), None)
            for c in et.get("classifiers") or []:
                if c.get("role") == "primary" and c.get("structure") == "ICD10":
                    continue                    # read by the primary loop, with its tree
                if c.get("structure") == "ICD10" and prefixes:       # its records decide (`_records`)
                    # an alternative of the primary's own structure codes the same events again (SIM's CAUSABAS_O, the
                    # cause before investigation): its rates are described beside the primary's, its questions,
                    # supports and links would restate the primary's (Alagoas's infarction deaths were asked twice
                    # over, 2026-10-14); of another structure (SIA's diagnosis beside its procedure) it reaches records
                    # the primary's codes do not, and is read whole
                    again = c.get("role") != "primary" and c.get("structure") == primary_structure
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
    os.environ["PEGASUS_NULLS"] = str(decl.nulls)        # every test's replicate worlds (`config.replicates`)
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
    items = [i for i in items if i.status != "none"]
    for it in items:
        # a code set's field is the codes' events only, a ratio's the numerator per denominator event: the declared
        # readers would read every event of the type against the population
        chosen = decl.choice("readers")
        it.readers = {} if it.source else {k: "all" for k in chosen if k != "linked"}
        it.questions = decl.questions
        coded = bool(it.source) and "codes" in it.source and not ({"population", "support"} & set(it.source))
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
            strength[r["code"]] = max(strength.get(r["code"], 0.0), float(r.get("low") or 0.0))
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
                        else decl.questions)
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
            # the persons must be the topic's: an agravo's own notifications (every record is the topic), or a source
            # whose own records carry the topic's related codes (a birth's anomalies); every admission of SIH is not
            if not (it.reason.startswith("seed sinan:") or same):
                continue
            outcomes = [(d, role) for d, role in sorted(reach)] + same
            years = [y for y in sorted(it.years)[::-1] if gateway.person_scopes(kind, y)][:PERSON_YEARS]
            label = f"{it.dataset} {kind[1]}"
            if not years:
                out.append({"cohort": label, "note": "no year of the study holds its persons' link runs"})
                continue
            for y in years:
                mine = sorted({o.dataset for o in scope.items if o.status == "in"})   # the persons of its own links
                key = {"what": "study_cohort", "kind": list(kind), "event": it.event, "outcomes": outcomes, "year": y,
                       "draws": decl.choice("draws"), "q": decl.q, "data": config.data_version(),
                       "code": config.code_key(tools.cohort), "datasets": mine}
                hit = store.get_table("study_table", key)
                if hit is not None:
                    out.extend(hit.to_pylist())
                    continue
                notes: list[dict] = []
                try:
                    found = tools.cohort(it.dataset, it.event, kind[1], outcomes, y, draws=decl.choice("draws"),
                                         q=decl.q, log=log, datasets=mine, notes=notes)
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
    for r in sorted(related, key=lambda r: -float(r.get("low") or 0.0)):
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
            why = (f"related code {code} ({r['label']}): on {here['observed']:.0f} of its records with the topic's codes, "
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


def folder_of(decl: Declaration) -> Path:
    return decl.path.parent / decl.study


def run(decl: Declaration, log=print) -> Path:
    """Compute the study and write its folder (ARCHITECTURE §3.4). Each read event type runs through `update` on its own
    years with the topic's nodes; the leads of those fields become the findings."""
    import yaml

    t0 = time.time()
    # the study's area for this process and its lanes (`config.study_area`): every block is the area's
    if decl.where not in (None, "BR"):
        os.environ["PEGASUS_AREA"] = ",".join(str(a) for a in decl.where)
    else:
        os.environ.pop("PEGASUS_AREA", None)
    out = folder_of(decl)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(decl.path, out / "study.yml")
    phases, t = {}, time.time()
    scope = resolve(decl, log=log)
    phases["scope"] = round(time.time() - t, 1)
    estimate = scope.to_dict()["estimated_minutes"]            # made before running (acceptance item 10), kept as made
    (out / "scope.yml").write_text(yaml.safe_dump(scope.to_dict(), sort_keys=False, allow_unicode=True), encoding="utf-8")
    read = [i for i in scope.items if i.status == "in"]
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
    steps = _run_items(decl, read, log)
    phases["lanes"], t = round(time.time() - t, 1), time.time()
    products = _Lap()
    tables = _write_products(decl, scope, out, log, products)
    phases["products"] = round(time.time() - t, 1)
    # the wall clock of each phase against the scope's estimate (acceptance item 10), what the next estimate reads
    prov = {"study": decl.study, "depth": decl.depth, "written": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "seconds": round(time.time() - t0, 1), "phases": phases, "products_seconds": dict(products),
            "estimated_minutes": estimate,
            "code_version": config.code_version(), "data_version": config.data_version(), "store": prepared,
            "steps": steps, "store_tables": tables}
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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"left": float(seconds)}), encoding="utf-8")
    tmp.replace(path)


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
    steps = {}
    for k, it in enumerate(group):
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


def _plan(it: Item, others: list | None = None):
    """The `update` plan of one item: its system with the readers its depth adds."""
    from . import update

    return update.Plan(years=it.years, systems=[update.System(it.dataset, it.event, it.blocks, nodes=it.nodes,
                                                              mentions=it.mentions, source=it.source, extract=it.extract,
                                                              **it.readers)],
                       relations=False, triage=True, report=None, questions=it.questions,
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

    def __call__(self, name: str) -> None:
        now = time.time()
        self[name] = round(self.get(name, 0.0) + now - self._t, 1)
        self._t = now


def _write_products(decl: Declaration, scope: Scope, out: Path, log, lap: _Lap | None = None) -> dict[str, str]:
    """Findings, descriptive tables, the expectation tables (in the store, viewed), figures, the report; each product's
    seconds into ``lap``."""
    import duckdb

    lap = _Lap() if lap is None else lap

    names = gateway.municipality_names()
    rows, desc, views, figs, groups = [], [], {}, [], []
    series = {}          # each primary field's observed and expected by place and period: the related fields' reading
    current = leads.Register().current()
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
                label = (f.label or node) + _codes_text(it) + (f" — {shown}" if shown else "")
                key = {"what": "study_expectations", "field": f.id, "years": list(it.years), "data": config.data_version(),
                       "code": config.code_key(_expectation_table)}
                path = store.address("study_table", key) / "table.parquet"
                if not path.exists():
                    store.put_table("study_table", key, _expectation_table(sv, names))
                views[f"expectations_{_slug(f'{it.dataset}_{name}_{node}')}"] = path.as_posix()
                rows_ = _descriptive(it, s, f, label) + (_race_rates(it, s, f, label) if not name else [])
                # a year the source says is not final yet (pegasus_data's ``final_after_years``: SINAN's notifications
                # are closed over three years; RS's 2023 congenital records had no closing date, the review, 2026-10-13)
                final = ((gateway.event_type(it.dataset, it.event) or {}).get("source_notes") or {}).get("final_after_years")
                if final:
                    for r in rows_:
                        if r.get("year") is not None:
                            r["provisional"] = int(r["year"]) > int(time.strftime("%Y")) - int(final)
                # the share placed, for the counts and for each other place they are read at: a place of infection
                # or of care left blank for 35-44 % of gestational cases makes its rates lower bounds (the review)
                support = (src or {}).get("support") if name and str(name).startswith("support:") else None
                if (not name or support) and (not it.source or (it.source or {}).get("codes")):
                    shares = _allocation(it, list(it.years), support=support)
                    for r in rows_:
                        if r.get("year") in shares and r["level"] == _whole()[0]:
                            r["allocated_share"] = shares[r["year"]]
                desc.extend(rows_ + _apc(rows_))
                # the field's own answers, on the item's years (each reader is its own field: counts, mentions, an
                # interval, a composition's share)
                rows.extend({**_finding(x, it, label, names), "_event": it.event,
                             "_places": [int(q) for q in x.locus.get("places") or []],
                             "_institutions": sorted({str(i) for i in x.locus.get("institutions") or []}
                                                     | ({str(f_)} if (f_ := _one_institution(x)) else set()))}
                            for x in current
                            if x.fields and x.kind == "answer" and x.status != "retired" and x.fields[0] == f.id
                            and list(x.provenance.get("years") or []) == list(it.years))
                if not name:
                    try:                   # B0 beside B1: a finding's O/E is against its own tier's expectation
                        mu0 = s.surprise(node, "B0").mu
                    except Exception:  # noqa: BLE001 - a field with no B0: its B0 findings' O/E are said missing
                        mu0 = None
                    series[f.id] = (label, it.dataset, np.asarray(sv.places), np.asarray(sv.years), sv.y, sv.mu, mu0)
                    figs.append(_series_figure(out, sv, f, label, it, session=s))
                    try:
                        d = s.expectations.model(f.block).data
                        expo = dict(zip(np.asarray(d.places).tolist(), d.N.sum(axis=(1, 2)).tolist(), strict=True))
                        figs.append(_map_figure(out, sv, f, label, it, [r for r in rows if r["field"] == f.id], expo,
                                                str(d.population)))
                    except Exception as exc:  # noqa: BLE001 - a map that cannot be drawn is a note; the tables stand
                        log(f"study: {it.dataset} {node} map: {type(exc).__name__}: {exc}")
                    lap("fields: tables, figures, maps")
                    groups.extend(_groups(it, s, f, label, log))
                    lap("fields: groups")
    related = _related(rows, series)
    pq.write_table(_rows_table(related) if related else pa.table({"finding": pa.array([], pa.string())}),
                   out / "related.parquet")
    lap("related")
    assoc = _associated(decl, scope, log)
    pq.write_table(_rows_table(assoc) if assoc else pa.table({"code": pa.array([], pa.string())}),
                   out / "associated.parquet")
    lap("associated")
    chosen = decl.choice("relations")
    rel = _relations(scope, decl, log) if "fields" in chosen else []
    lap("relations")
    rel += _determinants(scope, decl, log) if "contexts" in chosen else []
    lap("determinants")
    rel += _screen(scope, decl, log) if "screen" in chosen else []
    lap("screen")
    pq.write_table(_rows_table(rel) if rel else pa.table({"field": pa.array([], pa.string())}),
                   out / "relations.parquet")
    _institution_facts(rows, log)
    _institution_explains(rows)
    lap("institutions")
    persons = _persons(decl, scope, log) if decl.choice("persons") else []
    lap("persons")
    pq.write_table(_rows_table(persons) if persons else pa.table({"outcome": pa.array([], pa.string())}),
                   out / "persons.parquet")
    captured = _capture(decl, scope, log) if decl.choice("persons") else []
    lap("capture")
    pq.write_table(_rows_table(captured) if captured else pa.table({"population": pa.array([], pa.string())}),
                   out / "capture.parquet")
    profile = _context_profiles(decl, scope, rows, log)
    lap("context profiles")
    pq.write_table(_rows_table(profile) if profile else pa.table({"finding": pa.array([], pa.string())}),
                   out / "context_profile.parquet")
    _stories([r for r in rows if r.get("class") == "signal" and "quality:" not in str(r.get("label"))])  # `story` saved
    lap("stories")
    for r in rows:
        r.pop("_places", None)
        r.pop("_institutions", None)
        r.pop("_event", None)
    findings = _rows_table(rows) if rows else pa.table({"id": pa.array([], pa.string())})
    pq.write_table(findings, out / "findings.parquet")
    pq.write_table(_rows_table(desc) if desc else pa.table({"field": pa.array([], pa.string())}),
                   out / "descriptive.parquet")
    pq.write_table(_rows_table(groups) if groups else pa.table({"field": pa.array([], pa.string())}),
                   out / "groups.parquet")
    db = out / "study.duckdb"
    if db.exists():
        db.unlink()
    con = duckdb.connect(str(db))
    for name, path in views.items():
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')")
    # the folder's own tables by absolute path: DuckDB reads a relative path from the reader's working directory, and
    # the survey's folder opened only from the directory the study ran in (2026-10-11)
    out = out.resolve()
    con.execute(f"CREATE VIEW findings AS SELECT * FROM read_parquet('{(out / 'findings.parquet').as_posix()}')")
    con.execute(f"CREATE VIEW descriptive AS SELECT * FROM read_parquet('{(out / 'descriptive.parquet').as_posix()}')")
    con.execute(f"CREATE VIEW groups AS SELECT * FROM read_parquet('{(out / 'groups.parquet').as_posix()}')")
    con.execute(f"CREATE VIEW context_profile AS SELECT * FROM read_parquet('{(out / 'context_profile.parquet').as_posix()}')")
    con.execute(f"CREATE VIEW related AS SELECT * FROM read_parquet('{(out / 'related.parquet').as_posix()}')")
    con.execute(f"CREATE VIEW relations AS SELECT * FROM read_parquet('{(out / 'relations.parquet').as_posix()}')")
    con.execute(f"CREATE VIEW persons AS SELECT * FROM read_parquet('{(out / 'persons.parquet').as_posix()}')")
    con.execute(f"CREATE VIEW capture AS SELECT * FROM read_parquet('{(out / 'capture.parquet').as_posix()}')")
    con.close()
    lap("tables")
    hyp = _hypotheses(decl, scope)
    pq.write_table(_rows_table(hyp) if hyp else pa.table({"hypothesis": pa.array([], pa.string())}),
                   out / "hypotheses.parquet")
    lap("hypotheses")
    _report(decl, scope, out, rows, desc, [f for f in figs if f], hyp, rel, persons, captured)
    lap("report")
    _codebook(decl, scope, out)
    lap("codebook")
    return views


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
            var = sv.mu + np.where(np.isfinite(sv.phi), sv.mu ** 2 / np.where(np.isfinite(sv.phi), sv.phi, 1.0), 0.0)

            def window(sel_t, sv=sv, rows_u=rows_u, var=var):
                Y = float(sv.y[np.ix_(rows_u, sel_t)].sum())
                M = float(sv.mu[np.ix_(rows_u, sel_t)].sum())
                V = float(var[np.ix_(rows_u, sel_t)].sum())
                return Y, M, V

            monthly = bool(yrs.size) and int(yrs.max()) > 9999
            inside = np.isin(yrs, months) if monthly else np.isin(yrs, years)
            Y, M, V = window(inside)
            if comp == "step":
                Yb, Mb, _ = window(yrs < years[0])
                after = np.isin(yrs, [y for y in yrs if y >= years[0]])
                Ya, Ma, _ = window(after)
                ratio = (Ya / Ma) / (Yb / Mb) if Ma > 0 and Mb > 0 and Yb > 0 else None
                se = np.sqrt(1 / max(Ya, 0.5) + 1 / max(Yb, 0.5))
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


def _expectation_table(sv, names: dict) -> pa.Table:
    """Observed against expected per municipality and period, with the surprise and the place's names."""
    t = sv.table()
    u = [str(x) for x in t.column("u").to_pylist()]
    return t.append_column("municipality", pa.array([(names.get(c) or {}).get("name") for c in u])) \
            .append_column("state", pa.array([(names.get(c) or {}).get("uf_sigla") for c in u]))


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
    if d.n is not None or str(d.population).startswith("events:") or (it.source or {}).get("population")             or d.key.get("collapse"):
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
                out.append({"field": f.id, "label": f"{label} — race: {labels.get(v, v)}", "dataset": it.dataset,
                            "level": level, "unit": unit, "year": year, "events": ev, "population": ex,
                            "per": f"standardised ratio, race {race} (age-sex indirect, population account)",
                            "rate": ev / ex, "rate_low": lo / ex, "rate_high": hi / ex,
                            "crude_per_100k": None, "standardised_per_100k": None,
                            **({"note": note} if note else {})})
    return out


def _allocation(it: Item, years: list[int], support: str | None = None) -> dict[int, float]:
    """Each year's share of the field's events, nationally, that its counts can place (a residence, a sex, an age): the
    rest are unallocated and in no rate. A rate series whose share moves reads a recording change: SIA-PA's toxoplasma
    serology by residence rose 65-fold in Rio Grande do Sul over 2014-2023 while the tests billed stayed near five million
    a year, its consolidated production (no patient, no residence) giving way to individual records: 0.15 % of the
    tests placed in 2014, 9.7 % in 2023 (2026-10-13). The field's own codes for a code set."""
    import pyarrow.compute as pc

    src = it.source or {}
    codes = list(src.get("codes") or [])
    out = {}
    for y in years:
        try:
            ec = gateway.event_counts(it.dataset, it.event, int(y), classifier=src.get("classifier"), cell=False,
                                      codes=tuple(codes) if it.extract else (), support=support, area=(tuple(sorted(config.study_area())) if config.study_area() else None))
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
        lost = float(pc.sum(tabs[1].column("y")).as_py() or 0) if tabs[1].num_rows else 0.0
        if placed + lost > 0:
            out[int(y)] = placed / (placed + lost)
    return out


def _apc(rows: list[dict]) -> list[dict]:
    """Each series' annual percent change (the descriptive's rows of one field, level, unit and denominator over the
    years): a Poisson regression of the events on the year with the denominator as offset, the slope's interval
    widened by the Pearson dispersion (quasi-Poisson; never below Poisson's). APC = 100 (e^b - 1). A paper's trend is
    a number with an interval; the folder had the yearly rates only (2026-10-12)."""
    series: dict[tuple, list[dict]] = {}
    for r in rows:
        if r.get("year") is not None and not r.get("provisional") and r.get("population") and r.get("per") not in ("share", "mean per event") \
                and not str(r.get("per", "")).startswith(("days", "median")):
            series.setdefault((r["field"], r["level"], r["unit"], r["per"]), []).append(r)
    out = []
    for (field_, level, unit, per), rs in series.items():
        rs = sorted(rs, key=lambda r: r["year"])
        t = np.array([float(r["year"]) for r in rs])
        y = np.array([float(r["events"]) for r in rs])
        n = np.array([float(r["population"]) for r in rs])
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
        r0 = rs[0]
        out.append({"field": field_, "label": r0["label"], "dataset": r0["dataset"], "level": level, "unit": unit,
                    "year": None, "events": float(y.sum()), "population": float(n.sum()),
                    "per": f"annual percent change, {int(t[0])}-{int(t[-1])}, rate {per}",
                    "rate": 100 * np.expm1(b1), "rate_low": 100 * np.expm1(b1 - 1.96 * se),
                    "rate_high": 100 * np.expm1(b1 + 1.96 * se),
                    "crude_per_100k": None, "standardised_per_100k": None})
    return out


def _descriptive(it: Item, s, f, label: str) -> list[dict]:
    """Counts, crude and directly age–sex-standardised rates per 100,000 by year, nationally and by state, from the
    fitted block's own cells (the population of the model's exposure; the standard is the period's national
    age–sex structure). Each crude rate carries its exact Poisson 95% interval (Garwood), the exposure held fixed; a
    ratio field's rate is per denominator event (``per``), its "population" the denominator's events."""
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
    std = N.sum(axis=(0, 1))
    std = std / std.sum() if std.sum() > 0 else std
    out = []
    # the exposure the block was fitted on: person-years, or other events (a declared ratio, or the event type's
    # declared denominator: live births), reported per 1,000 of them
    ratio = str(d.population).startswith("events:")
    per, scale = ((f"1,000 {d.population[len('events:'):].replace(';', ' + ')} events", 1e3) if ratio
                  else ("100,000 person-years", 1e5))

    def row(level: str, unit: str, t: int, yy: np.ndarray, nn: np.ndarray) -> dict:
        with np.errstate(divide="ignore", invalid="ignore"):
            rate_g = np.where(nn > 0, yy / nn, 0.0)
        events, pop = float(yy.sum()), float(nn.sum())
        lo = chi2.ppf(0.025, 2 * events) / 2 if events > 0 else 0.0
        hi = chi2.ppf(0.975, 2 * events + 2) / 2
        return {"field": f.id, "label": label, "dataset": it.dataset, "level": level, "unit": unit,
                "year": int(np.asarray(d.years)[t]), "events": events, "population": pop, "per": per,
                "rate": scale * events / pop if pop else None, "rate_low": scale * lo / pop if pop else None,
                "rate_high": scale * hi / pop if pop else None,
                "crude_per_100k": None if ratio or not pop else 1e5 * events / pop,
                "standardised_per_100k": None if ratio or not pop else 1e5 * float((rate_g * std).sum())}

    for t in range(T):
        out.append(row(*_whole(), t, y[:, t].sum(0), N[:, t].sum(0)))
        for level, unit, sel_u in _levels_below(np.asarray(d.places)):
            out.append(row(level, unit, t, y[sel_u, t].sum(0), N[sel_u, t].sum(0)))
    if not ratio and _birth_related(it, d):
        # a perinatal or pregnancy field's rate is per live births, the convention of infant and maternal mortality
        # (RIPSA C.1, C.3): congenital toxoplasmosis' deaths had been given per 100,000 person-years of everyone
        # (2026-10-12); the person-year rows stay, the model's own exposure
        B = _births(d)
        births = {"per": "1,000 SINASC-DN:birth events", "crude_per_100k": None, "standardised_per_100k": None}

        def per_births(level, unit, t, sel_u):        # one cell: births carry no sex or age
            r = row(level, unit, t, y[sel_u, t].sum(keepdims=True), B[sel_u, t].sum(keepdims=True))
            pop = r["population"]
            return {**r, **births, **({"rate": 1e3 * r["events"] / pop, "rate_low": r["rate_low"] / scale * 1e3,
                                       "rate_high": r["rate_high"] / scale * 1e3} if pop else {})}
        for t in range(T):
            out.append(per_births(*_whole(), t, np.ones(U, bool)))
            for level, unit, sel_u in _levels_below(np.asarray(d.places)):
                out.append(per_births(level, unit, t, sel_u))
    return out


def _birth_related(it: Item, d) -> bool:
    """Whether a count field's events belong to pregnancy or the perinatal period: its codes all in ICD-10 chapter XV
    (O00–O99) or XVI (P00–P96), or its events mostly at age 0 (the model's newborn exposure, `monolith.default_population`)."""
    codes = [str(c) for c in ((it.source or {}).get("codes") or it.nodes or [])]
    icd = (it.source or {}).get("structure", "ICD10") == "ICD10" and all(c[:1].isalpha() for c in codes)
    return str(d.population).startswith("hybrid") or bool(codes and icd and all(c[:1] in "OP" for c in codes))


def _births(d) -> np.ndarray:
    """Live births (SINASC) per place and year of a block's lattice, [U, T]; sex and age summed."""
    import pyarrow.compute as pc

    years = [int(x) for x in np.asarray(d.years)]
    t = gateway.population(years, source="events:SINASC-DN:birth")
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
    would repeat the area's)."""
    area = config.study_area()
    states = list(np.unique(state))
    return [] if area is not None and len(states) == 1 and set(area) == {int(states[0])} else states


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
    bands = [f"{lo}-{hi - 1}" if hi - 1 > lo else f"{lo}" for lo, hi in zip(edges[:-1], edges[1:], strict=True)]
    bands.append(f"{edges[-1]}+")
    state = np.asarray(d.places) // 10000
    out = []
    for by, by_name, arr, values in (("sex", "Sexo", by_sex, [("1", "Masculino"), ("2", "Feminino")]),
                                     ("age band", "Faixa etária (anos)", by_age, [(b, b) for b in bands])):
        for t, year in enumerate(np.asarray(d.years)):
            for level, unit, rows_u in [(*_whole(), np.ones(len(state), bool))] + \
                    _levels_below(np.asarray(d.places)):
                obs = arr[rows_u, t].sum(0)
                tot = float(obs.sum())
                if tot <= 0:
                    continue
                for k, (v, vl) in enumerate(values):
                    if obs[k] <= 0:
                        continue
                    o = float(obs[k])
                    out.append({"field": f.id, "label": label, "dataset": it.dataset, "by": by, "by_name": by_name,
                                "value": v, "value_label": vl, "level": level, "unit": unit, "year": int(year),
                                "observed": o, "expected": None, "total": tot, "share": o / tot,
                                "share_low": float(beta.ppf(0.025, o, tot - o + 1)),
                                "share_high": float(beta.ppf(0.975, o + 1, tot - o)) if o < tot else 1.0})
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
        for t, year in enumerate(years):
            for level, unit, sel in geo:
                obs, exp = y[sel, t].sum(0), mu[sel, t].sum(0)
                # each value's share of the field's events, with its exact (Clopper–Pearson) interval: a case mix is
                # described by proportions, and the table gave counts against a model's expectation only (2026-10-12).
                # One vectorised call per level and year: per value, 138,612 calls took 113 s of a study (2026-10-14)
                tot = float(obs.sum())
                with np.errstate(invalid="ignore", divide="ignore"):
                    lo = np.where(obs > 0, beta.ppf(0.025, obs, tot - obs + 1), 0.0) if tot else None
                    hi = np.where(obs < tot, beta.ppf(0.975, obs + 1, tot - obs), 1.0) if tot else None
                out.extend({"field": f.id, "label": label, "dataset": it.dataset, "by": column, "by_name": names.get(column, "race"),
                            "value": v, "value_label": shown[v], "level": level, "unit": unit, "year": int(year),
                            "observed": float(obs[k]), "expected": float(exp[k]), "total": tot,
                            "share": float(obs[k]) / tot if tot else None,
                            "share_low": float(lo[k]) if tot else None, "share_high": float(hi[k]) if tot else None}
                           for k, v in enumerate(values) if obs[k] > 0 or exp[k] > 0)
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
        for fid, (label, dataset, pl, yrs, y, mu, mu0) in series.items():
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
                    r["ratio"], r["ratio_low"] = o / e_, (chi2.ppf(0.025, 2 * o) / 2 if o > 0 else 0.0) / e_
                    r["ratio_high"] = chi2.ppf(0.975, 2 * o + 2) / 2 / e_
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

    contexts = gateway.rated(scope.contexts)
    out = []
    for it in (i for i in scope.items if i.status == "in" and "population" not in (i.source or {})):
        for node in _study_nodes(it, None):
            if len(it.years) < 4:
                continue
            x = (it.dataset, it.event, node)
            key = {"what": "study_determinants", "x": list(x), "source": it.source, "years": it.years,
                   "contexts": contexts, "q": decl.q,
                   "data": config.data_version(), "code": config.code_key(tools.determinants)}
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


def _institution_volume(r: dict, codes: list[str], log) -> str | None:
    """Each institution's events of every code, the year before the finding and in its last (`facility.facility_cube`):
    a ward whose whole activity grew reads as a departure of any one code there (BACKLOG 7.1's other-chapter volume)."""
    import pyarrow.compute as pc

    from . import facility

    dataset, event = r.get("dataset"), r.get("_event")
    first, last = r.get("first_year"), r.get("last_year")
    if not (dataset and event and first and last):
        return None
    published = gateway.published_years(dataset)
    base = int(first) - 1 if int(first) - 1 in published else int(first)
    try:
        cubes = {y: facility.facility_cube(dataset, event, y) for y in sorted({base, int(last)})}
    except Exception as exc:  # noqa: BLE001 - a volume that cannot be read leaves the finding without it, said
        log(f"study: institution volume {dataset} {codes}: {type(exc).__name__}: {exc}")
        return None
    parts = []
    for c in codes:
        n = {y: int(pc.sum(t.filter(pc.equal(t.column("facility"), c)).column("y")).as_py() or 0) for y, t in cubes.items()}
        ratio = f" (×{n[int(last)] / n[base]:.2f})" if n.get(base) else ""
        parts.append(f"{c}: {n[base]:,} {event} events of every code in {base}, {n[int(last)]:,} in {last}{ratio}")
    return " | ".join(parts) or None


def _context_profiles(decl: Declaration, scope: Scope, rows: list[dict], log) -> list[dict]:
    """Every finding's context profile (ARCHITECTURE §9, BACKLOG 7.2): for each context of the scope (pegasus_data's
    declared fields, each over its declared denominator, `gateway.context_value`), the mean over the finding's places
    in the study's period and its percentile among Brazil's municipalities. Each finding row also names its three most
    extreme contexts (``context``). A context that cannot be read is skipped and logged, never zero."""
    from scipy.stats import percentileofscore

    if not rows or not scope.contexts:
        return []
    pop = gateway.population(decl.years[-1:]).group_by("u").aggregate([("n", "sum")])
    places = np.asarray(pop.column("u").to_numpy())
    index = {int(u): i for i, u in enumerate(places)}
    # a context is a rate over its declared denominator; a count with none would rank places by size alone (every
    # capital at p100), so size enters once, as the residents
    values = {"population (residents)": np.asarray(pop.column("n_sum").to_numpy(), dtype=float)}
    for entry in gateway.rated(scope.contexts):
        name = gateway.context_name(entry)
        try:
            v, _ = gateway.context_value(entry, list(decl.years), places)
        except Exception as exc:  # noqa: BLE001 - a context without data for the period is skipped, said
            log(f"study: context {name}: {type(exc).__name__}: {exc}")
            continue
        if np.isfinite(v).sum() >= 100:
            values[name] = v
    out = []
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
            pct = float(percentileofscore(v[np.isfinite(v)], m))
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

    def row(level: str, unit: str, t: int, keep: np.ndarray) -> dict:
        nn = float(n[keep].sum())
        base = {"field": f.id, "label": label, "dataset": it.dataset, "level": level, "unit": unit,
                "year": int(np.asarray(d.years)[t]), "events": nn, "population": None}
        if nn <= 0:
            return base
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
                return base
            return {**base, "events": float(q["n"]), "per": "days, median" if days else "median",
                    "rate": q["q50"] - days, "p90": q["q90"] - days}
        if kind == "count":
            return {**base, "per": "mean per event", "rate": float((n[keep] * y[keep]).sum() / nn)}
        k = float((n[keep] * y[keep]).sum())
        return {**base, "per": "share", "rate": k / nn,
                "rate_low": float(beta.ppf(0.025, k, nn - k + 1)) if k > 0 else 0.0,
                "rate_high": float(beta.ppf(0.975, k + 1, nn - k)) if k < nn else 1.0}

    for t in range(len(d.years)):
        at = t_of == t
        out.append(row(*_whole(), t, at))
        for level, unit, sel_u in _levels_below(np.asarray(d.places)[d.u[sel]]):
            out.append(row(level, unit, t, at & sel_u))
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


def _map_figure(out: Path, sv, f, label: str, it: Item, findings: list[dict], expo: dict, population: str = "") -> str | None:
    """Two maps of the field over the study's years: each state's rate (events per exposure: per 100,000 person-years,
    or per denominator event for a ratio) and each municipality's standardised departure from B1, the places
    of the field's findings outlined (pegasus_data's IBGE meshes, `pg.mesh`)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    import pegasus_data as pg

    places = np.asarray(sv.places)
    obs, mu = sv.y.sum(1), sv.mu.sum(1)
    ratio = str(population).startswith("events:")
    n_of = np.array([expo.get(int(p), 0.0) for p in places])
    states = pg.mesh("state", root=config.data_root())
    munis = pg.mesh("municipality", root=config.data_root())
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
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.6), dpi=110)
    rated.plot(column="rate", ax=a1, cmap="YlOrRd", legend=True, missing_kwds={"color": "#eee"},
               legend_kwds={"shrink": 0.6, "label": "per 1,000 denominator events" if ratio else "per 100,000"})
    if one_state:
        states.boundary.plot(ax=a1, color="#555", linewidth=0.3)
    a1.set_title(f"{label}: rate by {level}, {sv.years[0]}–{sv.years[-1]}", fontsize=9)
    munis.plot(column="z", ax=a2, cmap="RdBu_r", norm=mcolors.TwoSlopeNorm(0.0, -4.0, 4.0), legend=True,
               missing_kwds={"color": "#eee"}, legend_kwds={"shrink": 0.6, "label": "(observed − expected) / sd",
                                                            "extend": "both"})
    outlined = munis[munis["u"].isin(flagged)]
    if len(outlined):
        outlined.boundary.plot(ax=a2, color="black", linewidth=0.6)
    states.boundary.plot(ax=a2, color="#555", linewidth=0.3)
    a2.set_title(f"departure from expected (B1) by municipality; {len(outlined)} with findings outlined", fontsize=9)
    for ax in (a1, a2):
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(figs / name)
    plt.close(fig)
    return f"figures/{name}"


# ---------------------------------------------------------------------- the report


def _report(decl: Declaration, scope: Scope, out: Path, rows: list[dict], desc: list[dict], figs: list[str],
            hyp: list[dict] | None = None, relations: list[dict] | None = None, persons: list[dict] | None = None,
            captured: list[dict] | None = None) -> None:
    """`report.html`: the study as a person reads it (ARCHITECTURE §3.5), from the folder's own tables."""
    from pegasus_data.linkage.engine import CAUTION, VIABLE

    e = html.escape
    read = [i for i in scope.items if i.status == "in"]
    # a quality field's departures are the data's, not the disease's: their own section (ARCHITECTURE §9.1, BACKLOG 7.5)
    quality = [r for r in rows if "quality:" in str(r.get("label"))]
    rows = [r for r in rows if "quality:" not in str(r.get("label"))]
    signal = [r for r in rows if r.get("class") == "signal"]
    institutional = [r for r in rows if r.get("class") == "facility" or r.get("institution_facts")]
    other = [r for r in rows if r.get("class") not in ("signal", "facility") and not r.get("institution_facts")]
    rank = sorted(signal, key=lambda r: (r["q"], -abs(np.log(r["ratio"])) if r.get("ratio") and r["ratio"] > 0 else 0))
    stories = _stories(signal)

    def table(rs: list[dict], cols: list[tuple[str, str]], cap: int = 40) -> str:
        head = "".join(f"<th>{e(c)}</th>" for _, c in cols)
        body = "".join("<tr>" + "".join(f"<td>{e(_fmt(r.get(k)))}</td>" for k, _ in cols) + "</tr>" for r in rs[:cap])
        more = f"<p class=more>{len(rs) - cap} more in findings.parquet</p>" if len(rs) > cap else ""
        return f"<table><tr>{head}</tr>{body}</table>{more}"

    nat = [d for d in desc if d["level"] == _whole()[0]]
    parts = [f"<h1>{e(decl.study)}</h1>",
             f"<p class=meta>depth {e(decl.depth)} · period {decl.years[0]}–{decl.years[-1]} · q {decl.q} · written "
             f"{time.strftime('%Y-%m-%d %H:%M')}</p>",
             "<h2>1. Summary</h2>",
             f"<p>{len(read)} sources read, {len(rows)} findings: {len(signal)} unexplained by recording "
             f"(signal), {len(other)} with a recording or denominator explanation, in {len(stories)} stories (findings "
             "sharing a place and overlapping years, across fields and sources).</p>",
             "".join(_story_html(k, st, e) for k, st in enumerate(stories[:15], 1)),
             (f"<p class=more>{len(stories) - 15} more stories in findings.parquet (column story)</p>"
              if len(stories) > 15 else ""),
             "<h3>Every signal finding</h3>",
             table(rank, [("label", "field"), ("dataset", "source"), ("component", "component"),
                          ("place_names", "places"), ("groups", "group"), ("first_year", "from"), ("last_year", "to"),
                          ("effect", "effect"), ("effect_unit", "unit"), ("q", "q"), ("replication", "replication"),
                          ("corroborated", "corroborated"), ("related", "related fields there (O/E, 95%)"),
                          ("context", "context (national percentile)")], cap=20),
             "<h2>2. Descriptive epidemiology</h2>",
             table(nat, [("label", "field"), ("dataset", "source"), ("year", "year"), ("events", "events"),
                         ("rate", "rate"), ("rate_low", "95% from"), ("rate_high", "to"), ("per", "per"),
                         ("standardised_per_100k", "standardised /100k")], cap=80),
             "".join(f"<img src='{e(f)}' alt=''>" for f in figs),
             "<h2>3. Institutional findings</h2><p>Departures concentrated in one establishment: often real (a referral "
             "centre, a new service, a screening programme), read with the establishment's registration.</p>",
             table(institutional, [("label", "field"), ("dataset", "source"), ("component", "component"),
                                   ("first_year", "from"), ("last_year", "to"), ("effect", "effect"), ("q", "q"),
                                   ("institution_facts", "establishment (CNES)"),
                                   ("institution_volume", "its whole activity")], cap=30),
             "<h2>3a. Data quality</h2><p>Places and periods where a column's blank or 'ignored' share departs from its "
             "expectation: where the records of this topic are least complete, and where a recording practice changed.</p>",
             table(quality, [("label", "column"), ("dataset", "source"), ("component", "component"),
                             ("place_names", "places"), ("first_year", "from"), ("last_year", "to"), ("effect", "effect"),
                             ("q", "q")], cap=30) if quality else "<p>No quality departure at this depth.</p>",
             "<h3>Completeness across systems</h3>"
             + (table(captured, [("population", "population"), ("lists", "lists"), ("years", "years"),
                                 ("patterns", "persons by list (1 on it, 0 not)"), ("observed", "observed"),
                                 ("estimate", "estimated"), ("low", "95 % from"), ("high", "to"), ("model", "model"),
                                 ("completeness", "each list's share"), ("note", "rests on")], cap=10)
                + "<p>Every estimate assumes the links find every pair: a pair a link misses (SINAN carries an age, "
                  "not a birth date, for the link to match) raises the estimate, and lists that record the same "
                  "persons more often than chance lower it.</p>"
                if any(r.get("patterns") for r in captured or []) else f"<p>{e(_capture_note(scope))}</p>"),
             "<h2>3b. Findings with a recording explanation</h2>",
             table(other, [("label", "field"), ("dataset", "source"), ("component", "component"),
                           ("place_names", "places"), ("first_year", "from"), ("last_year", "to"), ("effect", "effect"),
                           ("class", "class"), ("class_reason", "why")], cap=30),
             "<h2>3c. Relations among the study's fields</h2><p>Fields whose departures move together, at which spatial "
             "scale and lag (the joint model over graph bands; a relation is statistical, never causal by itself).</p>",
             (table(sorted([r for r in (relations or []) if r.get("reported")], key=lambda r: r.get("p", 1)),
                    [("pair", "fields"), ("support", "scale"), ("lag", "lag"), ("rho", "ρ"), ("direct", "direct"),
                     ("p", "p"), ("years", "years")], cap=25) if relations else "<p>No pair of fields shares four years.</p>"),
             "<h2>3d. Persons</h2><p>The cohort scan over linked persons (ARCHITECTURE §7.8): each attribute of the "
             "persons of a source against each outcome they reach, on their own record or through the viable links "
             "of any route, adjusted for age, sex and place; linkage uncertainty by plausible link sets.</p>"
             + (table(sorted([r for r in persons if r.get("q") is not None], key=lambda r: r["q"]),
                      [("cohort", "persons"), ("year", "year"), ("outcome", "outcome"), ("attribute", "attribute"),
                       ("level", "level"), ("reference", "against"), ("rr", "RR"), ("low", "95 % from"), ("high", "to"),
                       ("q", "q")], cap=40)
                + "".join(f"<p>{e(r['cohort'])} {r.get('year') or ''}: {e(r['note'])}</p>" for r in persons if r.get("note"))
                if persons else f"<p>{'Not read (persons: false).' if not decl.choice('persons') else 'No source read holds persons on a usable link.'}</p>"),
             "<h2>4. Scope</h2>", "<ul>" + "".join(
                 f"<li><b>{e(i.dataset)}</b> ({e(i.event)}), {i.years[0]}–{i.years[-1]}: {e(i.reason)}"
                 + (f" — {e(i.note)}" if i.note else "") + "</li>" for i in read) + "</ul>",
             "<h3>Deferred</h3><ul>" + "".join(f"<li>{e(i.dataset)}: {e(i.note)}</li>"
                                               for i in scope.items if i.status != "in") + "</ul>",
             "<h3>Codes found with the topic's on the same records</h3>"
             + (table(scope.related, [("code", "code"), ("label", "condition"), ("dataset", "source"), ("where", "on"),
                                      ("observed", "records with both"), ("expected", "expected"), ("lift", "lift"),
                                      ("low", "95% from"), ("high", "to"), ("q", "q")], cap=25)
                if scope.related else "<p>None at q.</p>"),
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
             "<h2>5. Hypotheses</h2>",
             table(hyp or [], [("hypothesis", "hypothesis"), ("source", "source"), ("support", "place"), ("field_reader", "field"),
                               ("years", "years"), ("observed", "observed"), ("expected", "expected"),
                               ("effect", "effect"), ("low", "95 % low"), ("high", "95 % high"), ("p", "p"),
                               ("p_holm", "p (Holm, over its sources)"),
                               ("answer", "answer")], cap=60) if decl.hypotheses else "<p>None declared.</p>",
             "<h2>6. Methods and limitations</h2>", _limitations(decl, scope),
             "<h2>7. Provenance</h2><p>provenance.json; every table is in study.duckdb (views onto the store and lake; "
             "nothing copied). <code>pegasus-core export</code> materialises the folder.</p>"]
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
        for p_ in str(r.get("places") or "").replace(" (+", ",").split(","):
            if p_.strip().isdigit():
                by_place.setdefault(p_.strip(), []).append(i)
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
    if not codes:
        return ""
    try:
        labels = _tree_labels(_code_structure(it))
    except Exception:  # noqa: BLE001 - a tree pegasus_data does not hold: the codes as recorded, said undecoded
        labels = {}
    shown = [f"{c} {labels[c]}" if labels.get(c) else f"{c} (undecoded)" for c in codes[:4]]
    return ": " + ", ".join(shown) + (f" (+{len(codes) - 4})" if len(codes) > 4 else "")


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
    items = "".join(f"<li>{e(r['label'])} ({e(r['dataset'])}): {e(str(r['component']))}"
                    + (f" in {e(r['groups'])}" if r.get("groups") else "")
                    + _direction(r) + (f", observed {_fmt(r.get('observed'))} against {_fmt(r.get('expected'))} expected, "
                                       f"O/E {_fmt(r.get('ratio'))} [{_fmt(r.get('ratio_low'))}, {_fmt(r.get('ratio_high'))}]"
                                       if r.get("ratio") is not None else
                                       f", {e(str(r['effect_unit']))} {_fmt(r['effect'])} (the method's statistic)")
                    + f", q {_fmt(r['q'])}"
                    + (", corroborated" if r.get("corroborated") else "")
                    + (f" (method not calibrated: {e(r['reliability'])})" if r.get("uncalibrated") else "") + "</li>"
                    for r in rows[:6])
    excess = sum(max(r.get("excess") or 0.0, 0.0) for r in rows)
    return (f"<h3>Story {k}: {e(lead.get('place_names') or 'the whole study area')}, {span}</h3><p>{_n(len(rows), 'finding')} in "
            f"{_n(len(fields_), 'field')} from {_n(len(sources), 'source')} ({e(', '.join(sources))})"
            + (f"; {excess:,.0f} events above expectation" if excess else "") + f".</p><ul>{items}</ul>")


def _limitations(decl: Declaration, scope: Scope) -> str:
    """What the study's sources say of themselves (pegasus_data ``source_notes``: definition, known errors,
    limitations, validity and finality, with their citation), each field's declared exposure with its evidence, and
    the fields this depth reads. Assembled from declarations, never written by hand (ARCHITECTURE §2.4, BACKLOG 1.8)."""
    e = html.escape
    now = int(time.strftime("%Y"))
    seen, notes = set(), []
    for it in (i for i in scope.items if i.status == "in"):
        if (it.dataset, it.event) in seen:
            continue
        seen.add((it.dataset, it.event))
        et = gateway.event_type(it.dataset, it.event) or {}
        sn, ex = et.get("source_notes") or {}, et.get("exposure") or {}
        bits = []
        if sn.get("definition"):
            bits.append(f"definition: {e(sn['definition'])}")
        if sn.get("valid_from") and it.years and min(it.years) < sn["valid_from"]:
            bits.append(f"valid from {sn['valid_from']} (earlier years are read but are not the source's own)")
        if sn.get("final_after_years"):
            prelim = [y for y in it.years if y > now - sn["final_after_years"]]
            if prelim:
                bits.append(f"preliminary: {prelim[0]}–{prelim[-1]} (a year is final {sn['final_after_years']} years later)")
        bits += [f"known error: {e(x)}" for x in sn.get("known_errors") or ()]
        bits += [f"limitation: {e(x)}" for x in sn.get("limitations") or ()]
        if ex:
            bits.append(f"rates per {ex.get('per', 1):g} {e(' + '.join(ex['events']))}: {e(ex['evidence'])}")
        if bits:
            cite = f" <span class=meta>({e(sn['source'])})</span>" if sn.get("source") else ""
            notes.append(f"<li><b>{e(it.dataset)}</b> ({e(it.event)}){cite}<ul>"
                         + "".join(f"<li>{b}</li>" for b in bits) + "</ul></li>")
    readers = sorted(decl.choice("readers"))
    methods = ("<li>Expectations: hierarchical negative-binomial models per block (ARCHITECTURE §6); findings against "
               "tier B1 unless stated; Benjamini–Hochberg/Bogomolov per question family at the study's q.</li>"
               f"<li>Fields read at depth {e(decl.depth)}: counts" + ("".join(f", {e(r)}" for r in readers))
               + "; the seeds' codes in every classifier a source carries and on every certificate line or diagnosis."
               "</li><li>Rates are per resident unless a source declares other events as its denominator (below).</li>")
    body = f"<ul>{''.join(notes)}</ul>" if notes else "<p>No source of this study declares notes.</p>"
    return f"<ul>{methods}</ul><h3>What the sources say of themselves</h3>{body}"


#: Every column a study folder's tables carry: what it holds, its unit, how it was computed. `_codebook` writes them to
#: the folder's README.md and lists any column missing here as undocumented, which `body` refuses (a folder's numbers
#: were described only in the report's prose, 2026-10-12).
COLUMNS = {
    "field": "the field's id: dataset, event, classifier and codes or reader, block",
    "label": "the field's name as a reader reads it: event, codes with their labels, reader",
    "dataset": "the source (DATASUS system and series)",
    "level": "the row's geography: national (Brazil), area (the declared study area), region (IBGE macro-region) or state",
    "unit": "the geography's code: BR, the area's IBGE codes joined by +, the region's digit and name, or the state's "
            "two-digit IBGE code",
    "year": "the year of the events (the event type's own date)",
    "events": "the field's events in the row's geography and year",
    "population": "the denominator: person-years of residents (POPSVS; with the account's age 0 for a newborn field), "
                  "or, for a standardised ratio by race, the events expected of that race's population at the field's "
                  "own age-sex rates; "
                  "or the events named in per",
    "per": "the denominator's unit: 100,000 person-years, 1,000 of the named events (live births: SINASC-DN), share, "
           "days, median",
    "rate": "events over population, times the per unit; a share's proportion; an interval's median days",
    "rate_low": "lower 95 % bound: exact Poisson (Garwood 1936), the denominator fixed; Clopper-Pearson for a share",
    "rate_high": "upper 95 % bound, as rate_low",
    "crude_per_100k": "crude rate per 100,000 person-years (none for a rate per other events)",
    "standardised_per_100k": "directly age-sex-standardised rate per 100,000, standard the period's national structure",
    "p90": "90th percentile of an interval's days",
    "provisional": "true for a year the source declares not yet final (its notifications still being investigated "
                   "and closed): a fall in it may be the year still filling in",
    "allocated_share": "the year's share of the field's events, nationally, that carry the place, sex and age a rate needs; "
                       "the rest are in no rate, and a share that moves makes the series a recording change (SIA's "
                       "consolidated production names no residence)",
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
    "q": "false-discovery-rate q value in its question family (Benjamini-Hochberg 1995); a scan's p comes from a Gumbel "
         "tail fitted to its null replicates' maxima (200 replicates), so a q far below 1/200 is that tail extrapolated: "
         "read it as beyond every replicate, not as a precise probability (1e-83 on a cluster, the review, 2026-10-13)",
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
    "expected": "the expected count there under the model, tier B1: fitted on the same years with each year's own effect, "
                "so it reads a departure of the place from its own level and from the shared course, never a rise every "
                "place shares (a national or statewide one is absorbed: those are read prospectively, hypotheses and series)",
    "excess": "observed minus expected",
    "ratio": "observed over expected at the locus (a standardised ratio)",
    "ratio_low": "lower 95 % bound of ratio: exact Poisson, expected fixed (Breslow and Day 1987)",
    "ratio_high": "upper 95 % bound of ratio, as ratio_low",
    "related": "other fields departing at the same locus, with their ratio and interval",
    "context": "contexts (water, sanitation, ...) in which the locus stands out",
    "story": "the number of the story (findings of one place and period, read together in the report) it belongs to",
    "by": "the column the field is split by",
    "by_name": "that column's name in the source's dictionary",
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
    "topic_records": "the topic's records (in the area and years) the share is of: those naming a seed code on any of "
                     "the group's columns (a certificate's lines: the deaths the infarction took part in, beside those it "
                     "is the underlying cause of)",
    "lift_low": "lower 95 % bound of the lift (exact Poisson, the expected fixed)",
    "lift_high": "upper 95 % bound of the lift",
    "associated.parquet:code": "the ICD-10 category named beside the topic on its records",
    "associated.parquet:where": "the group of columns read together (a certificate's lines, an admission's diagnoses)",
    "associated.parquet:share": "the share of the topic's records naming the category, most frequent first",
    "associated.parquet:lift": "observed over expected records naming both, against the other records of the same sex "
                               "and ten-year age band: how specific to the topic the category is, beside how common",
    "hypotheses.parquet:tier": "the expectation tested against: BPA (trained on the years before the window, extrapolated) or B1, and the grain",
    "institution_facts": "each establishment of an institutional finding: its CNES registration (name, type, care "
                         "level, SUS link, beds, obstetric centre, neonatal unit) at the finding's first and last year",
    "institution_volume": "each establishment's events of every code the year before the finding and in its last",
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
        text = (f"- **{it.dataset} {it.event}**{_codes_text(it)}, {min(it.years)}-{max(it.years)}: one row is "
                f"{et.get('grain') or 'one event'}")
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
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return missing


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.3g}" if abs(v) < 1e4 else f"{v:,.0f}"
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
    desc = table("descriptive")
    counted = {x["dataset"] for x in read if (x.get("source") or {}).get("source") != "linked"}
    if desc is None or desc.empty:
        part("descriptive epidemiology", False, "no descriptive table")
    else:
        rated = desc[desc["rate"].notna() & desc["rate_low"].notna() & desc["rate_high"].notna()]
        missing = sorted(d for d in counted if d not in set(rated["dataset"]))
        part("descriptive epidemiology", not missing,
             f"{len(rated)} rates with 95 % intervals and their denominators ({', '.join(sorted(set(rated['per'])))[:120]})"
             + (f"; none for {missing}" if missing else ""))
        # the meaning of the numbers, not their presence (2026-10-12): an area's total is not Brazil's; a notified
        # condition with a confirmed-case event is rated on its cases; a pregnancy or perinatal field per live births
        whole = "national" if decl.where in (None, "BR") else "area"
        wrong = sorted(set(desc["level"]) - {whole, "region", "state"})
        part("descriptive: geography", not wrong, f"the whole at level {whole}" + (f"; also {wrong}" if wrong else ""))
        cased = sorted({x["dataset"] for x in read if x.get("event") == "case"})
        uncased = sorted({x["dataset"] for x in read if not x.get("source") and any(
            e.get("status") for e in gateway.event_types(x["dataset"]))} - set(cased))
        rated_cases = {d for d in cased if (desc["field"].astype(str).str.startswith(f"{d}:case:")).any()}
        part("descriptive: case definition", not uncased and rated_cases == set(cased),
             f"confirmed-case rates for {sorted(rated_cases) or 'no source'}"
             + (f"; read as notifications only: {uncased}" if uncased else "")
             + (f"; no case rate for {sorted(set(cased) - rated_cases)}" if set(cased) - rated_cases else ""))
        perinatal = desc[desc["label"].astype(str).str.contains(r": [OP]\d", regex=True)]
        births = perinatal[perinatal["per"].astype(str).str.contains("birth")]
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
        part("findings", len(f) == 0 or (named > 0.95 and classed > 0.9 and intervals > 0.99),
             f"{len(f)} findings, {classed:.0%} with a recording class, {named:.0%} with named places, {intervals:.0%} "
             "of those with an expectation with an O/E and its interval" + ("" if len(f) else " (none at q: said in the report)"))
    g = table("groups")
    if g is not None and len(g):
        ok = "share" in g and g["share"].notna().mean() > 0.99 and "value_label" in g
        # an undecoded value is shown as such, never guessed (CLAUDE.md §6): named here, not a threshold to fail on
        und = g[g["value_label"].astype(str).str.endswith("(undecoded)")] if "value_label" in g else g
        cols = sorted(set(und["dataset"].astype(str) + ":" + und["by"].astype(str))) if len(und) else []
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
        part("data quality", (q is not None and len(q) > 0) or (qd is not None and len(qd) > 0),
             f"{0 if q is None else len(q)} quality findings, {0 if qd is None else len(qd)} recorded shares by year")
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
    part("every step ran", bool(prov) and not failed, f"{len(prov.get('steps') or {})} steps, {len(failed)} failed"
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
    files = ["findings", "descriptive", "relations", "persons", "capture", "groups"]
    item(7, "products", [(f"{f}.parquet", (folder / f"{f}.parquet").exists()) for f in files] + [
        ("figures", any((folder / "figures").glob("*.png")) if (folder / "figures").exists() else False),
        ("report.html", (folder / "report.html").exists()), ("provenance.json", bool(prov))])
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


def export(folder: str | Path, to: str | Path, tables: list[str] | None = None, fmt: str = "parquet") -> Path:
    """Materialise a study folder (ARCHITECTURE §3.6): every view of its `study.duckdb` (or ``tables``) written as a
    file, with the folder's own files, so it stands alone away from this machine. The only operation that copies."""
    import duckdb

    folder, to = Path(folder), Path(to)
    to.mkdir(parents=True, exist_ok=True)
    for p in folder.iterdir():
        if p.name == "study.duckdb":
            continue
        if p.is_dir():
            shutil.copytree(p, to / p.name, dirs_exist_ok=True)
        else:
            shutil.copy2(p, to / p.name)
    con = duckdb.connect(str(folder / "study.duckdb"), read_only=True)
    names = [r[0] for r in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()]
    (to / "tables").mkdir(exist_ok=True)
    for name in names:
        if (tables and name not in tables) or (folder / f"{name}.parquet").exists():
            continue                     # a view of the folder's own file: copied above, wherever the folder was made
        target = to / "tables" / f"{name}.{fmt}"
        con.execute(f"COPY (SELECT * FROM {name}) TO '{target.as_posix()}' "
                    f"(FORMAT {'parquet' if fmt == 'parquet' else 'csv, HEADER'})")
    con.close()
    return to
