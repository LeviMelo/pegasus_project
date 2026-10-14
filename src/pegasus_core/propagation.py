"""Propagation (ARCHITECTURE §7.2, component 7; stage C): departures ordered in space through time.

Propagation is an *arrangement* of the place departures, not a term of the expectation (§7.1). It reads the cells that
the cell departure model (`departures.cell_excess`, BH at q over every cell) finds above the expectation, and asks
whether the periods at which places depart are ordered in space.

    onset_i      the first period at which place i departs (the departure model's first significant cell).
                 A place already departing in the first period has no observed onset (left-censored) and is left out of
                 the ordering; a place that never departs is right-censored and is counted.
    the wave     onset_i = t0 + D(o, i) / c + noise: a source place o among the departing places, a speed c, D the
                 great-circle distance between population centres (km) or the hops of the place graph. The source
                 maximises the Spearman correlation between the onsets and the distances from it (Cliff and Haggett 1988,
                 "Atlas of disease distributions", on the spatial diffusion of epidemics: onset against distance from the
                 source); the speed is the Theil-Sen slope of onset on distance, which is not moved by the isolated early
                 imports (a case notified a thousand km ahead of its epidemic) that least squares would follow; its
                 interval is a bootstrap over places. The direction of travel is the gradient of the planar trend surface
                 of the onsets (Haggett, Cliff and Frey 1977, "Locational analysis in human geography"; the trend-surface
                 analysis of epidemic onset), a bearing in degrees from north.
    the test     the maximum over sources of that Spearman correlation, against surrogates that keep the onsets'
                 marginal distribution *and their spatial autocorrelation*: Moran spectral randomisation (Wagner and Dray
                 2015, Methods Ecol Evol 6:1169), the sign of each coefficient of the onsets on the eigenvectors of the
                 departing places' neighbour-graph Laplacian flipped at random, so that the surrogate field is as smooth as
                 the observed one (Dirichlet energy exactly kept) but has no preferred origin. A plain permutation of the
                 onsets over places, which keeps no autocorrelation, is the other null (``null="permutation"``): it
                 over-states the evidence of any clustered onset (a state departing at once). The maximum over sources
                 is recomputed on every surrogate, so the search for the source is part of the test.
    waves        a field can enter by several doors (chikungunya in 2014: Oiapoque and Feira de Santana). After a wave is
                 found, the places it explains (|residual| within two robust sd) are set aside and the rest is tested for
                 a further wave, in order and each at q: a fixed-sequence procedure, which stops at the first wave that is
                 not significant and so keeps the family-wise error at q.
    emergence    a departing place *emerges* when the field was absent from it before its onset: no event observed in the
                 earlier periods and zero the likeliest outcome under the expectation there (the probability of no event
                 in them at least one half). Reported as a share of each wave's places.

The expectation is the caller's tier (`tools.Session.scan(..., tier=)`). For a field with a history, B1 (or BP, fitted on
the years before the event) is the reference; for a field that is new in the data, whose place effects the window itself
would teach, B0 ("how the place differs from Brazil given its population") is the one that does not absorb the front
(evaluation 2026-10-10-propagation).
"""

from __future__ import annotations

import hashlib

import numpy as np
from scipy import stats

from . import config, control, departures, gateway, graphs, mc, surprise
from .scans import lenses

MIN_PLACES = 10          # a wave needs this many departing places to be tested (debt: ARCHITECTURE §12)
SURROGATES = 999         # the null's size: p is never below 1/1000 (no Monte Carlo floor is claimed beyond it)
MAX_WAVES = 5
EARTH_KM = 6371.0088


# ---------------------------------------------------------------------- geometry


def planar(points: np.ndarray) -> np.ndarray:
    """(east, north) in km of (lon, lat) degrees, on the equirectangular plane at the points' mean latitude."""
    lon, lat = np.radians(points[:, 0]), np.radians(points[:, 1])
    return EARTH_KM * np.column_stack([(lon - lon.mean()) * np.cos(lat.mean()), lat - lat.mean()])


def great_circle(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distances (km) between each (lon, lat) of ``a`` and each of ``b``: [len(a), len(b)]."""
    la, lb = np.radians(a[:, 1])[:, None], np.radians(b[:, 1])[None, :]
    dlon = np.radians(a[:, 0])[:, None] - np.radians(b[:, 0])[None, :]
    h = np.sin((la - lb) / 2) ** 2 + np.cos(la) * np.cos(lb) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


def hops(places: np.ndarray, members: np.ndarray, graph: str) -> np.ndarray:
    """Hops on the place graph from each ``members[c]`` (indices into ``places``) to every member: [m, m]; inf where
    the graph does not connect them (islands)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import shortest_path

    e, _ = graphs.graph(places, graph)
    n = len(places)
    adj = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    d = shortest_path(adj, directed=False, unweighted=True, indices=members)
    return d[:, members]


# ---------------------------------------------------------------------- onsets


def onsets(s: surprise.Surprise, ledger: control.Ledger, q: float = 0.05) -> np.ndarray:
    """The first period index at which each place departs upward (the cell departure model at the municipality, BH at q
    over the field's cells); -1 where it never does. [U]"""
    found = departures.cell_excess(s, ledger, q=q, scales=None)
    period = {int(p): i for i, p in enumerate(s.years)}
    row = {int(p): i for i, p in enumerate(s.places)}
    out = np.full(len(s.places), -1, dtype=int)
    for f in found:
        t = period[int(f.locus["years"][0])]
        for p in f.locus["places"]:
            i = row[int(p)]
            out[i] = t if out[i] < 0 else min(out[i], t)
    return out


def absent_before(s: surprise.Surprise, onset: np.ndarray) -> np.ndarray:
    """Whether the field was absent from each departing place before its onset: nothing observed in the earlier periods
    and no event the likeliest outcome there, P(no event) = Π (1 + φμ)^(-1/φ) over them at least one half. False where
    there is no onset or no earlier period. [U]"""
    U, T = s.y.shape
    before = np.arange(T)[None, :] < onset[:, None]
    mu = np.where(np.isfinite(s.mu), s.mu, 0.0)
    phi = np.asarray(s.phi, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        log0 = np.where(np.isfinite(phi) & (phi > 0), -np.log1p(phi * mu) / phi, -mu)
    seen = np.where(before, np.nan_to_num(s.y), 0.0).sum(1)
    return (onset > 0) & (seen == 0) & (np.where(before, log0, 0.0).sum(1) >= np.log(0.5))


# ---------------------------------------------------------------------- the wave


def correlation_length(t: np.ndarray, dist: np.ndarray) -> float:
    """The distance at which the spatial autocorrelation of the onsets (Moran's I of their ranks, by the doubling
    bins of `radii`) has fallen to 1/e of its value in the first bin: the e-folding length of the onsets' correlogram
    (the whole diameter where it never does)."""
    z = stats.rankdata(t) - (len(t) + 1) / 2
    z = z / z.std()
    ladder = radii(dist)
    off = ~np.eye(len(t), dtype=bool)
    lo, first = 0.0, None
    for r in ladder:
        pair = off & (dist > lo) & (dist <= r)
        if pair.any():
            c = float((z[:, None] * z[None, :])[pair].mean())
            first = c if first is None else first
            if first > 0 and c < first / np.e:
                return float(r)
        lo = r
    return float(ladder[-1])


class _Surrogates:
    """Surrogates of an onset vector ``t`` over ``n`` places with distances ``dist``, drawn in blocks.
    ``null="spectral"``: Moran spectral randomisation (module docstring) in the eigenbasis of the Gaussian kernel
    exp(-(d / L)^2), L the onsets' own correlation length (`correlation_length`): the surrogates are as smooth as the
    onsets are, at the scale they are; ``"permutation"``: a permutation."""

    def __init__(self, t: np.ndarray, dist: np.ndarray, null: str, rng: np.random.Generator):
        self.n, self.null, self.rng = len(t), null, rng
        self.basis, self.length = None, None
        if null == "spectral":
            self.length = correlation_length(t, dist)
            _, self.basis = np.linalg.eigh(np.exp(-((dist / self.length) ** 2)))

    def draw(self, t: np.ndarray, count: int) -> np.ndarray:
        """``count`` surrogate onset vectors as columns [n, count]: the observed values reassigned by the surrogate
        field's ranks, so the marginal distribution (and its ties) is kept."""
        if self.null == "permutation":
            return np.column_stack([t[self.rng.permutation(self.n)] for _ in range(count)])
        z = stats.rankdata(t) - (self.n + 1) / 2
        coef = self.basis.T @ z
        field = self.basis @ (coef[:, None] * self.rng.choice([-1.0, 1.0], size=(self.n, count)))
        order = np.argsort(field, axis=0)
        srt = np.sort(t)
        out = np.empty_like(field)
        np.put_along_axis(out, order, srt[:, None].repeat(count, 1), axis=0)
        return out


def radii(dist: np.ndarray) -> np.ndarray:
    """The ladder of disc radii around a source: doubling from twice the median nearest-neighbour distance to the
    diameter, plus the whole set. Relative to the data, so the unit (km or hops) does not matter."""
    d = np.where(dist > 0, dist, np.inf)
    nn = float(np.median(d.min(1)[np.isfinite(d.min(1))])) if np.isfinite(d.min(1)).any() else 1.0
    top = float(dist[np.isfinite(dist)].max())
    r = nn * 2.0 ** np.arange(1, 40)
    return np.append(r[r < top], top)


class _Discs:
    """What the disc scan holds constant over a wave's places, on the device: the distances, the distance ranks, the
    sources that reach every place."""

    def __init__(self, dist: np.ndarray, rd: np.ndarray, ladder: np.ndarray, ok: np.ndarray):
        import torch

        self.dev = torch.device(config.array_device())
        self.dist = torch.as_tensor(dist, dtype=torch.float64, device=self.dev)
        self.rd = torch.as_tensor(rd, dtype=torch.float32, device=self.dev)
        self.ok = torch.as_tensor(ok, device=self.dev)
        self.ladder = [float(r) for r in ladder]


def _disc_scan(rt: np.ndarray, discs: _Discs) -> tuple:
    """For each column of ``rt`` [n, B] (onset ranks), the largest over sources o and radii R of the Fisher z of the
    rank correlation, among the places within R of o, between onset and distance from o, times sqrt(n_disc - 3) (so the
    scales compare: the scan statistic of Kulldorff 1997 for a correlation). Also returns the argmax (source, radius
    index) of the first column. Discs of fewer than MIN_PLACES places are not scored. On the device, in float32."""
    import torch

    rt = torch.as_tensor(rt, dtype=torch.float32, device=discs.dev)
    B = rt.shape[1]
    best = torch.full((B,), -float("inf"), device=discs.dev)
    arg = (-1, -1)
    rt2 = rt ** 2
    for j, r in enumerate(discs.ladder):
        m = ((discs.dist <= r) & discs.ok[:, None]).to(torch.float32)
        k = m.sum(1)
        keep = k >= MIN_PLACES
        if not bool(keep.any()):
            continue
        md = m * discs.rd
        sd, sdd = md.sum(1), (md * discs.rd).sum(1)
        st, stt, sdt = m @ rt, m @ rt2, md @ rt
        num = sdt - (sd / k)[:, None] * st
        den = torch.sqrt(torch.clamp(sdd - sd ** 2 / k, min=0)[:, None] * torch.clamp(stt - st ** 2 / k[:, None], min=0))
        corr = torch.where(den > 0, num / den, torch.zeros_like(num))
        z = torch.atanh(corr.clamp(-0.999999, 0.999999)) * torch.clamp(k - 3, min=0).sqrt()[:, None]
        z[~keep] = -float("inf")
        top = z.max(0).values
        if B and top[0] > best[0]:
            arg = (int(z[:, 0].argmax()), j)
        best = torch.maximum(best, top)
    return best.double().cpu().numpy(), arg


def fit_wave(t: np.ndarray, dist: np.ndarray, null: str, seed_parts: tuple, surrogates: int = SURROGATES,
             q: float | None = None) -> dict:
    """One wave over the places whose onsets are ``t`` [n] and whose distances to each other are ``dist`` [n, n]: the
    source and the disc of places around it (radius from `radii`) whose onsets rise most steadily with distance from it
    (`_disc_scan`), the test against ``surrogates`` surrogates of the onsets (the search over sources and radii is
    inside every surrogate's maximum), and the speed by Theil-Sen over the disc. Sources unreachable from some place
    (hops across islands) are not scored. With a level ``q`` the test is sequential (`mc`): it stops as soon as
    floor(q (N + 1)) surrogates reach the observed statistic, because the p-value (b + 1)/(N + 1) of the whole set
    exceeds q whatever the rest give, and returns that bound (the decision is exact, which is all `waves` reads)."""
    n = len(t)
    ok = np.isfinite(dist).all(1)
    if not ok.any() or np.ptp(t) == 0:
        return {"p": 1.0}
    d = np.where(np.isfinite(dist), dist, 0.0)
    rd = stats.rankdata(d, axis=1).astype(np.float32) / n
    ladder = radii(d)
    discs = _Discs(d, rd, ladder, ok)
    rt = (stats.rankdata(t) / n).astype(np.float32)[:, None]
    obs, (src, rad) = _disc_scan(rt, discs)
    if src < 0:
        return {"p": 1.0}
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(repr(seed_parts).encode()).digest()[:4], "little"))
    sur = _Surrogates(t, d, null, rng)

    def draw(start: int, count: int) -> np.ndarray:
        block = sur.draw(t, count)
        return _disc_scan((stats.rankdata(block, axis=0) / n).astype(np.float32), discs)[0]

    h = surrogates + 2 if q is None else max(1, int(np.floor(q * (surrogates + 1) + 1e-9)))
    seq = mc.sequential_p(draw, float(obs[0]), h, surrogates, 100)
    if seq.settled:
        return {"p": (h + 1) / (surrogates + 1), "stopped": seq.n}
    p = seq.p
    disc = np.flatnonzero(d[src] <= ladder[rad])
    slope, intercept, lo, hi = stats.theilslopes(t[disc], d[src][disc])
    return {"p": p, "source": src, "radius": float(ladder[rad]), "length": sur.length, "z": float(obs[0]), "disc": disc,
            "rho": float(stats.spearmanr(t[disc], d[src][disc])[0]), "slope": float(slope), "t0": float(intercept),
            "slope_ci": [float(lo), float(hi)], "n": int(len(disc))}


def bearing(t: np.ndarray, xy: np.ndarray) -> tuple[float, float]:
    """The direction of travel and the planar trend's speed: the gradient (months per km) of the least-squares plane
    of the onsets over (east, north), as a bearing in degrees from north and its speed in km per month."""
    x = np.column_stack([np.ones(len(t)), xy])
    beta = np.linalg.lstsq(x, t, rcond=None)[0]
    g = beta[1:]
    norm = float(np.hypot(*g))
    return float(np.degrees(np.arctan2(g[0], g[1])) % 360.0), (1.0 / norm if norm > 0 else float("inf"))


def waves(t: np.ndarray, dist: np.ndarray, q: float, null: str, seed_parts: tuple,
          surrogates: int = SURROGATES, max_waves: int = MAX_WAVES) -> list[dict]:
    """The successive waves over the places (indices into ``t``): each fitted on the places the earlier ones left, tested
    at q, the sequence stopped at the first that is not significant. A wave's ``members`` (indices into ``t``) are the
    places of its disc within two robust sd of its line; the others stay for the next wave."""
    left = np.arange(len(t))
    out: list[dict] = []
    while len(left) >= MIN_PLACES and len(out) < max_waves:
        sub = dist[np.ix_(left, left)]
        w = fit_wave(t[left], sub, null, (*seed_parts, len(out)), surrogates, q)
        if w["p"] > q or w.get("slope", 0.0) <= 0:
            break
        disc = w.pop("disc")
        res = t[left][disc] - (w["t0"] + w["slope"] * sub[w["source"]][disc])
        sd = 1.4826 * np.median(np.abs(res - np.median(res)))
        inside = np.abs(res) <= 2 * max(sd, 0.5)
        w["members"] = left[disc[inside]]
        w["source"] = int(left[w["source"]])
        w["sd"] = float(sd)
        out.append(w)
        left = np.setdiff1d(left, w["members"])
    return out


# ---------------------------------------------------------------------- the lens


def window_of(s: surprise.Surprise, window: tuple[int, int]) -> surprise.Surprise:
    """``s`` restricted to the periods from ``window[0]`` to ``window[1]`` (period codes: years, or YYYYMM at the monthly
    grain). The expectation is the one fitted on all the periods; only the departures sought are limited, so the
    periods before the window serve as the baseline and a place already departing at its first period is left-censored."""
    import dataclasses

    lo, hi = int(window[0]), int(window[1])
    if np.asarray(s.years).max() > 9999 and hi <= 9999:
        lo, hi = lo * 100 + 1, hi * 100 + 12          # a window of years on a monthly field: those years' months
    keep = (s.years >= lo) & (s.years <= hi)
    if not keep.any():
        raise ValueError(f"window {window} holds none of the field's periods {s.years[0]}-{s.years[-1]}")
    cut = {k: getattr(s, k)[:, keep] for k in ("y", "mu", "phi", "u", "z", "w", "flags")}
    return dataclasses.replace(s, years=s.years[keep], **cut)


def propagation(s: surprise.Surprise, ledger: control.Ledger, graph: str = "contiguity", q: float = 0.05,
                metric: str = "km", null: str = "spectral", bootstrap: int = 200,
                window: tuple[int, int] | None = None) -> list[lenses.Finding]:
    """The waves of a field's departures (module docstring) as findings: ``locus`` the wave's places and the periods of
    its first and last onset, ``effect`` its speed (km per month, or hops per month with ``metric="hops"``), ``p`` the
    spectral (or permutation) test of its source-and-ordering statistic, ``window`` the periods looked in (None: all; the expectation, and the history that decides whether the field was absent
    before, are those of all of them), ``stats`` its source, intercept, speed
    interval, bearing, the trend surface's speed, rho, the share of its places the field emerged in, and the places'
    onsets. Reads counts."""
    if s.extras.get("kind") == "mark":
        return []
    full, offset = s, 0
    if window is not None:
        s = window_of(s, window)
        offset = int(np.flatnonzero(np.isin(full.years, s.years))[0])
    family = f"propagation|{s.tier}|{s.field.block}"
    test = ledger.register(control.Hypothesis(family, "scan", {"lens": "propagation", "field": s.field.id,
                                                               "tier": s.tier, "metric": metric, "null": null,
                                                               "surrogates": SURROGATES}))
    onset = onsets(s, ledger, q)
    departing = onset >= 0
    first = departing & (onset == 0)               # departing from the start: no observed onset
    use = np.flatnonzero(departing & ~first)
    detail = {"periods": len(s.years), "departing": int(departing.sum()), "left_censored": int(first.sum()),
              "ordered": int(len(use)), "never": int((~departing).sum())}
    if len(use) < MIN_PLACES:
        ledger.complete(test, 1.0, None, {**detail, "waves": 0, "reason": f"fewer than {MIN_PLACES} places with an onset"})
        return []
    places = s.places[use]
    xy = planar(gateway.municipality_points(places))
    dist = great_circle(gateway.municipality_points(places), gateway.municipality_points(places)) if metric == "km" \
        else hops(s.places, use, graph)
    t = onset[use].astype(float)
    absent = absent_before(full, np.where(onset >= 0, onset + offset, -1))
    found = waves(t, dist, q, null, (s.field.id, s.tier, metric, null), SURROGATES)
    out = []
    rng = np.random.default_rng(0)
    for k, w in enumerate(found):
        m = w["members"]
        brg, trend_speed = bearing(t[m], xy[m])
        boots = []
        if bootstrap:
            for _ in range(bootstrap):
                b = rng.integers(0, len(m), len(m))
                sl = stats.theilslopes(t[m][b], dist[w["source"]][m][b])[0]
                bg = bearing(t[m][b], xy[m][b])[0]
                boots.append((sl, bg))
        boots = np.array(boots) if boots else np.empty((0, 2))
        speed = 1.0 / w["slope"]
        speed_ci = sorted([1.0 / w["slope_ci"][1] if w["slope_ci"][1] > 0 else float("inf"),
                           1.0 / w["slope_ci"][0] if w["slope_ci"][0] > 0 else float("inf")])
        circ = float(np.degrees(np.sqrt(-2 * np.log(max(np.hypot(np.cos(np.radians(boots[:, 1])).mean(),
                                                                  np.sin(np.radians(boots[:, 1])).mean()), 1e-12)))))\
            if len(boots) else None
        src_code = int(places[w["source"]])
        periods = s.years[onset[use][m].astype(int)]
        order = np.argsort(t[m], kind="stable")
        emerged = absent[use][m]
        out.append(lenses.Finding(
            "propagation", s.field.id, s.tier,
            {"places": [int(p) for p in places[m]], "years": [int(periods.min()), int(periods.max())],
             "source": src_code, "bearing": round(brg, 1)},
            float(speed), float(w["p"]),
            {"wave": k, "source": src_code, "source_onset": int(s.years[int(onset[use][w["source"]])]),
             "t0_period": float(w["t0"]), "radius": round(w["radius"], 1), "z": round(w["z"], 2), "rho": round(w["rho"], 3), "places": int(len(m)), "metric": metric,
             "speed_ci": [round(x, 1) for x in speed_ci], "bearing": round(brg, 1),
             "bearing_circular_sd": None if circ is None else round(circ, 1), "trend_speed": round(trend_speed, 1),
             "residual_sd": round(w["sd"], 2), "emerged": int(emerged.sum()), "emerged_share": round(float(emerged.mean()), 3),
             "null": null, "calibrated": bool(s.calibration.get("calibrated", True)),
             "earliest": [{"place": int(places[m][i]), "period": int(periods[i])} for i in order[:10]],
             "onsets": {int(places[m][i]): int(periods[i]) for i in range(len(m))},
             "shape": {"shape": "propagation"}, **detail}))
    ledger.complete(test, min([f.p for f in out], default=1.0), out[0].effect if out else None,
                    {**detail, "waves": len(out), "sources": [f.stats["source"] for f in out]})
    return out
