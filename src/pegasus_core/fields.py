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

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import numpy as np

from . import gateway

# supports, finest first; a field's support is where its law is exact
SUPPORTS = ("municipality", "ibge_immediate_region", "health_region", "ibge_intermediate_region", "uf",
            "ibge_macroregion", "national")
LAWS = ("sum", "ratio_of_sums", "weighted_mean", "none")

# Admission (ARCHITECTURE §8.4, ADR-0022): a field enters a lens scan when the lens's power for the reference effect
# (a rate ratio of REFERENCE_RATE_RATIO, or the smallest the lens can see, over one macro-region and window) is at least MIN_POWER at the field's expected
# count there, and a pair scan when the power to see a shared latent of correlation PAIR_RHO is.
REFERENCE_RATE_RATIO = 1.5
PAIR_RHO = 0.3
MIN_POWER = 0.5
MAX_OVERLAP = 0.05
CURVES = Path(__file__).with_name("admission_curves.json")
# the lenses with a curve at the reference effect, and the locus whose expected count it is read at:
# (share of a macro-region's events over the whole window that the locus holds): a region-year is 1/T of the window,
# the last three years of a change point 3/T, the whole period of a spatial cluster 1
COUNT_LENSES = ("outbreak", "change_point", "space_time", "spatial_cluster")
RECENT_YEARS = 3


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
            tree = gateway.code_structure(structure)
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
def curves() -> dict:
    """The lenses' measured power at the reference effect (`scripts/measure_admission.py`): per lens, bins of the
    locus's expected count with the share of planted loci the production lens detected."""
    if not CURVES.exists():
        raise FileNotFoundError(f"{CURVES.name}: run scripts/measure_admission.py (the admission rule is read from the "
                                "harness's power curves, ARCHITECTURE §8.4)")
    return json.loads(CURVES.read_text(encoding="utf-8"))


@cache
def reference_theta(lens: str) -> float | None:
    """The rate ratio a lens is admitted at: the reference 1.5 (§8.4) if some count gives it power 0.5 there, else the
    smallest measured ratio at which some count does (a lens that cannot see 1.5 anywhere would otherwise scan nothing);
    None if it never reaches 0.5 (ADR-0022)."""
    by_theta = curves()["lenses"][lens]["theta"]
    for theta in sorted(by_theta, key=float):
        if max((b["power"] for b in by_theta[theta]["bins"]), default=0.0) >= MIN_POWER:
            return float(theta)
    return None


@cache
def _curve(lens: str) -> tuple[np.ndarray, np.ndarray]:
    """(log expected count, power) of a lens at its reference ratio, made non-decreasing in the count by pooling
    adjacent violators (more expected events never lowers power), one point per bin."""
    theta = reference_theta(lens)
    if theta is None:
        return np.array([0.0]), np.array([0.0])
    bins = curves()["lenses"][lens]["theta"][str(theta)]["bins"]
    x = np.log(np.array([b["median_m"] for b in bins]))
    y = np.array([b["power"] for b in bins], dtype=float)
    w = np.array([b["n"] for b in bins], dtype=float)
    out: list[list[float]] = []
    for blk in ([yy, ww, 1] for yy, ww in zip(y, w, strict=True)):
        out.append(blk)
        while len(out) > 1 and out[-2][0] > out[-1][0]:
            b2, b1 = out.pop(), out.pop()
            tot = b1[1] + b2[1]
            out.append([(b1[0] * b1[1] + b2[0] * b2[1]) / tot, tot, b1[2] + b2[2]])
    return x, np.repeat([b[0] for b in out], [b[2] for b in out])


def power(lens: str, expected: float) -> float:
    """The lens's power for its reference effect over a locus of ``expected`` events: interpolated in the log count
    between the measured bins, 0 below the smallest, flat above the largest."""
    x, y = _curve(lens)
    if expected <= 0 or reference_theta(lens) is None:
        return 0.0
    return float(np.interp(np.log(expected), x, y, left=0.0, right=y[-1]))


def critical_count(lens: str) -> float | None:
    """The smallest locus count at which the lens reaches MIN_POWER; None if it never does."""
    x, y = _curve(lens)
    if reference_theta(lens) is None or y[-1] < MIN_POWER:
        return None
    return float(np.exp(np.interp(MIN_POWER, y, x))) if y[0] < MIN_POWER else float(np.exp(x[0]))


def locus_count(lens: str, region_events: np.ndarray, years: int) -> float:
    """The expected count of the reference locus for a field with ``region_events`` events per macro-region over
    ``years`` years: the typical (median) macro-region's share of the window the lens reads."""
    share = {"outbreak": 1 / years, "space_time": 1 / years, "change_point": min(RECENT_YEARS, years) / years,
             "spatial_cluster": 1.0}[lens]
    return float(np.median(region_events)) * share


def admission(lens: str, region_events: np.ndarray, years: int) -> tuple[bool, str]:
    """Whether a lens scans a field (ARCHITECTURE §8.4): its power for a rate ratio of 1.5 over a macro-region-year is at
    least 0.5 at the field's count, read from the measured curve (`curves`). ``region_events``: the field's events in
    each macro-region over the ``years`` of the window."""
    m = locus_count(lens, region_events, years)
    p = power(lens, m)
    return p >= MIN_POWER, (f"{lens}: {m:.0f} expected in the median macro-region's locus, power {p:.2f} at RR "
                            f"{reference_theta(lens)}")


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
