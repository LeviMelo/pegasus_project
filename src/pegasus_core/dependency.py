"""The dependency map (ARCHITECTURE §7.6) over the plan's systems: `dependency_map`, and its fields: place effects of every fitted field of the plan's systems and the context fields.

Every field is read from the production fits through declarations, nothing named here: a count field's place effect
b̂(u) is the shrunk Poisson intercept of ``surprise.refit_place`` over its tier-B0 expectation (the national rates by
age, sex and period, no place effects) summed over the window, with its posterior sd (the pair weight is 1/sd², §7.5);
a measure's or a share's is its precision-weighted mean residual, shrunk (`gaussian_effect`). Two systems share events
only where a declared link records the same event in both (`same_event`: a death in hospital is an admission and a
certificate); there a field's overlap with the other system is its measured linked share, and past `fields.MAX_OVERLAP`
the field's "not linked to" twin (its events less the expected linked ones) enters instead, sharing nothing (§8.5).
A context is a declared field over its declared denominator (``over``), as rank-based normal scores, with the
constant sd 0.05 the gate used (it cannot change ρ); the plan names which (``contexts``). Every field with events enters (ADR-0028: no field is left out for power).
"""

from __future__ import annotations

import numpy as np

from . import config, gateway, surprise
from .fields import MAX_OVERLAP
from .scans.maps import MapInputs

CONTEXT_SD = 0.05
YEARS = list(range(2015, 2020))


def place_effect(y: np.ndarray, mu: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """The shrunk Poisson place intercept over the expectation (B0 for E_b) and its posterior sd."""
    _, b, sd, tau = surprise.refit_place(y[:, None], mu[:, None], np.full((len(y), 1), np.inf), np.ones((1, 1)))
    return b[:, 0], sd[:, 0], float(tau[0])


def normal_scores(v: np.ndarray) -> np.ndarray:
    """A context on a common scale whatever its unit and skew: the rank-based normal scores Φ⁻¹(r / (n + 1)) of its
    finite values (van der Waerden), NaN kept. One transform for every context replaces a scaling chosen per field."""
    from scipy import special, stats

    out = np.full(len(v), np.nan)
    ok = np.isfinite(v)
    if ok.sum() > 1:
        out[ok] = special.ndtri(stats.rankdata(v[ok]) / (ok.sum() + 1))
    return out


#: the event kinds that count care used rather than a health state (pegasus_data `event_types` kind): a place's level of
#: use (access, referral, billing) enters every such field, and the map reads them net of it (`maps.factors`)
CARE_KINDS = ("hospitalisation", "authorisation")


def _window(su, years: list[int], places: np.ndarray) -> tuple[np.ndarray, ...]:
    """A surprise summed over the map's years on the map's places: y, μ [U], and the place weights Σw, Σw·(y − μ) [U]
    (a Gaussian location's precision and residual)."""
    cols = np.isin(np.asarray(su.years), years)
    index = {int(p): i for i, p in enumerate(su.places)}
    rows = np.array([index.get(int(u), -1) for u in places])
    have = rows >= 0
    out = [np.zeros(len(places)) for _ in range(4)]
    y, mu, w = (np.nan_to_num(np.asarray(a, dtype=float)[rows[have]][:, cols]) for a in (su.y, su.mu, su.w))
    out[0][have], out[1][have], out[2][have], out[3][have] = y.sum(1), mu.sum(1), w.sum(1), (w * (y - mu)).sum(1)
    return tuple(out)


def gaussian_effect(sw: np.ndarray, swr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A location field's place effect: each place's precision-weighted mean residual over the window, shrunk toward 0
    by the between-place variance τ² its places show beyond their sampling variance (a moment estimate); its sd."""
    ok = sw > 0
    r = np.where(ok, swr / np.where(ok, sw, 1.0), np.nan)
    v = np.where(ok, 1.0 / np.where(ok, sw, 1.0), np.nan)
    tau2 = max(float(np.nanvar(r) - np.nanmean(v)), 1e-12)
    return np.where(ok, r * tau2 / (tau2 + v), np.nan), np.where(ok, np.sqrt(tau2 * v / (tau2 + v)), np.nan)


def _readers(dataset: str, event: str) -> list[dict]:
    """The readers of a system's fitted fields on the production years: the counts ({}), and every measure, share or
    linked field fitted from its declarations (the reader its fit's key records; race-stratified fits are disparity
    readings, not map fields)."""
    from . import tools

    out: list[dict] = [{}]
    for k in tools.fitted(dataset, event, years=config.FIT_YEARS):
        key = k["key"]
        if key.get("source") in (None, "events") or key.get("race") or key.get("grain"):
            continue
        reader = {f: (tuple(v) if f == "bounds" else v) for f, v in key.items() if f in READER_KEYS}
        if reader not in out:
            out.append(reader)
    return out


#: the fields of a fit's key that make up its reader (`monolith.assemble`'s source)
READER_KEYS = ("source", "mark", "bounds", "missing", "classifier", "structure", "casemix", "indicator", "success",
               "link", "side", "anchor", "sign", "column", "place")


def _linked(dataset: str, event: str, link: str, side: str, years: list[int], places: np.ndarray,
            leaves: dict[str, set]) -> dict[str, np.ndarray]:
    """[U] the expected number of each field's events with a partner across ``link`` (Σ p_match, `gateway.linked_counts`
    on the event type's primary classifier), summed over the map's years, by field (``leaves``: its categories)."""
    et = gateway.event_type(dataset, event)
    primary = next((c["column"] for c in et.get("classifiers") or [] if c["role"] == "primary"), None)
    index = {int(u): i for i, u in enumerate(places)}
    out = {name: np.zeros(len(places)) for name in leaves}
    for year in years:
        t = gateway.linked_counts(dataset, event, year, link, side, classifier=primary).counts
        code3 = [str(c)[:3] for c in t.column("code").to_pylist()]
        for u, c, k in zip(t.column("u").to_pylist(), code3, t.column("k").to_pylist(), strict=True):
            i = index.get(int(u))
            if i is None or not k:
                continue
            for name, cats in leaves.items():
                if c in cats or "*" in cats:
                    out[name][i] += k
    return out


def build(systems: list[tuple[str, str, list[str]]], years: list[int] | None = None,
          places: np.ndarray | None = None, contexts: list | None = None) -> MapInputs:
    """The map's fields (module docstring), from declarations and the production fits: for every (dataset, event,
    blocks) in ``systems``, each chapter field of its count fits and every fitted measure, share or linked field, its
    place effect over ``years`` against tier B0 (`Session.surprise`: the national rates by age, sex and period, no
    place effects); the ``contexts`` (declared fields over their declared denominators, `gateway.context_value`, as
    normal scores); and, where a declared link records the same events in two systems
    (`same_event`), each field's measured overlap with the other system, with its "not linked to" field where that
    overlap passes `fields.MAX_OVERLAP` (its events less the expected linked ones: no event shared with the other)."""
    from . import tools

    years = years or YEARS
    if places is None:
        places = np.sort(gateway.population([years[-1]]).column("u").unique().to_numpy())
    names, groups, labels, B, SD = [], [], [], [], []
    cats: list[set] = []            # each field's categories (the overlap of two fields of one system)
    def add(name: str, group: str, label: str, b: np.ndarray, sd: np.ndarray, categories: set) -> None:
        names.append(name)
        groups.append(group)
        labels.append(label)
        B.append(b)
        SD.append(sd)
        cats.append(categories)

    counts: dict[str, tuple[np.ndarray, np.ndarray]] = {}       # a count field's (y, μ) for its linked variant
    kinds: dict[str, str] = {}
    for dataset, event, blocks in systems:
        kinds[dataset] = gateway.event_type(dataset, event).get("kind") or ""
        for reader in _readers(dataset, event):
            s = tools.Session(dataset, event, config.FIT_YEARS, source=reader)
            tag = "" if not reader else "|" + ":".join(str(reader.get(f)) for f in ("source", "mark", "indicator",
                                                                                   "link", "classifier") if reader.get(f))
            for block in (blocks if not reader else s._blocks()):
                if block not in s._blocks():
                    continue
                node = block
                su = s.surprise(node, "B0")
                y, mu, sw, swr = _window(su, years, places)
                field_cats = set(s.expectations.registry.leaves(node)) if node != "*" else {"*"}
                name = f"{dataset}:{node}{tag}"
                label = (s.expectations.field(node).label or node)[:60] + (f" ({tag[1:]})" if tag else "")
                if surprise.gaussian(su):
                    b, sd = gaussian_effect(sw, swr)
                    if np.isfinite(b).sum() >= 2:
                        add(name, dataset, label, b, sd, field_cats)   # its events: its categories'
                    continue
                if y.sum() <= 0:
                    continue
                b, sd, _ = place_effect(y, mu)
                add(name, dataset, label, b, sd, field_cats)
                counts[name] = (y, mu)
    # the same events in two systems: measured overlap, and the "not linked to" fields
    shared: dict[tuple[int, str], float] = {}           # (field index, other dataset) -> its events' linked share
    in_map = {ds.upper().replace(".", "-"): (ds, ev) for ds, ev, _ in systems}
    for spec_name, spec in gateway.link_specs().items():
        if not spec.same_event:
            continue
        for side, sd_, other in (("left", spec.left, spec.right), ("right", spec.right, spec.left)):
            mine, theirs = sd_.dataset.upper().replace(".", "-"), other.dataset.upper().replace(".", "-")
            if mine not in in_map or theirs not in in_map or (sd_.group and sd_.where):
                continue
            ds, ev = in_map[mine]
            idx = [i for i, n in enumerate(names) if groups[i] == ds and n in counts]
            linked = _linked(ds, ev, spec_name, side, years, places, {names[i]: cats[i] for i in idx})
            for i in idx:
                y, mu = counts[names[i]]
                k = np.minimum(linked[names[i]], y)
                share = float(k.sum() / max(y.sum(), 1e-12))
                shared[(i, in_map[theirs][0])] = share
                if share <= MAX_OVERLAP:
                    continue
                y2 = y - k
                mu2 = mu * (y2.sum() / max(y.sum(), 1e-12))     # the national share not linked, on B0's expectation
                b, sd, _ = place_effect(y2, mu2)
                add(f"{names[i]}|not linked to {in_map[theirs][0]}", ds,
                    labels[i] + f" (not linked to {in_map[theirs][0]})", b, sd, cats[i] | {f"unlinked:{in_map[theirs][0]}"})
    for entry in contexts or ():
        v, label = gateway.context_value(entry, years, places)
        z = normal_scores(v)
        name = entry["field"] if isinstance(entry, dict) else entry
        add(f"ctx:{name}", "context", label, z, np.where(np.isfinite(z), CONTEXT_SD, np.nan), set())
    F = len(names)
    overlap = np.zeros((F, F))
    for a in range(F):
        for b in range(a + 1, F):
            ga, gb = groups[a], groups[b]
            if "context" in (ga, gb):
                continue
            if ga == gb:            # one system: fields share events where their categories meet
                base_a, base_b = names[a].split("|not linked")[0], names[b].split("|not linked")[0]
                ov = 1.0 if (base_a == base_b or (cats[a] & cats[b]) - {""}) else 0.0
            else:
                base = {n: names.index(n.split("|not linked")[0]) for n in (names[a], names[b])}
                ia, ib = base[names[a]], base[names[b]]
                unl_a = f"unlinked:{gb}" in cats[a]
                unl_b = f"unlinked:{ga}" in cats[b]
                sa, sb = shared.get((ia, gb)), shared.get((ib, ga))
                if unl_a or unl_b or (sa is None and sb is None):
                    ov = 0.0        # no declared same-event link, or one side's linked events removed
                else:
                    ov = max(v for v in (sa, sb) if v is not None)
            overlap[a, b] = overlap[b, a] = ov
    return MapInputs(places, names, groups, labels, np.stack(B, 1), np.stack(SD, 1), overlap,
                     {"years": years, "systems": [list(x[:2]) for x in systems], "care": [d for d, k in kinds.items()
                                                                                 if k in CARE_KINDS],
                      "linked_share": {f"{names[i]}->{d}": v for (i, d), v
                                                                                     in shared.items()},
                      "missing_context": {n: int(np.isnan(B[i]).sum()) for i, n in enumerate(names)
                                          if groups[i] == "context"}})


def dependency_map(systems: list[tuple[str, str, list[str]]], contexts: list | tuple = (),
                   years: list[int] | None = None, ledger=None) -> dict:
    """A dependency map (§7.6) of every fitted field of ``systems`` ((dataset, event, blocks), a plan's) and the
    ``contexts`` over ``years`` (`build`: chapters, measures, shares; "not linked to" twins where a declared link records
    the same events): the inputs from the store (built on first use), the marginal and conditional layers controlled
    over the whole map, the admitted pairs as relation leads. Returns the summary, the edges, the inputs and the Moran
    bases a false-edge measurement reads (`harness.dependency_negatives`)."""
    from . import control, leads, store, tools
    from .scans import maps, pairs

    years = years or YEARS
    contexts = list(contexts or ())
    key = {"what": "map_inputs", "years": years, "systems": [list(s[:2]) for s in systems], "contexts": contexts,
           "code": config.code_key(build)}
    inp = maps.MapInputs.load(key)
    if inp is None:
        inp = build(systems, years, contexts=contexts)
        inp.save(key)
    # §11.4: a chapter whose count expectation failed calibration at B1 (the first tier with geography, whose field
    # dispersion the place effects' Poisson sd leans on) never enters a pair scan; the fits are the production ones
    calibration = {}
    for dataset, event, _ in systems:
        session = tools.Session(dataset, event, config.FIT_YEARS)
        for name in inp.names:
            if name.startswith(dataset + ":") and "|" not in name:      # a count field (its twin shares its fit)
                calibration[name] = session.calibration_of(name.split(":", 1)[1], "B1")
    inp = maps.exclude_miscalibrated(inp, calibration, "B1")
    basis, gen = pairs.MoranBasis(inp.places), pairs.MoranBasis(inp.places, "knn8")
    dm = maps.dependency_map(inp, basis, ledger or control.Ledger(), tag="-".join(map(str, (years[0], years[-1]))))
    out: dict = {"fields": len(inp.names), "tested": dm.tested, "excluded_by_overlap": dm.excluded,
                 "admitted": dm.controlled, "seconds": dm.seconds, "linked_share": inp.meta.get("linked_share", {}),
                 "excluded_calibration": inp.meta.get("excluded_calibration", {})}
    store.put_table("maps", {"what": "map_edges", "years": years}, dm.edges, {"summary": out})
    # the admitted pairs are relation leads (§9.1), read and triaged with every other lead
    e = dm.edges.to_pylist()
    adm = [r for r in e if r.get("admitted")]
    if adm:
        qv = dict(zip((id(r) for r in e), control.adjusted(np.array([r["p"] for r in e])), strict=True))
        leads.Register().add([leads.Lead(
            kind="relation", estimand="E_b", tier="B1", fields=[r["x"], r["y"]],
            locus={"band": "between places", "lag": 0, "years": [years[0], years[-1]]}, effect=float(r["rho"]),
            scale="rho", interval=None, p=float(r["p"]), q=float(qv[id(r)]), family=f"map|{r['family']}",
            null="Moran spectral randomisation", calibrated=True,
            method={"dependency_map": {"evidence": "map negatives (harness.dependency_negatives)"}},
            provenance={"n_eff": r.get("n_eff")}) for r in adm])
    return {"summary": out, "edges": dm.edges, "inputs": inp, "basis": basis, "generator": gen}
