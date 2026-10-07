"""The Laplace approximation of a fitted block's posterior (ARCHITECTURE §5.5).

At the MAP θ̂ the latent effects' posterior is N(θ̂, H⁻¹) on the centred subspace, H the Hessian of the penalised
negative log-likelihood. For counts the likelihood's information is the negative binomial's expected one,
w = φμ/(φ + μ) (the same weight as ARCHITECTURE §6.3): the mean is fitted by Poisson quasi-likelihood, but the cells
it must be uncertain about are overdispersed, and the Poisson information (w = μ) understates the posterior variance
by 1 + μ/φ in the cells that carry it. For a mark model H carries its family's Fisher weights. With the low-rank
interaction the draws are of the other effects, the interaction held at its MAP (ADR-0021).

**The draws are exact** (`solver.StructuredNewton.draws`): H is assembled and factored by the v1 solver, and a draw
is one triangular solve of the factor (all draws at once), the leaf-place block's conditional in closed form, and
the centrings by conditioning by kriging. This replaced perturb-and-MAP draws solved by preconditioned conjugate
gradients (40-90 iterations per draw; evaluation 2026-10-05, Laplace).

Every cell's marginal variance is then estimated with relative error √(2/S), whatever the correlation between cells,
and the predictive of any aggregate (a field's μ[u, t], the prospective tier) comes from the same draws.
"""

from __future__ import annotations

import time

import numpy as np
import scipy.sparse as sp
import torch

from . import config, monolith, solver


class Posterior:
    """The Laplace posterior of one fitted block (`monolith.Monolith` or a mark model)."""

    def __init__(self, model: monolith.Monolith, phi: float | None = None, poisson: bool = False):
        self.m = model
        phi = model.phi if phi is None else phi
        self.phi = float("inf") if poisson or phi is None or not np.isfinite(phi) else float(phi)
        self.draws: list[dict[str, torch.Tensor]] = []
        self.seconds = 0.0

    def sample(self, draws: int, seed: int | None = None, log=None, sweeps: int = 0, **_ignored
               ) -> list[dict[str, torch.Tensor]]:
        """``draws`` posterior draws of the effects, as dictionaries x̂ + δ_s (the interaction's at the MAP), each then
        given ``sweeps`` sweeps of exact conditional redraws of the levels (`_level_sweep`)."""
        t0 = time.time()
        seed = seed if seed is not None else config.seed("laplace", self.m.key())
        nw = solver.StructuredNewton(self.m)
        x_hat = {k: v.detach() for k, v in self.m.effects().items()}
        f = nw.factors(x_hat) if hasattr(self.m, "cell_derivatives") else nw.nb_factors(x_hat, self.phi)
        d = nw.draws(f, draws, seed)
        self.draws = []
        for s in range(draws):
            self.draws.append({**x_hat, **{k: x_hat[k] + torch.as_tensor(v[..., s].reshape(x_hat[k].shape),
                                                                         dtype=x_hat[k].dtype, device=x_hat[k].device)
                                           for k, v in d.items()}})
        if sweeps:
            rng = np.random.default_rng(seed + 1)
            for x in self.draws:
                for _ in range(sweeps):
                    self._level_sweep(x, rng)
        self.seconds = time.time() - t0
        if log:
            log(f"{draws} exact Laplace draws, {sweeps} level sweeps, {self.seconds:.1f}s")
        return self.draws

    # ---- N2: the levels from their exact conditionals ------------------------------------------

    def _level_sweep(self, x: dict[str, torch.Tensor], rng: np.random.Generator) -> None:
        """One Gibbs sweep, in place, over the nested levels of a draw: b0, θ_grp, θ_cat, then v_cat, each element
        from its exact conditional given the rest, p(θ) ∝ exp(Y θ − M e^(θ − θ_d) − τθ²/2) (Poisson: Y the events
        the level carries, M their expectation at the draw's θ_d; `_conditional`). The fit's centrings (θ_grp
        centred, θ_cat centred within its group) are restored after each, moving the means up the tree, which leaves
        every μ unchanged.

        Why (N2; evaluation 2026-10-06, SBC): a Gaussian in η gives a level with few events a symmetric right tail,
        where its exact posterior is cut by the likelihood, and exp() of that tail dominates every sum. On SIM VII
        (277 deaths) 100 Laplace draws put the expected total at a mean of 9.0 million and a median of 921 (10–90 %:
        519–13,864); one sweep of θ_cat and v_cat alone, at 290 and 290 (271–310) (2026-10-07). Poisson only:
        under NB weights the conditional needs every cell, not the level's totals."""
        if np.isfinite(self.phi):
            raise NotImplementedError("level sweeps are Poisson: the NB conditional is not built")
        m = self.m
        d = m.data
        E, U = len(d.leaves), m.N.shape[0]
        grp = m.grp.cpu().numpy()
        K = int(grp.max()) + 1
        if not hasattr(self, "_y"):
            y_eu = np.zeros((E, U))
            np.add.at(y_eu, (d.e, d.u), d.y)
            self._y = y_eu
        y_eu = self._y
        y_e = y_eu.sum(1)
        with torch.no_grad():
            pt = m._place_time(x)                                                         # [K, U, T]
            base = pt.sum(-1)[m.grp]                                                      # [E, U]
            lf = m.leaf_factor(x)
            if lf is not None:
                act, logf = lf
                base[act] = (pt[m.grp[act]] * torch.exp(logf)).sum(-1)
        base = base.cpu().numpy()
        b0 = float(x["b0"].reshape(-1)[0])
        thg = x["th_grp"][0].cpu().numpy().astype(float).copy()
        thc = x["th_cat"][0].cpu().numpy().astype(float).copy()
        vc = x["v_cat"].cpu().numpy().astype(float).copy()
        tau = {n: m.components[n].tau for n in ("th_grp", "th_cat", "v_cat")}

        def mu_eu():
            return np.exp(b0 + thg[grp] + thc)[:, None] * np.exp(vc) * base

        b0 = float(_conditional(np.array([y_e.sum()]), np.array([mu_eu().sum()]), np.array([b0]), 0.0, rng)[0])
        mk = np.bincount(grp, weights=mu_eu().sum(1), minlength=K)
        thg = _conditional(np.bincount(grp, weights=y_e, minlength=K), mk, thg, tau["th_grp"], rng)
        c = thg.mean()
        thg, b0 = thg - c, b0 + c
        thc = _conditional(y_e, mu_eu().sum(1), thc, tau["th_cat"], rng)
        ck = np.bincount(grp, weights=thc, minlength=K) / np.maximum(np.bincount(grp, minlength=K), 1)
        thc, thg = thc - ck[grp], thg + ck
        c = thg.mean()
        thg, b0 = thg - c, b0 + c
        vc = _conditional(y_eu, mu_eu(), vc, tau["v_cat"], rng)
        dt, dev = x["b0"].dtype, x["b0"].device
        x["b0"] = torch.full_like(x["b0"], b0)
        x["th_grp"] = torch.as_tensor(thg[None, :], dtype=dt, device=dev)
        x["th_cat"] = torch.as_tensor(thc[None, :], dtype=dt, device=dev)
        x["v_cat"] = torch.as_tensor(vc, dtype=dt, device=dev)

    # ---- Fellner-Schall on the full posterior covariance (a diagnostic) -----------------------

    def fellner_schall(self) -> dict[str, dict[str, float]]:
        """The Fellner-Schall update of every strength with the posterior covariance read from the draws:
        τ' = (rank − tr(τQΣ)) / (x̂ᵀQx̂), the trace the mean of dᵀ(τQ)d over the displacements d = x_s − x̂."""
        if not self.draws:
            raise RuntimeError("no draws: call sample() first")
        x_hat = self.m.effects()
        out = {}
        for name, c in self.m.components.items():
            if name.startswith("ix_"):
                continue
            Q = sp.kron(sp.identity(c.batch), c.shape.Q, format="csr")
            xv = x_hat[name].detach().cpu().numpy().ravel()
            trace = float(np.mean([c.tau * (dv @ (Q @ dv)) for dv in
                                   ((x[name] - x_hat[name]).detach().cpu().numpy().ravel() for x in self.draws)]))
            quad = float(xv @ (Q @ xv))
            new = (c.rank - trace) / max(quad, 1e-12) if c.rank > 0 else c.tau
            out[name] = {"tau": c.tau, "proposal": float(new), "trace": trace, "rank": float(c.rank), "quad": quad}
        return out

    # ---- the predictive of an aggregate -------------------------------------------------------

    def moments(self, leaves: np.ndarray, spatial: bool = True, relevel: bool = False,
                x_fn=None) -> dict[str, np.ndarray]:
        """The posterior-predictive moments of a field's μ[u, t] over the draws: ``mean`` E μ,
        ``var`` Var μ, ``mu2`` E Σ μ²_cells (the aggregate's own overdispersion), and ``point``, the
        MAP's μ. ``relevel`` re-levels each draw to its spatial total (tier B0). ``x_fn`` maps each
        draw's effects (the prospective tier extrapolates the history of each draw) and returns
        (model, effects) to evaluate."""
        if not self.draws:
            raise RuntimeError("no draws: call sample() first")
        n, s1, s2, sm2 = 0, 0.0, 0.0, 0.0
        with torch.no_grad():
            for x in self.draws:
                tm, xx = (self.m, x) if x_fn is None else x_fn(x)
                mu, mu2 = tm.expected(leaves, spatial, x=xx)
                if relevel:
                    ref, _ = tm.expected(leaves, True, x=xx)
                    c = ref.sum(0) / np.maximum(mu.sum(0), 1e-300)
                    mu, mu2 = mu * c, mu2 * c ** 2
                n += 1
                s1 = s1 + mu
                s2 = s2 + mu ** 2
                sm2 = sm2 + mu2
        mean = s1 / n
        return {"mean": mean, "var": np.maximum(s2 / n - mean ** 2, 0.0) * n / max(n - 1, 1), "mu2": sm2 / n}


def _conditional(y: np.ndarray, mu: np.ndarray, theta: np.ndarray, tau: float, rng: np.random.Generator,
                 points: int = 401, chunk: int = 20000) -> np.ndarray:
    """Exact draws, elementwise, of θ from p(θ) ∝ exp(y θ − μ e^(θ − θ_d) − τθ²/2): ``mu`` the expected count at the
    current ``theta`` (θ_d), τ the level's prior precision (0: flat). Log-concave and one-dimensional: the mode by
    Newton, then the inverse CDF on a grid of ±8 conditional sd around it."""
    shape = theta.shape
    y, mu, td = (np.broadcast_to(a, shape).ravel().astype(float) for a in (y, mu, theta))
    mu = np.maximum(mu, 1e-300)
    result = np.empty_like(td)
    # a level with no events whose expectation stays negligible six prior sds up has the prior as its conditional (to
    # within e^(−10⁻⁴)): drawn from it directly; most leaf-places of a sparse block are such
    if tau > 0:
        prior = (y == 0) & (mu * np.exp(6.0 / np.sqrt(tau) - td) < 1e-4)
        result[prior] = rng.standard_normal(int(prior.sum())) / np.sqrt(tau)
        if prior.all():
            return result.reshape(shape)
        rest = ~prior
        y, mu, td = y[rest], mu[rest], td[rest]
    else:
        rest = np.ones(td.shape, dtype=bool)
    th = td.copy()
    for _ in range(60):
        e = mu * np.exp(th - td)
        step = (y - e - tau * th) / (e + tau + 1e-12)
        th = th + np.clip(step, -2.0, 2.0)
        if np.abs(step).max() < 1e-8:
            break
    sd = 1.0 / np.sqrt(mu * np.exp(th - td) + tau + 1e-12)
    out = np.empty_like(th)
    grid = np.linspace(-8.0, 8.0, points)
    for i in range(0, th.size, chunk):
        sl = slice(i, i + chunk)
        z = th[sl, None] + sd[sl, None] * grid[None, :]
        lp = y[sl, None] * z - mu[sl, None] * np.exp(z - td[sl, None]) - 0.5 * tau * z ** 2
        w = np.exp(lp - lp.max(1, keepdims=True))
        c = np.cumsum(w, 1)
        c /= c[:, -1:]
        k = (c < rng.random(c.shape[0])[:, None]).sum(1)
        lo = np.clip(k - 1, 0, points - 1)
        out[sl] = z[np.arange(c.shape[0]), lo] + sd[sl] * (grid[1] - grid[0]) * rng.random(c.shape[0]) * (k > 0)
    result[rest] = out
    return result.reshape(shape)


def predictive_phi(mean: np.ndarray, var: np.ndarray, mu2: np.ndarray, phi: float) -> np.ndarray:
    """The dispersion of the NB matched to the posterior predictive's first two moments.

    y | θ is a sum of independent NB(μ_i, φ) cells: Var(y | θ) = Σμ + Σμ²/φ. Integrating over θ:
    Var y = E[Σμ] + E[Σμ²]/φ + Var(Σμ). The NB(m, φ_eff) with the same mean and variance has
        1/φ_eff = (E[Σμ²]/φ + Var(Σμ)) / m².
    With no parameter uncertainty this is the aggregate dispersion φ μ̂²/Σμ̂² of ``surprise``."""
    inv = (mu2 / (phi if np.isfinite(phi) else np.inf) + var) / np.maximum(mean, 1e-300) ** 2
    return np.divide(1.0, inv, out=np.full(mean.shape, np.inf), where=inv > 0)
