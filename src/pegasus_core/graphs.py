"""Proximity graphs over places (ARCHITECTURE §4.3), through the gateway.

A graph is (edges, weights) over an ordered array of places. The family:

    contiguity      shared border, weighted by border length (pegasus_data, IBGE 2022 mesh)
    contiguity01    shared border, unweighted
    distanceH       population-centre pairs within pegasus_data's distance graph,
                    weighted exp(−d/H) (H in km, e.g. ``distance50``)
    knnK            K nearest population centres (symmetrised), unweighted

Which graph carries spatial structure best is a measurement (ARCHITECTURE §12,
phase 1), not a choice made here. Places absent from a graph (islands) are
isolated nodes; the ICAR gives them an iid precision.
"""

from __future__ import annotations

import numpy as np

from . import gateway, store, structures

DEFAULT = "contiguity"


def edges(places: np.ndarray, kind: str = DEFAULT) -> np.ndarray:
    """Edges (index pairs into ``places``, i < j) of a named graph."""
    return graph(places, kind)[0]


def graph(places: np.ndarray, kind: str = DEFAULT) -> tuple[np.ndarray, np.ndarray]:
    """(edges [m, 2] with i < j, weights [m]) of a named graph over ``places``."""
    key = {"what": "graph", "kind": kind, "places": int(len(places)), "first": int(places[0]),
           "last": int(places[-1]), "sum": int(np.sum(places)), "v": 3}
    cached = store.get_arrays("graphs", key)
    if cached is not None:
        return cached["edges"], cached["weights"]
    if kind.startswith("knn"):
        out = structures.knn_graph(gateway.municipality_points(places), int(kind[3:]))
        w = np.ones(len(out))
    elif kind in ("contiguity", "contiguity01") or kind.startswith("distance"):
        table = gateway.proximity_graph("contiguity" if kind.startswith("contiguity") else "population_distance")
        index = {int(c): i for i, c in enumerate(places)}
        a = np.array([index.get(int(x), -1) for x in table.column("a").to_numpy()])
        b = np.array([index.get(int(x), -1) for x in table.column("b").to_numpy()])
        raw = table.column("weight").to_numpy()
        keep = (a >= 0) & (b >= 0) & (a < b)
        out = np.column_stack([a[keep], b[keep]])
        if kind == "contiguity":
            # border length, scale-free; an unknown length (null in pegasus_data) gets the median,
            # a corner touch (length 0) keeps its edge at a 1 km floor
            known = np.isfinite(raw[keep])
            length = np.where(known, raw[keep], np.median(raw[keep][known]))
            w = np.maximum(length, 1.0) / np.median(length)
        elif kind == "contiguity01":
            w = np.ones(int(keep.sum()))
        else:
            w = np.exp(-raw[keep] / float(kind[len("distance"):]))
    else:
        raise KeyError(f"unknown graph {kind!r}")
    store.put_arrays("graphs", key, {"edges": out, "weights": w})
    return out, w
