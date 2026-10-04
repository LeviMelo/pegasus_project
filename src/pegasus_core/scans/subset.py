"""Subset scanning (ARCHITECTURE §7.2–7.3).

The expectation-based Poisson score of a subset S of cells,

    F(S) = Y log(Y/M) + M − Y   if Y > M, else 0,     Y = Σ_S y,  M = Σ_S μ,

is maximised over places (a subset of a centre's graph neighbourhood) ×
contiguous time windows × free dimensions (codes of a subtree, groups). For a
free dimension with the others fixed, the best subset is a prefix of the
elements sorted by y/μ (linear-time subset scanning, Neill 2012). Dimensions
are optimised in turn until no subset changes (Neill, McFowland & Zheng 2013).

Two stages, both repeated identically on null replicates so the null matches
the search: (1) places × windows, vectorised over every centre; (2) the best
``refine`` centres re-optimised with the free dimensions.

The null: replicates y* ~ NB(μ, φ) over the scanned support; a Gumbel fitted
to the replicate maxima gives p-values without a Monte-Carlo floor (Abrams,
Kleinman & Kulldorff 2010).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
from scipy import stats

from .. import config


@dataclass
class Subset:
    score: float
    centre: int
    places: np.ndarray          # indices into the scanned places
    window: tuple[int, int]     # first and last time index, inclusive
    free: list[np.ndarray]      # selected indices per free dimension
    observed: float
    expected: float
    p: float = float("nan")
    p_empirical: float = float("nan")
    extra: dict = field(default_factory=dict)

    @property
    def ratio(self) -> float:
        return self.observed / self.expected if self.expected > 0 else float("inf")


def score(Y: np.ndarray, M: np.ndarray) -> np.ndarray:
    Y, M = np.asarray(Y, dtype=float), np.asarray(M, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        s = Y * np.log(np.where(M > 0, Y / M, 1.0)) + M - Y
    return np.where((Y > M) & (M > 0), s, 0.0)


def neighbourhoods(edges: np.ndarray, n: int, k: int) -> np.ndarray:
    """Each node's k nearest nodes by graph hops (itself first), padded with −1 on small components."""
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


def windows(T: int, max_length: int | None, full_only: bool = False) -> np.ndarray:
    """Contiguous windows [t0, t1] (inclusive) as an array [W, 2]."""
    if full_only:
        return np.array([[0, T - 1]])
    L = T if max_length is None else min(max_length, T)
    return np.array([(a, b) for a in range(T) for b in range(a, min(T, a + L))])


class Scanner:
    """A configured search over arrays y, μ of shape [U, T, *free] (free dims optional)."""

    def __init__(self, nbr: np.ndarray, max_window: int | None = None, full_period: bool = False,
                 refine: int = 50, sweeps: int = 6):
        self.nbr = nbr
        self.valid = nbr >= 0
        self.max_window = max_window
        self.full_period = full_period
        self.refine = refine
        self.sweeps = sweeps

    # ---- stage 1: places × windows, every centre at once ---------------------------

    def _stage1(self, y2: np.ndarray, m2: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        U, T = y2.shape
        W = windows(T, self.max_window, self.full_period)
        idx = np.where(self.valid, self.nbr, 0)
        Yn = np.where(self.valid[..., None], y2[idx], 0.0)          # [C, K, T]
        Mn = np.where(self.valid[..., None], m2[idx], 0.0)
        cy = np.concatenate([np.zeros(Yn.shape[:2] + (1,)), np.cumsum(Yn, axis=2)], axis=2)
        cm = np.concatenate([np.zeros(Mn.shape[:2] + (1,)), np.cumsum(Mn, axis=2)], axis=2)
        P = self.valid.copy()
        win = np.zeros(len(P), dtype=np.int64)
        best = np.zeros(len(P))
        for _ in range(self.sweeps):
            # windows given places
            Yw = (cy[:, :, W[:, 1] + 1] - cy[:, :, W[:, 0]])          # [C, K, W]
            Mw = (cm[:, :, W[:, 1] + 1] - cm[:, :, W[:, 0]])
            sw = score((Yw * P[..., None]).sum(1), (Mw * P[..., None]).sum(1))
            new_win = sw.argmax(1)
            # places given windows: LTSS on y/μ within the neighbourhood
            Yk = Yw[np.arange(len(P)), :, new_win]                   # [C, K]
            Mk = Mw[np.arange(len(P)), :, new_win]
            prio = np.where(self.valid & (Mk > 0), Yk / np.maximum(Mk, 1e-300), -np.inf)
            order = np.argsort(-prio, axis=1)
            sy = np.cumsum(np.take_along_axis(Yk, order, 1), 1)
            sm = np.cumsum(np.take_along_axis(Mk, order, 1), 1)
            sp = score(sy, sm)
            sp[~np.isfinite(np.take_along_axis(prio, order, 1))] = 0
            top = sp.argmax(1)
            ranks = np.argsort(order, axis=1)
            newP = ranks <= top[:, None]
            newP &= self.valid
            new_best = sp[np.arange(len(P)), top]
            if np.array_equal(newP, P) and np.array_equal(new_win, win):
                best = new_best
                break
            P, win, best = newP, new_win, new_best
        return best, P, W[win]

    # ---- stage 2: free dimensions on the best centres ------------------------------

    def _stage2(self, y: np.ndarray, m: np.ndarray, centre: int, P: np.ndarray, w: np.ndarray) -> Subset:
        nbr = self.nbr[centre][self.valid[centre]]
        P = P[self.valid[centre]].copy()
        free = [np.ones(d, dtype=bool) for d in y.shape[2:]]
        Yc, Mc = y[nbr], m[nbr]                                      # [K, T, *free]
        T = y.shape[1]
        W = windows(T, self.max_window, self.full_period)
        t0, t1 = int(w[0]), int(w[1])
        best = 0.0
        for _ in range(self.sweeps):
            changed = False
            # free dimensions
            for d in range(len(free)):
                Ysel = _reduce(Yc, P, (t0, t1), free, keep=2 + d)
                Msel = _reduce(Mc, P, (t0, t1), free, keep=2 + d)
                mask, s = _ltss(Ysel, Msel)
                changed |= not np.array_equal(mask, free[d])
                free[d], best = mask, s
            # windows
            Yt = _reduce(Yc, P, None, free, keep=1)
            Mt = _reduce(Mc, P, None, free, keep=1)
            cy, cm = np.concatenate([[0], np.cumsum(Yt)]), np.concatenate([[0], np.cumsum(Mt)])
            sw = score(cy[W[:, 1] + 1] - cy[W[:, 0]], cm[W[:, 1] + 1] - cm[W[:, 0]])
            k = int(sw.argmax())
            changed |= (int(W[k, 0]), int(W[k, 1])) != (t0, t1)
            t0, t1 = int(W[k, 0]), int(W[k, 1])
            # places
            Yp = _reduce(Yc, None, (t0, t1), free, keep=0)
            Mp = _reduce(Mc, None, (t0, t1), free, keep=0)
            mask, best = _ltss(Yp, Mp)
            changed |= not np.array_equal(mask, P)
            P = mask
            if not changed:
                break
        Y = float(_reduce(Yc, P, (t0, t1), free, keep=None))
        M = float(_reduce(Mc, P, (t0, t1), free, keep=None))
        return Subset(float(score(Y, M)), centre, nbr[P], (t0, t1), [np.nonzero(f)[0] for f in free], Y, M)

    # ---- the search ------------------------------------------------------------------

    def best(self, y: np.ndarray, m: np.ndarray) -> Subset:
        y2 = y.reshape(y.shape[0], y.shape[1], -1).sum(2)
        m2 = m.reshape(m.shape[0], m.shape[1], -1).sum(2)
        s1, P, Wb = self._stage1(y2, m2)
        if y.ndim == 2:
            c = int(s1.argmax())
            nb = self.nbr[c][P[c]]
            t0, t1 = int(Wb[c, 0]), int(Wb[c, 1])
            Y, M = float(y[nb, t0:t1 + 1].sum()), float(m[nb, t0:t1 + 1].sum())
            return Subset(float(s1[c]), c, nb, (t0, t1), [], Y, M)
        top = np.argsort(-s1)[: self.refine]
        found = [self._stage2(y, m, int(c), P[c], Wb[c]) for c in top]
        return max(found, key=lambda s: s.score)


def _reduce(A: np.ndarray, places: np.ndarray | None, window: tuple[int, int] | None, free: list[np.ndarray],
            keep: int | None) -> np.ndarray | float:
    """Sum A [K, T, *free] over the selected places, window and free masks, keeping one axis whole."""
    X = A
    if window is not None and keep != 1:
        X = X[:, window[0]:window[1] + 1]
    if places is not None and keep != 0:
        X = np.compress(places, X, axis=0)
    for d, mask in enumerate(free):
        if keep != 2 + d:
            X = np.compress(mask, X, axis=2 + d)
    if keep is None:
        return float(X.sum())
    return X.sum(axis=tuple(a for a in range(X.ndim) if a != keep))


def _ltss(Y: np.ndarray, M: np.ndarray) -> tuple[np.ndarray, float]:
    prio = np.where(M > 0, Y / np.maximum(M, 1e-300), -np.inf)
    order = np.argsort(-prio)
    s = score(np.cumsum(Y[order]), np.cumsum(M[order]))
    s[~np.isfinite(prio[order])] = 0
    k = int(s.argmax())
    mask = np.zeros(len(Y), dtype=bool)
    if s[k] > 0:
        mask[order[:k + 1]] = True
    else:
        mask[:] = True
    return mask, float(s[k])


# ---------------------------------------------------------------------- the null


def replicate(m: np.ndarray, phi: np.ndarray | float, rng: np.random.Generator) -> np.ndarray:
    """y* ~ NB(μ, φ) cellwise (Poisson where φ is infinite), via the gamma–Poisson mixture."""
    phi = np.broadcast_to(np.asarray(phi, dtype=float), m.shape)
    lam = m.copy()
    finite = np.isfinite(phi) & (m > 0)
    lam[finite] = rng.gamma(phi[finite], m[finite] / phi[finite])
    return rng.poisson(lam).astype(float)


@dataclass
class Null:
    maxima: np.ndarray
    loc: float
    scale: float

    def p(self, s: float) -> float:
        return float(stats.gumbel_r.sf(s, self.loc, self.scale))

    def p_empirical(self, s: float) -> float:
        return float((1 + np.sum(self.maxima >= s)) / (1 + len(self.maxima)))


def null(scanner: Scanner, m: np.ndarray, phi: np.ndarray | float, replicates: int = 200,
         seed_parts: tuple = ("subset-null",)) -> Null:
    rng = np.random.default_rng(config.seed(*seed_parts))
    maxima = np.array([scanner.best(replicate(m, phi, rng), m).score for _ in range(replicates)])
    loc, sc = stats.gumbel_r.fit(maxima)
    return Null(maxima, float(loc), float(sc))


def scan(y: np.ndarray, m: np.ndarray, phi: np.ndarray | float, scanner: Scanner, alpha: float = 0.05,
         max_subsets: int = 20, replicates: int = 200, seed_parts: tuple = ("subset",),
         nul: Null | None = None) -> tuple[list[Subset], Null]:
    """The recursive scan: report the best subset, condition it out (μ ← y on its cells),
    repeat until the next p exceeds α. Returns the subsets with Gumbel and empirical p."""
    nul = nul or null(scanner, m, phi, replicates, seed_parts)
    m = m.copy()
    out: list[Subset] = []
    for _ in range(max_subsets):
        s = scanner.best(y, m)
        s.p, s.p_empirical = nul.p(s.score), nul.p_empirical(s.score)
        if s.score <= 0 or s.p > alpha:
            break
        out.append(s)
        sel = np.ix_(s.places, np.arange(s.window[0], s.window[1] + 1), *s.free) if s.free else \
            np.ix_(s.places, np.arange(s.window[0], s.window[1] + 1))
        m[sel] = np.maximum(m[sel], y[sel])
    return out, nul
