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

from . import config, fields, gateway, leads, questions, store

DEPTHS = ("survey", "standard", "deep", "exhaustive")
#: gigabytes a depth may download (data not yet in the lake); years already in the lake are free (hand-set,
#: ARCHITECTURE §12.3: to become the cost model's budget, BACKLOG 9.1)
DOWNLOAD_BUDGET_GB = {"survey": 2.0, "standard": 10.0, "deep": 40.0, "exhaustive": float("inf")}
SEED_SYSTEMS = ("icd10", "sinan", "terms")
KEYS = {"study", "topic", "period", "where", "grain", "depth", "q", "hypotheses", "contexts", "ratios"}
RATIO_KEYS = {"numerator", "denominator", "lag"}
TOPIC_KEYS = {"seeds", "include", "exclude"}
#: the declared readers each depth adds to every source (ARCHITECTURE §3.3, §5.2): at standard and deeper, every
#: measure, composition, interval and care flow pegasus_data's roles declare for the source's records
_ALL = {"measures": "all", "compositions": "all", "intervals": "all", "flows": "all", "quality": "all", "supports": "all"}
DEPTH_READERS = {"survey": {}, "standard": dict(_ALL), "deep": dict(_ALL), "exhaustive": dict(_ALL)}


# ---------------------------------------------------------------------- the declaration


@dataclass
class Declaration:
    study: str
    seeds: dict[str, list[str]]
    years: list[int]
    path: Path
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    where: Any = "BR"
    grain: list[str] = field(default_factory=lambda: ["year"])
    depth: str = "survey"
    q: float = 0.05
    hypotheses: list[dict] = field(default_factory=list)
    contexts: Any = "auto"
    ratios: list[dict] = field(default_factory=list)   # {numerator, denominator: "DATASET[:event][:codes]", lag: years}


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
    if doc.get("where", "BR") != "BR":
        problems.append("where: only BR (the whole country) is read in this version (BACKLOG 1.x)")
    if problems:
        raise DeclarationError(f"{path}:\n  - " + "\n  - ".join(problems))
    return Declaration(study=str(doc["study"]), seeds={k: [str(c) for c in v] for k, v in seeds.items()}, years=years,
                       path=path, include=list(topic.get("include") or []), exclude=list(topic.get("exclude") or []),
                       where=doc.get("where", "BR"), grain=grain, depth=depth, q=float(doc.get("q", 0.05)),
                       hypotheses=list(doc.get("hypotheses") or []), contexts=doc.get("contexts", "auto"),
                       ratios=list(ratios) if isinstance(ratios, list) else [ratios])


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
    extract: bool = False                # its codes read from an extract of the dataset, file by file (`_extract_or_lake`)
    note: str = ""


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

    def to_dict(self) -> dict:
        """The scope as plain values (numpy scalars from the counts made plain: YAML refuses them)."""
        return json.loads(json.dumps(self._dict(), default=lambda o: o.item() if hasattr(o, "item") else str(o)))

    def _dict(self) -> dict:
        return {"study": self.study, "depth": self.depth, "download_budget_gb": self.budget_gb,
                "read": [asdict(i) for i in self.items if i.status == "in"],
                "deferred": [asdict(i) for i in self.items if i.status != "in"],
                "not_read": self.excluded, "contexts": self.contexts, "related_codes": self.related,
                "person_paths": self.paths, "link_runs_to_compute": self.link_runs, "medicines": self.medicines,
                "estimated_minutes": round((sum(i.est_seconds or 0 for i in self.items if i.status == "in")
                                            + sum(r["est_seconds"] or 0 for r in self.link_runs)) / 60, 1)}


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


def _cost(dataset: str, years: list[int]) -> tuple[list[int], dict[int, float | None]]:
    """The years ``dataset`` publishes among ``years``, and the gigabytes each would download: 0 when in the lake, None
    when the catalog does not size it (never read as free)."""
    import pegasus_data as pg

    published = gateway.published_years(dataset)
    ys = [y for y in years if not published or y in published]
    volume = _volumes(dataset, config.data_root())
    lake = pg.lake_coverage(dataset, root=config.data_root())        # not cached: a run's `ensure_lake` extends it
    return ys, {y: (0.0 if y in lake else volume.get(y)) for y in ys}


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
    prefixes = list(it.nodes or []) + list((it.source or {}).get("codes") or [])
    for y in years:
        c = gateway.event_counts(it.dataset, it.event, y, classifier=(it.source or {}).get("classifier")).counts
        if prefixes:
            hit = pc.starts_with(c.column("code"), prefixes[0])
            for n in prefixes[1:]:
                hit = pc.or_(hit, pc.starts_with(c.column("code"), n))
            c = c.filter(pc.fill_null(hit, False))
        total += int(pc.sum(c.column("y")).as_py() or 0)
    return total


def _estimate(decl: Declaration, items: list[Item]) -> None:
    """Each item's predicted wall clock (BACKLOG 9.1), from measured throughput: an item a past study ran is predicted
    by its own measured seconds (provenance of studies beside this one, scaled by its years); otherwise its fits by the
    nearest stored fit of the same dataset and block (scaled by years), or, for a source never fitted, by the stores'
    log-log relation of fit seconds to events; plus its questions at the median measured seconds per item."""
    import glob
    import json

    from . import store

    measured, per_item = {}, []
    for path in glob.glob(str(decl.path.parent / "*" / "provenance.json")):
        try:
            prov = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for step, v in (prov.get("steps") or {}).items():
            if isinstance(v, dict) and v.get("seconds") and "error" not in v:
                measured[step] = float(v["seconds"])
                per_item.append(float(v["seconds"]))
    fits = [m for m in store.manifests("monolith") if m.get("fit_seconds")]
    if len(fits) >= 10:
        e = np.log([max(float(m.get("events") or 1.0), 1.0) for m in fits])
        b, a = np.polyfit(e, np.log([float(m["fit_seconds"]) for m in fits]), 1)
    else:
        a, b = 3.0, 0.3
    questions = float(np.median(per_item)) if per_item else 120.0
    for it in items:
        if it.status != "in" or not it.years:
            continue
        step = f"{it.dataset} {it.event} {','.join(it.blocks)}" + (f" {json.dumps(it.source, sort_keys=True)}" if it.source else "")
        if step in measured:
            it.est_seconds = round(measured[step], 1)
            continue
        fit = 0.0
        for block in it.blocks:
            same = [m for m in fits if m["key"].get("dataset") == it.dataset and m["key"].get("block") == block]
            if same:
                m = max(same, key=lambda m: len(m["key"].get("years") or []))
                fit += float(m["fit_seconds"]) * len(it.years) / max(len(m["key"].get("years") or [1]), 1)
            else:
                fit += float(np.exp(a + b * np.log(max(float(it.records or 1), 1.0))))
        it.est_seconds = round(fit + questions, 1)


def _related_codes(decl: Declaration, items: list[Item], seeds: list[str], log) -> list[dict]:
    """The codes related to the seeds on the same records (BACKLOG 4.2, `cooccur.related_codes`), wherever a read item's
    records carry several codes (`fields.declared_mentions`: certificate lines, all diagnoses, anomaly lists), over the
    item's years in the lake; each with its strength (lift and interval) and FDR."""
    from . import cooccur

    if not seeds:
        return []
    out, seen = [], set()
    for it in (i for i in items if i.status == "in" and i.mentions):
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
            out += [{"dataset": it.dataset, "event": it.event, "where": d.column, "years": [it.years[0], it.years[-1]],
                     **r} for r in rows if r["related"]]
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
    with a usable verdict. A year without one is left out and said, never read as unlinked."""
    from pegasus_data.linkage.engine import link_method, stored_key

    verdicts = {(r["run"].get("spec"), r["stem"]): r.get("verdict") for r in runs}
    out = []
    for p in (p for p in paths if p["verdict"] in USABLE_LINKS):
        method = link_method(p["link"])
        for it in (i for i in items if i.status == "in" and i.source is None):
            for side in (s for s in p["sides_read"] if gateway.same_dataset(p[s], it.dataset)):
                column = f"link:{p['link']}:{side}"
                d = next((x for x in fields.declared_links(it.dataset, it.event) if x.column == column), None)
                if d is None:
                    continue
                if d.reason:
                    excluded.append({"seed": f"{it.dataset}:{column}", "why": d.reason})
                    continue

                def usable(z: int, link: str = p["link"], method: str = method) -> bool:
                    return verdicts.get((link, stored_key(link, method, z, "BR").stem)) in USABLE_LINKS

                ys = [y for y in it.years if all(usable(z) for z in gateway.covering_runs(p["link"], side, y))]
                if not ys:
                    excluded.append({"seed": f"{it.dataset}:{column}", "why": f"no year of {it.years[0]}-{it.years[-1]} "
                                     f"has every covering run of {p['link']} stored with a usable verdict"})
                    continue
                verdict = sorted({r["verdict"] for r in p["runs"] if r["verdict"] in USABLE_LINKS})
                items.append(Item(it.dataset, it.event, list(it.blocks), it.nodes, ys,
                                  f"person path {p['link']}: the share of its {side} side's events paired with "
                                  f"{p['right' if side == 'left' else 'left']} ({', '.join(verdict)})",
                                  source=fields.link_source(it.dataset, it.event, column), records=it.records,
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
                    items.append(Item(ds, et["name"], ["*"], None, [], f"its {c['role']} classifier {c['column']} "
                                      f"(ICD-10) carries {', '.join(prefixes)}, read as one code set",
                                      source={"classifier": c["column"], "codes": prefixes}))
                elif c.get("structure") == "SIGTAP" and procedures:
                    items.append(Item(ds, et["name"], ["*"], None, [], f"its {c['role']} classifier {c['column']} "
                                      f"(SIGTAP) holds the procedures named for the topic ({', '.join(procedures)})",
                                      source={"classifier": c["column"], "structure": "SIGTAP", "codes": procedures}))
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
                if held and decl.depth == "survey":
                    # a survey reads the topic's codes as one field of their own: its node inside a fitted chapter
                    # (every infectious disease in 5,570 places over 16 years, for B58) was most of the survey's hours,
                    # and the chapter's context is standard depth's (2026-10-11)
                    items.append(Item(ds, et["name"], ["*"], None, [], f"its primary classifier ({prim['column']}) "
                                      f"holds {', '.join(held)}, read as a field of its own at survey depth",
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
    # the cost: years in the lake are free, the rest download; the budget is spent cheapest first, and a source
    # whose tree holds the topic but whose records hold none is not read (its tree is not its records)
    budget = DOWNLOAD_BUDGET_GB[decl.depth]
    priced = []
    for it in items:
        ys, cost = _cost(it.dataset, decl.years)
        if it.denominator:
            # a ratio reads its denominator's years too (``lag`` earlier): both are priced, and only years both publish
            dys, dcost = _cost(it.denominator[0], [y - it.denominator[1] for y in decl.years])
            ys = [y for y in ys if y - it.denominator[1] in dys]
            cost = {y: (None if cost[y] is None or dcost[y - it.denominator[1]] is None
                        else cost[y] + dcost[y - it.denominator[1]]) for y in ys}
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
            it.note = (f"years {paid} deferred: {gb:.1f} GB to download against the {decl.depth} budget of {budget:g} GB"
                       + (f"; {unknown} not sized by the catalog" if unknown else ""))
        elif not paid:
            it.years = ys
        else:
            it.status, it.years, it.download_gb = "deferred", ys, round(gb, 2)
            it.note = (f"{gb:.1f} GB to download against the {decl.depth} budget of {budget:g} GB"
                       + (f"; {unknown} not sized by the catalog" if unknown else ""))
            continue
        if it.extract:
            continue                     # counted from its extract, which `_prepare_store` makes
        try:
            it.records = _records(it, it.years)
        except Exception as exc:  # noqa: BLE001 - a source that cannot be counted is deferred with why
            it.status, it.note = "deferred", f"its records could not be counted: {type(exc).__name__}: {exc}"
            continue
        if it.records == 0 and it.mentions:
            it.note = (it.note + "; " if it.note else "") + "no record has the topic as its primary code: read through its mentions"
        elif it.records == 0:
            it.status = "none"
            held = ", ".join(it.nodes or (it.source or {}).get("codes") or ["its events"])
            excluded.append({"seed": f"{it.dataset}:{it.event}", "why": f"its tree holds {held} "
                             f"but its records hold none in {it.years[0]}-{it.years[-1]}"})
    items = [i for i in items if i.status != "none"]
    for it in items:
        # a code set's field is the codes' events only, a ratio's the numerator per denominator event: the declared
        # readers would read every event of the type against the population
        it.readers = {} if it.source else dict(DEPTH_READERS[decl.depth])
        coded = bool(it.source) and "codes" in it.source and not ({"population", "support"} & set(it.source))
        if coded and "supports" in DEPTH_READERS[decl.depth]:
            it.readers = {"supports": DEPTH_READERS[decl.depth]["supports"]}     # the code set at its other places
    runs = _link_runs()
    paths = _person_paths(items, runs)
    if decl.depth != "survey":
        _linked_items(items, paths, runs, excluded)     # a survey lists the paths; each linked share is a fit of its own
    _estimate(decl, items)
    contexts = sorted(gateway.declared_fields()) if decl.contexts == "auto" else list(decl.contexts)
    medicines = [{"substance": sub["name"], "use": sub.get("use", ""), "conditions": t["conditions"], "source": t["source"],
                  "note": t["note"], "catmat": sub.get("catmat"),
                  "contexts": [f"{sub['name']} ({r['field']})" for r in sub.get("reads") or ()]}
                 for t in (gateway.treatments(nodes + codes) if nodes or codes else []) for sub in t["substances"]]
    contexts += _medicines(nodes + codes)
    related = _related_codes(decl, items, sorted(set(nodes) | set(codes)), log)
    if decl.depth != "survey":
        # beyond a survey, each related code is read where it was found, as a code set of its own (a lead, never a cause)
        for r in (r for r in related if r["related"]):
            items.append(Item(r["dataset"], r["event"], ["*"], None, list(r["years"]),
                              f"related code {r['code']} ({r['label']}): on {r['observed']:.0f} of its records with the "
                              f"topic's codes, {r['lift']:.1f} times expected", source={"codes": [r["code"]]}))
    if decl.depth in ("deep", "exhaustive"):
        items += _related_elsewhere(decl, [r for r in related if r["related"]], served)
    return Scope(decl.study, decl.depth, items, excluded, contexts, budget, related, paths,
                 _link_runs_needed([i for i in items if i.status == "in"]), medicines)


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
PERSON_DRAWS = {"deep": 10, "exhaustive": 20}


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
    for it in (i for i in scope.items if i.status == "in"):
        for kind, reach in kinds.items():
            if not gateway.same_dataset(kind[0], it.dataset) or (it.dataset, kind) in done:
                continue
            done.add((it.dataset, kind))
            # the outcome on the person's own record: the topic's codes on a declared code list the study reads in this
            # source (`_related_elsewhere`: SINASC's CODANOMAL with an anomaly found beside the topic's codes)
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
                key = {"what": "study_cohort", "kind": list(kind), "event": it.event, "outcomes": outcomes, "year": y,
                       "draws": PERSON_DRAWS[decl.depth], "q": decl.q, "data": config.data_version(),
                       "code": config.code_key(tools.cohort)}
                hit = store.get_table("study_table", key)
                if hit is not None:
                    out.extend(hit.to_pylist())
                    continue
                try:
                    found = tools.cohort(it.dataset, it.event, kind[1], outcomes, y, draws=PERSON_DRAWS[decl.depth],
                                         q=decl.q, log=log)
                except Exception as exc:  # noqa: BLE001 - a cohort that cannot be read is said; the others run
                    out.append({"cohort": label, "year": y, "note": f"not scanned: {type(exc).__name__}: {exc}"})
                    continue
                rows = [{"cohort": label, "year": y, "outcome": x.fields[1].removeprefix("person:"),
                         "attribute": x.locus.get("attribute"), "level": x.locus.get("level"),
                         "reference": x.locus.get("reference"), "rr": float(x.effect),
                         "low": float(x.interval[0]) if x.interval else None,
                         "high": float(x.interval[1]) if x.interval else None, "q": float(x.q)} for x in found]
                store.put_table("study_table", key, pa.Table.from_pylist(rows) if rows else pa.table({"cohort": pa.array([], pa.string())}))
                out.extend(rows)
    return out


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


def _related_elsewhere(decl: Declaration, related: list[dict], served: set[str]) -> list[Item]:
    """A related code read in every other served source that records it (ARCHITECTURE §4.3, acceptance item 1: births
    with the anomalies found beside the topic's codes in admissions or deaths): its ICD-10 classifiers, as a code set,
    and its ICD-10 code columns (SINASC's anomaly list), as the code's node of that column's tree; over the study's years
    already in the lake (a related code buys no download)."""
    tree = {r["code"]: r for r in gateway.code_tree("ICD10").to_pylist()}
    out, seen = [], set()
    for r in related:
        code = r["code"]
        if code not in tree:
            continue
        for ds in sorted(served - {r["dataset"]}):
            try:
                ets = gateway.event_types(ds)
                ys, cost = _cost(ds, decl.years)
            except Exception:  # noqa: BLE001 - a source that cannot be listed is not read for it
                continue
            ys = [y for y in ys if cost.get(y) == 0.0]
            if not ys:
                continue
            why = f"related code {code} ({r['label']}), found on {r['dataset']} records with the topic's codes"
            for et in ets:
                for c in et.get("classifiers") or []:
                    if c.get("structure") == "ICD10" and (ds, et["name"], c["column"], code) not in seen:
                        seen.add((ds, et["name"], c["column"], code))
                        out.append(Item(ds, et["name"], ["*"], None, ys, f"{why}; read in its {c['column']}",
                                        source={"classifier": c["column"], "codes": [code]}))
                for d in fields.declared_codes(ds):
                    src = fields.codes_source(ds, d.column)
                    if d.reason or src.get("structure") != "ICD10" or (ds, et["name"], d.column, code) in seen:
                        continue
                    seen.add((ds, et["name"], d.column, code))
                    out.append(Item(ds, et["name"], [_chapter(tree, code)], [code], ys,
                                    f"{why}; read in its {d.column.split(':', 1)[1]}", source=src))
    return out


# ---------------------------------------------------------------------- the run


def folder_of(decl: Declaration) -> Path:
    return decl.path.parent / decl.study


def run(decl: Declaration, log=print) -> Path:
    """Compute the study and write its folder (ARCHITECTURE §3.4). Each read event type runs through `update` on its own
    years with the topic's nodes; the leads of those fields become the findings."""
    import yaml

    t0 = time.time()
    out = folder_of(decl)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(decl.path, out / "study.yml")
    scope = resolve(decl, log=log)
    (out / "scope.yml").write_text(yaml.safe_dump(scope.to_dict(), sort_keys=False, allow_unicode=True), encoding="utf-8")
    read = [i for i in scope.items if i.status == "in"]
    prepared = _prepare_store(decl, read, log)
    steps = _run_items(decl, read, log)
    tables = _write_products(decl, scope, out, log)
    prov = {"study": decl.study, "written": time.strftime("%Y-%m-%dT%H:%M:%S"), "seconds": round(time.time() - t0, 1),
            "code_version": config.code_version(), "data_version": config.data_version(), "store": prepared,
            "steps": steps, "store_tables": tables}
    (out / "provenance.json").write_text(json.dumps(prov, indent=1, default=str), encoding="utf-8")
    log(f"study {decl.study}: written to {out} in {time.time() - t0:.0f} s")
    return out


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
    out["seconds"] = round(time.time() - t0, 1)
    log(f"study {decl.study}: store prepared in {out['seconds']:.0f} s")
    return out


def _ensure_extract(items: list[Item], out: dict, log) -> None:
    """The records of a dataset's extract items, in one pass over its files (`pegasus_data.build_extract`): each
    item's codes on its classifier (its own, else the event type's primary); resumes where an earlier run stopped."""
    import pegasus_data as pg

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


def _run_group(decl_study: str, group: list[Item], others: list, device: str | None, threads: int | None) -> dict:
    """One lane's work: a dataset's items in order (they share its fits and caches), on ``device`` with ``threads``.
    A module function so a spawned process can run it."""
    from . import jobs, update

    if device:
        os.environ["PEGASUS_DEVICE"] = device
    if threads:
        jobs.threads(threads)
    steps = {}
    for it in group:
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

    def balance() -> None:
        # Lanes grow after they are admitted: three survey lanes held 42 GB committed on a 31.6 GB machine, and all of
        # them paged (SIM-DO chapter I's robust refit alone 23 GB, 2026-10-11). Under pressure every lane but the
        # largest is suspended, so the system pages the idle ones out and the largest runs at its own speed; they are
        # resumed one at a time, the smallest first, as memory frees.
        avail = psutil.virtual_memory().available / 2**30
        lanes_now = {}
        for c in me.children():
            try:
                lanes_now[c.pid] = (c, c.memory_info().private / 2**30)
            except (psutil.Error, AttributeError):
                continue
        active = {pid: v for pid, v in lanes_now.items() if pid not in paused}
        if avail < LANE_PRESSURE_GB and len(active) > 1:
            keep = max(active, key=lambda pid: active[pid][1])
            for pid, (proc, gb) in active.items():
                if pid != keep and gb > 1.0:
                    try:
                        proc.suspend()
                        paused[pid] = proc
                        log(f"study {decl.study}: {avail:.1f} GB available: lane {pid} ({gb:.1f} GB) paused beside "
                            f"lane {keep} ({active[keep][1]:.1f} GB)")
                    except psutil.Error:
                        continue
        elif paused and avail > LANE_FREE_GB:
            pid = min(paused, key=lambda p: lanes_now.get(p, (None, 0.0))[1])
            try:
                paused.pop(pid).resume()
                log(f"study {decl.study}: {avail:.1f} GB available: lane {pid} resumed")
            except psutil.Error:
                pass

    with cf.ProcessPoolExecutor(max_workers=lanes, mp_context=mp.get_context("spawn")) as pool:
        try:
            while pending or running:
                balance()
                free_gb = room()
                while not paused and pending and len(running) < lanes and (not running or free_gb >= max(LANE_FREE_GB, need[pending[0][0].dataset])):
                    gpu_busy = any(dev == "cuda" for dev, _ in running.values())
                    device = "cuda" if gpu and not gpu_busy else "cpu"
                    group = pending.pop(0)
                    log(f"study {decl.study}: lane for {group[0].dataset} ({len(group)} items) on {device}, "
                        f"{free_gb:.1f} GB of room, {need[group[0].dataset]:.1f} GB expected")
                    try:
                        running[pool.submit(_run_group, decl.study, group, others, device, per_lane)] = (device, group)
                    except cf.process.BrokenProcessPool:
                        lost.append(group)
                    free_gb = room()
                done, _ = cf.wait(list(running), timeout=10, return_when=cf.FIRST_COMPLETED)
                for f in done:
                    _device, group = running.pop(f)
                    try:
                        steps.update(f.result())
                    except Exception as exc:  # noqa: BLE001 - a lane that died: its groups run again below, in this process
                        log(f"study {decl.study}: the lane of {group[0].dataset} failed ({type(exc).__name__}): run again here")
                        lost.append(group)
        finally:
            for proc in paused.values():         # never leave a lane suspended: the pool waits on it at shutdown
                with contextlib.suppress(psutil.Error):
                    proc.resume()
    for group in lost:
        steps.update(_run_group(decl.study, group, others, None, None))
    return steps


def _plan(it: Item, others: list | None = None):
    """The `update` plan of one item: its system with the readers its depth adds."""
    from . import update

    return update.Plan(years=it.years, systems=[update.System(it.dataset, it.event, it.blocks, nodes=it.nodes,
                                                              mentions=it.mentions, source=it.source, extract=it.extract,
                                                              **it.readers)],
                       relations=False, triage=True, report=None, extra={"corroborators": others or []})


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


def _write_products(decl: Declaration, scope: Scope, out: Path, log) -> dict[str, str]:
    """Findings, descriptive tables, the expectation tables (in the store, viewed), figures, the report."""
    import duckdb

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
                label = (f.label or node) + (f" — {name}" if name else "")
                key = {"what": "study_expectations", "field": f.id, "years": list(it.years), "data": config.data_version(),
                       "code": config.code_key(_expectation_table)}
                path = store.address("study_table", key) / "table.parquet"
                if not path.exists():
                    store.put_table("study_table", key, _expectation_table(sv, names))
                views[f"expectations_{_slug(f'{it.dataset}_{name}_{node}')}"] = path.as_posix()
                desc.extend(_descriptive(it, s, f, label))
                # the field's own answers, on the item's years (each reader is its own field: counts, mentions, an
                # interval, a composition's share)
                rows.extend({**_finding(x, it, label, names), "_places": [int(q) for q in x.locus.get("places") or []],
                             "_institutions": sorted({str(i) for i in x.locus.get("institutions") or []}
                                                     | ({str(f_)} if (f_ := ((x.robustness.get("triage") or {}).get("facility")
                                                                             or {}).get("one_institution")) else set()))}
                            for x in current
                            if x.fields and x.kind == "answer" and x.status != "retired" and x.fields[0] == f.id
                            and list(x.provenance.get("years") or []) == list(it.years))
                if not name:
                    series[f.id] = (label, it.dataset, np.asarray(sv.places), np.asarray(sv.years), sv.y, sv.mu)
                    figs.append(_series_figure(out, sv, f, label, it))
                    try:
                        d = s.expectations.model(f.block).data
                        expo = dict(zip(np.asarray(d.places).tolist(), d.N.sum(axis=(1, 2)).tolist(), strict=True))
                        figs.append(_map_figure(out, sv, f, label, it, [r for r in rows if r["field"] == f.id], expo,
                                                str(d.population)))
                    except Exception as exc:  # noqa: BLE001 - a map that cannot be drawn is a note; the tables stand
                        log(f"study: {it.dataset} {node} map: {type(exc).__name__}: {exc}")
                    groups.extend(_groups(it, s, f, label, log))
    related = _related(rows, series)
    pq.write_table(pa.Table.from_pylist(related) if related else pa.table({"finding": pa.array([], pa.string())}),
                   out / "related.parquet")
    rel = _relations(scope, decl, log) + (_determinants(scope, decl, log) if decl.depth in ("deep", "exhaustive") else []) \
        + (_screen(scope, decl, log) if decl.depth == "exhaustive" else [])
    pq.write_table(pa.Table.from_pylist(rel) if rel else pa.table({"field": pa.array([], pa.string())}),
                   out / "relations.parquet")
    _institution_facts(rows, log)
    persons = _persons(decl, scope, log) if decl.depth in ("deep", "exhaustive") else []
    pq.write_table(pa.Table.from_pylist(persons) if persons else pa.table({"outcome": pa.array([], pa.string())}),
                   out / "persons.parquet")
    profile = _context_profiles(decl, scope, rows, log)
    pq.write_table(pa.Table.from_pylist(profile) if profile else pa.table({"finding": pa.array([], pa.string())}),
                   out / "context_profile.parquet")
    _stories([r for r in rows if r.get("class") == "signal" and "quality:" not in str(r.get("label"))])  # `story` saved
    for r in rows:
        r.pop("_places", None)
        r.pop("_institutions", None)
    findings = pa.Table.from_pylist(rows) if rows else pa.table({"id": pa.array([], pa.string())})
    pq.write_table(findings, out / "findings.parquet")
    pq.write_table(pa.Table.from_pylist(desc) if desc else pa.table({"field": pa.array([], pa.string())}),
                   out / "descriptive.parquet")
    pq.write_table(pa.Table.from_pylist(groups) if groups else pa.table({"field": pa.array([], pa.string())}),
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
    con.close()
    hyp = _hypotheses(decl, scope)
    pq.write_table(pa.Table.from_pylist(hyp) if hyp else pa.table({"hypothesis": pa.array([], pa.string())}),
                   out / "hypotheses.parquet")
    _report(decl, scope, out, rows, desc, [f for f in figs if f], hyp, rel, persons)
    return views


def _when(text: Any) -> list[int]:
    """The years a hypothesis's ``when`` covers: ``2018``, ``2018-03``, ``2018-01..2018-06``, ``2016..2018``."""
    parts = str(text).split("..")
    first, last = int(parts[0][:4]), int(parts[-1][:4])
    return list(range(first, last + 1))


def _hypothesis_readers(scope: Scope):
    """(item, reader, support) for every read item at its residence and, for a field read at the residence by its own
    counts or a code set, at each other place it declares (`fields.support_sources`, the item's codes kept). A ratio or
    a linked share is read at the residence only: its denominator is the residence's."""
    for it in (i for i in scope.items if i.status == "in"):
        yield it, it.source, "residence"
        if it.source and ("population" in it.source or it.source.get("source") == "linked"):
            continue
        try:
            supports = fields.support_sources(it.dataset, it.event)
            span = {r["column"]: (r.get("first_year"), r.get("last_year")) for r in gateway.roles(it.dataset)}
        except Exception:  # noqa: BLE001 - a source whose supports cannot be listed is tested at its residence
            continue
        for name, src in supports:
            lo, hi = span.get(src["support"], (None, None))
            if (lo and int(lo) > it.years[-1]) or (hi and int(hi) < it.years[0]):
                continue                    # a column of another layout generation (DOFET's MUNIOCOR, before 1996)
            yield it, {**src, **(it.source or {}), "support": src["support"]}, name.removeprefix("support:")


def _hypotheses(decl: Declaration, scope: Scope) -> list[dict]:
    """The declared hypotheses (ARCHITECTURE §7.7, version 1): each tested once, at its locus, in every source of the
    scope whose years and places hold it, against the B1 expectation; its own test, not a member of a discovery family.
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
            try:
                sv = _session(it, reader).surprise(_study_nodes(it, None)[0], "B1")
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

            inside = np.isin(yrs, years)
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
            size = M ** 2 / max(V - M, 1e-9)                      # the sum's NB by moments (Poisson when V = M)
            pval = float(stats.nbinom.sf(Y - 1, size, size / (size + M))) if V > M * 1.0001 else                 float(stats.poisson.sf(Y - 1, M))
            lo = stats.chi2.ppf(0.025, 2 * Y) / 2 / M if Y > 0 else 0.0
            hi = stats.chi2.ppf(0.975, 2 * Y + 2) / 2 / M
            out.append({**base, "observed": Y, "expected": M, "effect": Y / M, "effect_unit": "rate ratio",
                        "low": float(lo), "high": float(hi), "p": pval, "answer": "tested"})
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
    state = np.asarray(d.places) // 10000
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
        out.append(row("national", "BR", t, y[:, t].sum(0), N[:, t].sum(0)))
        for st in np.unique(state):
            sel_u = state == st
            out.append(row("state", str(int(st)), t, y[sel_u, t].sum(0), N[sel_u, t].sum(0)))
    return out


def _groups(it: Item, s, f, label: str, log) -> list[dict]:
    """A count field split by each composition column (`tools.Session.by_composition`), observed and expected by value,
    nationally and by state per year: the expectation is the place's age–sex expectation at Brazil's mix of the value."""
    if (it.source or {}).get("population"):
        return []
    out = []
    places = np.asarray(s.expectations.model(f.block).data.places)
    state = places // 10000
    years = np.asarray(s.expectations.model(f.block).data.years)
    from . import tools

    names = {d.column: d.name for d in fields.declared(it.dataset)}
    for column in tools.group_columns(it.dataset, it.event):
        try:
            y, mu, values = config.on_cpu_if_cuda_fails(s.by_composition, f.node, column)
        except Exception as exc:  # noqa: BLE001 - a column that cannot be split is a note, the others are written
            log(f"study: {it.dataset} {f.node} by {column}: {type(exc).__name__}: {exc}")
            continue
        for t, year in enumerate(years):
            for level, unit, sel in [("national", "BR", np.ones(len(places), bool))] +                     [("state", str(int(st)), state == st) for st in np.unique(state)]:
                obs, exp = y[sel, t].sum(0), mu[sel, t].sum(0)
                out.extend({"field": f.id, "label": label, "dataset": it.dataset, "by": column, "by_name": names.get(column, "race"),
                            "value": v, "level": level, "unit": unit, "year": int(year), "observed": float(obs[k]),
                            "expected": float(exp[k])} for k, v in enumerate(values) if obs[k] > 0 or exp[k] > 0)
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
        for fid, (label, dataset, pl, yrs, y, mu) in series.items():
            ui = np.flatnonzero(np.isin(pl, list(places)))
            year_of = yrs // 100 if yrs.max() > 9999 else yrs          # YYYYMM periods at the monthly grain
            ti = np.flatnonzero((year_of >= lo_y) & (year_of <= hi_y))
            if not len(ui) or not len(ti):
                continue
            o, e_ = float(y[np.ix_(ui, ti)].sum()), float(mu[np.ix_(ui, ti)].sum())
            if fid == r["field"]:
                # the finding's own burden (BACKLOG 7.3): its field's events at its locus against the expectation
                r["observed"], r["expected"], r["excess"] = o, e_, o - e_
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
    """Relations among the study's primary fields (ARCHITECTURE §8.1, acceptance item 4; BACKLOG 3.5 the estimator):
    every pair of read items with a field of the default reader (its nodes, or the event type's own) is compared on the
    years both hold (at least four) by `tools.compare`, the joint model over graph bands and lags; every row kept,
    ``reported`` marking those at q."""
    from . import tools

    fields_ = []
    for it in (i for i in scope.items if i.status == "in" and not i.source):
        for node in _study_nodes(it, None):
            fields_.append((it.dataset, it.event, node, set(it.years)))
    out = []
    for (a, b) in ((fields_[i], fields_[j]) for i in range(len(fields_)) for j in range(i + 1, len(fields_))):
        years = sorted(a[3] & b[3])
        if len(years) < 4 or (a[0], a[2]) == (b[0], b[2]):
            continue
        # an object of the state: a re-run reads it (BACKLOG 1.3), the key the pair, its years, the data and the code
        key = {"what": "study_relation", "x": list(a[:3]), "y": list(b[:3]), "years": years, "q": decl.q,
               "data": config.data_version(), "code": config.code_key(tools.compare)}
        hit = store.get_table("study_table", key)
        if hit is not None:
            rows = hit.to_pylist()
        else:
            try:
                rows = config.on_cpu_if_cuda_fails(tools.compare, a[:3], b[:3], years, q=decl.q)
            except Exception as exc:  # noqa: BLE001 - a pair that cannot be compared is said, the others run
                log(f"study: relation {a[:3]} ~ {b[:3]}: {type(exc).__name__}: {exc}")
                continue
            flat = [{k: v for k, v in r.items() if not isinstance(v, (dict, list))} for r in rows]
            store.put_table("study_table", key, pa.Table.from_pylist(flat) if flat else pa.table({"p": pa.array([], pa.float64())}))
        out += [{**{k: v for k, v in r.items() if not isinstance(v, (dict, list))}, "pair": f"{a[0]}:{a[2]} ~ {b[0]}:{b[2]}",
                 "years": f"{years[0]}-{years[-1]}"} for r in rows]
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
                store.put_table("study_table", key, pa.Table.from_pylist(flat) if flat else pa.table({"p": pa.array([], pa.float64())}))
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
        store.put_table("study_table", key, pa.Table.from_pylist(rows) if rows else pa.table({"p": pa.array([], pa.float64())}))
    out += [{"support": "between places", "field": r["x"], "leader": r["y"], "lag": 0, "rho": r.get("rho"),
             "p": r.get("p"), "reported": bool(r.get("admitted")), "partial": r.get("rho_c"),
             "pair": f"{r['x']} ~ {r['y']}", "years": "study period"} for r in rows if r.get("x")]
    return out


def _screen(scope: Scope, decl: Declaration, log) -> list[dict]:
    """The data-space screen (ARCHITECTURE §8.3, BACKLOG 10.1), at exhaustive depth: every system the store has fitted
    over the topic's years (the window chosen to read the most data), read with the topic's own systems in one joint model (`tools.relation_survey`: the
    factor model over graph bands and lags, one BH over everything), so a field anywhere in the data that moves with the
    topic is found without being named. The relations involving a topic field are kept; each is a lead, never a cause."""
    from . import store, tools

    topic = [i for i in scope.items if i.status == "in" and not i.source]
    if not topic:
        return []
    topic_years = sorted(set.intersection(*(set(i.years) for i in topic)))
    if len(topic_years) < 4:
        log(f"study: screen: the topic's systems share {len(topic_years)} years; four are needed")
        return []
    # every system the store has fitted over at least four of the topic's years; the window is the run of the topic's
    # years from its first that maximises systems × years read (the fits on it are made on demand)
    cover: dict[tuple[str, str, str], set[int]] = {}
    for m in store.manifests("monolith"):
        k = m["key"]
        if k.get("codes") or k.get("source") or not k.get("block") or not k.get("event"):
            continue
        cover.setdefault((k["dataset"], k["event"], k["block"]), set()).update(k.get("years") or [])
    best = (0, topic_years[:4])
    for e in range(3, len(topic_years)):
        window = topic_years[:e + 1]
        n = sum(1 for ys in cover.values() if set(window) <= ys)
        best = max(best, (n * len(window), window))
    years = best[1]
    plan: dict[tuple[str, str], set[str]] = {}
    for it in topic:
        plan.setdefault((it.dataset, it.event), set()).update(it.blocks)
    for (ds, ev, block), ys in cover.items():
        if set(years) <= ys:
            plan.setdefault((ds, ev), set()).add(block)
    spec = [(ds, ev, sorted(bl)) for (ds, ev), bl in plan.items()]
    log(f"study: screen over {len(spec)} systems, {sum(len(b) for *_, b in spec)} blocks, {years[0]}-{years[-1]}")
    try:
        found = tools.relation_survey(spec, years, q=decl.q, log=log)
    except Exception as exc:  # noqa: BLE001 - the screen failing leaves the study's own relations, said
        log(f"study: screen: {type(exc).__name__}: {exc}")
        return []
    mine = {f"{i.dataset}:{i.event}:" for i in topic}
    out = []
    for x in found:
        if not any(f.startswith(tuple(mine)) for f in x.fields):
            continue
        out.append({"pair": " ~ ".join(x.fields), "support": x.locus.get("band") or x.locus.get("scale"),
                    "lag": x.locus.get("lag"), "rho": float(x.effect), "p": float(x.p), "q": float(x.q),
                    "reported": True, "screen": True, "years": f"{years[0]}-{years[-1]}"})
    return out


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
    state = np.asarray(d.places)[d.u[sel]] // 10000
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
            q = quant[year].get(0 if unit == "BR" else int(unit))
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
        out.append(row("national", "BR", t, at))
        for st in np.unique(state):
            out.append(row("state", str(int(st)), t, at & (state == st)))
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
        "n_places": len(places), "groups": ", ".join(x.locus.get("groups") or []) or None,
        "first_year": int(years[0]) if years else None,
        "last_year": int(years[-1]) if years else None,
        "effect": float(x.effect), "effect_unit": x.scale.replace("_", " "),
        "interval_low": float(x.interval[0]) if x.interval else None,
        "interval_high": float(x.interval[1]) if x.interval else None,
        "q": float(x.q), "family": x.family, "methods": ", ".join(sorted(x.provenance.get("methods") or []))
        if isinstance(x.provenance.get("methods"), list) else str(x.provenance.get("methods") or ""),
        "class": tri.get("class"), "class_reason": tri.get("reason"), "class_grade": tri.get("grade"),
        "replication": x.replication, "corroborated": bool(corr.get("ok")), "corroboration": corr.get("reason"),
        "status": x.status, **(_COMPOSITION if x.locus.get("groups_by") else _reliability(x.provenance.get("methods") or [x.estimand]))}


#: a composition's group answer: read against Brazil's mix of the value at the place's age and sex, so it restates the
#: population's own mix (OPEN_QUESTIONS 17); drawn worlds hold no compositions, so its null rate is not measured
_COMPOSITION = {"uncalibrated": True, "reliability": "a composition read against Brazil's mix, not the place's "
                "population's (OPEN_QUESTIONS 17); no null measured"}


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


def _series_figure(out: Path, sv, f, label: str, it: Item) -> str | None:
    """The field's national series, observed against expected (B1) with the expected's 90 % band."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import stats

    years = np.asarray(sv.years)
    obs, mu = sv.y.sum(0), sv.mu.sum(0)
    var = (sv.mu + np.where(np.isfinite(sv.phi), sv.mu ** 2 / np.where(np.isfinite(sv.phi), sv.phi, 1.0), 0.0)).sum(0)
    z = stats.norm.ppf(0.95)
    figs = out / "figures"
    figs.mkdir(exist_ok=True)
    name = f"{_slug(it.dataset + '_' + f.node)}_series.png"
    fig, ax = plt.subplots(figsize=(7, 3.2), dpi=110)
    ax.fill_between(years, np.maximum(mu - z * np.sqrt(var), 0), mu + z * np.sqrt(var), alpha=0.25, label="expected, 90 %")
    ax.plot(years, mu, lw=1.5, label="expected")
    ax.plot(years, obs, "o-", lw=1.5, label="observed")
    ax.set_title(f"{label} — {it.dataset}", fontsize=10)
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
    by_state = {}
    for k in np.unique(st):
        sel = st == k
        e = float(obs[sel].sum())
        n = float(n_of[sel].sum())
        by_state[str(int(k))] = (e / n * (1e3 if ratio else 1e5)) if n else np.nan
    states["rate"] = states["code"].map(by_state)
    # the standardised departure over the years, (O − E)/sd with the NB variance: a small place's ratio is mostly noise
    var = (sv.mu + np.where(np.isfinite(sv.phi), sv.mu ** 2 / np.where(np.isfinite(sv.phi), sv.phi, 1.0), 0.0)).sum(1)
    zd = np.where(var > 0, (obs - mu) / np.sqrt(np.maximum(var, 1e-12)), np.nan)
    munis["z"] = munis["u"].map(dict(zip(places.tolist(), zd.tolist(), strict=True)))
    flagged = {int(p) for r in findings for p in str(r.get("places") or "").replace(" (+", ",").split(",")
               if p.strip().isdigit()}
    figs = out / "figures"
    figs.mkdir(exist_ok=True)
    name = f"{_slug(it.dataset + '_' + f.node)}_map.png"
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.6), dpi=110)
    states.plot(column="rate", ax=a1, cmap="YlOrRd", legend=True, missing_kwds={"color": "#eee"},
                legend_kwds={"shrink": 0.6, "label": "per 1,000 denominator events" if ratio else "per 100,000"})
    a1.set_title(f"{label}: rate by state, {sv.years[0]}–{sv.years[-1]}", fontsize=9)
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
            hyp: list[dict] | None = None, relations: list[dict] | None = None, persons: list[dict] | None = None) -> None:
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
    rank = sorted(signal, key=lambda r: (r["q"], -abs(np.log(r["effect"])) if r["effect"] and r["effect"] > 0 else 0))
    stories = _stories(signal)

    def table(rs: list[dict], cols: list[tuple[str, str]], cap: int = 40) -> str:
        head = "".join(f"<th>{e(c)}</th>" for _, c in cols)
        body = "".join("<tr>" + "".join(f"<td>{e(_fmt(r.get(k)))}</td>" for k, _ in cols) + "</tr>" for r in rs[:cap])
        more = f"<p class=more>{len(rs) - cap} more in findings.parquet</p>" if len(rs) > cap else ""
        return f"<table><tr>{head}</tr>{body}</table>{more}"

    nat = [d for d in desc if d["level"] == "national"]
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
                                   ("institution_facts", "establishment (CNES)")], cap=30),
             "<h2>3a. Data quality</h2><p>Places and periods where a column's blank or 'ignored' share departs from its "
             "expectation: where the records of this topic are least complete, and where a recording practice changed.</p>",
             table(quality, [("label", "column"), ("dataset", "source"), ("component", "component"),
                             ("place_names", "places"), ("first_year", "from"), ("last_year", "to"), ("effect", "effect"),
                             ("q", "q")], cap=30) if quality else "<p>No quality departure at this depth.</p>",
             f"<h3>Completeness across systems</h3><p>{e(_capture_note(scope))}</p>",
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
                if persons else f"<p>{'Not read at this depth.' if decl.depth not in ('deep', 'exhaustive') else 'No source read holds persons on a usable link.'}</p>"),
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


def _story_html(k: int, rows: list[dict], e) -> str:
    """One story: where, when, what departs, in how many fields and sources, and its strongest findings."""
    lead = rows[0]
    fields_ = sorted({r["label"] for r in rows})
    sources = sorted({r["dataset"] for r in rows})
    years = [y for r in rows for y in (r.get("first_year"), r.get("last_year")) if y]
    span = f"{min(years)}–{max(years)}" if years else ""
    items = "".join(f"<li>{e(r['label'])} ({e(r['dataset'])}): {e(str(r['component']))}"
                    + (f" in {e(r['groups'])}" if r.get("groups") else "")
                    + f", effect {_fmt(r['effect'])} {e(str(r['effect_unit']))}, q {_fmt(r['q'])}"
                    + (", corroborated" if r.get("corroborated") else "")
                    + (f" (method not calibrated: {e(r['reliability'])})" if r.get("uncalibrated") else "") + "</li>"
                    for r in rows[:6])
    excess = sum(max(r.get("excess") or 0.0, 0.0) for r in rows)
    return (f"<h3>Story {k}: {e(lead.get('place_names') or '')}, {span}</h3><p>{len(rows)} findings in "
            f"{len(fields_)} fields from {len(sources)} sources ({e(', '.join(sources))})"
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
    readers = sorted(DEPTH_READERS[decl.depth])
    methods = ("<li>Expectations: hierarchical negative-binomial models per block (ARCHITECTURE §6); findings against "
               "tier B1 unless stated; Benjamini–Hochberg/Bogomolov per question family at the study's q.</li>"
               f"<li>Fields read at depth {e(decl.depth)}: counts" + ("".join(f", {e(r)}" for r in readers))
               + "; the seeds' codes in every classifier a source carries and on every certificate line or diagnosis."
               "</li><li>Rates are per resident unless a source declares other events as its denominator (below).</li>")
    body = f"<ul>{''.join(notes)}</ul>" if notes else "<p>No source of this study declares notes.</p>"
    return f"<ul>{methods}</ul><h3>What the sources say of themselves</h3>{body}"


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.3g}" if abs(v) < 1e4 else f"{v:,.0f}"
    return str(v)


# ---------------------------------------------------------------------- export


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
