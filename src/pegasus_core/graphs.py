"""Proximity graphs over places (ARCHITECTURE §4.3), through the gateway.

A graph is (edges, weights) over an ordered array of places. The family:

    contiguity      shared border, weighted by border length (pegasus_data, IBGE 2022 mesh)
    contiguity01    shared border, unweighted
    distanceH       population-centre pairs within pegasus_data's distance graph,
                    weighted exp(−d/H) (H in km, e.g. ``distance50``)
    knnK            K nearest population centres (symmetrised), unweighted
    careflow        where residents are treated: SIH admissions 2016–2019 by residence and the treating facility's
                    municipality; w_uv = F_uv/F_u + F_vu/F_v (each place's share of admissions treated in the other).
                    Its neighbourhoods are hospital catchments, along which supply and referral act

Which graph carries spatial structure best is a measurement (ARCHITECTURE §12,
phase 1), not a choice made here. Places absent from a graph (islands) are
isolated nodes; the ICAR gives them an iid precision.
"""

from __future__ import annotations

import numpy as np

from . import config, gateway, store, structures

DEFAULT = "contiguity"


def edges(places: np.ndarray, kind: str = DEFAULT) -> np.ndarray:
    """Edges (index pairs into ``places``, i < j) of a named graph."""
    return graph(places, kind)[0]


def graph(places: np.ndarray, kind: str = DEFAULT) -> tuple[np.ndarray, np.ndarray]:
    """(edges [m, 2] with i < j, weights [m]) of a named graph over ``places``."""
    key = {"what": "graph", "kind": kind, "places": int(len(places)), "first": int(places[0]),
           "last": int(places[-1]), "sum": int(np.sum(places)), "v": 3,
           **({} if kind.startswith("knn") else {"resource": config.resource_version("proximity.parquet")})}
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
            # border length, scale-free; a corner touch (length 0) keeps its edge at a 1 km floor.
            # (An unknown length would take the median; pegasus_data fixed its 32 nulls, 70b56fc.)
            known = np.isfinite(raw[keep])
            length = np.where(known, raw[keep], np.median(raw[keep][known]))
            w = np.maximum(length, 1.0) / np.median(length)
        elif kind == "contiguity01":
            w = np.ones(int(keep.sum()))
        else:
            w = np.exp(-raw[keep] / float(kind[len("distance"):]))
    elif kind == "careflow":
        out, w = _careflow(places)
    else:
        raise KeyError(f"unknown graph {kind!r}")
    store.put_arrays("graphs", key, {"edges": out, "weights": w})
    return out, w


CAREFLOW_YEARS = (2016, 2017, 2018, 2019)      # before COVID-19's reorganisation of admissions


def _careflow(places: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The care-flow graph over ``places`` (module docstring): edges between a residence and the municipality treating
    its residents, weighted by the symmetric sum of the two places' shares."""
    import duckdb

    from . import facility

    con = duckdb.connect()
    parts = []
    for y in CAREFLOW_YEARS:
        con.register("t", facility.facility_cube("SIH-RD", "hospitalisation", y))
        parts.append(con.execute("""SELECT u, CAST(fm AS INTEGER) AS v, sum(y) AS y FROM t
            WHERE fm <> '' AND TRY_CAST(fm AS INTEGER) IS NOT NULL GROUP BY ALL""").fetch_arrow_table())
    u = np.concatenate([p.column("u").to_numpy() for p in parts])
    v = np.concatenate([p.column("v").to_numpy() for p in parts])
    y = np.concatenate([p.column("y").to_numpy() for p in parts]).astype(float)
    index = {int(c): i for i, c in enumerate(places)}
    a = np.array([index.get(int(x), -1) for x in u])
    b = np.array([index.get(int(x), -1) for x in v])
    keep = (a >= 0) & (b >= 0)
    a, b, y = a[keep], b[keep], y[keep]
    n = len(places)
    total = np.bincount(a, weights=y, minlength=n)                       # each place's admissions
    off = a != b
    share = y[off] / np.maximum(total[a[off]], 1.0)                       # F_uv / F_u
    lo, hi = np.minimum(a[off], b[off]), np.maximum(a[off], b[off])
    key = lo.astype(np.int64) * n + hi
    uniq, inv = np.unique(key, return_inverse=True)
    w = np.bincount(inv, weights=share)
    return np.column_stack([uniq // n, uniq % n]).astype(np.int64), w
