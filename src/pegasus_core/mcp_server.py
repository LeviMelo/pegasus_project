"""PegaSUS over MCP (ARCHITECTURE §9.3, §11.1 `tools`): the tools of `tools` for agents and people.

A thin layer: every tool calls the Python API (`tools.Session`, `leads`, `control`) and returns compact JSON
with its provenance (data versions, the fitted model's manifest, the tier). Nothing is computed here that
the API does not compute.

**Read-mostly.** The exploration half (fields, expectations, leads, stories, gate, ledger) only reads. The one
write is `confirm_claim`, which spends the confirmation reserve under LOND (ADR-0008): it needs the server started
with ``--allow-confirm`` *and* ``spend=true`` *and* a named ``caller`` in the call; without them it returns a dry
run (the level the claim would be tested at) and changes nothing. A claim already spent is never re-read.

    pegasus-core mcp [--allow-confirm] [--ledger DIR]        # stdio
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.compute as pc
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError

from . import config, control, graphs, leads, replication, store, tools

DATASET, EVENT, YEARS = "SIM.DO", "death", "2010-2023"
ROOT = config.REPO
STATE: dict[str, Any] = {"allow_confirm": False, "ledger": None, "sessions": {}, "register": None}

server = MCPServer(
    "pegasus",
    instructions=(
        "PegaSUS reads Brazil's health events (SIM, SINASC, SIH, SINAN) against one fitted model and reports leads: "
        "findings that passed error control, with their replication tier (R0 survey only; R1 stands on held-out "
        "events; R2 recurs; R3 corroborated by an independent field). Places are 6-digit IBGE municipality codes, "
        "fields are ICD-10 nodes. A lead is a lead, not a conclusion: read `triage` (signal, noise, substitution, "
        "system artefact) and `replication` before relying on one. Exploration tools only read. `confirm_claim` "
        "spends a shared, finite error budget (the confirmation reserve): state the claim before looking, spend it "
        "once, and name yourself as the caller."))


# ---------------------------------------------------------------------------- plumbing


def _json(x: Any) -> Any:
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, np.ndarray):
        return x.tolist()
    return str(x)


def _clean(x: Any) -> Any:
    """Plain JSON: numpy to Python, NaN and infinities to null."""
    def fix(v: Any) -> Any:
        if isinstance(v, dict):
            return {str(k): fix(w) for k, w in v.items()}
        if isinstance(v, (list, tuple)):
            return [fix(w) for w in v]
        if isinstance(v, float) and not math.isfinite(v):
            return None
        return v
    return fix(json.loads(json.dumps(x, default=_json)))


def _years(text: str) -> list[int]:
    a, _, b = text.partition("-")
    return list(range(int(a), int(b or a) + 1))


def _ledger() -> control.Ledger:
    path = STATE["ledger"] or os.environ.get("PEGASUS_MCP_LEDGER")
    return control.Ledger(Path(path)) if path else control.Ledger()


def _session(dataset: str, event: str, years: str, graph: str) -> tools.Session:
    key = (dataset, event, years, graph)
    if key not in STATE["sessions"]:
        STATE["sessions"][key] = tools.Session(dataset, event, _years(years), graph, ledger=_ledger())
    return STATE["sessions"][key]


def _register() -> list[leads.Lead]:
    """The lead register, re-read when a part file is added."""
    reg = leads.Register()
    names = tuple(sorted(p.name for p in reg.path.glob("part-*.parquet")))
    if STATE["register"] is None or STATE["register"][0] != names:
        STATE["register"] = (names, reg.current())
    return STATE["register"][1]


def _provenance(session: tools.Session | None = None, block: str | None = None, tier: str | None = None
                ) -> dict[str, Any]:
    out: dict[str, Any] = {"data_version": config.data_version(), "data_code_version": config.data_code_version(),
                           "code_version": config.code_version(), "population": config.population_source()}
    if session is not None:
        out["graph"], out["years"] = session.graph, [session.years[0], session.years[-1]]
    if session is not None and block is not None:
        m = session.expectations.model(block)
        manifest = store.manifest("monolith", m.key()) or {}
        out["model"] = {"block": block, "id": store.address("monolith", m.key()).name,
                        "fitted": manifest.get("written"), "code_version": manifest.get("code_version"),
                        "data_code_version": manifest.get("data_code_version")}
    if tier:
        out["tier"] = tier
    return out


# ---------------------------------------------------------------------------- reading: the model


@server.tool()
def list_blocks(dataset: str | None = None, event: str | None = None) -> dict[str, Any]:
    """The fitted blocks (ICD-10 chapters, or `*` for an event type without a tree) in PegaSUS's store, by dataset,
    event, graph and years. Start here: a block must be fitted before its fields can be read."""
    rows = tools.fitted(dataset, event)
    grouped: dict[str, list[str]] = {}
    for r in rows:
        y = r["years"]
        grouped.setdefault(f"{r['dataset']}|{r['event']}|{r['graph']}|{y[0]}-{y[-1]}" if y else r["dataset"], []
                           ).append(r["block"])
    return _clean({"fits": {k: sorted(set(v)) for k, v in sorted(grouped.items())}, "n": len(rows),
                   "provenance": _provenance()})


@server.tool()
def list_fields(block: str, dataset: str = DATASET, event: str = EVENT, years: str = YEARS,
                graph: str = graphs.DEFAULT) -> dict[str, Any]:
    """The admissible fields (ICD-10 nodes with enough events to read, top-down) of a fitted block. The first
    call for a block loads its model and takes minutes; later calls are quick."""
    s = _session(dataset, event, years, graph)
    fs = s.fields(block)
    return _clean({"block": block, "fields": [{"node": f.node, "level": f.level, "label": f.label, "id": f.id}
                                              for f in fs], "n": len(fs), "provenance": _provenance(s, block)})


@server.tool()
def get_expectation(node: str, tier: str = "B1", places: list[int] | None = None, years: list[int] | None = None,
                    top: int = 25, dataset: str = DATASET, event: str = EVENT, span: str = YEARS,
                    graph: str = graphs.DEFAULT) -> dict[str, Any]:
    """Observed against expected for a field (ICD-10 node), tier and slice: per place-year the count y, the
    expectation mu, dispersion phi, the randomised PIT, the surprise z (positive: more than expected) and flags.
    Tiers: B0 national shape, B1 + place effects, B2 + place trends, B2s smoothed. With no `places`, the `top`
    cells of largest |z| over the grid. The field's calibration (is the expectation trustworthy?) comes with it:
    read `calibration.calibrated` before reading z."""
    s = _session(dataset, event, span, graph)
    sp = s.surprise(node, tier)
    t = sp.table()
    if places:
        t = t.filter(pc.is_in(t["u"], value_set=_arrow_ints(places)))
    if years:
        t = t.filter(pc.is_in(t["year"], value_set=_arrow_ints(years)))
    z = np.abs(np.nan_to_num(t["z"].to_numpy(zero_copy_only=False)))
    order = np.argsort(-z)[: min(top, 500)] if not places else np.arange(min(t.num_rows, 500))
    rows = t.take(order).to_pylist()
    cal = {k: v for k, v in sp.calibration.items() if k != "histogram"}
    return _clean({"field": sp.field.id, "label": sp.field.label, "tier": tier, "cells": len(z),
                   "selected": "by |z|" if not places else "as asked", "rows": rows, "calibration": cal,
                   "provenance": _provenance(s, sp.field.block, tier)})


def _arrow_ints(values: list[int]):
    import pyarrow as pa

    return pa.array([int(v) for v in values], type=pa.int32())


# ---------------------------------------------------------------------------- reading: leads


@server.tool()
def search_leads(triage_class: str | None = None, tier: str | None = None, place: int | None = None,
                 code: str | None = None, estimand: str | None = None, min_replication: str | None = None,
                 status: str | None = None, direction: str | None = None, year: int | None = None,
                 min_effect: float | None = None, max_q: float | None = None, limit: int = 20, offset: int = 0
                 ) -> dict[str, Any]:
    """Search the lead register, best rank first (evidence x effect x replication, never p alone). Filters, all
    optional: `triage_class` (signal | noise | substitution | system), `tier` (B0..B2), `place` (municipality code),
    `code` (an ICD-10 node: leads on it or under it), `estimand` (outbreak, change_point, trend_divergence,
    space_time, spatial_cluster, group_disparity), `min_replication` (R0..R3), `status`, `direction` (up | down |
    pattern), `year`, `min_effect` (a rate ratio r counts as max(r, 1/r)), `max_q`. Returns counts too."""
    register = _register()
    hits = tools.find_leads(register, cls=triage_class, tier=tier, place=place, code=code, estimand=estimand,
                            min_replication=min_replication, status=status, direction=direction, year=year,
                            min_effect=min_effect, max_q=max_q)
    limit = max(1, min(limit, 200))
    return _clean({"matched": len(hits), "register": len(register), "offset": offset,
                   "leads": [tools.lead_row(x) for x in hits[offset: offset + limit]],
                   "provenance": _provenance()})


@server.tool()
def explain_lead(lead_id: str) -> dict[str, Any]:
    """One lead in full: the lens's statistics and null, the triage verdict with its evidence (why it reads as a
    signal, an artefact or noise), each replication (split on side B, recurrence, corroboration by an independent
    field), the lead's siblings (same field, or same single place) and the story it belongs to."""
    register = _register()
    x = next((y for y in register if y.id == lead_id), None)
    if x is None:
        raise ToolError(f"no lead {lead_id!r} in the register (search_leads lists ids)")
    return _clean({**tools.explain_lead(x, register), "tier": x.tier, "provenance_of_run": _provenance()})


@server.tool()
def place_story(place: int | None = None, limit: int = 10, triage_class: str | None = None) -> dict[str, Any]:
    """The leads grouped by place (a single-place locus) or subset, best story first. With `place`, that place's
    story: every field and lens that flagged it, and any substitution (sibling codes moving in opposite
    directions). `triage_class` keeps only leads of that class (e.g. signal) before grouping."""
    register = _register()
    if triage_class:
        register = tools.find_leads(register, cls=triage_class)
    stories = leads.stories(register)
    if place is not None:
        stories = [st for st in stories if place in st.places]
    return _clean({"stories": [{"key": st.key, "places": st.places[:20], "rank": st.rank, "fields": st.fields,
                                "flags": st.flags, "n_leads": len(st.leads),
                                "leads": [tools.lead_row(m) for m in st.leads[:8]]} for st in stories[:limit]],
                   "matched": len(stories), "provenance": _provenance()})


# ---------------------------------------------------------------------------- reading: control and methods


@server.tool()
def method_status() -> dict[str, Any]:
    """Every method's measured record (ARCHITECTURE §10.5): the documented events it found, and its findings in null
    worlds, from the harness's stored results."""
    return _clean({"methods": tools.method_status(), "provenance": _provenance()})


@server.tool()
def ledger_status() -> dict[str, Any]:
    """The ledger, the denominator of every error rate: tests by family and by actor, and the confirmation
    reserve (tests spent, rejections, the level at which the next claim would be tested, the last claims with
    their callers)."""
    return _clean({**tools.ledger_status(_ledger()), "allow_confirm": STATE["allow_confirm"],
                   "provenance": _provenance()})


# ---------------------------------------------------------------------------- writing: the reserve


@server.tool()
def confirm_claim(node: str, lens: str, places: list[int], years: list[int], direction: str, caller: str,
                  spend: bool = False, actor: str = "agent", dataset: str = DATASET, event: str = EVENT,
                  span: str = YEARS, graph: str = graphs.DEFAULT) -> dict[str, Any]:
    """WRITES, and SPENDS error budget. Register one claim in the ledger and test it once on the confirmation
    reserve (the reserved period of the dataset, `control.RESERVED_PERIODS`: data no scan, fit or exploration may read) under online FDR (LOND). The claim is one fixed
    locus: field `node`, `lens` (outbreak | change_point | space_time | spatial_cluster), `places` (municipality
    codes), `years` ([first, last], the window the lead was selected on; the test is on the reserved period) and `direction` (up | down). Decide it before looking at the reserve; the
    budget is shared and finite, a rejection raises the budget a little, a miss spends it for good.

    Safety: nothing is written unless `spend` is true AND the server was started with `--allow-confirm` AND
    `caller` names who is asking (recorded with the claim; `actor` is `agent` or `person`). Otherwise this is a
    dry run returning the level the claim would be tested at. A claim already spent returns its earlier verdict;
    the reserve is read once per claim."""
    if lens not in replication.THETA:
        raise ToolError(f"lens {lens!r} cannot be confirmed; one of {sorted(replication.THETA)}")
    if direction not in ("up", "down"):
        raise ToolError("direction is 'up' or 'down'")
    years = [years[0], years[0]] if len(years) == 1 else years         # a single-year lead
    if not places or len(years) != 2 or years[0] > years[1]:
        raise ToolError("places must be non-empty and years [first, last]")
    if actor not in ("agent", "person"):
        raise ToolError("actor is 'agent' or 'person'")
    if not caller.strip():
        raise ToolError("caller must name who is asking; it is recorded with the claim")
    s = _session(dataset, event, span, graph)
    try:
        s.expectations.field(node)
    except KeyError as exc:
        raise ToolError(str(exc.args[0])) from exc
    locus = {"places": sorted(int(p) for p in places), "years": [int(y) for y in years], "direction": direction}
    spec = {"field": node, "lens": lens, "locus": locus}
    reserve = control.Reserve(s.ledger)
    before = {"spent": reserve.state()[0], "rejections": reserve.state()[1], "next_level": reserve.level()}
    prev = reserve.previous(spec)
    if prev:
        return _clean({"status": "already_spent", "claim": spec, "earlier": prev, "reserve": before,
                       "provenance": _provenance(s, s.expectations.field(node).block, tools.LENS_TIERS[lens])})
    if not (spend and STATE["allow_confirm"]):
        why = ("the server was started without --allow-confirm" if spend else "spend is false")
        return _clean({"status": "dry_run", "claim": spec, "wrote": False, "reserve": before,
                       "note": f"Not spent: {why}. A spend tests this claim once at level {before['next_level']:.3g}.",
                       "provenance": _provenance(s, s.expectations.field(node).block, tools.LENS_TIERS[lens])})
    result = s.confirm(node, lens, locus, actor=actor, caller=caller.strip())
    after = control.Reserve(s.ledger)
    return _clean({"status": "spent", "wrote": True, "claim": spec, "caller": caller.strip(), "actor": actor,
                   "result": result, "ledger": after.previous(spec),
                   "reserve": {"spent": after.state()[0], "rejections": after.state()[1],
                               "next_level": after.level()},
                   "provenance": _provenance(s, s.expectations.field(node).block, tools.LENS_TIERS[lens])})


# ---------------------------------------------------------------------------- resources


def _sections() -> list[tuple[str, str, int]]:
    """(number, title, line) of ARCHITECTURE.md's sections."""
    out = []
    for i, line in enumerate((ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8").splitlines(), 1):
        m = re.match(r"^(##|###) (\d+(?:\.\d+)?)\.? (.+)$", line)
        if m:
            out.append((m.group(2), m.group(3), i))
    return out


@server.resource("pegasus://architecture", mime_type="application/json")
def architecture_map() -> str:
    """The section map of ARCHITECTURE.md; read a section with pegasus://architecture/{number}."""
    return json.dumps([{"section": n, "title": t, "uri": f"pegasus://architecture/{n}"} for n, t, _ in _sections()],
                      ensure_ascii=False)


@server.resource("pegasus://architecture/{number}", mime_type="text/markdown")
def architecture_section(number: str) -> str:
    """One section of ARCHITECTURE.md by number (e.g. 8.3, 9)."""
    secs = _sections()
    lines = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8").splitlines()
    for k, (n, _, start) in enumerate(secs):
        if n == number:
            end = next((ln for m, _, ln in secs[k + 1:] if m.count(".") <= n.count(".")), len(lines) + 1)
            return "\n".join(lines[start - 1: end - 1])
    raise ResourceError(f"no section {number!r}; pegasus://architecture lists them")


@server.resource("pegasus://evaluation", mime_type="text/markdown")
def evaluation_index() -> str:
    """EVALUATION.md: the index of measurements and live runs, newest last; entries at pegasus://evaluation/{slug}."""
    return (ROOT / "EVALUATION.md").read_text(encoding="utf-8")


@server.resource("pegasus://evaluation/{slug}", mime_type="text/markdown")
def evaluation_entry(slug: str) -> str:
    """One evaluation entry (a file of docs/evaluation without its .md)."""
    path = ROOT / "docs" / "evaluation" / f"{slug}.md"
    if not re.fullmatch(r"[A-Za-z0-9._-]+", slug) or not path.is_file():
        raise ResourceError(f"no evaluation entry {slug!r}")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------- entry


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="pegasus-core mcp", description=__doc__.split("\n\n")[0])
    ap.add_argument("--allow-confirm", action="store_true",
                    help="let confirm_claim spend the confirmation reserve (default: dry runs only)")
    ap.add_argument("--ledger", default=None, help="a ledger directory other than PEGASUS_HOME/ledger (tests, demos)")
    args = ap.parse_args(argv)
    STATE["allow_confirm"], STATE["ledger"] = args.allow_confirm, args.ledger
    server.run("stdio")


if __name__ == "__main__":
    main()
