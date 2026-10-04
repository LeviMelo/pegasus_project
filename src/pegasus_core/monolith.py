"""The monolith: one hierarchical model of event intensities (ARCHITECTURE §4–§5).

For a block (one chapter of a classifier tree), leaves e (ICD categories),
places u, years t and groups g = sex × age band:

    y[e,u,t,g] ~ NegBin(μ, φ),   μ = N[u,t,g] · exp(η)
    η = b0 + θ_grp[p(e)] + θ_cat[e]                      levels along the tree
          + f_all[g] + f_grp[p(e), g]                     age–sex profiles (RW2 over age, per sex)
          + h_all[t] + h_grp[p(e), t]                     history (RW2 over years)
          + s_all[u] + v_all[u] + s_grp[p(e),u] + v_grp[p(e),u]   geography (scaled ICAR + iid: BYM)

p(e) is the leaf's ICD group (the profile and geography level). Every effect
is centred along its structure; every strength τ is learned by Fellner–Schall
updates (Wood & Fasiolo 2017) with a block-diagonal Hessian. The mean is fitted
by penalised Poisson likelihood through the factorised sum (§5.1): no empty
cell is ever formed. φ is estimated afterwards by moments (§5.2).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pyarrow as pa
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import torch
from scipy import optimize, special

from . import config, gateway, store, structures

AGE_EDGES = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]  # 18 bands; last is 80+
N_BANDS = len(AGE_EDGES)
TAU_BOUNDS = (1e-8, 1e8)
MAX_TAU_STEP = np.log(10.0)  # Fellner–Schall updates are damped to ×10 per outer iteration
SHRUNK = 1e5                 # a τ above this leaves its effect at a negligible size (sd < 0.003)


def age_band(age: np.ndarray) -> np.ndarray:
    return np.searchsorted(AGE_EDGES, age, side="right") - 1


# ---------------------------------------------------------------------- data


@dataclass
class BlockData:
    """Everything one block's fit needs, as dense arrays no larger than the population tensor."""

    dataset: str
    event: str
    block: str
    years: np.ndarray
    places: np.ndarray
    leaves: list[str]
    groups: list[str]
    leaf_group: np.ndarray            # index into groups, per leaf
    N: np.ndarray                     # [U, T, G] person-years, G = 2 sexes × 18 bands
    e: np.ndarray                     # non-empty cells: leaf, place, year, group, count
    u: np.ndarray
    t: np.ndarray
    g: np.ndarray
    y: np.ndarray
    unallocated: dict[str, int] = field(default_factory=dict)
    key: dict = field(default_factory=dict)


def assemble(dataset: str, event: str, block: str, years: range | list[int]) -> BlockData:
    """One chapter's counts and populations, from the gateway."""
    years = np.array(sorted(set(years)))
    pop = gateway.population(years.tolist())
    places = np.array(sorted(pop.column("u").unique().to_pylist()))
    uidx = {int(c): i for i, c in enumerate(places)}
    tidx = {int(y): i for i, y in enumerate(years)}
    N = np.zeros((len(places), len(years), 2 * N_BANDS))
    pu = np.array([uidx[int(c)] for c in pop.column("u").to_numpy()])
    pt = np.array([tidx[int(y)] for y in pop.column("year").to_numpy()])
    pg = (pop.column("sex").to_numpy().astype(int) - 1) * N_BANDS + age_band(pop.column("age").to_numpy())
    np.add.at(N, (pu, pt, pg), pop.column("n").to_numpy())

    tree = gateway.code_structure("ICD10")
    code, parent, level = (tree.column(c).to_pylist() for c in ("code", "parent", "level"))
    parent_of = dict(zip(code, parent, strict=True))
    level_of = dict(zip(code, level, strict=True))
    categories = sorted(c for c, lv in level_of.items() if lv == "category" and _chapter(c, parent_of) == block)
    groups = sorted({parent_of[c] for c in categories})
    gidx = {g: i for i, g in enumerate(groups)}
    eidx = {c: i for i, c in enumerate(categories)}

    parts, unallocated = [], {}
    for year in years:
        ec = gateway.event_counts(dataset, event, int(year), places=pa.array(places, pa.int32()))
        tab = ec.counts
        cat = np.array([c[:3] for c in tab.column("code").to_pylist()])
        in_block = np.array([c in eidx for c in cat])
        other = ~in_block & np.array([level_of.get(c) is None for c in cat])
        unallocated["code not in ICD-10 tree"] = unallocated.get("code not in ICD-10 tree", 0) + int(
            tab.column("y").to_numpy()[other].sum())
        for r in ec.unallocated.to_pylist():
            if _chapter(str(r["code"] or "")[:3], parent_of) == block:
                unallocated[r["reason"]] = unallocated.get(r["reason"], 0) + int(r["y"])
        sub = tab.filter(pa.array(in_block))
        parts.append((np.array([eidx[c[:3]] for c in sub.column("code").to_pylist()], dtype=np.int64),
                      np.array([uidx[int(x)] for x in sub.column("u").to_numpy()], dtype=np.int64),
                      np.full(sub.num_rows, tidx[int(year)], dtype=np.int64),
                      ((sub.column("sex").to_numpy().astype(np.int64) - 1) * N_BANDS
                       + age_band(sub.column("age").to_numpy())).astype(np.int64),
                      sub.column("y").to_numpy().astype(np.float64)))
    e, u, t, g, y = (np.concatenate(z) for z in zip(*parts, strict=True))
    # several subcategories share a category: sum them into one cell
    flat = ((e * len(places) + u) * len(years) + t) * (2 * N_BANDS) + g
    uniq, inv = np.unique(flat, return_inverse=True)
    ysum = np.bincount(inv, weights=y)
    g = uniq % (2 * N_BANDS)
    rest = uniq // (2 * N_BANDS)
    t, rest = rest % len(years), rest // len(years)
    u, e = rest % len(places), rest // len(places)
    key = {"dataset": dataset, "event": event, "block": block, "years": years.tolist(),
           "data": config.data_version()}
    return BlockData(dataset, event, block, years, places, categories, groups,
                     np.array([gidx[parent_of[c]] for c in categories]), N, e, u, t, g, ysum, unallocated, key)


def _chapter(code: str, parent_of: dict[str, str | None]) -> str | None:
    """The root (chapter) above a code, or None for a code the tree does not hold."""
    if code not in parent_of:
        return None
    node = code
    while parent_of.get(node) is not None:
        node = parent_of[node]  # type: ignore[assignment]
    return node


# ---------------------------------------------------------------------- model


@dataclass
class Component:
    name: str
    shape: structures.Shape     # precision along the structured (last) axis
    batch: int                  # leading dimension (1 when shared by the block)
    tau: float = 1.0

    @property
    def rank(self) -> int:
        return self.shape.rank * self.batch


class Monolith:
    """One block's fitted model."""

    def __init__(self, data: BlockData, graph: tuple[np.ndarray, np.ndarray], graph_kind: str,
                 device: str = "cpu"):
        self.data = data
        self.graph_kind = graph_kind
        self.device = torch.device(device)
        self.dtype = torch.float64
        nU, nT, nG = data.N.shape
        nE, nGrp = len(data.leaves), len(data.groups)
        icar = _cached_icar(graph[0], graph[1], nU)
        rw_age = structures.random_walk(N_BANDS, order=2)
        rw_t = structures.random_walk(nT, order=2 if nT >= 4 else 1)
        self.components = {
            "th_grp": Component("th_grp", structures.iid(nGrp), 1),
            "th_cat": Component("th_cat", _within_groups(data.leaf_group, nE), 1),
            "f_all": Component("f_all", rw_age, 2),
            "f_grp": Component("f_grp", rw_age, nGrp * 2),
            "h_all": Component("h_all", rw_t, 1),
            "h_grp": Component("h_grp", rw_t, nGrp),
            "s_all": Component("s_all", icar, 1),
            "v_all": Component("v_all", structures.iid(nU), 1),
            "s_grp": Component("s_grp", icar, nGrp),
            "v_grp": Component("v_grp", structures.iid(nU), nGrp),
            "v_cat": Component("v_cat", structures.iid(nU), nE),
        }
        self.params = {"b0": torch.zeros(1, dtype=self.dtype, device=self.device, requires_grad=True)}
        for c in self.components.values():
            self.params[c.name] = torch.zeros((c.batch, c.shape.Q.shape[0]), dtype=self.dtype,
                                              device=self.device, requires_grad=True)
        self._Q = {c.name: _torch_sparse(c.shape.Q, self.dtype, self.device) for c in self.components.values()}
        self._labels = {c.name: torch.as_tensor(c.shape.components if c.shape.components is not None
                                                else np.zeros(c.shape.Q.shape[0], dtype=int), device=self.device)
                        for c in self.components.values()}
        t = lambda a, dt=torch.int64: torch.as_tensor(a, dtype=dt, device=self.device)  # noqa: E731
        self.N = t(data.N, self.dtype)
        self.logN_nnz = torch.log(t(data.N[data.u, data.t, data.g], self.dtype))
        self.e, self.u, self.tt, self.g = t(data.e), t(data.u), t(data.t), t(data.g)
        self.y = t(data.y, self.dtype)
        self.grp = t(data.leaf_group)
        self.n_cells = float(nE * np.count_nonzero(data.N > 0))
        self.phi: float = float("inf")
        self.history: list[dict] = []
        self.trace_log: list[tuple] = []
        self.p_e = self.grp[self.e]
        self.scale = float(data.y.sum())

    # ---- effects (centred) -------------------------------------------------

    def effects(self) -> dict[str, torch.Tensor]:
        out = {"b0": self.params["b0"]}
        for name in self.components:
            v = _centre(self.params[name], self._labels[name])
            # group deviations sum to zero across groups; a leaf's place effect within its group
            if name in ("h_grp", "s_grp", "v_grp"):
                v = v - v.mean(dim=0, keepdim=True)
            elif name == "f_grp":
                v = (v.reshape(-1, 2, N_BANDS) - v.reshape(-1, 2, N_BANDS).mean(dim=0, keepdim=True)).reshape(v.shape)
            elif name == "v_cat":
                v = _centre(v.T.contiguous(), self.grp).T
            out[name] = v
        nGrp = len(self.data.groups)
        out["f_all"] = out["f_all"].reshape(1, 2 * N_BANDS)
        out["f_grp"] = out["f_grp"].reshape(nGrp, 2 * N_BANDS)
        return out

    def _place_time(self, x: dict[str, torch.Tensor], spatial: bool = True) -> torch.Tensor:
        """[groups, U, T] of exp(h + g) · M: the factor every leaf of a group shares."""
        M = torch.einsum("utg,kg->kut", self.N, torch.exp(x["f_all"] + x["f_grp"]))
        lin = (x["h_all"][0][None, None, :] + x["h_grp"][:, None, :])
        if spatial:
            lin = lin + (x["s_all"][0] + x["v_all"][0])[None, :, None] + (x["s_grp"] + x["v_grp"])[:, :, None]
        return torch.exp(lin) * M

    def _leaf_place(self, x: dict[str, torch.Tensor], spatial: bool = True) -> torch.Tensor:
        """[E, U] exp(b0 + θ_grp + θ_cat + v_cat): the leaf's level and its own place deviation."""
        lin = (x["b0"][0] + x["th_grp"][0][self.grp] + x["th_cat"][0])[:, None]
        return torch.exp(lin + x["v_cat"]) if spatial else torch.exp(lin).expand(-1, self.N.shape[0])

    def _level(self, x: dict[str, torch.Tensor]) -> torch.Tensor:
        """[E] exp(b0 + θ_grp + θ_cat)."""
        return torch.exp(x["b0"][0] + x["th_grp"][0][self.grp] + x["th_cat"][0])

    def eta_nnz(self, x: dict[str, torch.Tensor], spatial: bool = True) -> torch.Tensor:
        p = self.p_e
        eta = (x["b0"][0] + x["th_grp"][0][p] + x["th_cat"][0][self.e] + x["f_all"][0][self.g] + x["f_grp"][p, self.g]
               + x["h_all"][0][self.tt] + x["h_grp"][p, self.tt] + self.logN_nnz)
        if spatial:
            eta = (eta + x["s_all"][0][self.u] + x["v_all"][0][self.u] + x["s_grp"][p, self.u] + x["v_grp"][p, self.u]
                   + x["v_cat"][self.e, self.u])
        return eta

    def total(self, x: dict[str, torch.Tensor], spatial: bool = True) -> torch.Tensor:
        """Λ = Σ over every cell of μ, through the factorisation."""
        leaf_place = self._leaf_place(x, spatial)                                   # [E, U]
        per_group = torch.zeros((len(self.data.groups), self.N.shape[0]), dtype=self.dtype,
                                device=self.device).index_add_(0, self.grp, leaf_place)  # [K, U]
        return (per_group[:, :, None] * self._place_time(x, spatial)).sum()

    def penalty(self, x: dict[str, torch.Tensor]) -> torch.Tensor:
        out = torch.zeros((), dtype=self.dtype, device=self.device)
        for name, c in self.components.items():
            v = x[name].reshape(c.batch, -1)
            out = out + 0.5 * c.tau * (v * torch.sparse.mm(self._Q[name], v.T).T).sum()
        return out

    def objective(self) -> torch.Tensor:
        """−log L + penalty, divided by the number of events so gradients are of order one."""
        x = self.effects()
        loglik = (self.y * self.eta_nnz(x)).sum() - self.total(x)
        return (-loglik + self.penalty(x)) / self.scale

    # ---- fitting ----------------------------------------------------------------

    def fit(self, outer: int = 25, inner: int = 300, tol: float = 0.02, log=print) -> Monolith:
        start = time.time()
        self._initialise()
        for it in range(outer):
            self._fit_mean(inner)
            changes = self._update_taus()
            self.history.append({"iteration": it, "objective": float(self.objective()) * self.scale,
                                 "taus": {k: c.tau for k, c in self.components.items()}, "seconds": time.time() - start})
            taus = " ".join(f"{k}={c.tau:.3g}" for k, c in self.components.items())
            log(f"outer {it}: objective {self.history[-1]['objective']:.1f}, max τ change {max(changes):.3f}, "
                f"{time.time() - start:.0f}s | {taus}")
            if max(changes) < tol:
                break
        self._fit_mean(inner)
        self.phi = self._dispersion()
        log(f"φ = {self.phi:.3f}; {time.time() - start:.0f}s")
        return self

    def _initialise(self) -> None:
        """Closed-form marginal starting values: the block's rate, then log observed/expected
        by age–sex, by year and by leaf (each against the block's flat rate)."""
        d = self.data
        nE = len(d.leaves)
        rate = d.y.sum() / (d.N.sum() * nE)
        by_g = np.bincount(d.g, weights=d.y, minlength=d.N.shape[2]) / (d.N.sum(axis=(0, 1)) * nE * rate)
        by_t = np.bincount(d.t, weights=d.y, minlength=d.N.shape[1]) / (d.N.sum(axis=(0, 2)) * nE * rate)
        by_e = np.bincount(d.e, weights=d.y, minlength=nE) / (d.N.sum() * rate)
        with torch.no_grad():
            self.params["b0"].fill_(float(np.log(rate)))
            self.params["f_all"].copy_(torch.as_tensor(np.log(np.clip(by_g, 1e-6, None))).reshape(2, -1))
            self.params["h_all"].copy_(torch.as_tensor(np.log(np.clip(by_t, 1e-6, None)))[None, :])
            self.params["th_cat"].copy_(torch.as_tensor(np.log(np.clip(by_e, 1e-6, None)))[None, :])

    def _fit_mean(self, iterations: int) -> None:
        params = list(self.params.values())
        opt = torch.optim.LBFGS(params, lr=1, max_iter=iterations, tolerance_grad=1e-6, tolerance_change=1e-10,
                                history_size=20, line_search_fn="strong_wolfe")

        def closure():
            opt.zero_grad()
            loss = self.objective()
            loss.backward()
            return loss

        opt.step(closure)

    def _update_taus(self) -> list[float]:
        """Fellner–Schall: τ ← (rank − τ·tr(H⁻¹Q)) / (xᵀQx), H ≈ D + τQ per batch row."""
        x = {k: v.detach().requires_grad_(True) for k, v in self.effects().items()}
        lam = self.total(x)
        grads = torch.autograd.grad(lam, [x[k] for k in self.components])
        changes = []
        for (name, c), d in zip(self.components.items(), grads, strict=True):
            D = d.detach().reshape(c.batch, -1).cpu().numpy()  # Poisson: ∂Λ/∂effect = Σμ = the Fisher diagonal
            v = x[name].detach().reshape(c.batch, -1).cpu().numpy()
            Q = c.shape.Q
            quad = float(sum(v[b] @ (Q @ v[b]) for b in range(c.batch)))
            trace = sum(_trace_inv_times(D[b], c.tau, Q) for b in range(c.batch))
            new = (c.rank - c.tau * trace) / max(quad, 1e-12)
            new = float(np.clip(new, c.tau * np.exp(-MAX_TAU_STEP), c.tau * np.exp(MAX_TAU_STEP)))
            new = float(np.clip(new, *TAU_BOUNDS))
            # a τ climbing past SHRUNK has shrunk its effect to nothing; its further climb is not instability
            changes.append(0.0 if min(new, c.tau) > SHRUNK else abs(np.log(new / c.tau)))
            self.trace_log.append((name, c.rank, quad, trace, c.tau, new))
            c.tau = new
        return changes

    def _dispersion(self) -> float:
        """φ by maximum likelihood with μ fixed (ARCHITECTURE §5.2). Non-empty cells enter exactly;
        the empty cells' Σ log p(0) = −φ Σ_empty log(1 + μ/φ) is the sum over every cell minus the
        non-empty cells', the former streamed leaf by leaf (one [U, T, G] slab at a time, P10).

        Two estimators failed first, on chapter IX 2010–2023: moments (Pearson residuals of cells
        with tiny μ and y ≥ 1 dominate: φ = 0.013), and a power series for the empty cells
        (they hold 1.95 M of 4.99 M expected events, μ/φ is not small, the series diverges)."""
        with torch.no_grad():
            x = self.effects()
            mu = torch.exp(self.eta_nnz(x)).cpu().numpy()
            lp = self._leaf_place(x)                                              # [E, U]
            lin = (x["h_all"][0][None, None, :] + x["h_grp"][:, None, :]
                   + (x["s_all"][0] + x["v_all"][0])[None, :, None] + (x["s_grp"] + x["v_grp"])[:, :, None])
            base = torch.exp(lin)                                                 # [K, U, T]
            prof = torch.exp(x["f_all"] + x["f_grp"])                             # [K, G]
        y = self.data.y

        def all_cells_log1p(phi: float) -> float:
            total = 0.0
            with torch.no_grad():
                for e in range(lp.shape[0]):
                    k = int(self.grp[e])
                    m = lp[e][:, None, None] * base[k][:, :, None] * self.N * prof[k][None, None, :]
                    total += float(torch.log1p(m / phi).sum())
            return total

        def nll(log_phi: float) -> float:
            phi = float(np.exp(log_phi))
            full = (special.gammaln(y + phi) - special.gammaln(phi) - special.gammaln(y + 1)
                    + phi * np.log(phi / (phi + mu)) + y * np.log(mu / (phi + mu)))
            empty = -phi * (all_cells_log1p(phi) - float(np.log1p(mu / phi).sum()))
            return -(float(full.sum()) + empty)

        res = optimize.minimize_scalar(nll, bounds=(np.log(1e-3), np.log(1e6)), method="bounded",
                                       options={"xatol": 1e-3})
        phi = float(np.exp(res.x))
        self.dispersion_check = {"phi": phi, "evaluations": int(res.nfev),
                                 "loglik_gain_over_poisson": float(nll(np.log(1e6)) - res.fun)}
        return float("inf") if phi > 0.99e6 else phi

    # ---- prediction ---------------------------------------------------------------

    def expected(self, leaves: np.ndarray, spatial: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """For a set of leaves (a node of the tree): μ[u,t] summed over the leaves and groups,
        and Σμ²[u,t] over the underlying cells (for the aggregate's dispersion)."""
        with torch.no_grad():
            x = self.effects()
            lp = self._leaf_place(x, spatial)
            pt = self._place_time(x, spatial)
            sel = torch.as_tensor(leaves, device=self.device)
            K, U = len(self.data.groups), self.N.shape[0]
            w = torch.zeros((K, U), dtype=self.dtype, device=self.device).index_add_(0, self.grp[sel], lp[sel])
            mu = (w[:, :, None] * pt).sum(0)
            M2 = torch.einsum("utg,kg->kut", self.N ** 2, torch.exp(2 * (x["f_all"] + x["f_grp"])))
            lin = x["h_all"][0][None, None, :] + x["h_grp"][:, None, :]
            if spatial:
                lin = lin + (x["s_all"][0] + x["v_all"][0])[None, :, None] + (x["s_grp"] + x["v_grp"])[:, :, None]
            w2 = torch.zeros((K, U), dtype=self.dtype, device=self.device).index_add_(0, self.grp[sel], lp[sel] ** 2)
            mu2 = (w2[:, :, None] * torch.exp(2 * lin) * M2).sum(0)
        return mu.cpu().numpy(), mu2.cpu().numpy()

    def expected_by_group(self, leaves: np.ndarray, spatial: bool = True) -> np.ndarray:
        """μ[u,t,g] summed over the leaves (g = sex × age band)."""
        with torch.no_grad():
            x = self.effects()
            lp = self._leaf_place(x, spatial)
            sel = torch.as_tensor(leaves, device=self.device)
            K, U = len(self.data.groups), self.N.shape[0]
            w = torch.zeros((K, U), dtype=self.dtype, device=self.device).index_add_(0, self.grp[sel], lp[sel])
            lin = x["h_all"][0][None, None, :] + x["h_grp"][:, None, :]
            if spatial:
                lin = lin + (x["s_all"][0] + x["v_all"][0])[None, :, None] + (x["s_grp"] + x["v_grp"])[:, :, None]
            prof = torch.exp(x["f_all"] + x["f_grp"])                                   # [K, G]
            mu = torch.einsum("ku,kut,kg,utg->utg", w, torch.exp(lin), prof, self.N)
        return mu.cpu().numpy()

    def observed(self, leaves: np.ndarray) -> np.ndarray:
        nU, nT, _ = self.data.N.shape
        m = np.isin(self.data.e, leaves)
        out = np.zeros((nU, nT))
        np.add.at(out, (self.data.u[m], self.data.t[m]), self.data.y[m])
        return out

    def observed_by_group(self, leaves: np.ndarray) -> np.ndarray:
        out = np.zeros(self.data.N.shape)
        m = np.isin(self.data.e, leaves)
        np.add.at(out, (self.data.u[m], self.data.t[m], self.data.g[m]), self.data.y[m])
        return out

    def summary(self) -> dict:
        d = self.data
        bym = {}
        for level in ("all", "grp"):
            s, v = self.components[f"s_{level}"].tau, self.components[f"v_{level}"].tau
            bym[level] = {"rho": (1 / s) / (1 / s + 1 / v), "sd": float(np.sqrt(1 / s + 1 / v))}
        return {"block": d.block, "dataset": d.dataset, "graph": self.graph_kind, "years": [int(d.years[0]), int(d.years[-1])],
                "leaves": len(d.leaves), "groups": len(d.groups), "places": len(d.places),
                "events": float(d.y.sum()), "nonempty_cells": int(len(d.y)), "unallocated": d.unallocated,
                "phi": self.phi, "dispersion_check": getattr(self, "dispersion_check", None), "taus": {k: c.tau for k, c in self.components.items()}, "spatial_share": bym,
                "fit_seconds": self.history[-1]["seconds"] if self.history else None}

    # ---- persistence -------------------------------------------------------------

    def key(self) -> dict:
        return {**self.data.key, "graph": self.graph_kind}

    def save(self) -> None:
        arrays = {k: v.detach().cpu().numpy() for k, v in self.params.items()}
        store.put_arrays("monolith", self.key(), arrays, self.summary())

    @classmethod
    def load(cls, dataset: str, event: str, block: str, years: range | list[int],
             graph_kind: str = "contiguity") -> Monolith:
        """A fitted block from the store (its data re-assembled from the gateway's cache)."""
        from . import graphs

        data = assemble(dataset, event, block, years)
        model = cls(data, graphs.graph(data.places, graph_kind), graph_kind)
        arrays = store.get_arrays("monolith", model.key())
        meta = store.manifest("monolith", model.key())
        if arrays is None or meta is None:
            raise LookupError(f"no fitted monolith for {model.key()}")
        with torch.no_grad():
            for k, v in arrays.items():
                model.params[k].copy_(torch.as_tensor(v))
        for k, tau in meta["taus"].items():
            model.components[k].tau = float(tau)
        model.phi = float(meta["phi"])
        model.history = [{"seconds": meta.get("fit_seconds")}]
        return model


# ---------------------------------------------------------------------- helpers


def _within_groups(leaf_group: np.ndarray, n: int) -> structures.Shape:
    """θ_cat: iid, centred within each group (the group carries the mean)."""
    return structures.Shape("iid_within", sp.identity(n, format="csr"), n - len(np.unique(leaf_group)),
                            centred=True, components=leaf_group)


def _centre(x: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    ncomp = int(labels.max()) + 1
    sums = torch.zeros((x.shape[0], ncomp), dtype=x.dtype, device=x.device).index_add_(1, labels, x)
    counts = torch.bincount(labels, minlength=ncomp).to(x.dtype)
    return x - (sums / counts)[:, labels]


def _torch_sparse(Q: sp.csr_matrix, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
    coo = Q.tocoo()
    idx = torch.as_tensor(np.vstack([coo.row, coo.col]), dtype=torch.int64)
    return torch.sparse_coo_tensor(idx, torch.as_tensor(coo.data, dtype=dtype), coo.shape,
                                   device=device).coalesce()


def _trace_inv_times(D: np.ndarray, tau: float, Q: sp.csr_matrix, probes: int = 24) -> float:
    """tr((diag(D) + τQ)⁻¹ Q): exact for small n, Hutchinson with a sparse LU otherwise."""
    n = Q.shape[0]
    H = (sp.diags(D) + tau * Q).tocsc() + sp.identity(n, format="csc") * 1e-9
    if n <= 400:
        return float(np.trace(np.linalg.solve(H.toarray(), Q.toarray())))
    lu = spla.splu(H)
    rng = np.random.default_rng(config.seed("hutchinson", n))
    z = rng.choice([-1.0, 1.0], size=(n, probes))
    return float(np.mean(np.sum(z * lu.solve(Q @ z), axis=0)))


def _cached_icar(edges: np.ndarray, weights: np.ndarray, n: int) -> structures.Shape:
    key = {"what": "icar", "n": n, "edges": int(len(edges)), "hash": int(np.sum(edges[:, 0] * 7919 + edges[:, 1])),
           "w": round(float(np.sum(weights * (1 + edges[:, 0] % 97))), 6)}
    cached = store.get_arrays("structures", key)
    if cached is not None:
        Q = sp.csr_matrix((cached["data"], cached["indices"], cached["indptr"]), shape=(n, n))
        return structures.Shape("icar", Q, int(cached["rank"]), True, cached["components"])
    shape = structures.icar(edges, weights, n)
    store.put_arrays("structures", key, {"data": shape.Q.data, "indices": shape.Q.indices, "indptr": shape.Q.indptr,
                                         "rank": np.array(shape.rank), "components": shape.components})
    return shape
