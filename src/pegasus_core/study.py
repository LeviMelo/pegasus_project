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

import html
import json
import shutil
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import config, fields, gateway, leads, store

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
#: the question registry's names read as the components of ARCHITECTURE §7.2 (BACKLOG 3.1 re-cuts the registry)
COMPONENT = {"excess": "transient", "step": "step", "trend": "trend", "cluster": "level", "share": "ratio (share)",
             "institution": "facility support", "group": "group heterogeneity", "divergence": "trend (reference)",
             "prospective": "prospective"}


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
    note: str = ""


@dataclass
class Scope:
    study: str
    depth: str
    items: list[Item]
    excluded: list[dict]                 # what a seed named and the study does not read, with why
    contexts: list[str]
    budget_gb: float

    def to_dict(self) -> dict:
        return {"study": self.study, "depth": self.depth, "download_budget_gb": self.budget_gb,
                "read": [asdict(i) for i in self.items if i.status == "in"],
                "deferred": [asdict(i) for i in self.items if i.status != "in"],
                "not_read": self.excluded, "contexts": self.contexts}


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
    try:
        volume = {int(r["year"]): float(r.get("gigabytes") or 0.0)
                  for r in pg.explore(dataset, root=config.data_root()).rows}
    except Exception:  # noqa: BLE001 - a dataset the catalog does not size: counted as free, said in the note
        volume = {}
    lake = pg.lake_coverage(dataset, root=config.data_root())
    return ys, {y: (0.0 if y in lake else volume.get(y)) for y in ys}


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


def _concept_items(decl: Declaration, nodes: list[str], codes: list[str], items: list[Item], excluded: list[dict],
                   served: set[str]) -> None:
    """Scope v2's sources beyond the primary classifiers (ARCHITECTURE §4, BACKLOG 4.3), from pegasus_data's concept
    index (`pegasus_data.concept_index`):
    - every other ICD-10 classifier holding the seeds (SIA's diagnoses), read as a code set on that classifier;
    - SINAN agravos whose records carry the codes beyond the seeded ones (SINAN-SDTA's toxoplasmosis outbreaks), read
      as a code set on ``ID_AGRAVO``;
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
    for d in ix["sinan"]:
        if d["dataset"] in seeded or d["dataset"] not in served:
            continue
        for et in gateway.event_types(d["dataset"]):
            items.append(Item(d["dataset"], et["name"], ["*"], None, [], f"its records' agravo code (ID_AGRAVO) carries "
                              f"{', '.join(f'{k} ({v})' for k, v in d['codes'].items())} in {d['year']}",
                              source={"classifier": "ID_AGRAVO", "codes": sorted(d["codes"])}))
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
                if held:
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
    contexts = sorted(gateway.declared_fields()) if decl.contexts == "auto" else list(decl.contexts)
    return Scope(decl.study, decl.depth, items, excluded, contexts, budget)


# ---------------------------------------------------------------------- the run


def folder_of(decl: Declaration) -> Path:
    return decl.path.parent / decl.study


def run(decl: Declaration, log=print) -> Path:
    """Compute the study and write its folder (ARCHITECTURE §3.4). Each read event type runs through `update` on its own
    years with the topic's nodes; the leads of those fields become the findings."""
    import yaml

    from . import update

    t0 = time.time()
    out = folder_of(decl)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(decl.path, out / "study.yml")
    scope = resolve(decl, log=log)
    (out / "scope.yml").write_text(yaml.safe_dump(scope.to_dict(), sort_keys=False, allow_unicode=True), encoding="utf-8")
    read = [i for i in scope.items if i.status == "in"]
    steps = {}
    for it in read:
        others = [[o.dataset, o.event] for o in read if o.dataset != it.dataset]
        plan = _plan(it, others)
        log(f"study {decl.study}: {it.dataset} {it.event} {it.years[0]}-{it.years[-1]} blocks {it.blocks}")
        # one step per item: a dataset read as a code set, a chapter and a ratio is three
        step = f"{it.dataset} {it.event} {','.join(it.blocks)}" + (f" {json.dumps(it.source, sort_keys=True)}" if it.source else "")
        try:
            steps[step] = update.run(plan, log=log)
        except Exception as exc:  # noqa: BLE001 - one source failing is recorded in the folder, the others still run
            where = traceback.extract_tb(exc.__traceback__)[-3:]
            steps[step] = {"error": f"{type(exc).__name__}: {exc}",
                           "at": [f"{Path(w.filename).name}:{w.lineno} {w.name}" for w in where]}
            log(f"study {decl.study}: {step} failed: {type(exc).__name__}: {exc} at {steps[step]['at']}")
    tables = _write_products(decl, scope, out, log)
    prov = {"study": decl.study, "written": time.strftime("%Y-%m-%dT%H:%M:%S"), "seconds": round(time.time() - t0, 1),
            "code_version": config.code_version(), "data_version": config.data_version(), "steps": steps,
            "store_tables": tables}
    (out / "provenance.json").write_text(json.dumps(prov, indent=1, default=str), encoding="utf-8")
    log(f"study {decl.study}: written to {out} in {time.time() - t0:.0f} s")
    return out


def _plan(it: Item, others: list | None = None):
    """The `update` plan of one item: its system with the readers its depth adds."""
    from . import update

    return update.Plan(years=it.years, systems=[update.System(it.dataset, it.event, it.blocks, nodes=it.nodes,
                                                              mentions=it.mentions, source=it.source, **it.readers)],
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
                    sv = s.surprise(node, "B1")
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
                rows.extend(_finding(x, it, label, names) for x in current
                            if x.fields and x.kind == "answer" and x.status != "retired" and x.fields[0] == f.id
                            and list(x.provenance.get("years") or []) == list(it.years))
                if not name:
                    figs.append(_series_figure(out, sv, f, label, it))
                    try:
                        d = s.expectations.model(f.block).data
                        expo = dict(zip(np.asarray(d.places).tolist(), d.N.sum(axis=(1, 2)).tolist(), strict=True))
                        figs.append(_map_figure(out, sv, f, label, it, [r for r in rows if r["field"] == f.id], expo,
                                                str(d.population)))
                    except Exception as exc:  # noqa: BLE001 - a map that cannot be drawn is a note; the tables stand
                        log(f"study: {it.dataset} {node} map: {type(exc).__name__}: {exc}")
                    groups.extend(_groups(it, s, f, label, log))
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
    con.execute(f"CREATE VIEW findings AS SELECT * FROM read_parquet('{(out / 'findings.parquet').as_posix()}')")
    con.execute(f"CREATE VIEW descriptive AS SELECT * FROM read_parquet('{(out / 'descriptive.parquet').as_posix()}')")
    con.execute(f"CREATE VIEW groups AS SELECT * FROM read_parquet('{(out / 'groups.parquet').as_posix()}')")
    con.close()
    hyp = _hypotheses(decl, scope)
    pq.write_table(pa.Table.from_pylist(hyp) if hyp else pa.table({"hypothesis": pa.array([], pa.string())}),
                   out / "hypotheses.parquet")
    _report(decl, scope, out, rows, desc, [f for f in figs if f], hyp)
    return views


def _when(text: Any) -> list[int]:
    """The years a hypothesis's ``when`` covers: ``2018``, ``2018-03``, ``2018-01..2018-06``, ``2016..2018``."""
    parts = str(text).split("..")
    first, last = int(parts[0][:4]), int(parts[-1][:4])
    return list(range(first, last + 1))


def _hypotheses(decl: Declaration, scope: Scope) -> list[dict]:
    """The declared hypotheses (ARCHITECTURE §7.7, version 1): each tested once, at its locus, in every source of the
    scope whose years and places hold it, against the B1 expectation; its own test, not a member of a discovery family.
    level and transient: observed against expected over the locus, the upper tail of the sum under its negative
    binomial (moments of the cells' predictive), the rate ratio with an exact Poisson interval; step: the ratio of
    observed to expected after the declared year against before it."""
    from scipy import stats

    out = []
    for h in decl.hypotheses:
        comp, places = str(h.get("component", "transient")), [int(p) for p in (h.get("where") or [])]
        years = _when(h.get("when"))
        for it in (i for i in scope.items if i.status == "in"):
            base = {"hypothesis": h.get("note") or json.dumps(h, ensure_ascii=False), "component": comp,
                    "source": it.dataset, "field_reader": json.dumps(it.source or {"nodes": it.nodes}),
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
                sv = _session(it).surprise(_study_nodes(it, None)[0], "B1")
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
            y, mu, values = s.by_composition(f.node, column)
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
        "id": x.id, "component": COMPONENT.get(x.estimand, x.estimand), "question": x.estimand,
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
        "status": x.status}


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
            hyp: list[dict] | None = None) -> None:
    """`report.html`: the study as a person reads it (ARCHITECTURE §3.5), from the folder's own tables."""
    e = html.escape
    read = [i for i in scope.items if i.status == "in"]
    signal = [r for r in rows if r.get("class") == "signal"]
    other = [r for r in rows if r.get("class") != "signal"]
    rank = sorted(signal, key=lambda r: (r["q"], -abs(np.log(r["effect"])) if r["effect"] and r["effect"] > 0 else 0))

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
             f"(signal), {len(other)} with a recording or denominator explanation.</p>",
             table(rank, [("label", "field"), ("dataset", "source"), ("component", "component"),
                          ("place_names", "places"), ("groups", "group"), ("first_year", "from"), ("last_year", "to"),
                          ("effect", "effect"), ("effect_unit", "unit"), ("q", "q"), ("replication", "replication"),
                          ("corroborated", "corroborated")], cap=20),
             "<h2>2. Descriptive epidemiology</h2>",
             table(nat, [("label", "field"), ("dataset", "source"), ("year", "year"), ("events", "events"),
                         ("rate", "rate"), ("rate_low", "95% from"), ("rate_high", "to"), ("per", "per"),
                         ("standardised_per_100k", "standardised /100k")], cap=80),
             "".join(f"<img src='{e(f)}' alt=''>" for f in figs),
             "<h2>3. Findings with a recording explanation</h2>",
             table(other, [("label", "field"), ("dataset", "source"), ("component", "component"),
                           ("place_names", "places"), ("first_year", "from"), ("last_year", "to"), ("effect", "effect"),
                           ("class", "class"), ("class_reason", "why")], cap=30),
             "<h2>4. Scope</h2>", "<ul>" + "".join(
                 f"<li><b>{e(i.dataset)}</b> ({e(i.event)}), {i.years[0]}–{i.years[-1]}: {e(i.reason)}"
                 + (f" — {e(i.note)}" if i.note else "") + "</li>" for i in read) + "</ul>",
             "<h3>Deferred</h3><ul>" + "".join(f"<li>{e(i.dataset)}: {e(i.note)}</li>"
                                               for i in scope.items if i.status != "in") + "</ul>",
             "<h3>Named by a seed and not read</h3><ul>" + "".join(
                 f"<li>{e(x['seed'])}: {e(x['why'])}</li>" for x in scope.excluded) + "</ul>",
             "<h2>5. Hypotheses</h2>",
             table(hyp or [], [("hypothesis", "hypothesis"), ("source", "source"), ("field_reader", "field"),
                               ("years", "years"), ("observed", "observed"), ("expected", "expected"),
                               ("effect", "effect"), ("low", "95 % low"), ("high", "95 % high"), ("p", "p"),
                               ("answer", "answer")], cap=60) if decl.hypotheses else "<p>None declared.</p>",
             "<h2>6. Methods and limitations</h2>",
             "<ul><li>Expectations: hierarchical negative-binomial models per block (PegaSUS ARCHITECTURE §6); findings "
             "against tier B1 unless stated; error control by Benjamini–Hochberg/Bogomolov per question family at the "
             "study's q.</li><li>Rates use the model's exposure (resident or SUS-dependent population); births as the "
             "denominator of congenital fields comes with BACKLOG 2.x.</li><li>This version reads the seeds' codes in "
             "each source's primary classifier only (principal diagnosis, underlying cause); secondary diagnoses, "
             "certificate lines and code lists come with BACKLOG 2.1.</li><li>Relations, persons, seasonality and "
             "propagation are not read at this depth or in this version.</li></ul>",
             "<h2>7. Provenance</h2><p>provenance.json; every table is in study.duckdb (views onto the store and lake; "
             "nothing copied). <code>pegasus-core export</code> materialises the folder.</p>"]
    css = ("body{font-family:system-ui,sans-serif;max-width:1100px;margin:2em auto;padding:0 1em;color:#222}"
           "table{border-collapse:collapse;font-size:13px;margin:.5em 0}td,th{border-bottom:1px solid #ddd;"
           "padding:3px 8px;text-align:left}th{background:#f4f4f4}img{max-width:100%;margin:.5em 0}.meta,.more{color:#666}")
    (out / "report.html").write_text(f"<!doctype html><meta charset=utf-8><title>{e(decl.study)}</title><style>{css}"
                                     f"</style>{''.join(parts)}", encoding="utf-8")


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
        if tables and name not in tables:
            continue
        target = to / "tables" / f"{name}.{fmt}"
        con.execute(f"COPY (SELECT * FROM {name}) TO '{target.as_posix()}' "
                    f"(FORMAT {'parquet' if fmt == 'parquet' else 'csv, HEADER'})")
    con.close()
    return to
