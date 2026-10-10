"""The update of PegaSUS's persistent state when data arrive (ARCHITECTURE §9.3).

PegaSUS is one model of the events, read many ways; its state is the fitted blocks, the ledger and the register.
`run` brings that state up to a declared plan (the systems and blocks it holds, the years, the readings kept current):
blocks not fitted are fitted (`monolith.fit_block`), and each reading (the stage-C questions of every field, the relation map
across the systems, stage E on the answers, the report) is redone only where its inputs changed: every step is keyed
by the data and code versions and its inputs in the store. A plan:

    years: 2010-2023
    systems:
      - {dataset: SIM.DO, event: death, blocks: [I, IX, X, XX], levels: [group],
         measures: all, compositions: all, intervals: all, links: all, classifiers: all, codes: all}   # from declarations
    corroborators: [[SINAN-DENG, probable_case]]    # served systems read as independent fields, not modelled
    persons: true             # the plan reads persons (cohorts): every link that declares a person is computed
    confirm_last: 2019        # stage E's later years: select on the years up to it, test on the years after
    prospective: 2021         # the prospective questions: the years after it against fits on the years up to it
    relations: true
    triage: true
    report: reports/leads.md
"""

from __future__ import annotations

import dataclasses
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa

from . import config, control, fields, gateway, monolith, store


@dataclass
class System:
    dataset: str
    event: str
    blocks: list[str]
    levels: list[str] | None = None
    measures: list[str] | str | None = None     # "all", or columns of `fields.declared`: the measurement fields read
    compositions: list[str] | str | None = None  # "all", or category columns of `fields.declared`: their share fields
    links: list[str] | str | None = None         # "all", or `fields.declared_links` columns: person-level fields
    intervals: list[str] | str | None = None     # "all", or `fields.declared` interval:<date> fields: days from the event
    classifiers: list[str] | str | None = None   # "all", or alternative classifier columns: counts by their own tree
    mentions: list[str] | str | None = None      # "all", or `fields.declared_mentions` fields: every code a record carries
    flows: list[str] | str | None = None         # "all", or `fields.declared_flows` fields: events away from residence
    codes: list[str] | str | None = None         # "all", or `fields.declared_codes` fields: a code column's own tree
    disparities: list[str] | None = None         # nodes whose race disparities are kept current (`tools.disparity`)
    nodes: list[str] | None = None               # only the fields under these tree nodes are asked (a study's topic)
    source: dict | None = None                   # the counts' reader (`monolith.assemble`): e.g. {"codes": ["P371"]}
    quality: list[str] | str | None = None       # "all", or columns: each one's blank or "ignored" share (`fields.quality_sources`)
    supports: list[str] | str | None = None      # "all", or place columns: the counts at another support (`fields.support_sources`)


#: the plan's other keys: served systems read only as corroborating sources; the dependency map's contexts; stage E's
#: later years (select on the years up to it, test on the years after); the prospective questions' training years
EXTRA = {"corroborators", "contexts", "confirm_last", "prospective", "persons"}


@dataclass
class Plan:
    years: list[int]
    systems: list[System]
    questions: list[str] | None = None
    relations: bool = True
    triage: bool = True
    report: str | None = "reports/leads.md"
    graph: str = "contiguity"
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, source: str | Path | dict) -> Plan:
        """From a YAML file or a dict (the module docstring's form); years as "first-last" or a list."""
        import yaml

        raw = source if isinstance(source, dict) else yaml.safe_load(Path(source).read_text(encoding="utf-8"))
        years = raw.get("years", "2010-2023")
        if isinstance(years, str):
            a, b = years.split("-")
            years = list(range(int(a), int(b) + 1))
        keys = {f.name for f in dataclasses.fields(System)} - {"dataset", "event", "blocks"}
        for s in raw.get("systems") or ():
            unknown = set(s) - keys - {"dataset", "event", "blocks"}
            if unknown:
                raise ValueError(f"plan system {s.get('dataset')}: unknown keys {sorted(unknown)}")
        systems = [System(s["dataset"], s["event"], list(s.get("blocks") or ["*"]), **{k: s.get(k) for k in keys})
                   for s in raw.get("systems") or ()]       # by name: a positional list put every key one place off
        known = {"years", "systems", "questions", "relations", "triage", "report", "graph"}
        unknown = set(raw) - known - EXTRA
        if unknown:
            raise ValueError(f"plan: unknown keys {sorted(unknown)} (known: {sorted(known | EXTRA)})")
        return cls(list(years), systems, raw.get("questions"), bool(raw.get("relations", True)),
                   bool(raw.get("triage", True)), raw.get("report", "reports/leads.md"), raw.get("graph", "contiguity"),
                   {k: v for k, v in raw.items() if k not in known})


def _links(sys_: System) -> list[str]:
    if not sys_.links:
        return []
    modelled = [d.column for d in fields.declared_links(sys_.dataset, sys_.event) if not d.reason]
    if sys_.links == "all":
        return modelled
    unknown = [c for c in sys_.links if c not in modelled]
    if unknown:
        raise ValueError(f"{sys_.dataset}: not modelled person-level fields {unknown} (`fields.declared_links` says why)")
    return list(sys_.links)


def _chapters(sys_: System) -> list[str]:
    """``blocks: [all]``: every chapter of the event type's primary tree (``*`` for an event type without one)."""
    et = gateway.event_type(sys_.dataset, sys_.event)
    primary = next((c for c in et.get("classifiers") or [] if c["role"] == "primary"), None)
    if primary is None or not primary.get("structure"):
        return ["*"]
    tree = gateway.code_tree(primary["structure"])
    return sorted(c for c, lv in zip(tree.column("code").to_pylist(), tree.column("level").to_pylist(), strict=True)
                  if lv == "chapter")


def _measures(sys_: System, plan: Plan, out: dict | None = None) -> list[str]:
    return _declared(sys_, "measure", sys_.measures, plan, out)


def _declared(sys_: System, kind: str, wanted: list[str] | str | None, plan: Plan, out: dict | None = None) -> list[str]:
    """The declared fields of ``kind`` a system's plan reads: every modelled one of `fields.declared` ("all"), or the
    columns listed (each must be modelled), and only where the column fills every year of the plan: a column of a later
    form (dengue's 2014 warning signs) read over 2010-2023 was absent before 2014, which reads as a collapse."""
    if not wanted:
        return []
    roles = {r["column"]: r for r in gateway.roles(sys_.dataset)}
    modelled = []
    for d in fields.declared(sys_.dataset):
        if d.kind != kind or d.reason:
            continue
        r = roles.get(d.column.split(":", 1)[-1], {})
        first, last = r.get("first_year") or plan.years[0], r.get("last_year") or plan.years[-1]
        gap = sorted(set(r.get("unfilled") or ()) & set(plan.years))
        if first > plan.years[0] or last < plan.years[-1] or gap:
            if out is not None:
                out[f"{kind} {sys_.dataset} {d.column}"] = (f"not read: unfilled in {gap}" if gap else
                                                           f"not read: filled {first}-{last} only")
            continue
        modelled.append(d.column)
    if wanted == "all":
        return modelled
    unknown = [c for c in wanted if c not in modelled]
    if unknown:
        raise ValueError(f"{sys_.dataset}: not modelled {kind} fields {unknown} (`fields.declared` says why)")
    return list(wanted)


def _key(step: str, code: tuple, **inputs: Any) -> dict[str, Any]:
    """A step's key: its inputs, the data version and the code the step runs (`config.code_key` of ``code``), never
    the repository's commit, which re-keyed every step on every commit (survey 2026-10-07)."""
    return {"step": step, "data": config.data_version(), "code": config.code_key(*code), **inputs}


def _done(key: dict[str, Any]) -> bool:
    return store.manifest("update", key) is not None


def _mark(key: dict[str, Any], result: dict[str, Any]) -> None:
    store.put_table("update", key, pa.table({"done": [time.strftime("%Y-%m-%dT%H:%M:%S")]}), {**key, **result})


resolved: dict[str, list[str]] = {}       # the blocks each system's plan resolved to in the current run


def _later_years(plan: Plan, sys_: System, s, answers: list, last: int, force: bool, log) -> Any:
    """§8.3's later years for a system's answers: the questions asked again on the years up to ``last`` (its own
    fits and register, `Session.train`), what they select tested once on the later years (`Session.temporal_confirm`),
    and each answer given the verdict of the selection that is the same finding (`Session.retier`)."""
    blocks = resolved.get(sys_.dataset, sys_.blocks)
    from . import tools

    key = _key("later_years", (tools.Session.train, tools.Session.survey_questions, tools.Session.temporal_confirm,
                               tools.Session.retier), dataset=sys_.dataset, event=sys_.event, blocks=blocks, levels=sys_.levels,
               questions=plan.questions, last=last, years=plan.years, leads=sorted(x.id for x in answers))
    if not force and _done(key):
        return "done on these versions"
    t = s.train(last)
    for block in blocks:
        try:
            t.expectations.model(block)
        except LookupError:
            monolith.fit_block(sys_.dataset, sys_.event, block, t.years, plan.graph, log=log)
    t.survey_questions(blocks, tuple(plan.questions) if plan.questions else None,
                       levels=tuple(sys_.levels) if sys_.levels else None, log=log)
    selected = s.temporal_confirm(last, log=log)
    s.register.add(s.retier(answers, selected))
    stood = sum((x.replications.get("prospective") or {}).get("ok") is True for x in answers)
    _mark(key, {"selected": len(selected), "stood": stood})
    return {"selected": len(selected), "answers standing on the later years": stood}


def monolith_class_load(s, block: str, years: list[int]):
    """The stored fit of ``block`` on ``years`` for session ``s``'s reader (raises LookupError when missing)."""
    from . import monolith

    return monolith.model_class(s.source).load(s.dataset, s.event, block, years, s.graph, **s.expectations._reader())


def _codes_readers(sys_: System, plan: Plan, out: dict) -> list[tuple[str, dict, list[str]]]:
    """The code-column fields a system's plan reads (`fields.declared_codes`), each on every chapter of its tree, and
    only where its role's years hold the plan's: a column that stopped being filled would read as a collapse
    (SIH's cause of death in hospital ends in 2014, pegasus_data a033d19)."""
    if not sys_.codes:
        return []
    roles = {r["column"]: r for r in gateway.roles(sys_.dataset)}
    found = []
    for d in fields.declared_codes(sys_.dataset):
        col = d.column.split(":", 1)[1]
        if sys_.codes != "all" and col not in sys_.codes:
            continue
        r = roles[col]
        first, last = r.get("first_year") or plan.years[0], r.get("last_year") or plan.years[-1]
        gap = sorted(set(r.get("unfilled") or ()) & set(plan.years))
        if d.reason or first > plan.years[0] or last < plan.years[-1] or gap:
            out[f"codes {sys_.dataset} {col}"] = f"not read: {d.reason or (f'unfilled in {gap}' if gap else f'filled {first}-{last} only')}"
            continue
        source = fields.codes_source(sys_.dataset, d.column)
        tree = gateway.code_tree(source["structure"])
        roots = sorted(c for c, lv in zip(tree.column("code").to_pylist(), tree.column("level").to_pylist(), strict=True)
                       if lv == "chapter")
        found.append((d.column, source, roots))
    return found


def system_readers(sys_: System, plan: Plan, blocks: list[str], out: dict | None = None) -> list[tuple[str, dict, list[str]]]:
    """A system's fields beyond its primary counts, as (name, reader, blocks): its declared measures, compositions (one
    share per value), person-level links, intervals, mentions, care flows, other classifiers and code columns. `run`
    fits and asks each; a study writes each one's products (`study`), so both read one list."""
    out = {} if out is None else out
    readers = [(column, fields.measure_source(sys_.dataset, sys_.event, column)) for column in _measures(sys_, plan, out)]
    readers += [(f"{column}={value}", source) for column in _declared(sys_, "composition", sys_.compositions, plan, out)
                for value, source in fields.share_sources(sys_.dataset, sys_.event, column, plan.years[-1])]
    readers += [(column, fields.link_source(sys_.dataset, sys_.event, column)) for column in _links(sys_)]
    readers += [(column, fields.interval_source(sys_.dataset, sys_.event, column, plan.years[-1]))
                for column in _declared(sys_, "interval", sys_.intervals, plan, out)]
    wanted = [d.column for d in fields.declared_mentions(sys_.dataset)]
    readers += [(c, fields.mentions_source(sys_.dataset, c)) for c in wanted
                if sys_.mentions == "all" or c in (sys_.mentions or [])]
    readers += [(d.column, fields.flow_source(sys_.dataset, sys_.event, d.column))
                for d in fields.declared_flows(sys_.dataset) if sys_.flows == "all" or d.column in (sys_.flows or [])]
    readers += [(name, source) for name, source in fields.support_sources(sys_.dataset, sys_.event)
                if sys_.supports == "all" or name.split(":", 1)[1] in (sys_.supports or [])]
    readers += [(name, source) for name, source in fields.quality_sources(sys_.dataset, sys_.event, plan.years)
                if sys_.quality == "all" or name.split(":", 1)[1] in (sys_.quality or [])]
    readers = [(column, source, list(blocks)) for column, source in readers]
    # another classifier's counts: the same events by its own tree, every chapter of it
    readers += [(name, source, roots) for name, source, roots in fields.classifier_sources(sys_.dataset, sys_.event)
                if sys_.classifiers == "all" or name.split(":", 1)[1] in (sys_.classifiers or [])]
    return readers + _codes_readers(sys_, plan, out)


def _ensure_total(s, plan: Plan, label: str, out: dict, log) -> None:
    """The all-events fit (block ``*``) a count reader's share question reads as its denominator
    (`tools.Session._expected_total`), fitted as a declared step of the plan."""
    if plan.questions == [] or (plan.questions and "share" not in plan.questions) or s.expectations.registry.classifier == "*"             or any(s.source.get(k) for k in ("mark", "indicator", "link", "place")):
        return
    from . import tools

    if str(s.source.get("population", "")).startswith("events:"):
        return                  # a ratio field asks no share (`tools.Session.lens`)
    # a code set's share is of all the type's events: the denominator is the unrestricted reader's fit
    src = {k: v for k, v in s.source.items() if k != "codes"}
    try:
        (s.expectations if src == s.source else tools.Session(s.dataset, s.event, s.years, s.graph, source=src).expectations).model("*")
    except LookupError:
        try:
            monolith.fit_block(s.dataset, s.event, "*", list(s.years), s.graph, source=src or None, log=log)
            out[f"fit {label} * (share denominator)"] = "fitted"
        except (ValueError, LookupError) as exc:
            out[f"fit {label} * (share denominator)"] = f"failed: {exc}"


def plan_links(plan: Plan) -> list[tuple[str, str]]:
    """The declared links a plan reads, with the side read: its systems' person-level fields, and the links through
    which its corroborating event types share records with its systems (`corroborate.sources`, which removes them)."""
    from . import corroborate

    out = []
    for s in plan.systems:
        for c in _links(s):
            src = fields.link_source(s.dataset, s.event, c)
            out.append((src["link"], src["side"]))
    if plan.triage:
        served = [(x.dataset, x.event) for x in plan.systems] + [tuple(c) for c in plan.extra.get("corroborators") or ()]
        out += [src.link for s in plan.systems for src in corroborate.sources(s.dataset, served) if src.link]
    if plan.extra.get("persons"):
        # a plan that reads persons (S2.4) needs every link that declares one: persons are merged from all of a scope's
        # runs, and a route through another link finds what the direct one missed
        from pegasus_data.linkage.engine import links_file
        from pegasus_data.semantics.curation import read_yaml

        raw = read_yaml(links_file()).get("links") or {}
        out += [(name, side) for name in gateway.link_specs() if (raw.get(name) or {}).get("person")
                for side in ("left", "right")]
    return list(dict.fromkeys(out))


def _ensure_lake(plan: Plan, out: dict, log) -> None:
    """The lake over every dataset the plan reads, its systems' and its links' sides, for the plan's years (and the
    year before, which a padded link side reads), as a step of its own: a raw read then scans Parquet instead of
    decoding the DBC files in every process (`gateway.ensure_lake`)."""
    specs = gateway.link_specs()
    datasets = [s.dataset for s in plan.systems]
    for link, _side in plan_links(plan):
        spec = specs.get(link)
        if spec is not None:
            datasets += [spec.left.dataset, spec.right.dataset]
    years = list(range(min(plan.years) - 1, max(plan.years) + 1))
    for dataset in dict.fromkeys(datasets):
        key = _key("lake", (gateway.ensure_lake,), dataset=dataset, years=years)
        if _done(key):
            continue
        try:
            counts = gateway.ensure_lake(dataset, years, log=log)
            _mark(key, {"files": counts.get("files", 0), "partitions": counts.get("partitions", 0)})
            out[f"lake {dataset}"] = f"{counts.get('partitions', 0)} written, {counts.get('partitions_reused', 0)} kept"
        except Exception as exc:  # noqa: BLE001 - without a lake the reads decode, slower, never wrong: said, not fatal
            out[f"lake {dataset}"] = f"not built: {type(exc).__name__}: {exc}"
            log(f"lake {dataset} not built: {exc}")


def _ensure_links(plan: Plan, out: dict, log) -> None:
    """The stored national runs every link the plan reads needs for its years (S2.2; `gateway.covering_runs`: a padded
    side's year is read by the runs after it too): a reading never launches one (`gateway.stored_pairs`), so the plan
    computes them, once, as a step of their own. No run after the plan's last year is computed: the plan's years are
    its data horizon (a later year's run reads that year's records; SIM 2024 is held out). A year whose covering runs
    are incomplete, or that cannot be linked, is read as unlinked, and said."""
    specs = gateway.link_specs()
    for link, side in plan_links(plan):
        runs = sorted({z for y in plan.years for z in gateway.covering_runs(link, side, y)})
        need = [z for z in runs if z <= max(plan.years)]
        # a year either side publishes nothing for is not linkable, and is said so rather than attempted on every run
        # (CIHA starts in 2011)
        sides = [specs[link].left.dataset, specs[link].right.dataset] if link in specs else []
        unpublished = [z for z in need if any(z not in gateway.published_years(d) for d in sides)]
        for z in unpublished:
            out[f"link {link} {z}"] = "no publication on a side: not linked"
        need = [z for z in need if z not in unpublished]
        missing = []
        for z in need:
            try:
                gateway.stored_pairs(link, z)
            except gateway.LinkNotStored:
                missing.append(z)
        for z in missing:
            t0 = time.time()
            try:
                pairs = gateway.stored_pairs(link, z, compute=True)
                log(f"link {link} {z}: {pairs.num_rows} pairs ({time.time() - t0:.0f} s)")
            except Exception as exc:  # noqa: BLE001 - a year that cannot be linked is read as unlinked, and said
                log(f"FAIL link {link} {z}: {type(exc).__name__}: {exc}")
                out[f"link {link} {z}"] = f"failed: {exc}"
        failed = sum(f"link {link} {z}" in out for z in missing)
        beyond = [z for z in runs if z > max(plan.years)]
        out[f"links {link} {side}"] = (f"{len(need) - len(missing)} stored, {len(missing) - failed} computed, {failed} failed"
                                       + (f"; runs {beyond} after the plan's years not computed" if beyond else ""))


def run(plan: Plan, force: bool = False, log=print) -> dict[str, Any]:
    """Every stage of ``plan`` (module docstring); returns what each step did or why it was skipped."""
    from . import report, tools

    out: dict[str, Any] = {}
    sessions = {}
    resolved.clear()
    _ensure_lake(plan, out, log)
    _ensure_links(plan, out, log)
    for sys_ in plan.systems:
        s = tools.Session(sys_.dataset, sys_.event, plan.years, plan.graph, source=dict(sys_.source or {}))
        sessions[sys_.dataset] = s
        blocks = _chapters(sys_) if sys_.blocks == ["all"] else sys_.blocks
        for block in list(blocks):
            key = _key("fit", (monolith.fit_block,), dataset=sys_.dataset, event=sys_.event, block=block, years=plan.years, graph=plan.graph)
            try:
                s.expectations.model(block)
                out[f"fit {sys_.dataset} {block}"] = "fitted already"
            except LookupError:
                try:
                    monolith.fit_block(sys_.dataset, sys_.event, block, s.years, plan.graph, source=sys_.source,
                                       log=log)   # the years it publishes
                except (ValueError, LookupError) as exc:     # "all": a chapter the events never use
                    if sys_.blocks != ["all"]:
                        raise
                    log(f"FAIL fit {sys_.dataset} {block}: {type(exc).__name__}: {exc}")
                    out[f"fit {sys_.dataset} {block}"] = f"failed: {exc}"
                    blocks.remove(block)
                    continue
                _mark(key, {})
                out[f"fit {sys_.dataset} {block}"] = "fitted"
        _ensure_total(s, plan, f"{sys_.dataset}", out, log)
        key = _key("questions", (tools.Session.survey_questions,), dataset=sys_.dataset, event=sys_.event,
                   blocks=blocks, levels=sys_.levels, questions=plan.questions, years=plan.years,
                   **({"nodes": sys_.nodes} if sys_.nodes else {}), **({"source": sys_.source} if sys_.source else {}))
        if plan.questions == []:                  # an empty list asks none (a plan of disparities, of fits)
            out[f"questions {sys_.dataset}"] = "none asked"
        elif force or not _done(key):
            leads = s.survey_questions(blocks, tuple(plan.questions) if plan.questions else None,
                                       levels=tuple(sys_.levels) if sys_.levels else None, log=log,
                                       nodes=tuple(sys_.nodes) if sys_.nodes else None)
            _mark(key, {"answers": len(leads)})
            out[f"questions {sys_.dataset}"] = len(leads)
        else:
            out[f"questions {sys_.dataset}"] = "done on these versions"
        resolved[sys_.dataset] = list(blocks)
        for column, source, blocks in system_readers(sys_, plan, list(resolved[sys_.dataset]), out):  # noqa: B020
            ms = tools.Session(sys_.dataset, sys_.event, plan.years, plan.graph, source=source)
            for block in blocks:
                try:
                    ms.expectations.model(block)
                except LookupError:
                    try:
                        monolith.fit_block(sys_.dataset, sys_.event, block, ms.years, plan.graph, source=source, log=log)
                    except (ValueError, LookupError) as exc:     # a chapter of another tree the events never use
                        log(f"FAIL fit {sys_.dataset} {column} {block}: {type(exc).__name__}: {exc}")
                        out[f"fit {sys_.dataset} {column} {block}"] = f"failed: {exc}"
            blocks = [b for b in blocks if f"fit {sys_.dataset} {column} {b}" not in out]
            _ensure_total(ms, plan, f"{sys_.dataset} {column}", out, log)
            key = _key("questions", (tools.Session.survey_questions,), dataset=sys_.dataset, event=sys_.event,
                       blocks=blocks, levels=sys_.levels, measure=column, questions=plan.questions, years=plan.years,
                       **({"nodes": sys_.nodes} if sys_.nodes else {}))
            if plan.questions == []:
                out[f"questions {sys_.dataset} {column}"] = "none asked"
            elif force or not _done(key):
                leads = ms.survey_questions(blocks, tuple(plan.questions) if plan.questions else None,
                                            levels=tuple(sys_.levels) if sys_.levels else None, log=log,
                                            nodes=tuple(sys_.nodes) if sys_.nodes else None)
                _mark(key, {"answers": len(leads)})
                out[f"questions {sys_.dataset} {column}"] = len(leads)
            else:
                out[f"questions {sys_.dataset} {column}"] = "done on these versions"
    for sys_ in plan.systems:
        for node in sys_.disparities or []:
            key = _key("disparity", (tools.disparity,), dataset=sys_.dataset, event=sys_.event, node=node, years=plan.years)
            if force or not _done(key):
                for k in gateway.RACE:               # each race's fit of the node's block: declared steps of the plan
                    rs = tools.Session(sys_.dataset, sys_.event, plan.years, plan.graph, source={"race": k})
                    block = rs.expectations.field(node).block
                    try:
                        rs.expectations.model(block)
                    except LookupError:
                        monolith.fit_block(sys_.dataset, sys_.event, block, plan.years, plan.graph, source={"race": k}, log=log)
                        out[f"fit {sys_.dataset} {block} race {k}"] = "fitted (disparity)"
                found = tools.disparity(sys_.dataset, sys_.event, node, plan.years, graph=plan.graph, log=log)
                _mark(key, {"leads": len(found)})
                out[f"disparity {sys_.dataset} {node}"] = len(found)
            else:
                out[f"disparity {sys_.dataset} {node}"] = "done on these versions"
    t0 = plan.extra.get("prospective")
    for sys_ in plan.systems if t0 else ():
        s = sessions[sys_.dataset]
        blocks = resolved.get(sys_.dataset, sys_.blocks)
        train = [y for y in plan.years if y <= int(t0)]
        for block in blocks:                     # the fits on the training years: declared steps of the plan
            try:
                monolith_class_load(s, block, train)
            except LookupError:
                monolith.fit_block(sys_.dataset, sys_.event, block, train, plan.graph, log=log)
                out[f"fit {sys_.dataset} {block} {train[0]}-{train[-1]}"] = "fitted (prospective)"
        key = _key("prospective", (tools.Session.survey_questions,), dataset=sys_.dataset, event=sys_.event,
                   blocks=blocks, levels=sys_.levels, train_last=int(t0), years=plan.years)
        if force or not _done(key):
            found = s.survey_questions(blocks, levels=tuple(sys_.levels) if sys_.levels else None, log=log,
                                       train_last=int(t0))
            _mark(key, {"answers": len(found)})
            out[f"prospective {sys_.dataset}"] = len(found)
        else:
            out[f"prospective {sys_.dataset}"] = "done on these versions"
    if plan.relations and len(plan.systems) >= 1:
        spec = [(x.dataset, x.event, resolved.get(x.dataset, x.blocks)) for x in plan.systems]   # `all` resolved
        key = _key("relations", (tools.relation_survey,), plan=spec, years=plan.years)
        if force or not _done(key):
            levels = tuple(sorted({lv for x in plan.systems for lv in (x.levels or ["group"])}))
            rel = tools.relation_survey(spec, plan.years, plan.graph, levels=levels, log=log)
            _mark(key, {"relations": len(rel)})
            out["relations"] = len(rel)
        else:
            out["relations"] = "done on these versions"
    if plan.triage:
        for sys_ in plan.systems:
            s = sessions[sys_.dataset]
            # this plan's answers: the dataset's, on the years its sessions read (another period's are another run's)
            answers = [x for x in s.register.current() if x.kind == "answer" and x.status != "retired"
                       and x.fields and x.fields[0].startswith(f"{sys_.dataset}:")
                       and list(x.provenance.get("years") or s.years) in (list(s.years), list(plan.years))]
            served = [(x.dataset, x.event) for x in plan.systems] +                 [tuple(c) for c in plan.extra.get("corroborators") or ()]
            key = _key("triage", (tools.Session.triage, tools.Session.corroborate), dataset=sys_.dataset,
                       leads=sorted(x.id for x in answers), served=sorted(served))
            if answers and (force or not _done(key)):
                # each reader's answers by its own session (S4.3): a measure's are read on its admissions, not on counts
                by_reader: dict[str, list] = {}
                for x in answers:
                    by_reader.setdefault(json.dumps(x.provenance.get("source") or {}, sort_keys=True, default=list), []).append(x)
                done = []
                for src_key, group in sorted(by_reader.items()):
                    src = json.loads(src_key)
                    # the session of the answers' own reader: a system read as a code set holds, in the register, the
                    # dataset's chapter answers too, which its session cannot read (CIH-CR P37.1 and chapter I, 2026-10-10)
                    mine = json.loads(json.dumps(s.source or {}, sort_keys=True, default=list))
                    rs = s if src == mine else tools.Session(sys_.dataset, sys_.event, plan.years, plan.graph, source=src)
                    done += rs.triage(register=group, log=log)
                # stage E's independent units: another record system at the lead's places and years (§8.3)
                corr = s.corroborate(done, served=served, log=log)
                s.register.add(corr)
                _mark(key, {"leads": len(answers), "corroborated": len(corr)})
                out[f"triage {sys_.dataset}"] = len(answers)
                out[f"corroboration {sys_.dataset}"] = sum(bool(x.replications.get("corroboration", {}).get("ok"))
                                                          for x in corr)
            else:
                out[f"triage {sys_.dataset}"] = "nothing new" if answers else "no answers"
            last = plan.extra.get("confirm_last")
            if last and answers:
                out[f"later years {sys_.dataset}"] = _later_years(plan, sys_, s, answers, int(last), force, log)
    if plan.report:
        out["report"] = str(report.write(plan.report))
    merged = control.Ledger().compact()          # stage E writes a part per batch: one file again, rows unchanged
    out["ledger"] = f"{merged} parts merged"
    return out
