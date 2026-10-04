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

import numpy as np

from . import gateway

# supports, finest first; a field's support is where its law is exact
SUPPORTS = ("municipality", "ibge_immediate_region", "health_region", "ibge_intermediate_region", "uf",
            "ibge_macroregion", "national")
LAWS = ("sum", "ratio_of_sums", "weighted_mean", "none")

# provisional admission until the harness's power curves exist (ARCHITECTURE §8.4)
MIN_EVENTS = 1000
MIN_UNIT_SHARE = 0.05
MAX_OVERLAP = 0.05


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
        import pegasus_data as pg  # only for the event type's declared classifier name

        if classifier is None:
            spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
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

    def chapter(self, code: str) -> str:
        node = code
        while self.parent.get(node) is not None:
            node = self.parent[node]
        return node

    def field(self, node: str) -> Field:
        if node not in self.level:
            raise KeyError(f"{node!r} is not a node of {self.structure}")
        return Field(id=f"{self.dataset}:{self.event}:{self.classifier}:{node}", dataset=self.dataset,
                     event=self.event, classifier=self.classifier, structure=self.structure, node=node,
                     level=self.level[node], block=self.chapter(node), label=self.label.get(node) or "",
                     signature={self.classifier: self.prefixes(node)})

    def leaves(self, node: str, leaf_level: str = "category") -> list[str]:
        """The leaf-level codes under a node (the node itself when it is a leaf)."""
        if self.level.get(node) == leaf_level:
            return [node]
        out: list[str] = []
        for child in self.children.get(node, []):
            out.extend(self.leaves(child, leaf_level))
        return out

    def prefixes(self, node: str) -> list[str]:
        """Code prefixes whose records belong to the node: its categories (I20, I21…)."""
        return self.leaves(node) if self.level.get(node) in ("chapter", "group") else [node]

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


def admission(events_total: float, units_with_events: int, units: int) -> tuple[bool, str]:
    """The provisional rule of ARCHITECTURE §8.4 (replaced by power curves once calibrated)."""
    if events_total < MIN_EVENTS:
        return False, f"{events_total:.0f} events < {MIN_EVENTS}"
    if units_with_events < MIN_UNIT_SHARE * units:
        return False, f"events in {units_with_events}/{units} units < {MIN_UNIT_SHARE:.0%}"
    return True, "admitted (provisional rule)"


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
