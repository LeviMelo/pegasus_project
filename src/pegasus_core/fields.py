"""Fields: projections of events onto a lattice (ARCHITECTURE §3.2, §8.4, §8.5).

A count field is one node of an event type's classifier structure: its events
are those whose classifier code falls under the node. Every node of a block's
tree down to the monolith's leaf level is a field, so scanning "every field"
means walking the tree, descending only while children stay admissible.

Lattices form a ladder of supports. Two fields are compared at the finest
support both lift to; a count lifts by summing, a ratio by summing its
numerator and denominator, a level never lifts below its own grain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

import numpy as np

from . import gateway

# supports, finest first; a field's support is where its law is exact
SUPPORTS = ("municipality", "ibge_immediate_region", "health_region", "ibge_intermediate_region", "uf",
            "ibge_macroregion", "national")
LAWS = ("sum", "ratio_of_sums", "weighted_mean", "none")

MAX_OVERLAP = 0.05   # two fields sharing more of their events than this are not a testable pair (§8.5)


@dataclass(frozen=True)
class Field:
    id: str                          # "SIM.DO:death:CAUSABAS:I20-I25"
    dataset: str
    event: str
    classifier: str                  # the column the structure classifies
    structure: str                   # "ICD10"
    node: str                        # the node's code
    level: str                       # chapter | group | category
    block: str                       # the chapter the node lies in (the monolith block)
    label: str = ""
    kind: str = "count"              # count | mark | share | level
    law: str = "sum"
    support: str = "municipality"
    grain: str = "year"
    signature: dict = field(default_factory=dict, hash=False, compare=False)  # {column: [prefixes]}


class Registry:
    """The fields of one event type's classifier tree, with the tree's relations."""

    def __init__(self, dataset: str, event: str, structure: str = "ICD10", classifier: str | None = None):
        if classifier is None:
            spec = gateway.event_type(dataset, event)
            primary = [c["column"] for c in spec.get("classifiers", []) if c["role"] == "primary"]
            classifier = primary[0] if primary else None
        self.classifier = classifier or "*"
        self.dataset, self.event, self.structure = dataset, event, structure if classifier else None
        if classifier is None:
            # an event type without a classifier: one field, all its events
            self.parent, self.level, self.label = {"*": None}, {"*": "category"}, {"*": event}
        else:
            tree = gateway.code_tree(structure)
            codes = tree.column("code").to_pylist()
            self.parent = dict(zip(codes, tree.column("parent").to_pylist(), strict=True))
            self.level = dict(zip(codes, tree.column("level").to_pylist(), strict=True))
            self.label = dict(zip(codes, tree.column("label").to_pylist(), strict=True))
        self.children: dict[str | None, list[str]] = {}
        for c, p in self.parent.items():
            self.children.setdefault(p, []).append(c)
        # fields that cross the tree (ARCHITECTURE §3.3): chapter XX's categories by intent and by mechanism (NCHS's
        # External Cause of Injury Mortality Matrix, pegasus_data `code_attributes`), where a category carries one value
        # (firearm deaths span W32-W34, X72-X74, X93-X95 and Y22-Y24). Each is a node under XX with its members listed,
        # not a child in the tree (a category keeps its one parent)
        self.members: dict[str, list[str]] = {}
        if self.structure == "ICD10":
            for node, label, members in _external_cause_axes():
                if all(m in self.level for m in members):
                    self.members[node], self.level[node], self.label[node] = members, "axis", label
                    self.parent[node] = "XX"
        # list fields (ARCHITECTURE §3.3, §8.6): the Ministry's concept lists' items (pegasus_data `code_lists`) as
        # nodes across blocks, `LIST[<list>=<item>]`, read through `list_fields`; their blocks are their members'
        # chapters (`blocks`). Built on demand: the lists hold some 70 k memberships
        self._lists: dict[str, list[str]] | None = None

    def chapter(self, code: str) -> str:
        node = code
        while self.parent.get(node) is not None:
            node = self.parent[node]
        return node

    def field(self, node: str) -> Field:
        if node not in self.level and node.startswith("LIST[") and "=" in node:
            self.list_fields(node[5:].split("=", 1)[0])           # a list's items are registered on first use
        if node not in self.level and node.startswith("CONS[") and node.endswith("]"):
            return self.conserved(node[5:-1])
        if node not in self.level:
            raise KeyError(f"{node!r} is not a node of {self.structure}")
        return Field(id=f"{self.dataset}:{self.event}:{self.classifier}:{node}", dataset=self.dataset,
                     event=self.event, classifier=self.classifier, structure=self.structure, node=node,
                     level=self.level[node],
                     block=("+".join(self.blocks(node)) if self.level[node] == "list" else self.chapter(node)),
                     label=self.label.get(node) or "",
                     signature={self.classifier: self.prefixes(node)})

    def list_fields(self, name: str) -> list[Field]:
        """The items of a concept list (pegasus_data `code_structure(name)`, e.g. ``SIM-POUCO-UTEIS``) as fields across
        blocks. A list's codes are read at the leaves' grain: an item holds a category when it lists the category or
        every one of its subcategories; an item that holds part of a category is left out (counted in
        ``self.partial[name]``), never rounded to the whole category."""
        if self.structure != "ICD10":
            return []
        t = gateway.code_structure(name)
        items, codes = t.column("item").to_pylist(), t.column("code").to_pylist()
        subs: dict[str, set[str]] = {}
        for c, lv in self.level.items():
            if lv == "subcategory":
                subs.setdefault(c[:3], set()).add(c)
        by_item: dict[str, set[str]] = {}
        for it, c in zip(items, codes, strict=True):
            by_item.setdefault(str(it), set()).add(str(c))
        self.partial = getattr(self, "partial", {})
        out, partial = [], 0
        for it, cs in sorted(by_item.items()):
            cats = {c[:3] for c in cs if c[:3] in self.level and self.level[c[:3]] == "category"}
            whole = [k for k in cats if k in cs or (subs.get(k) and subs[k] <= cs)]
            if len(whole) < len(cats) or not whole:
                partial += 1
                continue
            node = f"LIST[{name}={it}]"
            self.members[node], self.level[node], self.label[node] = sorted(whole), "list", f"{name}: {it}"
            self.parent[node] = None
            out.append(self.field(node))
        self.partial[name] = partial
        return out

    def conserved(self, node: str) -> Field:
        """The conserved level of a node (ARCHITECTURE §8.6): its ICD family (the outermost group below its chapter,
        `leads.family`'s rule), plus the ill-defined causes R00-R99, plus, for an external cause, the events of
        undetermined intent Y10-Y34: the pools a coding change exchanges with. A departure that a recoding makes
        shows at the node and not here; one in the events shows in both. A field across blocks (`CONS[<family>]`)."""
        fam = node
        while self.parent.get(fam) is not None and self.parent.get(self.parent[fam]) is not None:
            fam = self.parent[fam]
        if self.level.get(fam) == "chapter":
            raise ValueError(f"{node!r} is a chapter: its conserved level is not defined below it")
        members = set(self.leaves(fam))
        members |= {c for c in self.level if self.level[c] == "category" and "R00" <= c <= "R99"}
        if self.chapter(fam) == "XX":
            members |= {c for c in self.level if self.level[c] == "category" and "Y10" <= c <= "Y34"}
        cons = f"CONS[{fam}]"
        self.members[cons], self.level[cons], self.parent[cons] = sorted(members), "list", None
        self.label[cons] = f"conserved level of {fam}: + R00-R99" + (" + Y10-Y34" if self.chapter(fam) == "XX" else "")
        return self.field(cons)

    def blocks(self, node: str) -> list[str]:
        """The chapters a node's leaves fall in (one for a tree node or an axis, several for a list item)."""
        return sorted({self.chapter(c) for c in self.leaves(node)})

    def leaves(self, node: str, leaf_level: str = "category") -> list[str]:
        """The leaf-level codes under a node (the node itself when it is a leaf; an axis node's members)."""
        if node in self.members:
            return list(self.members[node])
        if self.level.get(node) == leaf_level:
            return [node]
        out: list[str] = []
        for child in self.children.get(node, []):
            out.extend(self.leaves(child, leaf_level))
        return out

    def prefixes(self, node: str) -> list[str]:
        """Code prefixes whose records belong to the node: its categories (I20, I21…)."""
        return self.leaves(node) if self.level.get(node) in ("chapter", "group", "axis", "list") else [node]

    def walk(self, block: str, admissible) -> list[Field]:
        """Every field of a block, top-down, descending only into admissible nodes."""
        out: list[Field] = []
        frontier = [block]
        while frontier:
            node = frontier.pop()
            if not admissible(node):
                continue
            out.append(self.field(node))
            if self.level.get(node) != "category":
                frontier.extend(sorted(self.children.get(node, []), reverse=True))
        out.extend(self.field(n) for n in sorted(self.members) if self.parent[n] == block and admissible(n))
        return out

    def related(self, a: str, b: str) -> bool:
        """One node lies under the other (their events nest: overlap 1 by construction)."""
        def ancestors(x: str) -> set[str]:
            out = {x}
            while self.parent.get(x) is not None:
                x = self.parent[x]
                out.add(x)
            return out
        return a in ancestors(b) or b in ancestors(a)


@cache
def _external_cause_axes() -> list[tuple[str, str, list[str]]]:
    """(node, label, member categories) for every intent and mechanism value chapter XX's categories carry."""
    a = gateway.code_attributes("ICD10")
    cols = {c: a.column(c).to_pylist() for c in ("code", "level", "chapter", "intent", "mechanism")}
    out = []
    for axis in ("intent", "mechanism"):
        by: dict[str, list[str]] = {}
        for code, level, chap, value in zip(cols["code"], cols["level"], cols["chapter"], cols[axis], strict=True):
            if level == "category" and chap == "XX" and value:
                by.setdefault(value, []).append(code)
        for value, members in sorted(by.items()):
            slug = value.lower().replace("/", "-").replace(" ", "-")           # ids may become paths
            out.append((f"XX[{axis}={slug}]", f"{axis}: {value} (NCHS matrix)", sorted(members)))
    return out


@cache
def overlap(a: Field, b: Field, registry: Registry | None = None, period: object | None = None) -> float | None:
    """Share of events in common (ARCHITECTURE §8.5): structural when the answer is
    known by construction, measured from records otherwise; None when unknown."""
    if (a.dataset, a.event) != (b.dataset, b.event):
        return 0.0  # different event types: different events (they may share persons, which is not overlap)
    if a.classifier == b.classifier and a.structure == b.structure:
        if registry is not None and registry.related(a.node, b.node):
            return 1.0
        return 0.0  # one code per event on a single-valued classifier: disjoint nodes share nothing
    if period is None:
        return None
    measured = gateway.field_overlap(a.dataset, a.event, a.signature, b.signature, period)
    return float(measured["overlap"]) if "overlap" in measured else None


def testable(a: Field, b: Field, registry: Registry | None = None, period: object | None = None) -> bool:
    """A pair may be tested for dependence only if its overlap is known and ≤ 0.05."""
    o = overlap(a, b, registry, period)
    return o is not None and o <= MAX_OVERLAP


def lift(values: np.ndarray, places: np.ndarray, support: str, law: str = "sum",
         denominator: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Values over places [U, …] lifted to a coarser support: (units, lifted [V, …]).
    A ratio lifts as Σ numerator / Σ denominator; a level does not lift."""
    if support == "municipality":
        return places, values
    if law == "none":
        raise ValueError("a level field does not lift to a coarser support")
    units = np.full(len(places), "BR") if support == "national" else gateway.regions(places, support)
    keys, inv = np.unique(units, return_inverse=True)
    out = np.zeros((len(keys), *values.shape[1:]))
    np.add.at(out, inv, values)
    if law == "ratio_of_sums":
        if denominator is None:
            raise ValueError("a ratio lifts only with its denominator")
        den = np.zeros_like(out)
        np.add.at(den, inv, denominator)
        out = np.divide(out, den, out=np.full_like(out, np.nan), where=den > 0)
    return keys, out


def common_support(a: Field, b: Field) -> str:
    """The finest support both fields lift to."""
    return SUPPORTS[max(SUPPORTS.index(a.support), SUPPORTS.index(b.support))]


# ---------------------------------------------------------------------- fields from declarations (S1)


@dataclass(frozen=True)
class Declared:
    """A field pegasus_data's roles declare beyond the counts (docs/plans/2026-10-07-fields-from-roles.md):
    ``kind`` measure (a number that is a measurement) or composition (a category's codes), the ``column``, its role
    and name, and for a measure its declared missing codes and domain. ``reason`` is set when it is not modelled."""
    dataset: str
    column: str
    role: str
    name: str
    kind: str
    missing: tuple[str, ...] = ()
    domain: tuple[float, float] | None = None
    reason: str = ""


def declared(dataset: str) -> list[Declared]:
    """Every mark or dimension column of ``dataset`` as a field, or with the reason it is not one: a draft role, a
    number that is no measurement, a measurement whose missing codes are undeclared, a kind not yet read (a date, a
    place, a code tree, a text). A date (a mark, or another `when` than the event's own) is an interval field
    ``interval:<column>``: the days between the event's own date (`gateway._when`) and it. Nothing is named here:
    every field comes from the declarations (`gateway.roles`)."""
    from . import gateway

    try:
        anchor = gateway._when(dataset)
    except LookupError:
        anchor = None
    out = []
    for r in gateway.roles(dataset):
        if r.get("model") not in ("mark", "dimension") and not (r.get("model") == "when" and r["kind"] == "date"):
            continue
        if r["kind"] == "date" and anchor is None:
            out.append(Declared(dataset, f"interval:{r['column']}", r["role"], r.get("name") or "", "interval",
                                reason="the event type declares no date of its own"))
            continue
        base = {"dataset": dataset, "column": r["column"], "role": r["role"], "name": r.get("name") or ""}
        if not r.get("reviewed", True):
            out.append(Declared(**base, kind="", reason="role is a draft"))
        elif r["kind"] == "number":
            if not r.get("measure"):
                out.append(Declared(**base, kind="", reason="a number that is not a measurement"))
            elif r.get("missing") is None:
                out.append(Declared(**base, kind="measure", reason="missing codes not declared"))
            else:
                dom = r.get("domain")
                out.append(Declared(**base, kind="measure", missing=tuple(r["missing"]),
                                    domain=tuple(dom) if dom else None))
        elif r["kind"] == "category":
            if r.get("missing") is None:
                out.append(Declared(**base, kind="composition", reason="missing codes not declared"))
            else:
                out.append(Declared(**base, kind="composition", missing=tuple(r["missing"])))
        elif r["kind"] == "date":
            out.append(Declared(**{**base, "column": f"interval:{r['column']}"}, kind="interval",
                                reason="the event's own date" if r["column"] == anchor else ""))
        else:
            out.append(Declared(**base, kind="", reason=f"kind {r['kind']} not yet read"))
    return out


def measure_source(dataset: str, event: str, column: str) -> dict:
    """The reader of a declared measure (`monolith.assemble`'s ``source``): positive values on the log scale, or the
    count family when the declared domain admits zero; the declared domain (else positive) and missing codes, the event type's primary classifier, and as case-mix its first
    alternative classifier with a structure (SIH's procedures), all from the declarations."""
    from . import gateway

    d = next(x for x in declared(dataset) if x.column == column)
    if d.kind != "measure" or d.reason:
        raise ValueError(f"{dataset}.{column} is not a modelled measure: {d.reason or d.kind}")
    et = gateway.event_type(dataset, event)
    cls = et.get("classifiers") or []
    primary = next((c["column"] for c in cls if c["role"] == "primary"), None)
    casemix = next((c["column"] for c in cls if c["role"] == "alternative" and c.get("structure")), None)
    lo, hi = d.domain if d.domain else (0.0, 1e300)
    # a domain that admits zero is a count's (previous pregnancies, Apgar): the count family, whose support holds 0;
    # otherwise a positive quantity on the log scale (a weight, a length of stay)
    family = "count" if d.domain and lo <= 0 else "mark"
    return {"source": family, "mark": column, "bounds": (lo, hi) if family == "count" else (max(lo, 1e-9), hi),
            "missing": list(d.missing),
            **({"classifier": primary} if primary else {}), **({"casemix": casemix} if casemix else {})}


def declared_flows(dataset: str) -> list[Declared]:
    """The care-flow fields of ``dataset``: every place column in the residence's own code system (its first declared
    codelist) that is not an attribute of the person (its entity is not the residence's: a birthplace is the person's,
    a hospital or a place of death is the event's) is a field ``away:<column>``, the share of events that happened away
    from the residence municipality (`gateway.away_counts`)."""
    from . import gateway

    rows = gateway.roles(dataset)
    res = next((r for r in rows if r["column"] == gateway._strata(dataset)["residence"]), None)
    if res is None or not res.get("codelists"):
        return []
    system = res["codelists"][0]
    return [Declared(dataset, f"away:{r['column']}", r["role"], f"events away from residence ({r['role']})", "away")
            for r in rows if r["kind"] == "place" and r["column"] != res["column"] and r.get("reviewed", True)
            and (r.get("codelists") or [None])[0] == system and r["entity"] != res["entity"]]


def flow_source(dataset: str, event: str, column: str) -> dict:
    """The reader of a care-flow field (`declared_flows`): its place against the residence, on the event type's primary
    classifier."""
    from . import gateway

    et = gateway.event_type(dataset, event)
    primary = next((c["column"] for c in et.get("classifiers") or [] if c["role"] == "primary"), None)
    return {"source": "away", "place": column.split(":", 1)[1], **({"classifier": primary} if primary else {})}


def declared_mentions(dataset: str) -> list[Declared]:
    """The multiple-code fields of ``dataset``: every group of columns pegasus_data declares to be read together as one
    set of codes (`gateway.code_groups`: an admission's diagnoses, the causes a certificate mentions) is a field
    ``mentions:<role>`` whose events count once under each category any of its columns carries."""
    from . import gateway

    return [Declared(dataset, f"mentions:{role}", role, f"every code of {role} ({', '.join(cols)})", "mentions")
            for role, cols in gateway.code_groups(dataset).items()]


def mentions_source(dataset: str, column: str) -> dict:
    """The reader of a multiple-code field (`declared_mentions`): the code list of its columns, on ICD-10's tree."""
    from . import gateway

    role = column.split(":", 1)[1]
    cols = gateway.code_groups(dataset)[role]
    return {"source": "code_list", "column": cols, "classifier": column}


def interval_source(dataset: str, event: str, column: str, probe_year: int) -> dict:
    """The reader of an interval field (`declared`, ``interval:<date column>``): the days from the event's own date to
    the column's, plus one, as a positive measure (`gateway.mark_moments` with ``anchor``); its sign, which of the two
    dates comes first, is read from the data of ``probe_year`` (the median), never assumed. No missing code: an
    unparseable date is a missing mark."""
    import duckdb

    from . import gateway

    d = next(x for x in declared(dataset) if x.column == column)
    if d.kind != "interval" or d.reason:
        raise ValueError(f"{dataset}.{column} is not a modelled interval: {d.reason or d.kind}")
    col, anchor = column.split(":", 1)[1], gateway._when(dataset)
    raw = gateway._records(dataset, event, probe_year, [anchor, col])
    con = duckdb.connect()
    con.register("r", raw)
    med = con.execute(f"SELECT median(date_diff('day', {gateway._date_sql(anchor)}, {gateway._date_sql(col)})) "
                      "FROM r").fetchone()[0]
    et = gateway.event_type(dataset, event)
    primary = next((c["column"] for c in et.get("classifiers") or [] if c["role"] == "primary"), None)
    return {"source": "mark", "mark": col, "anchor": anchor, "sign": -1 if med is not None and med < 0 else 1,
            "bounds": (1.0, 1e300), "missing": [], **({"classifier": primary} if primary else {})}


def classifier_sources(dataset: str, event: str) -> list[tuple[str, dict, list[str]]]:
    """The event type's other declared classifiers with a code tree (SIH's procedures by SIGTAP, SIM's original
    cause by ICD-10): each as (``classifier:<column>``, its reader, the chapters of its tree). Counts of the same
    events, classified another way."""
    from . import gateway

    out = []
    for c in gateway.event_type(dataset, event).get("classifiers") or []:
        if c["role"] == "primary" or not c.get("structure"):
            continue
        tree = gateway.code_tree(c["structure"])
        roots = sorted(x for x, lv in zip(tree.column("code").to_pylist(), tree.column("level").to_pylist(), strict=True)
                       if lv == "chapter")
        out.append((f"classifier:{c['column']}", {"classifier": c["column"], "structure": c["structure"]}, roots))
    return out


def share_sources(dataset: str, event: str, column: str, probe_year: int) -> list[tuple[str, dict]]:
    """The share fields of a declared composition: one per recorded value of ``column`` except its most frequent (the
    reference: a value's share and its complement carry one question), each with its reader (`monolith.assemble`'s
    ``source``: indicator, success, the declared missing codes, the event type's primary classifier). The values are
    read from the data of ``probe_year`` (`gateway.composition_counts`), never listed here."""
    from . import gateway

    d = next(x for x in declared(dataset) if x.column == column)
    if d.kind != "composition" or d.reason:
        raise ValueError(f"{dataset}.{column} is not a modelled composition: {d.reason or d.kind}")
    et = gateway.event_type(dataset, event)
    primary = next((c["column"] for c in et.get("classifiers") or [] if c["role"] == "primary"), None)
    comp = gateway.composition_counts(dataset, event, probe_year, column, d.missing, primary).counts.to_pandas()
    order = comp.groupby("value")["n"].sum().sort_values(ascending=False).index.tolist()
    return [(v, {"source": "share", "indicator": column, "success": (v,), "missing": list(d.missing),
                 **({"classifier": primary} if primary else {})}) for v in order[1:]]


def declared_links(dataset: str, event: str) -> list[Declared]:
    """The person-level fields of ``dataset`` (S2): for every declared link (pegasus_data `links.yml`) with a side
    on this dataset, the share of that side's events linked to the other side's (`gateway.linked_counts`): an outcome
    after the event on a cohort's side, a recording measure on the other. ``column`` names the field
    ``link:<spec>:<side>``; a grouped side with a filter carries the reason it is not read yet."""
    from . import gateway

    out = []
    for name, spec in gateway.link_specs().items():
        for side, sd, other in (("left", spec.left, spec.right), ("right", spec.right, spec.left)):
            if sd.dataset.upper().replace(".", "-") != dataset.upper().replace(".", "-"):
                continue
            reason = ("a grouped side with a filter or a 'latest' order is not read yet"
                      if sd.group and (sd.where or getattr(sd, "latest", None)) else "")
            out.append(Declared(dataset, f"link:{name}:{side}", f"linked.{other.dataset}",
                                f"{dataset} events linked to {other.dataset} ({name})", "linked", reason=reason))
    return out


def link_source(dataset: str, event: str, column: str) -> dict:
    """The reader of a person-level field (`declared_links`): the linked share of one side of a declared link, on the
    event type's primary classifier."""
    from . import gateway

    d = next(x for x in declared_links(dataset, event) if x.column == column)
    if d.reason:
        raise ValueError(f"{dataset}.{column}: {d.reason}")
    _, name, side = column.split(":")
    et = gateway.event_type(dataset, event)
    primary = next((c["column"] for c in et.get("classifiers") or [] if c["role"] == "primary"), None)
    return {"source": "linked", "link": name, "side": side, **({"classifier": primary} if primary else {})}

