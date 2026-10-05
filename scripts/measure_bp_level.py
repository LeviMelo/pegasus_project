"""The level of the prospective tier BP (ARCHITECTURE §6.1; OQ 6): which forecast of the history, which place course
and which dispersion centre BP's predictive, by rolling origins.

Usage: python scripts/measure_bp_level.py annual|dengue [origin ...]     (origins: the last training year)
Fits are those of `scripts/fit_blocks.py` (SIM.DO death, blocks IX X I XVIII; SINAN-DENG monthly) for each origin.
Writes data/logs/bp_level_<kind>.json: per (node, origin, variant) the PIT's KS overall and in the worst
macro-region, and the held-out log score (the NB mixture's, every cell with an expectation, test periods within
five years of the origin), with the PITs for pooling across origins (`scripts/bp_level_table.py`)."""

from __future__ import annotations

import json
import sys

import numpy as np
from scipy import stats

from pegasus_core import fields, gateway, laplace, monolith, surprise

SIM_NODES = {"IX": ["IX", "I20-I25", "I60-I69", "I64", "I10-I15"], "X": ["X"], "I": ["I"], "XVIII": ["XVIII"]}
GH_NODES, GH_WEIGHTS = np.polynomial.hermite_e.hermegauss(7)
GH_WEIGHTS = GH_WEIGHTS / GH_WEIGHTS.sum()
HORIZON = 5                                  # years
TAG = next((a[6:] for a in sys.argv if a.startswith("--tag=")), "")   # a suffix on the artefact's name
BLOCKS = next((a[9:].split(",") for a in sys.argv if a.startswith("--blocks=")), None)
LEAN = "--lean" in sys.argv                  # only the earlier BP and the adopted one (the rolling origins of the break)


def mixture(y, comps, seed=1):
    """(PIT, log score per cell) of a mixture of NBs, comps = [(weight, mu, phi_agg)]."""
    v = np.random.default_rng(seed).random(y.shape)
    low, pm = np.zeros(y.shape), np.zeros(y.shape)
    for w, mu, a in comps:
        d = stats.nbinom(a, a / (a + np.maximum(mu, 1e-300)))
        low += w * d.cdf(y - 1)
        pm += w * d.pmf(y)
    return np.clip(low + v * pm, 0, 1), np.log(np.maximum(pm, 1e-300))


class Case:
    """One block at one origin: the fit, the test data and what the variants share."""

    def __init__(self, dataset, event, block, t0, last, source):
        years = list(range(2010, t0 + 1))
        self.monthly = bool(source)
        self.m = monolith.Monolith.load(dataset, event, block, years, "contiguity", **source)
        self.td = monolith.assemble(dataset, event, block, list(range(t0 + 1, last + 1)), **source)
        self.tm = monolith.Monolith(self.td, self.m.graph, self.m.graph_kind)
        self.tm.phi = self.m.phi
        self.macro = gateway.regions(self.td.places, "ibge_macroregion")
        self.levels = surprise._dispersion_levels(self.td.places, self.macro)
        self.T = self.td.N.shape[1]
        self.t0 = t0
        self.keep = np.arange(self.T) < HORIZON * (12 if self.monthly else 1)
        self.x0 = self.m.effects()

    def forecast(self, history):
        return monolith.extrapolate_effects(self.m, self.tm, self.x0, history)


def node_ingredients(case, leaf_names):
    m, tm = case.m, case.tm
    lf = np.array([tm.data.leaves.index(c) for c in leaf_names if c in tm.data.leaves])
    li = np.array([m.data.leaves.index(c) for c in leaf_names if c in m.data.leaves])
    mui, mu2i = m.expected(li, spatial=True)
    yi = m.observed(li)
    ci = laplace.predictive_phi(mui, np.zeros_like(mui), mu2i, m.phi)
    extra = np.asarray(surprise.place_year_phi(yi, mui, ci, *case.levels))[:, None]
    return lf, mui, mu2i, yi, extra


def evaluate(case, lf, ing, y, variants):
    """variants: name -> [(weight, effects, log shift [U,T] or 0, extra log-variance or 0, use in-sample extra)]."""
    extra = ing[4]
    out = {}
    for name, spec in variants.items():
        comps, mean = [], 0.0
        for w, x, shift, addv, use_extra in spec:
            mu, mu2 = case.tm.expected(lf, spatial=True, x=x)
            mu, mu2 = mu * np.exp(shift), mu2 * np.exp(2 * shift)
            inv = 1.0 / laplace.predictive_phi(mu, np.zeros_like(mu), mu2, case.m.phi)
            if use_extra:
                inv = inv + 1.0 / extra
            inv = inv + np.expm1(addv)
            comps.append((w, mu, 1.0 / inv))
            mean = mean + w * mu
        u, lp = mixture(y, comps)
        inf = (mean > 1e-6) & case.keep[None, :]
        regs = [stats.kstest(u[(case.macro[:, None] == r) & inf], "uniform").statistic for r in np.unique(case.macro)
                if ((case.macro[:, None] == r) & inf).sum() >= 50]
        reg_ks = {str(r): float(stats.kstest(u[(case.macro[:, None] == r) & inf], "uniform").statistic)
                  for r in np.unique(case.macro) if ((case.macro[:, None] == r) & inf).sum() >= 50}
        out[name] = {"ks": float(stats.kstest(u[inf], "uniform").statistic), "worst": float(max(regs, default=0.0)),
                     "by_region": reg_ks,
                     "ll": float(lp[inf].sum()), "obs_exp": float(y[:, case.keep].sum() / mean[:, case.keep].sum()),
                     "cells": int(inf.sum()), "u": np.round(u[inf], 4).tolist()}
    return out


def gh_members(case, history, var):
    """Seven Gauss-Hermite members around a history forecast; var: [T] log-level variance of the national h."""
    base = case.forecast(history)
    sd = base["h_all"].new_tensor(np.sqrt(var))
    spec = []
    for z, w in zip(GH_NODES, GH_WEIGHTS, strict=True):
        x = {k: v.clone() for k, v in base.items()}
        x["h_all"] = x["h_all"] + float(z) * sd[None, :]
        spec.append((float(w), x, 0.0, 0.0, True))
    return spec


def annual_variants(case, lf, ing, y):
    """The grid: the history's forecast (linear, damped, flat) x the place course's damping, with the training
    fit's place-year component and the course coefficients' variance; and the block's-φ reference."""
    m = case.m
    _, mui, mu2i, yi, extra = ing
    fc = {h: case.forecast(h) for h in (("linear", "damped5") if LEAN else ("linear", "damped8", "damped5", "level"))}
    v = {"ref: linear, block phi": [(1.0, fc["linear"], 0.0, 0.0, False)]}
    n = len(m.data.years)
    s = (np.arange(n) - (n - 1) / 2) / max(np.arange(n).std(), 1e-9)
    s_new = (np.arange(n, n + case.T) - (n - 1) / 2) / max(np.arange(n).std(), 1e-9)
    ph = surprise.aggregate_phi(mui, mu2i, m.phi)
    _, b, _, _, _, _, pv = surprise.refit_place(yi, mui, ph, np.stack([np.ones(n), s], 1), variance=True,
                                                X_new=np.stack([np.ones(case.T), s_new], 1))
    for h, x in fc.items():
        for d in ((0.5,) if LEAN and h == "damped5" else () if LEAN else (0.0, 0.25, 0.5, 1.0)):
            shift = b[:, [0]] + d * b[:, [1]] * s_new[None, :]
            v[f"H={h} d={d}" + (" (extra only)" if d == 0.0 else "")] = [(1.0, x, shift if d else 0.0, pv if d else 0.0, True)]
    if LEAN:
        return {k: v[k] for k in ("ref: linear, block phi", "H=damped5 d=0.5")} if "H=damped5 d=0.5" in v else v
    # the national level: a random walk with the variance of the fitted history's yearly increments
    dh = np.diff((m.effects()["h_all"] + m.effects()["h_grp"].mean(0, keepdim=True))[0].detach().cpu().numpy())
    sigma = float(np.sqrt(np.mean(dh ** 2)))
    shift = b[:, [0]] + 0.5 * b[:, [1]] * s_new[None, :]
    v["H=linear d=0.5 + level spread"] = [(w, x, shift, pv, u_) for w, x, _, _, u_ in
                                         gh_members(case, "linear", sigma ** 2 * np.arange(1, case.T + 1))]
    return v


def dengue_variants(case, lf, ing, y):
    l36 = case.forecast("level36")
    v = {"M0 level36, block phi": [(1.0, l36, 0.0, 0.0, False)],
         "M1 level36 + in-sample extra": [(1.0, l36, 0.0, 0.0, True)]}
    for name in () if LEAN else ("median", "robust"):
        v[f"M1 {name} + extra"] = [(1.0, case.forecast(name), 0.0, 0.0, True)]
    J = case.m.data.N.shape[1] // 12
    for tag, js in (("M2 climatology of the fit's years", range(J)),) + (() if LEAN else (("M2 last 5 years", range(max(J - 5, 0), J)),)):
        js = list(js)
        spec = []
        for j in js:
            idx = np.array([12 * j + (t % 12) for t in range(case.T)])
            x = {k: x_.clone() for k, x_ in l36.items()}
            x["h_all"], x["h_grp"] = case.x0["h_all"][:, idx], case.x0["h_grp"][:, idx]
            spec.append((1.0 / len(js), x, 0.0, 0.0, True))
        v[tag] = spec
    return v


def run(kind, origins):
    res = {}
    if kind == "annual":
        cases = [("SIM.DO", "death", b, {}, annual_variants, nodes) for b, nodes in SIM_NODES.items()
                 if BLOCKS is None or b in BLOCKS]
    else:
        cases = [("SINAN-DENG", "probable_case", "*", {"grain": "month"}, dengue_variants, ["*"])]
    for dataset, event, block, source, variants, nodes in cases:
        reg = fields.Registry(dataset, event, "ICD10")
        for t0 in origins:
            try:
                case = Case(dataset, event, block, t0, 2023, source)
            except LookupError as e:
                print("skip", block, t0, e, flush=True)
                continue
            for node in nodes:
                leaf_names = case.m.data.leaves if node == "*" else reg.leaves(reg.field(node).node)
                ing = node_ingredients(case, leaf_names)
                y = case.tm.observed(ing[0])
                r = evaluate(case, ing[0], ing, y, variants(case, ing[0], ing, y))
                res[f"{node}@{t0}"] = r
                print(kind, node, t0, {k: (round(v["ks"], 3), round(v["worst"], 3), round(v["ll"])) for k, v in r.items()},
                      flush=True)
                with open(f"data/logs/bp_level_{kind}_{'_'.join(map(str, origins))}{TAG}.json", "w", encoding="utf-8") as fh:
                    json.dump(res, fh)
    return res


if __name__ == "__main__":
    run(sys.argv[1], [int(a) for a in sys.argv[2:] if a.isdigit()])
