"""Marks of an event type, fitted and read (ARCHITECTURE §4.4): length of stay, cost, death in hospital, ICU days of SIH.

A mark's location follows the monolith's structure (levels, profiles, history, geography; `monolith.MarkModel`,
`ShareModel`, `CountModel`) plus two things the structure cannot carry:

* **case-mix.** The diagnosis category is a leaf of the tree, so each category has its own level and place effects. The
  procedure is the other half of what a stay is (a surgery or a clinical stay): for a log-normal mark the reader subtracts
  from each log mark the shrunk mean departure of its (category, procedure group) stratum (`gateway._mark_frame`).
* **an institution effect.** The recording facility's departure from the fit, shrunk by empirical Bayes (`shrink_facilities`).
  It is estimated from the residuals of a first fit, taken out of the marks by the reader (`facility_effects`), and the
  location refitted: the places' effects are then the places', not their hospitals'. The effect is kept per facility, and
  `facility_jumps` reads a facility's own change in time, which is a lead of the facility (ADR-0014), never a place's.

A sole provider's effect and its place's are one: the place absorbs it, and the facility's shrunk effect comes out near zero.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import torch

from . import gateway, graphs, monolith

SHRINK_ITERATIONS = 200
MIN_FACILITY_YEARS = 3      # a facility's own change in time needs this many years with admissions
MIN_FACILITY_N = 30         # admissions of a facility-year below which the year carries nothing
HOME = Path("data/marks")


def spec(dataset: str, event: str, column: str) -> dict:
    """A declared measure's reader (`fields.measure_source`): nothing here names a column (S1)."""
    from . import fields

    return fields.measure_source(dataset, event, column)


def reader(dataset: str, event: str, column: str, facility_effects: str | None = None) -> dict:
    """The ``source`` of `monolith.assemble` / `surprise.Expectations` for a declared measure (bounds a tuple)."""
    out = dict(spec(dataset, event, column))
    if facility_effects:
        out["facility_effects"] = facility_effects
    return out


def nu_table(model: monolith.MarkModel, year_index: int) -> pa.Table:
    """The fitted location of a year's non-empty cells as the (code3, u, sex, band, nu) lookup of `gateway.mark_facility_moments`.
    For a share ν is the logit, for a count the log mean: residuals against it are on the model's own link scale only for the
    log-normal mark, which is the one with a facility effect."""
    d = model.data
    with torch.no_grad():
        nu = model.eta_nnz(model.effects()).cpu().numpy()
    m = d.t == year_index
    nB = d.N.shape[2] // 2
    return pa.table({"code3": pa.array(np.array(d.leaves, dtype=object)[d.e[m]].tolist(), pa.string()),
                     "u": pa.array(d.places[d.u[m]].astype(np.int32)), "sex": pa.array((d.g[m] // nB + 1).astype(np.int8)),
                     "band": pa.array((d.g[m] % nB).astype(np.int16)), "nu": pa.array(nu[m])})


def facility_residuals(model: monolith.MarkModel, name: str, years: list[int], facility_effects: str | None,
                       places: np.ndarray | None = None) -> pa.Table:
    """(facility, year, n, sr, sr2) over the years: the admissions' residuals from the fitted location, by recording facility."""
    sp = spec(model.data.dataset, model.data.event, name)
    edges = gateway.age_edges(model.data.population)
    parts = []
    for i, year in enumerate(years):
        parts.append(gateway.mark_facility_moments(
            model.data.dataset, model.data.event, int(year), sp["mark"], tuple(sp["bounds"]), nu_table(model, i), edges,
            classifier=sp.get("classifier"), casemix=sp.get("casemix"), facility_effects=facility_effects,
            missing=sp.get("missing", ()),
            places=None if places is None else pa.array(places, pa.int32())))
    return pa.concat_tables(parts)


@dataclass
class FacilityFit:
    facilities: np.ndarray
    n: np.ndarray
    mean: np.ndarray        # the facility's mean residual (log scale)
    delta: np.ndarray       # shrunk effect
    sd: np.ndarray          # posterior sd
    sigma2_f: float         # between-facility variance of the true effects
    sigma2_w: float         # within-facility-year variance of an admission's residual

    def table(self) -> pa.Table:
        return pa.table({"facility": pa.array(self.facilities.tolist(), pa.string()), "delta": pa.array(self.delta)})


def shrink_facilities(res: pa.Table) -> FacilityFit:
    """Empirical-Bayes effects of the recording facilities on the log mark. A facility's mean residual ȳ_f has variance
    σ²_w/n_f + σ²_f; σ²_w is the within facility-year variance of an admission's residual, σ²_f is found by the
    precision-weighted moment iteration (DerSimonian–Laird), and δ_f = (ȳ_f − μ) σ²_f / (σ²_f + σ²_w/n_f). The records
    naming no facility have no effect (δ = 0)."""
    df = res.to_pandas()
    df = df[df.facility != ""]
    within = float((df.sr2 - df.sr ** 2 / df.n).sum() / max((df.n - 1).clip(lower=0).sum(), 1))
    g = df.groupby("facility").agg(n=("n", "sum"), sr=("sr", "sum"))
    ybar = (g.sr / g.n).to_numpy()
    n = g.n.to_numpy().astype(float)
    v = within / n
    s2 = 0.01
    for _ in range(SHRINK_ITERATIONS):
        w = 1.0 / (v + s2)
        mu = float((w * ybar).sum() / w.sum())
        new = float(max((w ** 2 * ((ybar - mu) ** 2 - v)).sum() / (w ** 2).sum(), 1e-8))
        done = abs(np.log(new / s2)) < 1e-4
        s2 = new
        if done:
            break
    w = 1.0 / (v + s2)
    mu = float((w * ybar).sum() / w.sum())
    delta = (ybar - mu) * s2 / (s2 + v)
    return FacilityFit(g.index.to_numpy().astype(str), n, ybar, delta, np.sqrt(s2 * v / (s2 + v)), s2, within)


def facility_jumps(res: pa.Table, fit: FacilityFit) -> list[dict]:
    """Facilities whose own mean residual steps in time: for each facility with ≥ MIN_FACILITY_YEARS years of at least
    MIN_FACILITY_N admissions, the split of its years that maximises the standardised difference of the mean residual
    after against before. The variance of a year's mean is σ²_w/n plus a facility-year component τ² (moments over all
    facility-years), so a facility whose years merely scatter is not a step. Returned by |z| descending; ``effect`` is the
    ratio of the mark after to before (exp of the log difference)."""
    df = res.to_pandas()
    df = df[(df.facility != "") & (df.n >= MIN_FACILITY_N)].copy()
    df["m"] = df.sr / df.n
    fac_mean = df.groupby("facility").apply(lambda g: (g.m * g.n).sum() / g.n.sum(), include_groups=False)
    df["dev2"] = (df.m - df.facility.map(fac_mean)) ** 2 - fit.sigma2_w / df.n
    tau2 = float(max(np.average(df.dev2, weights=df.n), 0.0))
    out = []
    for fac, g in df.groupby("facility"):
        if len(g) < MIN_FACILITY_YEARS:
            continue
        g = g.sort_values("year")
        m, n = g.m.to_numpy(), g.n.to_numpy().astype(float)
        var = fit.sigma2_w / n + tau2
        w = 1.0 / var
        best = None
        for s in range(1, len(g)):
            a, b = slice(0, s), slice(s, None)
            ma, mb = np.average(m[a], weights=w[a]), np.average(m[b], weights=w[b])
            z = (mb - ma) / np.sqrt(1.0 / w[a].sum() + 1.0 / w[b].sum())
            if best is None or abs(z) > abs(best[0]):
                best = (float(z), s, float(mb - ma), float(ma), float(mb))
        z, s, diff, ma, mb = best
        years = g.year.to_numpy()
        out.append({"facility": str(fac), "z": z, "effect": float(np.exp(diff)), "before": [int(years[0]), int(years[s - 1])],
                    "after": [int(years[s]), int(years[-1])], "n": int(n.sum()), "n_before": int(n[:s].sum()),
                    "n_after": int(n[s:].sum()), "resid_before": ma, "resid_after": mb})
    out.sort(key=lambda r: -abs(r["z"]))
    return out


FAC_K = 3          # a mark lead is one institution's when at most this many facilities carry ...
FAC_SHARE = 0.7    # ... this share of its excess (the thresholds of the count triage, scans.explain), and without them it is gone


def triage_lead(model: monolith.MarkModel, name: str, years: list[int], places: np.ndarray, window: list[int],
                facility_effects: str | None, names: dict | None = None) -> dict:
    """Is a mark lead one institution's? (ADR-0014 for marks; ARCHITECTURE §7.7.) The lead's admissions (the residents of its
    places in its window) summed by recording facility: residual ``sr`` from the fitted location, admissions ``n``. The smallest
    set of at most FAC_K facilities carrying FAC_SHARE of the lead's excess (the sum of its residuals, in the lead's direction);
    ``facility`` is true when such a set exists and the lead's mean residual without it is within the minimum effect. The
    facility's municipality (of the record) is read from the facility cube, and named with ``names``."""
    from . import facility as fac_mod
    from .scans import lenses

    sp = spec(model.data.dataset, model.data.event, name)
    d = model.data
    edges = gateway.age_edges(d.population)
    use = [i for i, y in enumerate(years) if window[0] <= y <= window[1]]
    parts = [gateway.mark_facility_moments(d.dataset, d.event, int(years[i]), sp["mark"], tuple(sp["bounds"]), nu_table(model, i),
                                           edges, classifier=sp.get("classifier"), casemix=sp.get("casemix"),
                                           facility_effects=facility_effects, places=pa.array(places.astype(np.int32)),
                                           missing=sp.get("missing", ()))
             for i in use]
    df = pa.concat_tables(parts).to_pandas().groupby("facility", as_index=False)[["n", "sr"]].sum()
    n_all, sr_all = float(df.n.sum()), float(df.sr.sum())
    direction = 1.0 if sr_all >= 0 else -1.0
    out: dict = {"admissions": int(n_all), "mean_residual": sr_all / max(n_all, 1.0), "facilities": int((df.facility != "").sum()),
                 "facility": False}
    named = df[df.facility != ""].assign(c=lambda x: direction * x.sr).sort_values("c", ascending=False)
    gain = float(named.c.clip(lower=0).sum())
    if gain <= 0:
        return out
    for k in range(1, FAC_K + 1):
        top = named.head(k)
        if float(top.c.clip(lower=0).sum()) / gain >= FAC_SHARE:
            rest = (sr_all - float(top.sr.sum())) / max(n_all - float(top.n.sum()), 1.0)
            fm = ""
            cube = fac_mod.facility_cube(d.dataset, d.event, int(years[use[-1]]))
            hit = cube.filter(pc.equal(cube.column("facility"), str(top.facility.iloc[0]))).column("fm").to_pylist()
            if hit:
                code = max(set(hit), key=hit.count)
                m = (names or {}).get(code) or (names or {}).get(code[:6])
                fm = f"{m['name']}/{m['uf_sigla']}" if m else code
            out.update(top=[{"facility": str(f), "n_share": float(n / n_all), "mean_residual": float(sr / max(n, 1))}
                            for f, n, sr in zip(top.facility, top.n, top.sr, strict=True)],
                       share_of_excess=float(top.c.clip(lower=0).sum() / gain), rest_mean_residual=rest, top_municipality=fm,
                       facility=bool(abs(rest) < lenses.MARK_LOG))
            return out
    out["spread"] = True        # carried by more than FAC_K facilities: the lead belongs to the place
    return out


def fit_chapter(name: str, block: str, years: list[int], graph: str = "contiguity", device: str = "cpu", rounds: int = 2,
                dataset: str = "SIH-RD", event: str = "hospitalisation", outer: tuple[int, int] = (40, 12), log=print) -> dict:
    """One declared measure (``name``: its column, `fields.declared`) of one chapter: the location fitted, the facility effects estimated from its residuals and taken out
    (a log-normal mark with a facility: ``rounds`` = 2), the location refitted from the first fit (``outer``: the outer
    iterations allowed to the first fit and to the refit). Stores the final model
    (`Monolith.save`, under the reader's key, which carries the facility effects' id) and returns the record."""
    start = time.time()
    sp = spec(dataset, event, name)
    cls = monolith.model_class(sp)
    fx_id = None
    record: dict = {"mark": name, "block": block, "years": [years[0], years[-1]], "graph": graph}
    previous = None
    cumulative: dict[str, float] = {}
    for r in range(rounds if "casemix" in sp else 1):
        source = {k: (tuple(v) if k == "bounds" else v) for k, v in reader(dataset, event, name, fx_id).items()}
        data = monolith.assemble(dataset, event, block, years, **source)
        log(f"round {r}: assembled {len(data.y)} cells, {data.n.sum():.0f} events, unallocated {data.unallocated} ({time.time() - start:.0f}s)")
        model = cls(data, graphs.graph(data.places, graph), graph, device=device)
        if previous is not None:
            with torch.no_grad():
                for k, v in previous.params.items():
                    model.params[k].copy_(v)
            for k, c in previous.components.items():
                model.components[k].tau = c.tau
        model.fit(outer=outer[0] if previous is None else outer[1], log=lambda line, r=r: log(f"  r{r} {line}"))
        model.save()
        record[f"round{r}"] = {"fit": model.summary(), "facility_effects": fx_id, "seconds": round(time.time() - start)}
        if "casemix" in sp:
            res = facility_residuals(model, name, years, fx_id)
            fit = shrink_facilities(res)
            for f, d in zip(fit.facilities.tolist(), fit.delta.tolist(), strict=True):
                cumulative[f] = cumulative.get(f, 0.0) + d
            record[f"round{r}"]["facility"] = {"n_facilities": len(fit.facilities), "sigma_f": float(np.sqrt(fit.sigma2_f)),
                                               "sigma_w": float(np.sqrt(fit.sigma2_w)),
                                               "sd_delta": float(np.sqrt(np.average(fit.delta ** 2, weights=fit.n)))}
            log(f"  r{r} facilities {len(fit.facilities)}: σ_f {np.sqrt(fit.sigma2_f):.4f}, σ_w {np.sqrt(fit.sigma2_w):.4f}")
            if r + 1 < rounds:
                fx_id = gateway.store_facility_effects(pa.table({"facility": list(cumulative), "delta": list(cumulative.values())}))
                previous = model
            fit.delta = np.array([cumulative[f] for f in fit.facilities.tolist()])      # the effect taken out plus the one left
            record["effects"], record["residuals"] = fit, res
    record["final_reader_effects"] = fx_id
    return record


def save_record(record: dict, tag: str) -> Path:
    """The record's JSON beside its facility tables under data/marks/ (gitignored)."""
    HOME.mkdir(parents=True, exist_ok=True)
    fit = record.pop("effects", None)
    res = record.pop("residuals", None)
    path = HOME / f"{tag}.json"
    path.write_text(json.dumps(record, indent=1, default=float), encoding="utf-8")
    if fit is not None:
        import pyarrow.parquet as pq

        pq.write_table(pa.table({"facility": fit.facilities.tolist(), "n": fit.n, "mean": fit.mean, "delta": fit.delta, "sd": fit.sd}),
                       HOME / f"{tag}_facility.parquet")
        pq.write_table(res, HOME / f"{tag}_facility_year.parquet")
    return path


__all__ = ["spec", "reader", "fit_chapter", "triage_lead", "shrink_facilities", "facility_jumps", "facility_residuals", "save_record"]
