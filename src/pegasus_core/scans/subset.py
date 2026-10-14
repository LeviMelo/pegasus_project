"""Subset scanning (ARCHITECTURE §7.2–7.3).

The expectation-based Poisson score of a subset S of cells,

    F(S) = Y log(Y/M) + M − Y   if Y > M, else 0,     Y = Σ_S y,  M = Σ_S μ,

is maximised over graph-connected place sets (a subset of a centre's graph neighbourhood: the connected component of
the places ranked by y/μ that holds the best-ranked one) × contiguous time windows. For a window, the best place set is
a prefix of the elements sorted by y/μ (linear-time subset scanning, Neill 2012); the prefix's connected component is
kept (Speakman, McFowland & Neill 2016), so a reported cluster is one piece. Places and windows alternate until nothing
changes, vectorised over every centre and every null replicate on the device.

The null: replicates y* ~ NB(μ, φ) over the scanned support, searched identically and drawn on demand (`Null`): a score
is tested by Besag and Clifford's (1991) sequential Monte Carlo, which stops at the tenth replicate above it; only a
score the replicates do not settle takes the Gumbel tail fitted to their maxima (Abrams, Kleinman & Kulldorff 2010).
The replicates are drawn with the field's noise structure (N1, `surprise.Noise`): gamma frailties joined by a Gaussian
copula over periods and, where the field's spatial share ω is positive (`surprise.spatial_structure`), over places by
the heat kernel of the place graph (``root``, `surprise.spatial_root`), the same latent field the multiscale replicates
draw. A cluster over several places sums neighbours whose frailties are correlated, and a null of independent places
gave it a p-value too small (the statistic spread 1.2 to 1.4 times wider on stroke at 256 places).
"""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field

import numpy as np
from scipy import stats

from .. import config, mc


@dataclass
class Subset:
    score: float
    centre: int
    places: np.ndarray          # indices into the scanned places
    window: tuple[int, int]     # first and last time index, inclusive
    observed: float
    expected: float
    p: float = float("nan")
    p_empirical: float = float("nan")
    null: str = ""              # how p was reached (`Null.p`): sequential, gumbel or empirical
    extra: dict = field(default_factory=dict)

    @property
    def ratio(self) -> float:
        return self.observed / self.expected if self.expected > 0 else float("inf")


def score(Y: np.ndarray, M: np.ndarray, kind: str = "poisson") -> np.ndarray:
    """Expectation-based scores (Neill 2012). ``poisson``: Y = Σy, M = Σμ. ``gaussian`` (marks):
    Y = Σ w·(y − μ), M = Σ w, F = Y²/(2M) for Y > 0. ``poisson_low``: the same Poisson score for a
    deficit (Y < M). All keep the linear-time property, with priority Y/M per element (ascending
    for the deficit: `_sign`)."""
    Y, M = np.asarray(Y, dtype=float), np.asarray(M, dtype=float)
    if kind == "gaussian":
        return np.where((Y > 0) & (M > 0), Y * Y / (2 * np.maximum(M, 1e-300)), 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(Y > 0, Y * np.log(np.where((M > 0) & (Y > 0), Y / M, 1.0)), 0.0) + M - Y
    if kind == "poisson_low":
        return np.where((Y < M) & (M > 0), s, 0.0)
    return np.where((Y > M) & (M > 0), s, 0.0)


def _sign(kind: str) -> float:
    """Priority direction: an excess ranks elements by descending y/μ, a deficit by ascending."""
    return -1.0 if kind == "poisson_low" else 1.0


_NEIGHBOURHOODS: dict[tuple, np.ndarray] = {}
_ADJACENCY: dict[tuple, np.ndarray] = {}


def neighbourhoods(edges: np.ndarray, n: int, k: int) -> np.ndarray:
    """Each node's k nearest nodes by graph hops (itself first), padded with −1 on small components.
    A pure function of the graph: the result is kept (read-only) for the next field's scan of it."""
    key = (n, k, hashlib.sha1(np.ascontiguousarray(edges).tobytes()).hexdigest())
    if key not in _NEIGHBOURHOODS:
        out = _neighbourhoods(edges, n, k)
        out.flags.writeable = False
        _NEIGHBOURHOODS[key] = out
    return _NEIGHBOURHOODS[key]


def _neighbourhoods(edges: np.ndarray, n: int, k: int) -> np.ndarray:
    adj: list[list[int]] = [[] for _ in range(n)]
    for a, b in edges:
        adj[a].append(int(b))
        adj[b].append(int(a))
    out = np.full((n, k), -1, dtype=np.int64)
    for c in range(n):
        seen = {c}
        order = [c]
        queue = deque([c])
        while queue and len(order) < k:
            node = queue.popleft()
            for nb in sorted(adj[node]):
                if nb not in seen:
                    seen.add(nb)
                    order.append(nb)
                    queue.append(nb)
                    if len(order) == k:
                        break
        out[c, :len(order)] = order
    return out


def adjacency(edges: np.ndarray, nbr: np.ndarray) -> np.ndarray:
    """[C, K, K] boolean: whether the k-th and l-th nodes of centre c's neighbourhood are joined by an edge (a node
    with itself: true; the −1 padding: false). A pure function of the graph, kept for the next field's scan of it."""
    key = (nbr.shape, hashlib.sha1(np.ascontiguousarray(nbr).tobytes()).hexdigest(),
           hashlib.sha1(np.ascontiguousarray(edges).tobytes()).hexdigest())
    if key not in _ADJACENCY:
        e = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
        n = max(int(nbr.max()) + 1, int(e.max()) + 1 if e.size else 0)
        keys = np.unique(np.concatenate([e[:, 0] * n + e[:, 1], e[:, 1] * n + e[:, 0]]))
        valid = nbr >= 0
        idx = np.where(valid, nbr, 0).astype(np.int64)
        pair = idx[:, :, None] * n + idx[:, None, :]
        if len(keys):
            joined = keys[np.searchsorted(keys, pair).clip(max=len(keys) - 1)] == pair
        else:
            joined = np.zeros(pair.shape, dtype=bool)
        out = (joined | np.eye(nbr.shape[1], dtype=bool)[None]) & valid[:, :, None] & valid[:, None, :]
        out.flags.writeable = False
        _ADJACENCY[key] = out
    return _ADJACENCY[key]


def windows(T: int, max_length: int | None, full_only: bool = False) -> np.ndarray:
    """Contiguous windows [t0, t1] (inclusive) as an array [W, 2]."""
    if full_only:
        return np.array([[0, T - 1]])
    L = T if max_length is None else min(max_length, T)
    return np.array([(a, b) for a in range(T) for b in range(a, min(T, a + L))])


class Scanner:
    """A configured search over arrays y, μ of shape [U, T]: ``nbr`` the centres' neighbourhoods (`neighbourhoods`),
    ``adj`` their adjacency (`adjacency`)."""

    def __init__(self, nbr: np.ndarray, adj: np.ndarray, max_window: int | None = None, full_period: bool = False,
                 kind: str = "poisson", sweeps: int = 6):
        self.nbr = nbr
        self.adj = adj
        self.kind = kind
        self.valid = nbr >= 0
        self.max_window = max_window
        self.full_period = full_period
        self.sweeps = sweeps

    def best(self, y: np.ndarray, m: np.ndarray) -> Subset:
        """The best connected place set and window of a dataset (the torch alternation, GPU when present, in float64
        for the observed data)."""
        import torch

        dev = _device()
        best, P, win, W = _alternate(self, torch.as_tensor(y, dtype=torch.float64, device=dev)[None],
                                     torch.as_tensor(m, dtype=torch.float64, device=dev))
        c = int(best[0].argmax())
        nb = self.nbr[c][P[0, c].cpu().numpy()]
        t0, t1 = (int(v) for v in W[win[0, c]].cpu().numpy())
        Y, M = float(y[nb, t0:t1 + 1].sum()), float(m[nb, t0:t1 + 1].sum())
        return Subset(float(score(Y, M, self.kind)), c, nb, (t0, t1), Y, M)


# ---------------------------------------------------------------------- the null


def replicate(m: np.ndarray, phi: np.ndarray | float, rng: np.random.Generator, kind: str = "poisson") -> np.ndarray:
    """y* ~ NB(μ, φ) cellwise (Poisson where φ is infinite), via the gamma–Poisson mixture."""
    if kind == "gaussian":
        return rng.normal(0.0, np.sqrt(np.maximum(m, 0.0)))  # w·(y − μ) ~ N(0, w) under the model
    phi = np.broadcast_to(np.asarray(phi, dtype=float), m.shape)
    lam = m.copy()
    finite = np.isfinite(phi) & (m > 0)
    lam[finite] = rng.gamma(phi[finite], m[finite] / phi[finite])
    return rng.poisson(lam).astype(float)


SEQUENTIAL_EXCEEDANCES = mc.EXCEEDANCES
BLOCK = 32             # replicates drawn at a time
MIN_POSITIVE = 20      # positive null maxima needed to fit the tail
MAX_REPLICATES = 2000  # replicates drawn, at most, to reach them


class Null:
    """The null of the maximum score, drawn on demand (`mc.Draws`). ``cap`` replicates (the study's scale of them, in
    blocks) test a score sequentially (`mc.Draws.test`): the p-value is h/N when the h-th replicate at or above it came
    at the N-th, and (b + 1)/(n + 1) when the cap leaves b < h of n. A score the cap does not settle takes the tail
    model: an atom at zero (mass π0, no subset above the expectation) and a Gumbel fitted to the positive maxima,
    P(F ≥ s) = (1 − π0)·Gumbel_sf(s) (a Gumbel fitted to all maxima failed on sparse fields, survey of IX, I63,
    2026-10-04), drawing more replicates (up to `MAX_REPLICATES`) until `MIN_POSITIVE` are positive. When too few are,
    or all are equal, the field carries too little information for the tail and the p-value is the empirical one at
    all the replicates drawn, not 1: an untestable tail is not "no cluster"."""

    def __init__(self, scanner: Scanner, m: np.ndarray, phi: np.ndarray | float, cap: int, seed_parts: tuple,
                 noise=None, root: np.ndarray | None = None):
        self.scanner, self.m, self.phi, self.noise, self.root = scanner, m, phi, noise, root
        self.cap, self.seed_parts = -(-max(int(cap), BLOCK) // BLOCK) * BLOCK, seed_parts
        self.draws = mc.Draws(self._block, BLOCK)
        self._fit: tuple | None = None          # (n drawn, loc, scale, π0, testable)
        self.kind = "none"                      # how the last `p` was reached

    @property
    def maxima(self) -> np.ndarray:
        return self.draws.values

    def _block(self, start: int, count: int) -> np.ndarray:
        seed = config.seed(*self.seed_parts, "block", start // BLOCK)
        return _maxima_batched(self.scanner, self.m, self.phi, count, seed, chunk=BLOCK, noise=self.noise, root=self.root)

    def tail(self) -> tuple[float, float, float, bool]:
        """(loc, scale, π0, testable) of the tail model over the replicates drawn: to the cap, then on until
        `MIN_POSITIVE` of them are positive."""
        self.draws.extend(self.cap)
        while (self.maxima > 0).sum() < MIN_POSITIVE and len(self.draws) < MAX_REPLICATES:
            self.draws.more()
        if self._fit is None or self._fit[0] != len(self.maxima):
            positive = self.maxima[self.maxima > 0]
            pi0 = 1 - len(positive) / len(self.maxima)
            if len(positive) < MIN_POSITIVE or np.ptp(positive) <= 0:
                self._fit = (len(self.maxima), 0.0, 1.0, pi0, False)
            else:
                loc, sc = stats.gumbel_r.fit(positive)
                self._fit = (len(self.maxima), float(loc), float(sc), pi0, True)
        return self._fit[1:]

    @property
    def loc(self) -> float | None:
        return self._fit[1] if self._fit else None

    @property
    def scale(self) -> float | None:
        return self._fit[2] if self._fit else None

    def p_empirical(self, s: float) -> float:
        return float((1 + np.sum(self.maxima >= s)) / (1 + len(self.maxima)))

    def p(self, s: float, h: int = SEQUENTIAL_EXCEEDANCES) -> float:
        """The p-value of a score; ``self.kind`` then names how it was reached: sequential, gumbel or empirical."""
        if s <= 0:
            self.kind = "none"
            return 1.0
        r = self.draws.test(s, h, max(self.cap, len(self.draws)))
        if r.settled:
            self.kind = "sequential"
            return r.p
        loc, sc, pi0, testable = self.tail()
        if not testable:
            self.kind = "empirical"
            return self.p_empirical(s)
        self.kind = "gumbel"
        return float((1 - pi0) * stats.gumbel_r.sf(s, loc, sc))


def _torch_score(Y, M, kind: str):
    import torch

    if kind == "gaussian":
        return torch.where((Y > 0) & (M > 0), Y * Y / (2 * M.clamp(min=1e-30)), torch.zeros_like(Y))
    ratio = torch.where((M > 0) & (Y > 0), Y / M.clamp(min=1e-30), torch.ones_like(Y))
    s = Y * torch.log(ratio) + M - Y
    if kind == "poisson_low":
        return torch.where((Y < M) & (M > 0), s, torch.zeros_like(Y))
    return torch.where((Y > M) & (M > 0), s, torch.zeros_like(Y))


def _device():
    import torch

    return torch.device(config.array_device())


def _alternate(scanner: Scanner, Y, M):
    """The search in torch for a batch of datasets Y [R, U, T] against M [U, T]: places × windows by alternation for
    every centre, a fixed number of sweeps (stopping when nothing changes). The places of a sweep are the prefix of the
    neighbourhood ranked by y/μ, cut at its best score, then reduced to the connected component of its best-ranked
    element (a cluster is one piece); the score is that of the reduced set. Returns best [R, C], P [R, C, K] and the
    window index [R, C]."""
    import torch

    dev = Y.device
    U, T = M.shape
    W = torch.as_tensor(windows(T, scanner.max_window, scanner.full_period), device=dev)
    valid = torch.as_tensor(scanner.valid, device=dev)
    idx = torch.as_tensor(np.where(scanner.valid, scanner.nbr, 0), device=dev)
    adj = torch.as_tensor(np.array(scanner.adj), device=dev).to(Y.dtype)                      # [C, K, K]
    zero = torch.zeros((), device=dev, dtype=Y.dtype)
    Mn = torch.where(valid[..., None], M[idx], zero)                                  # [C, K, T]
    # window sums as one product with the windows' indicator [T, W] (a cumsum over the short time axis
    # was the largest kernel: 46% of the device time)
    t = torch.arange(T, device=dev)[:, None]
    ind = ((t >= W[:, 0][None]) & (t <= W[:, 1][None])).to(Y.dtype)
    Mw = Mn @ ind                                                                    # [C, K, W]
    R, C = Y.shape[0], idx.shape[0]
    K = idx.shape[1]
    Yn = torch.where(valid[None, ..., None], Y[:, idx], zero)                         # [R, C, K, T]
    Yw = Yn @ ind                                                                    # [R, C, K, W]
    del Yn
    P = valid.expand(R, -1, -1).clone()
    best = torch.zeros((R, C), device=dev, dtype=Y.dtype)
    win = torch.zeros((R, C), device=dev, dtype=torch.int64)
    for _ in range(scanner.sweeps):
        # Σ over the selected places of every window: a batched product, no [R, C, K, W] temporary
        Pf = P.to(Y.dtype)
        sw = _torch_score(torch.matmul(Pf.unsqueeze(2), Yw)[:, :, 0],
                          torch.bmm(Pf.transpose(0, 1), Mw).transpose(0, 1), scanner.kind)
        win = sw.argmax(2)
        gi = win[..., None, None].expand(R, C, Yw.shape[2], 1)
        Yk = Yw.gather(3, gi)[..., 0]
        Mk = Mw[None].expand(R, -1, -1, -1).gather(3, gi)[..., 0]
        prio = torch.where(valid[None] & (Mk > 0), _sign(scanner.kind) * Yk / Mk.clamp(min=1e-30),
                           torch.full_like(Yk, -float("inf")))
        order = torch.argsort(-prio, dim=2)
        sp = _torch_score(Yk.gather(2, order).cumsum(2), Mk.gather(2, order).cumsum(2), scanner.kind)
        sp = torch.where(torch.isfinite(prio.gather(2, order)), sp, torch.zeros_like(sp))
        top = sp.argmax(2)
        newP = (torch.argsort(order, dim=2) <= top[..., None]) & valid[None]
        # the connected component of the best-ranked element within the prefix, by boolean propagation over the
        # neighbourhood's adjacency
        comp = torch.zeros_like(newP)
        comp.scatter_(2, order[..., :1], True)
        comp &= newP
        for _hop in range(K):
            grown = (torch.bmm(comp.to(Y.dtype).transpose(0, 1), adj).transpose(0, 1) > 0) & newP
            if torch.equal(grown, comp):
                break
            comp = grown
        newP = comp
        best = _torch_score((Yk * newP).sum(2), (Mk * newP).sum(2), scanner.kind)
        if torch.equal(newP, P):
            break
        P = newP
    return best, P, win, W


def _maxima_batched(scanner: Scanner, m: np.ndarray, phi: np.ndarray | float, replicates: int, seed: int,
                    chunk: int = 32, noise=None, root: np.ndarray | None = None) -> np.ndarray:
    """The null's maxima: replicates drawn on the device (gamma–Poisson for counts, Gaussian for
    marks; with a ``noise`` structure the Poisson–lognormal frailty of `surprise.replicate_correlated`, its spatial
    share ω > 0 correlating the places by ``root`` [U, U], `surprise.spatial_root`) and searched in batches by
    `_alternate`, float32."""
    import torch

    if noise is not None and noise.omega > 0 and root is None:
        raise ValueError("a noise structure with a spatial share (omega > 0) needs the root of its place kernel")

    dev = _device()
    gen = torch.Generator(device=dev).manual_seed(seed % (2 ** 63))
    U, T = m.shape
    M = torch.as_tensor(m, dtype=torch.float32, device=dev)
    phi_t = torch.as_tensor(np.broadcast_to(np.asarray(phi, dtype=float), m.shape).copy(), dtype=torch.float32,
                            device=dev)
    out = []
    for start in range(0, replicates, chunk):
        R = min(chunk, replicates - start)
        if scanner.kind == "gaussian":
            Y = torch.randn((R, U, T), generator=gen, device=dev) * M.clamp(min=0).sqrt()
        elif noise is not None and not noise.null:
            # the predictive's frailty (gamma marginals, AR(1) Gaussian copula: surprise.frailty), drawn on the CPU
            from .. import surprise
            nrng = np.random.default_rng([seed % (2 ** 63), start])
            phi_c = np.broadcast_to(np.asarray(phi, dtype=float), m.shape)
            fr = surprise.gamma_frailty(surprise.copula_normals((R, U, T), noise, nrng, root), phi_c, noise)
            Y = torch.poisson(M * torch.as_tensor(fr, dtype=torch.float32, device=dev), generator=gen)
        else:
            finite = torch.isfinite(phi_t) & (M > 0)
            shape = torch.where(finite, phi_t, torch.ones_like(M))
            lam = torch.where(finite, torch._standard_gamma(shape.expand(R, U, T).contiguous(), generator=gen)
                              * (M / shape), M.expand(R, U, T))
            Y = torch.poisson(lam, generator=gen)
        best, *_ = _alternate(scanner, Y, M)
        out.append(best.max(1).values.double().cpu().numpy())
    return np.concatenate(out)


def scan(y: np.ndarray, m: np.ndarray, phi: np.ndarray | float, scanner: Scanner, alpha: float = 0.05,
         max_subsets: int = 20, replicates: int = 200, seed_parts: tuple = ("subset",),
         nul: Null | None = None, noise=None, root: np.ndarray | None = None) -> tuple[list[Subset], Null | None]:
    """The recursive scan: report the best subset, condition it out (μ ← y on its cells; for the Gaussian score, its
    residuals ← 0), repeat until the next p exceeds α. Returns the subsets with their p-value (`Null.p`) and empirical
    p, and the null, which is drawn only as far as a score needs it: ``Null`` is None when no subset beat the
    expectation. A ``nul`` given is the one of the unconditioned expectation ``m`` (extended in place). The null's
    ``noise`` (with its spatial ``root``) is given, or a function returning the pair, called when the first score
    needs the null."""
    replicates = config.replicates(replicates)          # the study's `nulls`
    m0, m = m, m.copy()          # the null is of the unconditioned expectation
    y = y.copy()
    out: list[Subset] = []
    for _ in range(max_subsets):
        s = scanner.best(y, m)
        if s.score <= 0:
            break
        nul = nul or Null(scanner, m0, phi, replicates, seed_parts, *(noise() if callable(noise) else (noise, root)))
        s.p = nul.p(s.score)
        s.null, s.p_empirical = nul.kind, nul.p_empirical(s.score)
        if s.p > alpha:
            break
        out.append(s)
        sel = np.ix_(s.places, np.arange(s.window[0], s.window[1] + 1))
        if scanner.kind == "gaussian":
            y[sel] = 0.0
        else:
            m[sel] = np.minimum(m[sel], y[sel]) if scanner.kind == "poisson_low" else np.maximum(m[sel], y[sel])
    return out, nul
