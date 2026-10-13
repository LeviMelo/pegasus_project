"""Completeness across systems by capture–recapture (ARCHITECTURE §5.2, §8.4; acceptance items 2 and 5).

Each system that records a topic is a list of its cases; the persons pegasus_data's links make (`gateway.persons`) say
which cases two lists share. With three lists the unseen cases are estimated by a log-linear model of the seven
observed patterns (Fienberg 1972; Hook and Regal 1995), the model chosen by AIC among those allowing any pairwise
dependence, with Chao's log-transformed interval; with two lists by Chapman's estimator, a lower bound when the lists
are positively dependent (a child admitted is likelier to be notified), which two lists cannot test.

A population and its lists are pegasus_data's declarations (`pegasus_data.captures`: one definition across systems,
a list's ``group`` making one person of a child's admissions, ``death`` its members who died of the condition): a
link's side filter is written for pairing, and SIM's took B58 deaths at every age into a congenital population
(2026-10-12). A death certificate lists only deaths, so the cases are listed by the systems of cases, the deaths by
every system.
"""

from __future__ import annotations

import collections
import itertools
from dataclasses import replace

import numpy as np
import pyarrow as pa

from . import config, gateway, store


def lists_of(datasets: list[str], codes: list[str]) -> dict | None:
    """The declared capture population of ``codes`` (`pegasus_data.captures`) whose lists are systems among
    ``datasets`` (pegasus_data codes): each list with its filter, grouping, death, the person role its links name, and
    whether its records are deaths; the declared links between two lists. None without a population of two lists."""
    import pegasus_data as pg
    from pegasus_data.linkage.engine import links_file
    from pegasus_data.linkage.roles import load_roles
    from pegasus_data.semantics.curation import read_yaml

    keys = {gateway.dataset_key(d) for d in datasets}
    raw = read_yaml(links_file()).get("links") or {}
    kinds = load_roles()
    for cap in pg.captures(codes):
        lists = {gateway.dataset_key(d): {**v, "dataset": d} for d, v in cap["lists"].items()
                 if gateway.dataset_key(d) in keys}
        if len(lists) < 2:
            continue
        links = []
        for name, spec in gateway.link_specs().items():
            person = list((raw.get(name) or {}).get("person") or [])
            a, b = gateway.dataset_key(spec.left.dataset), gateway.dataset_key(spec.right.dataset)
            if len(person) != 2 or a not in lists or b not in lists or a == b:
                continue
            for k, role in ((a, person[0]), (b, person[1])):
                lists[k].setdefault("role", role)
            # a link of the population's own records (a side naming its codes, or a list whose every record is the
            # population: SINAN's agravo), not one of every death or every admission
            if any(any(c in (sd.where or "") for c in cap["conditions"]) or not lists[gateway.dataset_key(sd.dataset)]["where"]
                   for sd in (spec.left, spec.right)):
                links.append(name)
        for v in lists.values():
            v["deaths"] = getattr(kinds.get(v["dataset"]), "record", "") == "death"
        lists = {k: v for k, v in lists.items() if v.get("role")}
        if len(lists) >= 2:
            return {"capture": cap["capture"], "description": cap["description"], "lists": lists, "links": links}
    return None


def records(lst: dict, year: int, deaths: bool) -> pa.Table | None:
    """One list's records of ``year`` (``_record_key`` and its grouping roles): the population's filter, and for its
    deaths the list's declared death (None when the list declares none: it cannot list them)."""
    from pegasus_data.linkage.engine import Side, _side_table
    from pegasus_data.linkage.roles import load_roles

    where = lst["where"]
    if deaths and not lst["deaths"]:
        if not lst.get("death"):
            return None
        where = f"({where}) AND ({lst['death']})" if where else lst["death"]
    side = replace(Side(lst["dataset"]), where=where)
    declared = load_roles()[lst["dataset"]].roles
    home = next((r for r in declared if r.endswith(".residence")), None)
    # the grouping roles and the residence (any one role else: the identity columns come with every side table)
    roles = list(dict.fromkeys([*lst["group"], *([home] if home else [])])) or [next(iter(declared))]
    # stored: a list's year is a national read cut to the area (DATASUS files a record by its place of care, not of
    # residence), 2.3 minutes a year in a slice's capture, read again on every run (2026-10-12)
    area = config.study_area()
    key = {"what": "capture_records", "dataset": lst["dataset"], "where": where, "roles": roles, "year": int(year),
           **({"area": sorted(area)} if area else {}), "data": config.data_version(), "code": config.code_key(records)}
    hit = store.get_table("gateway", key)
    if hit is not None:
        return hit
    table = _side_table(side, roles, period=year, geography="BR")
    if area is not None and home:
        # an area's study captures its residents (the national persons, cut to them)
        codes = [str(v or "")[:6] for v in table.column(home).to_pylist()]
        table = table.filter(pa.array(config.in_area(np.array([int(c) if c.isdigit() else -1 for c in codes]))))
    store.put_table("gateway", key, table)
    return table


def patterns(lists: dict[str, dict], year: int, deaths: bool, datasets: list[str], draw: int | None = None):
    """The persons of ``year`` on each list, as patterns (one bool per list, in ``lists``' order) and their counts.
    A record on no link is a person of its own; a list's records sharing its grouping are one person."""
    tables = {k: records(v, year, deaths) for k, v in lists.items()}
    tables = {k: t for k, t in tables.items() if t is not None}
    ent = gateway.persons(year, draw=draw, datasets=datasets)
    nodes = ent.nodes.to_pandas()
    person = {(gateway.dataset_key(d), r, rec): p for d, r, rec, p in
              zip(nodes.dataset, nodes.role, nodes.record, nodes.person, strict=True)}
    parent: dict = {}

    def find(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    members: dict[str, set] = {}
    for k, t in tables.items():
        lst = lists[k]
        ids = []
        recs = t.column("_record_key").to_pylist()
        groups = (list(zip(*[t.column(g).to_pylist() for g in lst["group"]], strict=True)) if lst["group"]
                  else [None] * len(recs))
        first: dict = {}
        for rec, g in zip(recs, groups, strict=True):
            pid = ("p", person[(k, lst["role"], rec)]) if (k, lst["role"], rec) in person else ("r", k, rec)
            if g is not None and all(v is not None for v in g):
                if g in first:                       # one person for a group's records (a child's admissions)
                    parent[find(pid)] = find(first[g])
                else:
                    first[g] = pid
            ids.append(pid)
        members[k] = set(ids)
    order = [k for k in lists if k in members]
    who: dict = collections.defaultdict(set)
    for k in order:
        for pid in members[k]:
            who[find(pid)].add(k)
    counts = collections.Counter(tuple(k in s for k in order) for s in who.values())
    return order, counts


def loglinear(counts: dict[tuple, int]) -> dict:
    """Three lists: the unseen cases by every hierarchical log-linear model with pairwise interactions (the three-way
    is not identifiable), the one of least AIC reported, each model's estimate kept. Chao's interval on the log of the
    unseen count."""
    import statsmodels.api as sm

    cells = [c for c in itertools.product([0, 1], repeat=3) if any(c)]
    y = np.array([counts.get(tuple(bool(v) for v in c), 0) for c in cells], dtype=float)
    n = y.sum()
    terms = [(0, 1), (0, 2), (1, 2)]
    models = []
    for k in range(4):
        for inter in itertools.combinations(terms, k):
            X = np.array([[1, *c, *[c[i] * c[j] for i, j in inter]] for c in cells], dtype=float)
            if X.shape[1] > len(cells):
                continue
            try:
                fit = sm.GLM(y, X, family=sm.families.Poisson()).fit()
            except Exception:  # noqa: BLE001 - a model the cells cannot fit is left out, said by its absence
                continue
            b0, se = float(fit.params[0]), float(fit.bse[0])
            if not np.isfinite(b0) or not np.isfinite(se):
                continue
            f0 = float(np.exp(b0))
            var = f0 ** 2 * se ** 2
            c = float(np.exp(1.96 * np.sqrt(np.log(1 + var / max(f0, 1e-9) ** 2))))
            models.append({"model": "independence" if not inter else " + ".join(
                "".join("ABC"[i] for i in t) for t in inter), "aic": float(fit.aic), "unseen": f0,
                "estimate": n + f0, "low": n + f0 / c, "high": n + f0 * c, "df": int(len(cells) - X.shape[1])})
    if not models:
        return {"estimate": None, "note": "no log-linear model fits the cells"}
    best = min(models, key=lambda m: m["aic"])
    return {**best, "observed": int(n), "models": models}


def chapman(n1: int, n2: int, m: int) -> dict:
    """Two lists: Chapman's estimator and its interval; a lower bound under positive dependence."""
    est = (n1 + 1) * (n2 + 1) / (m + 1) - 1
    var = (n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m) / ((m + 1) ** 2 * (m + 2))
    f0 = max(est - (n1 + n2 - m), 0.0)
    c = float(np.exp(1.96 * np.sqrt(np.log(1 + var / max(f0, 1e-9) ** 2)))) if f0 > 0 else 1.0
    n = n1 + n2 - m
    return {"model": "Chapman (two lists)", "estimate": est, "low": n + f0 / c, "high": n + f0 * c,
            "observed": n, "unseen": f0}


def capture(datasets: list[str], codes: list[str], years: list[int], usable_years, draw: int | None = None,
            log=print) -> list[dict]:
    """Every population the read systems list (the topic's cases; its deaths), pooled over the years whose run of
    every link between its lists is usable (``usable_years(links, year)``: the worst verdict, "viable" or "use with
    caution", else None): its patterns, and where every link is viable the estimate and each list's completeness
    against it. A link rated "use with caution" misses pairs, and each counts a person twice: the overlap is reported
    and no total (acceptance item 5: where links are not viable, the report says so; TOXC × SIH 2019-2021 gave 47,029
    cases against some 8.4 M births). ``datasets`` are pegasus_data codes."""
    found = lists_of(datasets, codes)
    if found is None:
        return []
    out = []
    for deaths in (False, True):
        lists = {k: v for k, v in found["lists"].items() if deaths or not v["deaths"]}
        if len(lists) < 2:
            continue
        # the links between this population's lists only (the cases' are TOXC-SIH's; a death certificate's link is
        # not theirs)
        keys = set(lists)
        own = [name for name in found["links"]
               if {gateway.dataset_key(gateway.link_specs()[name].left.dataset),
                   gateway.dataset_key(gateway.link_specs()[name].right.dataset)} <= keys]
        verdicts = {y: usable_years(own, y) for y in years}
        ys = [y for y in years if verdicts[y]]
        if not ys:
            out.append({"population": "deaths" if deaths else "cases", "lists": " × ".join(lists),
                        "note": "no year has a usable run of every link between the lists"})
            continue
        total: collections.Counter = collections.Counter()
        order = None
        for y in ys:
            order, c = patterns(lists, y, deaths, datasets, draw)
            total.update(c)
            log(f"capture {'deaths' if deaths else 'cases'} {y}: " + ", ".join(
                f"{''.join('1' if b else '0' for b in k)} {v}" for k, v in sorted(c.items())))
        if order is None or len(order) < 2:
            continue
        viable = all(verdicts[y] == "viable" for y in ys)
        if not viable:
            est = {"observed": sum(total.values())}
        elif len(order) == 3:
            est = loglinear(total)
        else:
            n1 = sum(v for k, v in total.items() if k[0])
            n2 = sum(v for k, v in total.items() if k[1])
            m = total.get((True, True), 0)
            est = chapman(n1, n2, m)
        sizes = {k: sum(v for p, v in total.items() if p[i]) for i, k in enumerate(order)}
        row = {"capture": found["capture"], "population": "deaths" if deaths else "cases", "lists": " × ".join(order),
               "years": f"{ys[0]}-{ys[-1]}" if len(ys) > 1 else str(ys[0]),
               "patterns": ", ".join(f"{''.join('1' if b else '0' for b in k)}:{v}" for k, v in sorted(total.items())),
               "observed": est.get("observed"), "estimate": est.get("estimate"), "low": est.get("low"),
               "high": est.get("high"), "model": est.get("model"),
               "completeness": ", ".join(f"{k} {sizes[k] / est['estimate']:.0%}" for k in order)
               if est.get("estimate") else None,
               "note": ("no total estimated: a link between the lists is rated 'use with caution', and the pairs it "
                        "misses would each count a person twice; the overlap is the persons the lists share"
                        if not viable else
                        "two lists: a lower bound if they are positively dependent, which they cannot test"
                        if len(order) == 2 else f"log-linear, least AIC of {len(est.get('models') or [])} models")}
        out.append(row)
    return out
