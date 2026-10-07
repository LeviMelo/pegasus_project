"""The update of PegaSUS's persistent state when data arrive (ARCHITECTURE §9.3).

PegaSUS is one model of the events, read many ways; its state is the fitted blocks, the ledger and the register.
`run` brings that state up to a declared plan (the systems and blocks it holds, the years, the readings kept current):
blocks not fitted are fitted (`fit_block`), and each reading (the stage-C questions of every field, the relation map
across the systems, stage E on the answers, the report) is redone only where its inputs changed: every step is keyed
by the data and code versions and its inputs in the store. A plan:

    years: 2010-2023
    systems:
      - {dataset: SIM.DO, event: death, blocks: [I, IX, X, XX], levels: [group],
         measures: all, compositions: all, intervals: all, links: all, classifiers: all}   # fields from declarations
    corroborators: [[SINAN-DENG, probable_case]]    # served systems read as independent fields, not modelled
    confirm_last: 2019        # stage E's later years: select on the years up to it, test on the years after
    relations: true
    triage: true
    report: reports/leads.md
"""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa

from . import config, fields, gateway, store


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
    disparities: list[str] | None = None         # nodes whose race disparities are kept current (`tools.disparity`)


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
        return cls(list(years), systems, raw.get("questions"), bool(raw.get("relations", True)),
                   bool(raw.get("triage", True)), raw.get("report", "reports/leads.md"), raw.get("graph", "contiguity"),
                   {k: v for k, v in raw.items() if k not in known})


def fit_block(dataset: str, event: str, block: str, years: list[int], graph: str = "contiguity",
              device: str = "cpu", source: dict | None = None, warm: str | None = "auto", log=print):
    """Assemble one block, fit its model and store it: the one fitting path (`fit`, `update`, scripts/fit_blocks.py).
    ``source`` chooses a non-default reader (`monolith.assemble`'s arguments; `monolith.model_class` picks the model);
    ``warm`` starts from the best related stored fit ("auto") or from nothing (None)."""
    from . import graphs, monolith

    source = dict(source or {})
    if "bounds" in source:
        source["bounds"] = tuple(source["bounds"])
    data = monolith.assemble(dataset, event, block, years, **source)
    model = monolith.model_class(source)(data, graphs.graph(data.places, graph), graph, device=device)
    model.fit(outer=40, warm=warm, mean_tol=1.0, log=lambda line: log(f"{dataset} {block} {line}"))
    model.save()
    return model


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


def _measures(sys_: System) -> list[str]:
    return _declared(sys_, "measure", sys_.measures)


def _declared(sys_: System, kind: str, wanted: list[str] | str | None) -> list[str]:
    """The declared fields of ``kind`` a system's plan reads: every modelled one of `fields.declared` ("all"), or the
    columns listed (each must be modelled)."""
    if not wanted:
        return []
    modelled = [d.column for d in fields.declared(sys_.dataset) if d.kind == kind and not d.reason]
    if wanted == "all":
        return modelled
    unknown = [c for c in wanted if c not in modelled]
    if unknown:
        raise ValueError(f"{sys_.dataset}: not modelled {kind} fields {unknown} (`fields.declared` says why)")
    return list(wanted)


def _key(step: str, **inputs: Any) -> dict[str, Any]:
    return {"step": step, "data": config.data_version(), "code": config.code_version(), **inputs}


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
    key = _key("later_years", dataset=sys_.dataset, event=sys_.event, blocks=blocks, levels=sys_.levels,
               questions=plan.questions, last=last, years=plan.years, leads=sorted(x.id for x in answers))
    if not force and _done(key):
        return "done on these versions"
    t = s.train(last)
    for block in blocks:
        try:
            t.expectations.model(block)
        except LookupError:
            fit_block(sys_.dataset, sys_.event, block, t.years, plan.graph, log=log)
    t.survey_questions(blocks, tuple(plan.questions) if plan.questions else None,
                       levels=tuple(sys_.levels) if sys_.levels else None, log=log)
    selected = s.temporal_confirm(last, log=log)
    s.register.add(s.retier(answers, selected))
    stood = sum((x.replications.get("prospective") or {}).get("ok") is True for x in answers)
    _mark(key, {"selected": len(selected), "stood": stood})
    return {"selected": len(selected), "answers standing on the later years": stood}


def run(plan: Plan, force: bool = False, log=print) -> dict[str, Any]:
    """Every stage of ``plan`` (module docstring); returns what each step did or why it was skipped."""
    from . import report, tools

    out: dict[str, Any] = {}
    sessions = {}
    resolved.clear()
    for sys_ in plan.systems:
        s = tools.Session(sys_.dataset, sys_.event, plan.years, plan.graph)
        sessions[sys_.dataset] = s
        blocks = _chapters(sys_) if sys_.blocks == ["all"] else sys_.blocks
        for block in list(blocks):
            key = _key("fit", dataset=sys_.dataset, event=sys_.event, block=block, years=plan.years, graph=plan.graph)
            try:
                s.expectations.model(block)
                out[f"fit {sys_.dataset} {block}"] = "fitted already"
            except LookupError:
                try:
                    fit_block(sys_.dataset, sys_.event, block, plan.years, plan.graph, log=log)
                except (ValueError, LookupError) as exc:     # "all": a chapter the events never use
                    if sys_.blocks != ["all"]:
                        raise
                    log(f"FAIL fit {sys_.dataset} {block}: {type(exc).__name__}: {exc}")
                    out[f"fit {sys_.dataset} {block}"] = f"failed: {exc}"
                    blocks.remove(block)
                    continue
                _mark(key, {})
                out[f"fit {sys_.dataset} {block}"] = "fitted"
        key = _key("questions", dataset=sys_.dataset, event=sys_.event, blocks=blocks, levels=sys_.levels,
                   questions=plan.questions, years=plan.years)
        if force or not _done(key):
            leads = s.survey_questions(blocks, tuple(plan.questions) if plan.questions else None,
                                       levels=tuple(sys_.levels) if sys_.levels else None, log=log)
            _mark(key, {"answers": len(leads)})
            out[f"questions {sys_.dataset}"] = len(leads)
        else:
            out[f"questions {sys_.dataset}"] = "done on these versions"
        readers = [(column, fields.measure_source(sys_.dataset, sys_.event, column)) for column in _measures(sys_)]
        readers += [(f"{column}={value}", source) for column in _declared(sys_, "composition", sys_.compositions)
                    for value, source in fields.share_sources(sys_.dataset, sys_.event, column, plan.years[-1])]
        readers += [(column, fields.link_source(sys_.dataset, sys_.event, column)) for column in _links(sys_)]
        readers += [(column, fields.interval_source(sys_.dataset, sys_.event, column, plan.years[-1]))
                    for column in _declared(sys_, "interval", sys_.intervals)]
        wanted = [d.column for d in fields.declared_mentions(sys_.dataset)]
        readers += [(c, fields.mentions_source(sys_.dataset, c)) for c in wanted
                    if sys_.mentions == "all" or c in (sys_.mentions or [])]
        readers += [(d.column, fields.flow_source(sys_.dataset, sys_.event, d.column))
                    for d in fields.declared_flows(sys_.dataset) if sys_.flows == "all" or d.column in (sys_.flows or [])]
        resolved[sys_.dataset] = list(blocks)
        readers = [(column, source, list(blocks)) for column, source in readers]
        # another classifier's counts: the same events by its own tree, every chapter of it
        readers += [(name, source, roots) for name, source, roots in fields.classifier_sources(sys_.dataset, sys_.event)
                    if sys_.classifiers == "all" or name.split(":", 1)[1] in (sys_.classifiers or [])]
        for column, source, blocks in readers:
            ms = tools.Session(sys_.dataset, sys_.event, plan.years, plan.graph, source=source)
            for block in blocks:
                try:
                    ms.expectations.model(block)
                except LookupError:
                    try:
                        fit_block(sys_.dataset, sys_.event, block, plan.years, plan.graph, source=source, log=log)
                    except (ValueError, LookupError) as exc:     # a chapter of another tree the events never use
                        log(f"FAIL fit {sys_.dataset} {column} {block}: {type(exc).__name__}: {exc}")
                        out[f"fit {sys_.dataset} {column} {block}"] = f"failed: {exc}"
            blocks = [b for b in blocks if f"fit {sys_.dataset} {column} {b}" not in out]
            key = _key("questions", dataset=sys_.dataset, event=sys_.event, blocks=blocks, levels=sys_.levels,
                       measure=column, questions=plan.questions, years=plan.years)
            if force or not _done(key):
                leads = ms.survey_questions(blocks, tuple(plan.questions) if plan.questions else None,
                                            levels=tuple(sys_.levels) if sys_.levels else None, log=log)
                _mark(key, {"answers": len(leads)})
                out[f"questions {sys_.dataset} {column}"] = len(leads)
            else:
                out[f"questions {sys_.dataset} {column}"] = "done on these versions"
    for sys_ in plan.systems:
        for node in sys_.disparities or []:
            key = _key("disparity", dataset=sys_.dataset, event=sys_.event, node=node, years=plan.years)
            if force or not _done(key):
                found = tools.disparity(sys_.dataset, sys_.event, node, plan.years, graph=plan.graph, log=log)
                _mark(key, {"leads": len(found)})
                out[f"disparity {sys_.dataset} {node}"] = len(found)
            else:
                out[f"disparity {sys_.dataset} {node}"] = "done on these versions"
    if plan.relations and len(plan.systems) >= 1:
        spec = [(x.dataset, x.event, resolved.get(x.dataset, x.blocks)) for x in plan.systems]   # `all` resolved
        key = _key("relations", plan=spec, years=plan.years)
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
            answers = [x for x in s.register.current() if x.kind == "answer"
                       and x.fields and x.fields[0].startswith(f"{sys_.dataset}:")]
            key = _key("triage", dataset=sys_.dataset, leads=sorted(x.id for x in answers))
            if answers and (force or not _done(key)):
                done = s.triage(register=answers, log=log)
                # stage E's independent units: another record system at the lead's places and years (§8.3)
                corr = s.corroborate(done, served=[(x.dataset, x.event) for x in plan.systems] +
                                     [tuple(c) for c in plan.extra.get("corroborators") or ()], log=log)
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
    return out
