"""Space at every scale, from the place graph itself (ARCHITECTURE §7.0, stages C and D).

A departure's or a relation's spatial support is unknown: one town, a cluster across state lines, a corridor. A fixed
partition (municipality, region, state) makes every result depend on the zoning (the modifiable areal unit problem;
Openshaw 1984) and offers three scales where the truth is a continuum. Here the scales come from the graph.

**The heat kernel.** With A the place graph's adjacency and L = I − D^{-1/2} A D^{-1/2} its normalised Laplacian
(eigenpairs L = Q Λ Qᵀ, computed once), K_s = exp(−sL) = Q e^{−sΛ} Qᵀ is a non-negative smoothing whose footprint
grows continuously with s from the place alone (s = 0) to the whole graph, along the graph's connectivity and blind to
administrative borders (graph signal processing: Shuman et al. 2013; spectral graph wavelets, Hammond, Vandergheynst
& Gribonval 2011). `GraphSpectrum.scales` picks s so that the median footprint holds a geometric ladder of effective
numbers of places (1, 3, 10, … : a grid on a continuum, not a zoning).

**Multiscale peak testing** (`peaks`): at each scale s and period t, the standardised kernel excess at centre c,

    S_s(c, t) = Σ_u K_s(c, u)(y_ut − μ_ut) / √(Σ_u K_s(c, u)² V_ut),

V the predictive's cell variance under its noise structure (N1). Its local maxima over the graph are the candidate
departures, each with its scale; a peak's p-value is the share of peaks at least as high among the peaks of the
same scale in replicate fields drawn from the predictive (STEM, smoothing and testing of maxima: Schwartzman,
Gavrilov & Adler 2011; across scales, Cheng & Schwartzman 2017, with the peak-height law simulated as on a graph it
has no closed form). One BH over every peak of every scale and period controls the FDR over peaks: a regional excess
is one finding with its scale and footprint, not hundreds of correlated cells.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp

from . import surprise


def _torch():
    import torch

    return torch, ("cuda" if torch.cuda.is_available() else "cpu")


@dataclass
class GraphSpectrum:
    """The normalised Laplacian's eigenpairs of a place graph (``edges`` over ``n`` places, with the graph's
    ``weights``: border length for contiguity, `graphs.graph`), on the device."""
    edges: np.ndarray
    n: int
    weights: np.ndarray | None = None
    _eig: tuple = field(default=None, repr=False)

    def __post_init__(self):
        torch, dev = _torch()
        w = np.ones(len(self.edges)) if self.weights is None else np.asarray(self.weights, dtype=float)
        A = sp.coo_matrix((w, (self.edges[:, 0], self.edges[:, 1])), shape=(self.n, self.n))
        A = A.maximum(A.T).tocsr()
        deg = np.asarray(A.sum(1)).ravel()
        dinv = np.where(deg > 0, 1.0 / np.sqrt(np.maximum(deg, 1e-300)), 0.0)
        L = np.eye(self.n) - (sp.diags(dinv) @ A @ sp.diags(dinv)).toarray()   # an island's row is the identity's
        lam, Q = torch.linalg.eigh(torch.as_tensor(L, dtype=torch.float64, device=dev))
        self._eig = (lam.clamp(min=0.0), Q)
        self._q32 = Q.float()
        self._qsq = Q * Q                                   # (Q∘Q): K_s's squared row sums in closed form
        self._q1 = Q.T @ torch.ones(self.n, dtype=torch.float64, device=dev)
        self.neighbours = A

    def kernel(self, s: float):
        """K_s = exp(−sL) [n, n] on the device (float32)."""
        torch, _ = _torch()
        lam, _ = self._eig
        Q = self._q32
        return (Q * torch.exp(-s * lam).float()) @ Q.T

    def footprint(self, s: float) -> float:
        """The median over centres of the effective number of places in K_s's row: (Σ K)² / Σ K²."""
        torch, _ = _torch()
        lam, Q = self._eig
        rows = Q @ (torch.exp(-s * lam) * self._q1)                      # Σ_u K(c, u)
        squares = self._qsq @ torch.exp(-2 * s * lam)                    # Σ_u K(c, u)² = (K²)_cc
        return float((rows ** 2 / torch.clamp(squares, min=1e-300)).nanmedian())

    def scales(self, footprints: tuple[float, ...] = (1, 3, 10, 30, 100, 300)) -> list[float]:
        """The s whose median footprint is each of ``footprints`` (bisection on log s; 0 for a single place)."""
        out = []
        for target in footprints:
            if target <= 1:
                out.append(0.0)
                continue
            lo, hi = -6.0, 6.0
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if self.footprint(10 ** mid) < target else (lo, mid)
            out.append(float(10 ** (0.5 * (lo + hi))))
        return out


def contrasts(T: int, shape: str, min_past: int = 3, min_years: int = 2) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Temporal contrasts [T, m] of a departure shape and each one's window [t0, t1): ``spike``, one period each;
    ``step``, the sum from a start τ to the series' end, for τ leaving ``min_past`` periods before and ``min_years``
    after (the change-point windows); ``trend``, a course bending upward from τ, the hinge (t − τ)₊ over the same
    starts (a trend change; from τ = 0 it is the series' own slope against the reference)."""
    if shape == "spike":
        return np.eye(T), [(t, t + 1) for t in range(T)]
    if shape == "step":
        starts = range(min_past, T - min_years + 1)
        C = np.stack([(np.arange(T) >= tau).astype(float) for tau in starts], 1)
        return C, [(tau, T) for tau in starts]
    if shape == "trend":
        starts = [0, *range(min_past, T - min_years + 1)]
        C = np.stack([np.clip(np.arange(T) - tau + 1, 0, None).astype(float) for tau in starts], 1)
        return C, [(tau, T) for tau in starts]
    raise ValueError(f"unknown shape {shape!r}")


def contrast_variance(s: surprise.Surprise, C: np.ndarray) -> np.ndarray:
    """[U, m] Var(cᵀ y_u) per place and contrast under the predictive with its noise structure (N1):
    Σ_t c_t² V_t + 2 Σ_k Σ_t c_t c_{t+k} Cov(y_t, y_{t+k})."""
    phi = np.broadcast_to(np.asarray(s.phi, dtype=float), s.mu.shape)
    out = surprise.cell_variance(s.mu, phi, s.noise) @ (C ** 2)
    T = C.shape[0]
    for lag in range(1, T):
        if s.noise.rho <= 0 or s.noise.rho ** lag < 1e-4:
            break
        cov = surprise.lag_covariance(s.mu, phi, s.noise, lag)              # [U, T − lag]
        out += 2 * np.einsum("ut,tj->uj", cov, C[:-lag] * C[lag:])
    return out


@dataclass
class Peak:
    """A local maximum of the standardised kernel excess: its centre (place index), the window [t0, t1) of its
    temporal contrast, scale (s and the footprint's effective places), height S, the kernel rate ratio
    Σ K cᵀy / Σ K cᵀμ, the relevance statistic, its p-value."""
    centre: int
    window: tuple
    s: float
    places: float
    height: float
    rate_ratio: float
    relevance_z: float
    p: float = 1.0


def tail_p(null: np.ndarray, h: np.ndarray, exceedances: int = 250) -> np.ndarray:
    """P(a null peak ≥ h) from sorted replicate peak heights ``null``: the empirical share below the top
    ``exceedances``, and beyond it a generalised Pareto fitted to the exceedances (peaks over threshold: Knijnenburg,
    Wessels, Reinders & Shmulevich 2009). The empirical p alone stops at 1/(n + 1), where BH over tens of thousands of
    peaks needs far smaller ones: the first grid of the multiscale model lost most of its power there (2026-10-07)."""
    from scipy import stats

    n = len(null)
    emp = (n - np.searchsorted(null, h, side="left") + 1) / (n + 1)
    if n < 4 * exceedances:
        return emp
    u = null[n - exceedances - 1]
    exc = null[n - exceedances:] - u
    shape, _, scale = stats.genpareto.fit(exc, floc=0.0)
    if shape < 0:          # a bounded tail would give p = 0 past its endpoint: the exponential (Gumbel domain, where
        shape, scale = 0.0, float(exc.mean())     # a smooth Gaussian field's peaks lie) is the conservative bound
    beyond = h > u
    out = emp.copy()
    out[beyond] = exceedances / n * stats.genpareto.sf(h[beyond] - u, shape, loc=0.0, scale=scale)
    return np.maximum(out, 1e-300)


def torch_sqrt(x):
    torch, _ = _torch()
    return torch.sqrt(torch.clamp(x, min=1e-12))


def _local_maxima(S, rows: np.ndarray, cols: np.ndarray):
    """[n, m] boolean: S[c] > 0 and ≥ every graph neighbour's S (edges as index arrays, both directions)."""
    torch, dev = _torch()
    r, c = torch.as_tensor(rows, device=dev), torch.as_tensor(cols, device=dev)
    best = torch.full_like(S, -torch.inf)
    best = best.index_reduce_(0, r, S[c], "amax", include_self=True)
    return (best <= S) & (S > 0)


def peaks(s: surprise.Surprise, spectrum: GraphSpectrum, scales: list[float], shape: str = "spike",
          replicates: int = 40, seed: int = 0, rate_ratio: float = 1.0) -> tuple[list[Peak], dict]:
    """The field's multiscale peaks for a departure ``shape`` (`contrasts`) with their STEM p-values (module
    docstring). At scale s and contrast c the statistic is S = Σ_u K(·, u) cᵀ(y_u − μ_u) / √(Σ_u K(·, u)² cᵀΣ_u c),
    Σ_u the place's covariance over periods under N1 (`contrast_variance`). Each scale's S is calibrated to the
    replicates' by its median and MAD (the empirical null), and the peaks are the joint maxima over place and scale
    (scale-space detection: Lindeberg 1998). A peak's p-value is read against the joint peaks of the same scale and
    contrast in replicate fields drawn from the predictive. Each peak also carries its relevance statistic, the excess
    over ``rate_ratio`` times the expectation; the returned dict also holds each scale's calibration."""
    torch, dev = _torch()
    U, T = s.y.shape
    phi = np.broadcast_to(np.asarray(s.phi, dtype=float), s.mu.shape)
    ok = (s.flags & (surprise.DENOMINATOR | surprise.NO_INFORMATION)) == 0
    C, windows = contrasts(T, shape)
    m = C.shape[1]
    Ct = torch.as_tensor(C, dtype=torch.float32, device=dev)
    y0, mu0 = np.where(ok, s.y, 0.0), np.where(ok, s.mu, 0.0)
    D = torch.as_tensor(y0 - mu0, dtype=torch.float32, device=dev) @ Ct                    # [U, m]
    CM = torch.as_tensor(mu0, dtype=torch.float32, device=dev) @ Ct
    W = torch.as_tensor(np.where(ok.all(1, keepdims=True), contrast_variance(s, C), 0.0), dtype=torch.float32,
                        device=dev)                                                         # [U, m]
    rng = np.random.default_rng(seed)
    noise = surprise.spatial_structure(s, spectrum)                   # N1 with its spatial part, on this graph
    root = surprise.spatial_root(spectrum, noise.scale) if noise.omega > 0 else None
    reps = [(np.where(ok, surprise.replicate_correlated(s.mu, phi, noise, rng, root), 0.0) - mu0) @ C
            for _ in range(replicates)]
    Dr = torch.as_tensor(np.concatenate(reps, 1), dtype=torch.float32, device=dev)          # [U, R·m]
    A = (spectrum.neighbours + sp.identity(U)).tocoo()       # a place counts among its own neighbourhood
    rows, cols = A.row, A.col
    # pass 1: the standardised excess at every scale, observed [k, U, m] and replicated [k, U, R, m]
    S_all, Sr_all, places = [], [], []
    for sc in scales:
        K = torch.eye(U, device=dev) if sc == 0 else spectrum.kernel(sc)
        KW = (K * K) @ W
        S_all.append((K @ D) / torch_sqrt(KW))
        Sr_all.append(((K @ Dr) / torch_sqrt(KW.repeat(1, replicates))).reshape(U, replicates, m))
        places.append(spectrum.footprint(sc))                     # in double precision: far rows underflow in single
        del K, KW
    S_all, Sr_all = torch.stack(S_all), torch.stack(Sr_all)
    # the empirical null per scale (Efron's central matching, by median and MAD): the field's own statistic re-centred
    # and re-scaled to the replicates' wherever the predictive misstates it; a real departure is too rare to move them
    calibration = {}
    for k in range(len(scales)):
        o, r = S_all[k].flatten(), Sr_all[k].flatten()
        mo, mr = o.median(), r.median()
        so = (o - mo).abs().median().clamp(min=1e-6)
        sr = (r - mr).abs().median().clamp(min=1e-6)
        S_all[k] = (S_all[k] - mo) * (sr / so) + mr
        calibration[places[k]] = {"shift": round(float(mo - mr), 4), "scale": round(float(so / sr), 4)}
    # pass 2: joint maxima in place x scale (scale-space: a peak beats its graph neighbours at its own scale and its
    # own place at the scales either side), so one departure is one test at the scale that fits it best
    def joint(X):                                   # X [k, U, ...] -> boolean of the same shape
        flat = X.reshape(len(scales), U, -1)
        loc = torch.stack([_local_maxima(flat[k], rows, cols) for k in range(len(scales))])
        up = torch.ones_like(loc)
        up[:-1] &= flat[:-1] >= flat[1:]
        up[1:] &= flat[1:] >= flat[:-1]
        return (loc & up).reshape(X.shape)
    is_peak, rpeak = joint(S_all), joint(Sr_all)
    found, null = [], {"calibration": calibration, "noise": {"omega": noise.omega, "places": spectrum.footprint(
        noise.scale) if noise.omega > 0 else 1.0}}
    for k, sc in enumerate(scales):
        K = torch.eye(U, device=dev) if sc == 0 else spectrum.kernel(sc)
        KW = (K * K) @ W
        KC, KM = K @ (D + CM), K @ CM
        null[places[k]] = float(rpeak[k].sum()) / replicates
        for j in range(m):
            null_heights = torch.sort(Sr_all[k][:, :, j][rpeak[k][:, :, j]]).values
            cs = torch.nonzero(is_peak[k][:, j], as_tuple=True)[0]
            if cs.numel() == 0 or null_heights.numel() == 0:
                continue
            h = S_all[k][cs, j]
            p = torch.as_tensor(tail_p(null_heights.cpu().numpy(), h.cpu().numpy()), device=dev)
            rr = KC[cs, j] / torch.clamp(KM[cs, j], min=1e-12)
            zrel = (KC[cs, j] - rate_ratio * KM[cs, j]) / torch_sqrt(KW[cs, j])
            for c, hh, pp, r, zr in zip(cs.tolist(), h.tolist(), p.tolist(), rr.tolist(), zrel.tolist(), strict=True):
                found.append(Peak(c, windows[j], sc, places[k], hh, r, zr, pp))
        del K, KW, KC, KM
    return found, null


def footprint(spectrum: GraphSpectrum, centre: int, s: float, mass: float = 0.5) -> list[int]:
    """The smallest set of places holding ``mass`` of K_s's row at ``centre``."""
    if s == 0:
        return [centre]
    torch, _ = _torch()
    lam, Q = spectrum._eig
    row = ((Q[centre] * torch.exp(-s * lam)) @ Q.T).cpu().numpy()
    order = np.argsort(row)[::-1]
    k = int(np.searchsorted(np.cumsum(row[order]) / row.sum(), mass)) + 1
    return order[:k].tolist()
