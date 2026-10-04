"""Patterns: multiplicative departures shared by places, times and fields (ARCHITECTURE §7.4).

Non-negative Poisson tensor factorisation of observed against expected
(CP-APR, Chi & Kolda 2012), the monolith's μ as offset:

    y[u,t,f] ~ Poisson(μ[u,t,f] · m[u,t,f]),   m = Σ_r a_r(u) b_r(t) c_r(f) ≥ 0

fitted by the multiplicative updates of the Poisson likelihood (for mode A,
a ← a ⊙ [Σ (y/m) b c] / [Σ μ b c], and likewise for the others). Component 0
starts constant, so it absorbs the overall level and the others are departures.
A coding substitution shows as a component positive on one code and a
matching departure below one on another, at the same places and times.

A component is reported with its loadings, its share of deviance and its
stability: refitted on each half of a split, matched by Tucker congruence
(≥ 0.9 on the modes the split does not cut).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from scipy.optimize import linear_sum_assignment

from .. import config


@dataclass
class Factorisation:
    A: np.ndarray       # [U, R]
    B: np.ndarray       # [T, R]
    C: np.ndarray       # [F, R]
    deviance: float     # of the factorised model
    deviance0: float    # of μ alone (m ≡ 1)
    shares: np.ndarray  # deviance reduction attributable to each component (leave-one-out)


def _dev(y: torch.Tensor, lam: torch.Tensor) -> float:
    lam = lam.clamp(min=1e-30)
    return float(2 * (torch.where(y > 0, y * torch.log(y / lam), torch.zeros_like(y)) - (y - lam)).sum())


def fit(y: np.ndarray, mu: np.ndarray, rank: int, iterations: int = 500, tol: float = 1e-7,
        seed_parts: tuple = ("cp_apr",)) -> Factorisation:
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    Y = torch.as_tensor(y, dtype=torch.float64, device=dev)
    M = torch.as_tensor(mu, dtype=torch.float64, device=dev)
    U, T, F = y.shape
    g = torch.Generator(device="cpu").manual_seed(config.seed(*seed_parts) % (2 ** 63))
    A = (0.5 + torch.rand((U, rank), generator=g, dtype=torch.float64)).to(dev)
    B = (0.5 + torch.rand((T, rank), generator=g, dtype=torch.float64)).to(dev)
    C = (0.5 + torch.rand((F, rank), generator=g, dtype=torch.float64)).to(dev)
    A[:, 0], B[:, 0], C[:, 0] = 1.0, 1.0, 1.0
    A[:, 1:] *= 0.1
    prev = np.inf
    for _ in range(iterations):
        for mode in range(3):
            m = torch.einsum("ur,tr,fr->utf", A, B, C).clamp(min=1e-30)
            ratio = Y / m
            if mode == 0:
                A = A * torch.einsum("utf,tr,fr->ur", ratio, B, C) / torch.einsum("utf,tr,fr->ur", M, B, C).clamp(min=1e-30)
            elif mode == 1:
                B = B * torch.einsum("utf,ur,fr->tr", ratio, A, C) / torch.einsum("utf,ur,fr->tr", M, A, C).clamp(min=1e-30)
            else:
                C = C * torch.einsum("utf,ur,tr->fr", ratio, A, B) / torch.einsum("utf,ur,tr->fr", M, A, B).clamp(min=1e-30)
        d = _dev(Y, M * torch.einsum("ur,tr,fr->utf", A, B, C))
        if abs(prev - d) < tol * max(abs(d), 1.0):
            break
        prev = d
    # normalise B and C to unit max; scale in A
    for X in (B, C):
        s = X.max(0).values.clamp(min=1e-30)
        X /= s
        A *= s
    full = M * torch.einsum("ur,tr,fr->utf", A, B, C)
    d_full = _dev(Y, full)
    shares = []
    for r in range(rank):
        keep = [k for k in range(rank) if k != r]
        part = M * torch.einsum("ur,tr,fr->utf", A[:, keep], B[:, keep], C[:, keep])
        shares.append(_dev(Y, part) - d_full)
    d0 = _dev(Y, M)
    return Factorisation(A.cpu().numpy(), B.cpu().numpy(), C.cpu().numpy(), d_full, d0,
                         np.array(shares) / max(d0 - d_full, 1e-12))


def congruence(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Tucker's congruence between the columns of two loading matrices."""
    nx = np.linalg.norm(x, axis=0)
    ny = np.linalg.norm(y, axis=0)
    return (x.T @ y) / np.maximum(np.outer(nx, ny), 1e-30)


def stability(full: Factorisation, half_a: Factorisation, half_b: Factorisation, modes: tuple[str, ...]
              ) -> np.ndarray:
    """Per component of ``full``: the minimum congruence, over the two halves and the modes the
    split leaves whole ("A", "B", "C"), after matching components by assignment."""
    out = np.ones(full.A.shape[1])
    for half in (half_a, half_b):
        sims = np.ones((full.A.shape[1], half.A.shape[1]))
        for mode in modes:
            sims = np.minimum(sims, congruence(getattr(full, mode), getattr(half, mode)))
        rows, cols = linear_sum_assignment(-sims)
        matched = np.zeros(full.A.shape[1])
        matched[rows] = sims[rows, cols]
        out = np.minimum(out, matched)
    return out


def temporal_stability(y: np.ndarray, mu: np.ndarray, rank: int, full: Factorisation | None = None
                       ) -> tuple[Factorisation, np.ndarray]:
    """Fit on all years and on each temporal half; stability on the place and field modes."""
    T = y.shape[1]
    mid = T // 2
    full = full or fit(y, mu, rank)
    a = fit(y[:, :mid], mu[:, :mid], rank, seed_parts=("cp_apr", "first"))
    b = fit(y[:, mid:], mu[:, mid:], rank, seed_parts=("cp_apr", "second"))
    return full, stability(full, a, b, ("A", "C"))


def spatial_stability(y: np.ndarray, mu: np.ndarray, rank: int, side_a: np.ndarray,
                      full: Factorisation | None = None) -> tuple[Factorisation, np.ndarray]:
    """Fit on all places and on each spatial half (boolean ``side_a``); stability on time and field."""
    full = full or fit(y, mu, rank)
    a = fit(y[side_a], mu[side_a], rank, seed_parts=("cp_apr", "A"))
    b = fit(y[~side_a], mu[~side_a], rank, seed_parts=("cp_apr", "B"))
    return full, stability(full, a, b, ("B", "C"))
