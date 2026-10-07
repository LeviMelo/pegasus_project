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

    def sample(self, draws: int, seed: int | None = None, log=None, **_ignored) -> list[dict[str, torch.Tensor]]:
        """``draws`` posterior draws of the effects, as dictionaries x̂ + δ_s (the interaction's at the MAP)."""
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
        self.seconds = time.time() - t0
        if log:
            log(f"{draws} exact Laplace draws, {self.seconds:.1f}s")
        return self.draws

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
                with tm.without_offset():           # a draw's mean is e^η: N2's offset is the draws' own spread
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


def marginal(model: monolith.Monolith, draws: int = 100, iterations: int = 12, tol: float = 0.05, poisson: bool = False,
             damping: float = 0.5, seed: int | None = None, log=None) -> monolith.Monolith:
    """N2 (ARCHITECTURE §12; evaluation 2026-10-06, SBC): the mean refitted so that the posterior, not its mode,
    reproduces the data. The joint mode of a log-link hierarchical model sets data-poor effects at zero and moves the
    mass their e^η would carry into the intercept and the large places (the joint-mode bias of GLMMs: Breslow & Lin
    1995; lme4's nAGQ = 0 against the Laplace marginal of nAGQ = 1). SBC showed it on SIM VII and XIII alike: every
    count-scale sum of the Laplace draws above its truth.

    The remedy is the Gaussian variational approximation of a Poisson GLMM (Ormerod & Wand 2012): the posterior is
    N(m, Σ), m solving the score with every cell's mean at e^(η + v/2), v = Var(η | y) the cell's posterior variance
    (to first order, the Laplace marginal likelihood's score in the globals: TMB, Kristensen et al. 2016), and Σ the
    inverse Hessian with the weights at those means. Fixed point: the draws at the current fit give v per
    leaf-place-period (the variance of log μ over the draws), the mean is refitted with the offset v/2 at the same
    strengths (`Monolith.refit`, warm), until the offset moves by less than ``tol``. The returned model's expectation is
    the posterior mean; its draws (`Posterior`) are evaluated without the offset (`Monolith.without_offset`)."""
    m = model
    E = len(m.data.leaves)
    prev = None
    for it in range(iterations):
        t0 = time.time()
        post = Posterior(m, poisson=poisson)
        post.sample(draws, seed=config.seed("marginal", m.key(), it) if seed is None else seed + it)
        U, T = m.N.shape[:2]
        s1 = np.zeros((E, U, T))
        s2 = np.zeros((E, U, T))
        pos = np.ones((E, U, T), dtype=bool)
        with torch.no_grad(), m.without_offset():
            for x in post.draws:
                for e in range(E):
                    mu = m.expected(np.array([e]), True, x=x)[0]
                    pos[e] &= mu > 0
                    lm = np.log(np.maximum(mu, 1e-300))
                    s1[e] += lm
                    s2[e] += lm ** 2
        n = len(post.draws)
        v = np.maximum(s2 / n - (s1 / n) ** 2, 0.0) * n / max(n - 1, 1)
        # pooled over each leaf-place's periods: a sparse cell's variance is its leaf's and place's effects', nearly
        # constant in time, and 100 draws alone left the fixed point moving by ±1 at log-variances near 12 (SIM VII)
        cnt = pos.sum(2, keepdims=True)
        v = np.where(pos, (np.where(pos, v, 0.0).sum(2, keepdims=True) / np.maximum(cnt, 1)), 0.0)
        off = torch.as_tensor(0.5 * v, dtype=m.dtype, device=m.device)
        if prev is not None:                # damped: the plain fixed point oscillated on SIM VII (2026-10-07)
            off = damping * off + (1 - damping) * prev
        moved = float((off - prev).abs().max()) if prev is not None else float(off.abs().max())
        post.draws = []
        m = m.refit(m.data, off=off)
        prev = off
        if log:
            log(f"N2 iteration {it}: offset max {float(off.max()):.3g}, mean {float(off.mean()):.3g}, moved {moved:.3g}, "
                f"{time.time() - t0:.0f}s")
        if moved < tol:
            break
    return m


def predictive_phi(mean: np.ndarray, var: np.ndarray, mu2: np.ndarray, phi: float) -> np.ndarray:
    """The dispersion of the NB matched to the posterior predictive's first two moments.

    y | θ is a sum of independent NB(μ_i, φ) cells: Var(y | θ) = Σμ + Σμ²/φ. Integrating over θ:
    Var y = E[Σμ] + E[Σμ²]/φ + Var(Σμ). The NB(m, φ_eff) with the same mean and variance has
        1/φ_eff = (E[Σμ²]/φ + Var(Σμ)) / m².
    With no parameter uncertainty this is the aggregate dispersion φ μ̂²/Σμ̂² of ``surprise``."""
    inv = (mu2 / (phi if np.isfinite(phi) else np.inf) + var) / np.maximum(mean, 1e-300) ** 2
    return np.divide(1.0, inv, out=np.full(mean.shape, np.inf), where=inv > 0)
