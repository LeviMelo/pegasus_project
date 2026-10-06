"""The Laplace approximation of the monolith's posterior (ARCHITECTURE §5.3).

At the MAP θ̂ the posterior of the latent effects is N(θ̂, H⁻¹) with

    H = Fᵀ W F + Cᵀ (⊕ τ_e Q_e) C

C maps the raw parameters to the centred effects, F maps effects to the three additive parts of a
cell's linear predictor (η[e,u,t,g] = a[e,u] + b[e,t] + c[e,g] + log N), and W holds the cells'
information. The likelihood's information is the negative binomial's expected one,
w = φ μ / (φ + μ) (the same weight as ARCHITECTURE §6.3): the mean is fitted by Poisson
quasi-likelihood, but the cells it must be uncertain about are overdispersed, and the Poisson
information (w = μ) understates the posterior variance by 1 + μ/φ in the cells that carry it.

**The Hessian is never formed.** Because η is additive over (u, t, g), FᵀWF depends on the weights
only through their *pairwise marginal sums* per leaf (W_ut, W_ug, W_tg and the three one-way sums),
which one pass over the leaf slabs [U, T, G] computes (the size of the population tensor, P10).
A Hessian–vector product is then three small contractions per leaf. Posterior draws are by
perturbation (Papandreou & Yuille 2010): H δ = Fᵀ W^{1/2} ε₁ + Cᵀ (τQ)^{1/2} ε₂ has covariance H,
so δ = H⁻¹(…) is a draw of θ − θ̂, solved by preconditioned conjugate gradients. Every cell's
marginal variance is then estimated with relative error √(2/S), whatever the correlation between
cells (a Hutchinson probe in cell space errs with the correlations), and the predictive of any
aggregate (a field's μ[u, t], the prospective tier) comes from the same draws.

``measure_laplace.py`` compares the draws with an exact dense inverse on a small block.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import torch

from . import config, monolith


@dataclass
class Solve:
    iterations: int
    residual: float


class Posterior:
    """The Laplace posterior of one fitted count block (a `monolith.Monolith`)."""

    def __init__(self, model: monolith.Monolith, phi: float | None = None, poisson: bool = False):
        if isinstance(model, monolith.MarkModel):
            raise NotImplementedError("the Laplace posterior is built for count blocks")
        if getattr(model, "ix_on", False):
            raise NotImplementedError("the Laplace posterior is built for effects linear in η; the low-rank interaction is not (ADR-0021)")
        self.m = model
        self.dtype, self.device = model.dtype, model.device
        phi = model.phi if phi is None else phi
        self.phi = float("inf") if poisson or not np.isfinite(phi) else float(phi)
        self.names = ["b0", *model.components]
        self.shapes = [tuple(model.params[k].shape) for k in self.names]
        self.sizes = [int(np.prod(s)) for s in self.shapes]
        self.theta0 = self.flat({k: model.params[k].detach() for k in self.names})
        self._W: dict[str, torch.Tensor] | None = None
        self._noise: dict[int, list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]]] = {}
        self._prior_factor: dict[str, tuple] = {}
        self.draws: list[dict[str, torch.Tensor]] = []
        self.solves: list[Solve] = []
        self._build_map()

    # ---- parameters <-> vectors ---------------------------------------------------------------

    def flat(self, d: dict[str, torch.Tensor]) -> torch.Tensor:
        return torch.cat([d[k].reshape(-1) for k in self.names])

    def unflat(self, v: torch.Tensor) -> dict[str, torch.Tensor]:
        out, i = {}, 0
        for k, shape, n in zip(self.names, self.shapes, self.sizes, strict=True):
            out[k] = v[i:i + n].view(shape)
            i += n
        return out

    # ---- the linear maps ----------------------------------------------------------------------

    def design(self, x: dict[str, torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """The three additive parts of the linear predictor per leaf: a [E, U], b [E, T], c [E, G]."""
        m, grp = self.m, self.m.grp
        sv = x["s_all"][0] + x["v_all"][0]
        a = ((x["b0"][0] + x["th_grp"][0][grp] + x["th_cat"][0])[:, None] + x["v_cat"] + sv[None, :]
             + (x["s_grp"] + x["v_grp"])[grp])
        b = m._time(x)[grp]
        c = (x["f_all"][0][None, :] + x["f_grp"])[grp]
        return a, b, c

    def _build_map(self) -> None:
        """θ ↦ (a, b, c, centred effects): linear, so one vector–Jacobian product serves every call."""
        names = self.names

        def fun(theta: torch.Tensor):
            x = self.m.effects(self.unflat(theta))
            return (*self.design(x), tuple(x[k] for k in names))

        self._fun = fun
        _, self._vjp = torch.func.vjp(fun, self.theta0)
        self._eff_shapes = [tuple(e.shape) for e in fun(self.theta0)[3]]

    def effects_of(self, delta: torch.Tensor) -> dict[str, torch.Tensor]:
        """The centred effects of a parameter displacement (the map is linear)."""
        return self.m.effects(self.unflat(delta))

    # ---- the likelihood's information ---------------------------------------------------------

    def _slabs(self, x: dict[str, torch.Tensor]):
        """Yield (leaf, [U, T, G] information weights) one leaf slab at a time."""
        m = self.m
        lp = m._leaf_place(x)                                                       # [E, U]
        lin = (m._time(x)[:, None, :] + (x["s_all"][0] + x["v_all"][0])[None, :, None]
               + (x["s_grp"] + x["v_grp"])[:, :, None])
        base = torch.exp(lin)                                                       # [K, U, T]
        prof = torch.exp(x["f_all"] + x["f_grp"])                                   # [K, G]
        for e in range(lp.shape[0]):
            k = int(m.grp[e])
            mu = lp[e][:, None, None] * base[k][:, :, None] * m.N * prof[k][None, None, :]
            yield e, (mu if not np.isfinite(self.phi) else self.phi * mu / (self.phi + mu))

    def information(self, draws: int = 0, seed: int | None = None) -> None:
        """One pass over the leaf slabs: the pairwise marginals of the weights, and ``draws``
        likelihood-noise vectors (the (a, b, c) reductions of √w·ε) for perturbation sampling."""
        m = self.m
        E, (U, T, G) = len(m.data.leaves), m.N.shape
        kw = {"dtype": self.dtype, "device": self.device}
        W = {"u": torch.zeros(E, U, **kw), "t": torch.zeros(E, T, **kw), "g": torch.zeros(E, G, **kw),
             "ut": torch.zeros(E, U, T, **kw), "ug": torch.zeros(E, U, G, **kw), "tg": torch.zeros(E, T, G, **kw)}
        noise = [(torch.zeros(draws, E, U, **kw), torch.zeros(draws, E, T, **kw), torch.zeros(draws, E, G, **kw))]
        gen = torch.Generator(device=self.device)
        gen.manual_seed(seed if seed is not None else config.seed("laplace", "likelihood", m.key()))
        with torch.no_grad():
            for e, w in self._slabs(m.effects()):
                W["ut"][e], W["ug"][e], W["tg"][e] = w.sum(2), w.sum(1), w.sum(0)
                W["u"][e], W["t"][e], W["g"][e] = w.sum((1, 2)), w.sum((0, 2)), w.sum((0, 1))
                if draws:
                    sw = torch.sqrt(w)
                    for s in range(draws):
                        z = sw * torch.randn(w.shape, generator=gen, **kw)
                        noise[0][0][s, e], noise[0][1][s, e], noise[0][2][s, e] = z.sum((1, 2)), z.sum((0, 2)), z.sum((0, 1))
        self._W = W
        self._noise = {draws: noise} if draws else {}
        self._diag = None
        self._blocks = None

    def _info_mul(self, a: torch.Tensor, b: torch.Tensor, c: torch.Tensor):
        W = self._W
        ra = W["u"] * a + torch.einsum("eut,et->eu", W["ut"], b) + torch.einsum("eug,eg->eu", W["ug"], c)
        rb = torch.einsum("eut,eu->et", W["ut"], a) + W["t"] * b + torch.einsum("etg,eg->et", W["tg"], c)
        rc = torch.einsum("eug,eu->eg", W["ug"], a) + torch.einsum("etg,et->eg", W["tg"], b) + W["g"] * c
        return ra, rb, rc

    # ---- the penalty --------------------------------------------------------------------------

    def _tauQ(self, xs: tuple[torch.Tensor, ...]) -> tuple[torch.Tensor, ...]:
        """τ_e Q_e x_e per effect (zero for the unpenalised b0)."""
        out = [torch.zeros_like(xs[0])]
        for (name, c), x in zip(self.m.components.items(), xs[1:], strict=True):
            v = x.reshape(c.batch, -1)
            q = v if c.shape.name.startswith("iid") else torch.sparse.mm(self.m._Q[name], v.T).T
            out.append((c.tau * q).reshape(x.shape))
        return tuple(out)

    def hvp(self, v: torch.Tensor) -> torch.Tensor:
        """H v for a raw-parameter vector, exactly: Fᵀ W F v + Cᵀ τQ C v."""
        a, b, c, xs = self._fun(v)
        ra, rb, rc = self._info_mul(a, b, c)
        return self._vjp((ra, rb, rc, self._tauQ(xs)))[0]

    def diagonal(self) -> torch.Tensor:
        """The Hessian's diagonal, to the centring's approximation: Σ w over the cells an entry
        touches, plus τ Q_ii (the preconditioner)."""
        if getattr(self, "_diag", None) is None:
            W = self._W
            zero_x = tuple(torch.zeros(sh, dtype=self.dtype, device=self.device) for sh in self._eff_shapes)
            lik = self._vjp((W["u"], W["t"], W["g"], zero_x))[0]
            pen = []
            for c in self.m.components.values():
                d = torch.as_tensor(c.shape.Q.diagonal(), dtype=self.dtype, device=self.device)
                pen.append((c.tau * d[None, :].expand(c.batch, -1)).reshape(-1))
            d = lik + torch.cat([torch.zeros(self.sizes[0], dtype=self.dtype, device=self.device), *pen])
            self._diag = torch.where(d > 1e-12 * d.max(), d, torch.ones_like(d))
        return self._diag

    # ---- conjugate gradients ------------------------------------------------------------------

    def _block_preconditioner(self) -> list:
        """Block-Jacobi per effect, in effect space: B_e = diag(Σ w over the cells an entry touches)
        + τ_e Q_e, one sparse LU per batch row. The diagonal alone treats a smooth ICAR/RW mode as
        stiff as a rough one; with τ up to 1e8 (effects shrunk to nothing) that is a condition number
        near 1e5 and CG stalls. The coupling *between* effects (s, v, v_cat all explain the same
        a[e, u]) is left to CG: it costs a factor of about the number of such effects."""
        if self._blocks is not None:
            return self._blocks
        W, x_hat = self._W, self.m.effects()
        with torch.no_grad():
            xs = tuple(x_hat[k] for k in self.names)
            _, vj = torch.func.vjp(lambda t: self.design(dict(zip(self.names, t, strict=True))), xs)
            d = vj((W["u"], W["t"], W["g"]))[0]
        blocks: list = [("diag", d[0].clamp_min(1e-12))]
        for c, di in zip(self.m.components.values(), d[1:], strict=True):
            Q = c.shape.Q.tocsr()
            dd = di.reshape(c.batch, -1).cpu().numpy()
            if (Q - sp.diags(Q.diagonal())).nnz == 0:
                tot = dd + c.tau * Q.diagonal()[None, :]
                blocks.append(("diag", torch.as_tensor(np.maximum(tot, 1e-12 * max(tot.max(), 1e-300)),
                                                       dtype=self.dtype, device=self.device).reshape(di.shape)))
                continue
            lus = []
            for row in dd:
                A = (c.tau * Q + sp.diags(row)).tocsc()
                ridge = 1e-8 * A.diagonal().max() + 1e-12
                lus.append(spla.splu(A + ridge * sp.eye(A.shape[0], format="csc")))
            blocks.append(("lu", lus))
        self._blocks = blocks
        return blocks

    def _apply_blocks(self, xs: tuple[torch.Tensor, ...]) -> tuple[torch.Tensor, ...]:
        out = []
        for (kind, data), x in zip(self._block_preconditioner(), xs, strict=True):
            if kind == "diag":
                out.append(x / data)
            else:
                v = x.reshape(len(data), -1).cpu().numpy()
                r = np.stack([lu.solve(row) for lu, row in zip(data, v, strict=True)])
                out.append(torch.as_tensor(r, dtype=self.dtype, device=self.device).reshape(x.shape))
        return tuple(out)

    def precondition(self, r: torch.Tensor, kind: str = "block") -> torch.Tensor:
        """M⁻¹ r. ``block``: Cᵀ B⁻¹ C r (C, the centring, is an orthogonal projector, so this is
        symmetric positive semi-definite on the range CG lives in); ``diag``: r / diag H."""
        if kind == "diag":
            return r / self.diagonal()
        xs = self.effects_of(r)
        z = self._apply_blocks(tuple(xs[k] for k in self.names))
        return self._vjp((torch.zeros_like(self._W["u"]), torch.zeros_like(self._W["t"]),
                          torch.zeros_like(self._W["g"]), z))[0]

    def solve(self, rhs: torch.Tensor, tol: float = 1e-3, maxiter: int = 1000,
              precond: str = "block") -> tuple[torch.Tensor, Solve]:
        """H x = rhs by preconditioned CG (H is singular along the centring's null space, which
        rhs and every CG direction's image leave alone)."""
        x = torch.zeros_like(rhs)
        r = rhs.clone()
        z = self.precondition(r, precond)
        d = z.clone()
        rz = float(r @ z)
        bnorm = float(rhs.norm())
        for it in range(1, maxiter + 1):  # noqa: B007
            Hd = self.hvp(d)
            alpha = rz / float(d @ Hd)
            x = x + alpha * d
            r = r - alpha * Hd
            if float(r.norm()) <= tol * bnorm:
                break
            z = self.precondition(r, precond)
            rz_new = float(r @ z)
            d = z + (rz_new / rz) * d
            rz = rz_new
        return x, Solve(it, float(r.norm()) / bnorm)

    # ---- posterior draws ----------------------------------------------------------------------

    def _prior_noise(self, gen: torch.Generator) -> tuple[torch.Tensor, ...]:
        """One draw per penalised effect with covariance τ_e Q_e (b0: none), in effect space."""
        out = [torch.zeros(self._eff_shapes[0], dtype=self.dtype, device=self.device)]
        for (name, c), shape in zip(self.m.components.items(), self._eff_shapes[1:], strict=True):
            n = c.shape.Q.shape[0]
            eps = torch.randn((c.batch, n), generator=gen, dtype=self.dtype, device=self.device)
            L = self._prior_factor.get(name)
            if L is None:
                L = self._prior_factor[name] = _precision_factor(c.shape)
            if L[0] == "diag":
                z = eps * torch.as_tensor(L[1], dtype=self.dtype, device=self.device)
            elif L[0] == "dense":
                z = eps @ torch.as_tensor(L[1], dtype=self.dtype, device=self.device).T
            else:                                   # edges: Q = Σ a_ij (e_i − e_j)(e_i − e_j)ᵀ + diag(r)
                i, j, a, r = (torch.as_tensor(q, device=self.device) for q in L[1:])
                ee = torch.randn((c.batch, len(a)), generator=gen, dtype=self.dtype, device=self.device)
                z = (eps * torch.sqrt(r.to(self.dtype))
                     ).index_add(1, i, ee * torch.sqrt(a.to(self.dtype))).index_add(1, j, -ee * torch.sqrt(a.to(self.dtype)))
            out.append((np.sqrt(c.tau) * z).reshape(shape))
        return tuple(out)

    def sample(self, draws: int, seed: int | None = None, tol: float = 1e-3, precond: str = "block", log=None) -> list[dict[str, torch.Tensor]]:
        """``draws`` posterior displacements, as centred-effect dictionaries x̂ + C δ_s."""
        t0 = time.time()
        seed = seed if seed is not None else config.seed("laplace", self.m.key())
        self.information(draws, seed)
        la, lb, lc = self._noise[draws][0]
        gen = torch.Generator(device=self.device)
        gen.manual_seed(seed + 1)
        x_hat = self.m.effects()
        self.draws, self.solves = [], []
        for s in range(draws):
            rhs = self._vjp((la[s], lb[s], lc[s], self._prior_noise(gen)))[0]
            delta, info = self.solve(rhs, tol=tol, precond=precond)
            self.solves.append(info)
            with torch.no_grad():
                dx = self.effects_of(delta)
                self.draws.append({k: x_hat[k] + dx[k] for k in dx})
            if log:
                log(f"draw {s + 1}/{draws}: {info.iterations} CG iterations, residual {info.residual:.1e}, "
                    f"{time.time() - t0:.0f}s")
        return self.draws

    # ---- Fellner-Schall on the full Hessian ---------------------------------------------------

    def fellner_schall(self) -> dict[str, dict[str, float]]:
        """The Fellner-Schall update of every tau with the full posterior covariance instead of
        the block-diagonal Poisson Fisher diagonal: tau' = (rank - tr(tau Q Sigma_ee)) / (x'Qx), the
        trace estimated from the draws as the mean of d'(tau Q)d over the displacements d = x_s - x
        of effect e. Returns, per component, the current tau, the proposal, and the trace."""
        if not self.draws:
            raise RuntimeError("no draws: call sample() first")
        x_hat = self.m.effects()
        tr = dict.fromkeys(self.m.components, 0.0)
        for xs in self.draws:
            d = tuple(xs[k] - x_hat[k] for k in self.names)
            q = self._tauQ(d)
            for i, name in enumerate(self.m.components, start=1):
                tr[name] += float((d[i] * q[i]).sum())
        out = {}
        q_hat = self._tauQ(tuple(x_hat[k] for k in self.names))
        for i, (name, c) in enumerate(self.m.components.items(), start=1):
            trace = tr[name] / len(self.draws)
            quad = float((x_hat[name] * q_hat[i]).sum()) / c.tau
            new = (c.rank - trace) / max(quad, 1e-12) if c.rank > 0 else c.tau
            out[name] = {"tau": c.tau, "proposal": float(new), "trace": trace, "rank": float(c.rank),
                         "quad": quad}
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


def predictive_phi(mean: np.ndarray, var: np.ndarray, mu2: np.ndarray, phi: float) -> np.ndarray:
    """The dispersion of the NB matched to the posterior predictive's first two moments.

    y | θ is a sum of independent NB(μ_i, φ) cells: Var(y | θ) = Σμ + Σμ²/φ. Integrating over θ:
    Var y = E[Σμ] + E[Σμ²]/φ + Var(Σμ). The NB(m, φ_eff) with the same mean and variance has
        1/φ_eff = (E[Σμ²]/φ + Var(Σμ)) / m².
    With no parameter uncertainty this is the aggregate dispersion φ μ̂²/Σμ̂² of ``surprise``."""
    inv = (mu2 / (phi if np.isfinite(phi) else np.inf) + var) / np.maximum(mean, 1e-300) ** 2
    return np.divide(1.0, inv, out=np.full(mean.shape, np.inf), where=inv > 0)


# ---------------------------------------------------------------------- helpers


def _precision_factor(shape) -> tuple:
    """A square-root factor of a shape's Q for perturbation noise: ``diag`` (Q diagonal), ``edges``
    (a graph Laplacian: Σ a_ij (e_i − e_j)(e_i − e_j)ᵀ + diag r) or ``dense`` (a random walk's
    small Q, by eigendecomposition)."""
    Q = shape.Q.tocsr()
    off = Q - sp.diags(Q.diagonal())
    if off.nnz == 0:
        return ("diag", np.sqrt(np.clip(Q.diagonal(), 0, None)))
    if shape.name.startswith("icar"):
        up = sp.triu(off, k=1).tocoo()
        a = -up.data
        assert (a >= -1e-12).all(), "an ICAR precision has non-positive off-diagonals"
        r = Q.diagonal() + np.asarray(off.sum(axis=1)).ravel()          # d_i − Σ_j a_ij
        return ("edges", up.row.astype(np.int64), up.col.astype(np.int64), np.clip(a, 0, None), np.clip(r, 0, None))
    n = Q.shape[0]
    if n > 5000:
        raise NotImplementedError(f"no square-root factor for {shape.name} of size {n}")
    lam, V = np.linalg.eigh(Q.toarray())
    return ("dense", V * np.sqrt(np.clip(lam, 0, None)))
