"""The v1 solver of a count block: exact Newton on the assembled block-arrowhead Hessian (ARCHITECTURE §5.3;
`docs/plans/2026-10-06-optimization.md` §3–4).

The objective of a count block is Poisson in η (`Monolith.objective`): −Σ y·η + Λ + ½ Σ τ xᵀQx, with x the centred
effects. Its gradient is M − Y + τQx (M the marginal sums of μ over each effect's cells, Y the sufficient
statistics) and its Hessian JᵀWJ + τQ with W = μ, every entry a sum of μ over the cells two effects share. All of it
is read from the factorisation μ[e,u,t,g] = LP[e,u] · EX[k,u,t] · N[u,t,g] · F[k,g]; no cell array is formed.

The parameters fall into three classes:
- **v**, the leaf × place deviations v_cat[e,u]: H_vv is diagonal, and v[e,u] couples only to its own place's
  effects and to its leaf's and group's globals, always through LP[e,u] times a vector shared by the leaves of the
  group at that place. Its within-group centring makes each (group, place) block a diagonal matrix under one
  sum-to-zero constraint, whose constrained inverse Z = D⁻¹ − D⁻¹11ᵀD⁻¹ / 1ᵀD⁻¹1 is closed-form; v is eliminated by
  it, and the update of the rest is a weight per (group, place) times outer products of shared vectors;
- **ℓ**, the place effects (s_all, v_all, s_grp, v_grp at each place), coupled across places only by the ICAR
  penalties; the group deviations' centring per place is a contrast basis inside each place's block;
- **γ**, the globals (b0, θ, f, h, season), dense, projected onto their centred subspace by an orthonormal basis.

The reduced (ℓ, γ) system is one sparse symmetric matrix factored by CHOLMOD, its symbolic analysis kept across
Newton steps (the pattern does not change). The centrings across places (each leaf's and each place effect's sum over
places) are imposed by conditioning by kriging on the full solve (Rue & Held 2005, §2.3.3).

v1 covers `Monolith` count blocks at the annual and monthly grain without the low-rank interaction; the mark and share
models and the interaction keep the v0 Newton–CG until they are ported."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import torch

PLACE = ("s_all", "v_all", "s_grp", "v_grp")
RIDGE = 1e-9            # relative ridge on the reduced system's diagonal: the flat directions kriging removes


def _np(t: torch.Tensor) -> np.ndarray:
    return t.detach().cpu().numpy().astype(np.float64, copy=False)


def _contrast(K: int) -> np.ndarray:
    """An orthonormal basis (K × (K−1)) of the vectors summing to zero over K groups."""
    if K <= 1:
        return np.zeros((K, 0))
    u, s, _ = np.linalg.svd(np.eye(K) - 1.0 / K)
    return u[:, : K - 1]


@dataclass
class Factors:
    LP: np.ndarray        # [E, U]   exp(b0 + θ_grp + θ_cat + v_cat)
    EX: np.ndarray        # [K, U, T] exp(time + place)
    F: np.ndarray         # [K, G]   exp(f_all + f_grp)
    W: np.ndarray         # [K, U]   Σ_{e∈k} LP
    Pk: np.ndarray        # [K, U, T] EX · Σ_g N F
    Pu: np.ndarray        # [K, U]   Σ_t Pk
    R: np.ndarray         # [K, U, G] F · Σ_t EX N
    m: np.ndarray         # [E, U]   Σ_{t,g} μ / … : LP · Pu[k(e)], the active leaves' with their interaction
    mubar: np.ndarray     # [E, T, G] Σ_u μ
    total: float
    # the interaction (`Monolith(rank=R)` with it on): each active leaf's place-time factor is its group's times
    # J = exp(I); its features differ from its group's by these (zero-size arrays without the interaction)
    act: np.ndarray | None = None    # [A]       the active leaves
    dPk: np.ndarray | None = None    # [A, U, T] Pk_a − Pk[k(a)]
    dPu: np.ndarray | None = None    # [A, U]
    dR: np.ndarray | None = None     # [A, U, G]
    cell_grad: np.ndarray | None = None   # a mark model's score per non-empty cell (log-likelihood units)


class Arrowhead:
    """A factored arrowhead [[A, B],[Bᵀ, C]] (place system, globals in reduced coordinates). With LLᵀ = PAPᵀ
    (CHOLMOD) and Y = L⁻¹PB: S = C − YᵀY = L_S L_Sᵀ, and a solve is one forward and one back substitution with L
    plus a dense solve with L_S."""

    def __init__(self, fa, Y: np.ndarray, B: np.ndarray, Sc: np.ndarray, nl: int, L: Supernodal | None = None):
        self.fa, self.Y, self.B, self.Sc, self.nl, self.L = fa, Y, B, Sc, nl, L
        self.p = np.asarray(fa.perm)

    def __call__(self, b: np.ndarray) -> np.ndarray:
        one = b.ndim == 1
        b = b[:, None] if one else b
        bl, bg = b[: self.nl], b[self.nl:]
        many = self.L is not None and b.shape[1] >= 8
        yl = self.L.lower(bl[self.p]) if many else self.fa.solve(bl[self.p], system="L")
        rhs = bg - self.Y.T @ yl
        xg = np.linalg.solve(self.Sc.T, np.linalg.solve(self.Sc, rhs))
        z = self.L.lower_t(yl - self.Y @ xg) if many else self.fa.solve(yl - self.Y @ xg, system="Lt")
        xl = np.empty_like(z)
        xl[self.p] = z
        out = np.vstack([xl, xg])
        return out[:, 0] if one else out

    def logdet(self) -> float:
        return float(self.fa.logdet()) + 2.0 * float(np.log(np.diag(self.Sc)).sum())


class StructuredNewton:
    """Exact Newton steps for one fitted `Monolith` (count block, no interaction)."""

    def __init__(self, model):
        self.m = model
        d = model.data
        self.U, self.T, self.G = d.N.shape
        self.E, self.K = len(d.leaves), len(d.groups)
        self.grp = np.asarray(d.leaf_group, dtype=np.int64)
        self.N = np.asarray(d.N, dtype=np.float64)
        self.monthly = d.grain == "month"
        self.moy = np.asarray(d.month_of_year if self.monthly else np.zeros(self.T, dtype=np.int64))
        self.C = _contrast(self.K)
        self._global_layout()
        self._place_layout()
        self._constraints()
        self._symbolic = None
        self.timing: dict[str, float] = {}
        self._last_reused = False

    # ------------------------------------------------------------------ layouts

    def _global_layout(self) -> None:
        """Offsets of the globals in x-space (effects as `Monolith.effects` returns them), and the orthonormal basis of
        their centred subspace, read from the model's own centring (a linear map: its matrix is the projector)."""
        K, E, T, G = self.K, self.E, self.T, self.G
        names = ["b0", "th_grp", "th_cat", "f_all", "f_grp", "h_all", "h_grp"] + (["c_all", "c_grp"] if self.monthly else [])
        sizes = {"b0": 1, "th_grp": K, "th_cat": E, "f_all": G, "f_grp": K * G, "h_all": T, "h_grp": K * T,
                 "c_all": 12, "c_grp": K * 12}
        self.gnames = names
        self.goff, o = {}, 0
        for n in names:
            self.goff[n] = o
            o += sizes[n]
        self.ng = o
        # the projector of each global effect: the Jacobian of its own centring (`Monolith._centred`), and the basis of its
        # range per component (block-diagonal; kept dense: the f_grp and h_grp blocks fill 40 % of it, and SciPy's
        # dense-by-sparse product took 11 s per factor on IX where the dense one takes 0.3 s)
        m = self.m
        blocks = [np.ones((1, 1))]
        for n in names[1:]:
            p = m.params[n].detach()
            J = _np(torch.autograd.functional.jacobian(lambda r, n=n: m._centred(n, r).reshape(-1), p).reshape(sizes[n], sizes[n]))
            w, v = np.linalg.eigh((J + J.T) / 2)
            blocks.append(v[:, w > 0.5])               # orthonormal basis of range(P_n)
        self.Cg = sp.block_diag(blocks).toarray()
        self.ng_red = self.Cg.shape[1]

    def _place_layout(self) -> None:
        """Per place: s_all, v_all, s_grp[0..K−1], v_grp[0..K−1] in x-space; in reduced coordinates the group
        deviations are replaced by their K−1 contrasts. Places are blocks of consecutive rows (CHOLMOD locality)."""
        K = self.K
        self.npl = 2 + 2 * K                  # x-space per place
        self.npl_red = 2 + 2 * (K - 1)        # reduced per place
        U = self.U
        # T_place: x-space place block (npl) <- reduced (npl_red)
        Tb = np.zeros((self.npl, self.npl_red))
        Tb[0, 0] = Tb[1, 1] = 1.0
        Tb[2:2 + K, 2:2 + K - 1] = self.C
        Tb[2 + K:, 2 + K - 1:] = self.C
        self.Tblock = Tb
        self.Tplace = sp.kron(sp.identity(U, format="csr"), sp.csr_matrix(Tb), format="csr")
        self.nl = U * self.npl
        self.nl_red = U * self.npl_red

    def _constraints(self) -> None:
        """The centrings across places, as rows over the reduced (ℓ, γ) coordinates plus the v part: each component of
        s_all and s_grp's contrasts per connected component of the graph; v_all, v_grp's contrasts and each leaf of
        v_cat over all places where their shape is centred (the iid place effects are not, since 2026-10-06)."""
        m = self.m
        U, K = self.U, self.K
        comp = _np(m._labels["s_all"].to(torch.float64)).astype(np.int64)
        rows_l = []                                     # (indices into reduced ℓ, values)
        for c in np.unique(comp):
            places = np.nonzero(comp == c)[0]
            rows_l.append((places * self.npl_red + 0, np.ones(len(places))))
            for j in range(K - 1):
                rows_l.append((places * self.npl_red + 2 + j, np.ones(len(places))))
        allp = np.arange(U)
        if m.components["v_all"].shape.centred:
            rows_l.append((allp * self.npl_red + 1, np.ones(U)))
        if m.components["v_grp"].shape.centred:
            for j in range(K - 1):
                rows_l.append((allp * self.npl_red + 2 + (K - 1) + j, np.ones(U)))
        self.con_l = rows_l
        # one per leaf, Σ_u v[e, u] = 0, where v_cat is centred
        self.con_v = list(range(self.E)) if m.components["v_cat"].shape.centred else []

    # ------------------------------------------------------------------ factors and gradient

    def factors(self, x: dict[str, torch.Tensor]) -> Factors:
        m = self.m
        if hasattr(m, "cell_derivatives"):
            return self._mark_factors(x)
        t0 = time.time()
        with torch.no_grad():
            LP = m._leaf_place(x)                                                 # [E, U]
            Fk = torch.exp(x["f_all"] + x["f_grp"])                              # [K, G]
            lin = m._time(x)[:, None, :] + (x["s_all"][0] + x["v_all"][0])[None, :, None] + (x["s_grp"] + x["v_grp"])[:, :, None]
            EX = torch.exp(lin)                                                  # [K, U, T]
            NF = torch.einsum("utg,kg->kut", m.N, Fk)
            Pk = EX * NF
            W = torch.zeros((self.K, self.U), dtype=LP.dtype, device=LP.device).index_add_(0, m.grp, LP)
            Pu = Pk.sum(2)
            R = Fk[:, None, :] * torch.einsum("kut,utg->kug", EX, m.N)
            mm = LP * Pu[m.grp]
            # Σ_u μ[e,u,t,g]: by group, LP·EX contracted with N over u
            mubar = torch.empty((self.E, self.T, self.G), dtype=LP.dtype, device=LP.device)
            for k in range(self.K):
                leaves = torch.nonzero(m.grp == k).ravel()
                mubar[leaves] = torch.einsum("eu,ut,utg->etg", LP[leaves], EX[k], m.N) * Fk[k][None, None, :]
            dev = {}
            if getattr(m, "ix_on", False):
                act = m.ixl
                ka = m.grp[act]
                Xa = EX[ka] * torch.exp(m._I(x))                                 # [A, U, T]
                dPk = Xa * NF[ka] - Pk[ka]
                dPu = dPk.sum(2)
                dR = Fk[ka][:, None, :] * torch.einsum("aut,utg->aug", Xa, m.N) - R[ka]
                mm[act] = LP[act] * (Pu[ka] + dPu)
                mubar[act] = torch.einsum("au,aut,utg->atg", LP[act], Xa, m.N) * Fk[ka][:, None, :]
                dev = {"act": _np(act).astype(np.int64), "dPk": _np(dPk), "dPu": _np(dPu), "dR": _np(dR)}
            total = float(mm.sum())
        f = Factors(_np(LP), _np(EX), _np(Fk), _np(W), _np(Pk), _np(Pu), _np(R), _np(mm), _np(mubar), total, **dev)
        self.timing["factors"] = time.time() - t0
        return f

    def _mark_factors(self, x: dict[str, torch.Tensor]) -> Factors:
        """A mark model's (MarkModel, ShareModel, CountModel) cells exist only where events do, each with its own
        Fisher weight h_c (the family's), so every leaf has its own features: they are written as the interaction's
        active-leaf deviations of a zero shared factor (LP = 1, every leaf active), which the assembly and the solve
        already carry exactly. The scores are kept for the gradient."""
        m = self.m
        t0 = time.time()
        d = m.data
        with torch.no_grad():
            g, h = (_np(a) for a in m.cell_derivatives(m.eta_nnz(x)))
        E, U, T, G, K = self.E, self.U, self.T, self.G, self.K
        e, u, t, gg = (np.asarray(a, dtype=np.int64) for a in (d.e, d.u, d.t, d.g))
        mm = np.bincount(e * U + u, weights=h, minlength=E * U).reshape(E, U)
        mubar = np.bincount((e * T + t) * G + gg, weights=h, minlength=E * T * G).reshape(E, T, G)
        dPk = np.bincount((e * U + u) * T + t, weights=h, minlength=E * U * T).reshape(E, U, T)
        dR = np.bincount((e * U + u) * G + gg, weights=h, minlength=E * U * G).reshape(E, U, G)
        zK = np.zeros((K, U))
        f = Factors(np.ones((E, U)), np.zeros((K, U, T)), np.zeros((K, G)), np.bincount(self.grp, minlength=K)[:, None] * np.ones((1, U)),
                    np.zeros((K, U, T)), zK, np.zeros((K, U, G)), mm, mubar, float(h.sum()),
                    act=np.arange(E, dtype=np.int64), dPk=dPk, dPu=mm, dR=dR, cell_grad=g)
        self.timing["factors"] = time.time() - t0
        return f

    def _mark_gradient(self, x: dict[str, torch.Tensor], f: Factors) -> dict[str, np.ndarray]:
        """The gradient from a mark model's cell scores, summed over the cells each effect touches."""
        m = self.m
        d = m.data
        r = f.cell_grad
        E, U, T, G, K = self.E, self.U, self.T, self.G, self.K
        e, u, t, gg = (np.asarray(a, dtype=np.int64) for a in (d.e, d.u, d.t, d.g))
        k = self.grp[e]
        M = {"b0": np.array([r.sum()]), "th_grp": np.bincount(k, weights=r, minlength=K)[None, :],
             "th_cat": np.bincount(e, weights=r, minlength=E)[None, :],
             "f_all": np.bincount(gg, weights=r, minlength=G)[None, :],
             "f_grp": np.bincount(k * G + gg, weights=r, minlength=K * G).reshape(K, G),
             "h_all": np.bincount(t, weights=r, minlength=T)[None, :],
             "h_grp": np.bincount(k * T + t, weights=r, minlength=K * T).reshape(K, T),
             "s_all": np.bincount(u, weights=r, minlength=U)[None, :],
             "s_grp": np.bincount(k * U + u, weights=r, minlength=K * U).reshape(K, U),
             "v_cat": np.bincount(e * U + u, weights=r, minlength=E * U).reshape(E, U)}
        M["v_all"], M["v_grp"] = M["s_all"], M["s_grp"]
        if self.monthly:
            mo = self.moy[t]
            M["c_all"] = np.bincount(mo, weights=r, minlength=12)[None, :]
            M["c_grp"] = np.bincount(k * 12 + mo, weights=r, minlength=K * 12).reshape(K, 12)
        out = {}
        for n, val in M.items():
            out[n] = val
            if n in m.components:
                c = m.components[n]
                xv = _np(x[n]).reshape(c.batch, -1)
                out[n] = val + ((c.shape.Q @ xv.T).T * c.tau).reshape(val.shape)
        return out

    def gradient(self, x: dict[str, torch.Tensor], f: Factors) -> dict[str, np.ndarray]:
        """∂(−log L + penalty)/∂x for every effect (x-space, unscaled: log-likelihood units)."""
        m = self.m
        if f.cell_grad is not None:
            return self._mark_gradient(x, f)
        WPu, Ht, Fg = self._leaf_sums(f)
        M = {"b0": np.array([f.total]), "th_grp": WPu.sum(1)[None, :], "th_cat": f.m.sum(1)[None, :],
             "f_all": Fg.sum(0)[None, :], "f_grp": Fg, "h_all": Ht.sum(0)[None, :], "h_grp": Ht,
             "s_all": WPu.sum(0)[None, :], "v_all": WPu.sum(0)[None, :], "s_grp": WPu, "v_grp": WPu, "v_cat": f.m}
        if self.monthly:
            agg = np.zeros((self.T, 12))
            agg[np.arange(self.T), self.moy] = 1.0
            M["c_all"] = (Ht.sum(0) @ agg)[None, :]
            M["c_grp"] = Ht @ agg
        g = {}
        for n, val in M.items():
            y = _np(m.Y[n]).reshape(val.shape)
            g[n] = val - y
            if n in m.components:
                c = m.components[n]
                xv = _np(x[n]).reshape(c.batch, -1)
                pen = (c.shape.Q @ xv.T).T * c.tau
                g[n] = g[n] + pen.reshape(val.shape)
        return g

    def _leaf_sums(self, f: Factors):
        """Σ over each group's leaves of LP·Pu [K, U], LP·Pk summed over places [K, T] and LP·R summed over places
        [K, G]: the group's shared factor, plus the active leaves' deviations."""
        WPu = f.W * f.Pu
        Ht = (f.W[:, :, None] * f.Pk).sum(1)
        Fg = (f.W[:, :, None] * f.R).sum(1)
        if f.act is not None:
            ka = self.grp[f.act]
            LPa = f.LP[f.act]
            np.add.at(WPu, ka, LPa * f.dPu)
            np.add.at(Ht, ka, np.einsum("au,aut->at", LPa, f.dPk))
            np.add.at(Fg, ka, np.einsum("au,aug->ag", LPa, f.dR))
        return WPu, Ht, Fg

    def _dfeatures(self, f: Factors) -> np.ndarray:
        """The active leaves' feature deviations [A, U, nf], in `_features`' layout."""
        parts = [f.dPu[:, :, None], f.dPk, f.dR]
        if self.monthly:
            agg = np.zeros((self.T, 12))
            agg[np.arange(self.T), self.moy] = 1.0
            parts.append(f.dPk @ agg)
        return np.concatenate(parts, axis=2)

    def _active_terms(self, f: Factors, vs, feat: np.ndarray):
        """The leaf-place elimination's terms from the active leaves, per group: with the coupling row of leaf e at
        place u written LP_e·(φ_k + δφ_e) (δφ zero for an inactive leaf), the Schur update q·φφᵀ gains
        φ·G1ᵀ + G1·φᵀ + Σ_a (LP_a²/d_a) δφ_a δφ_aᵀ − H1·H1ᵀ/s, G1 = Σ_a LP_a ζ_a δφ_a, H1 = Σ_a LP_a δφ_a / d_a.
        Returns G1, H1 [K, U, nf], the summed active–active matrices AA [K, nf, nf], and its place-scalar rows AA0
        [K, U, nf] per place."""
        d, inv_d, s, a1, q, alpha, zeta = vs
        df = self._dfeatures(f)
        act = f.act
        ka = self.grp[act]
        LPa = f.LP[act]
        K, U, nf = feat.shape
        G1 = np.zeros((K, U, nf))
        H1 = np.zeros((K, U, nf))
        np.add.at(G1, ka, (LPa * zeta[act])[:, :, None] * df)
        np.add.at(H1, ka, (LPa * inv_d[act])[:, :, None] * df)
        w2 = LPa * LPa * inv_d[act]                                            # [A, U]
        AA = np.zeros((K, nf, nf))
        AA0 = np.zeros((K, U, nf))
        for k in np.unique(ka):
            sel = np.nonzero(ka == k)[0]
            dk = df[sel]
            AA[k] = np.einsum("au,auf,aug->fg", w2[sel], dk, dk) - np.einsum("uf,ug,u->fg", H1[k], H1[k], 1.0 / s[k])
            AA0[k] = np.einsum("au,au,auf->uf", w2[sel], dk[:, :, 0], dk) - H1[k][:, :1] * H1[k] / s[k][:, None]
        return df, G1, H1, AA, AA0

    # ------------------------------------------------------------------ the v block

    def _v_stats(self, f: Factors):
        """Per (group, place): the diagonal d, and the constrained inverse's scalars."""
        tau_v = self.m.components["v_cat"].tau
        d = f.m + tau_v                                                       # [E, U]
        LP = f.LP
        inv_d = 1.0 / d
        grp = self.grp
        s = self._gsum(inv_d)
        a1 = self._gsum(LP * inv_d)
        a2 = self._gsum(LP * LP * inv_d)
        q = a2 - a1 * a1 / s                                                   # LPᵀ Z LP
        alpha = LP * inv_d                                                     # LP / d
        zeta = alpha - inv_d * (a1 / s)[grp]                                   # Z LP
        return d, inv_d, s, a1, q, alpha, zeta

    def _gsum(self, a: np.ndarray) -> np.ndarray:
        """Σ over the leaves of each group of a [E, ...] array: [K, ...] (a sparse indicator product, not np.add.at)."""
        if getattr(self, "_gind", None) is None:
            self._gind = sp.csr_matrix((np.ones(self.E), (self.grp, np.arange(self.E))), shape=(self.K, self.E))
        return (self._gind @ a.reshape(self.E, -1)).reshape((self.K,) + a.shape[1:])

    def _Z(self, b: np.ndarray, inv_d: np.ndarray, s: np.ndarray) -> np.ndarray:
        """Z applied to b [E, U] (or [E, U, n]) per (group, place)."""
        grp = self.grp
        idv = inv_d if b.ndim == 2 else inv_d[..., None]
        bd = b * idv
        corr = self._gsum(bd) / (s if b.ndim == 2 else s[..., None])
        bd -= idv * corr[grp]
        return bd

    # ------------------------------------------------------------------ the shared vectors ω

    def _feature_map(self) -> list[sp.csr_matrix]:
        """For each group k, the map from its feature vector [scalar, time T, age G (, month 12)] to the global
        coordinates (x-space): the scalar to b0 and θ_grp[k]; time t to h_all[t] and h_grp[k,t]; age g to f_all[g]
        and f_grp[k,g]; month to c_all and c_grp[k]."""
        if getattr(self, "_fmap", None) is not None:
            return self._fmap
        T, G = self.T, self.G
        nf = 1 + T + G + (12 if self.monthly else 0)
        out = []
        for k in range(self.K):
            r, c = [], []
            r += [0, 0]
            c += [self.goff["b0"], self.goff["th_grp"] + k]
            for t in range(T):
                r += [1 + t, 1 + t]
                c += [self.goff["h_all"] + t, self.goff["h_grp"] + k * T + t]
            for g in range(G):
                r += [1 + T + g, 1 + T + g]
                c += [self.goff["f_all"] + g, self.goff["f_grp"] + k * G + g]
            if self.monthly:
                for mo in range(12):
                    r += [1 + T + G + mo, 1 + T + G + mo]
                    c += [self.goff["c_all"] + mo, self.goff["c_grp"] + k * 12 + mo]
            out.append(sp.csr_matrix((np.ones(len(r)), (r, c)), shape=(nf, self.ng)))
        self._fmap = out
        return out

    def _fmap_dense(self) -> list[np.ndarray]:
        if getattr(self, "_fd", None) is None:
            self._fd = [mk.toarray() for mk in self._feature_map()]
        return self._fd

    def _features(self, f: Factors) -> np.ndarray:
        """ω's feature values per (k, u): [K, U, nf] = [Pu, Pk[t], R[g] (, Pk summed by month)]."""
        parts = [f.Pu[:, :, None], f.Pk, f.R]
        if self.monthly:
            agg = np.zeros((self.T, 12))
            agg[np.arange(self.T), self.moy] = 1.0
            parts.append(f.Pk @ agg)
        return np.concatenate(parts, axis=2)

    # ------------------------------------------------------------------ assembly of the reduced system

    def _global_design(self) -> sp.csr_matrix:
        """Rows (e, t, g) → the globals each cell's η carries (x-space)."""
        if getattr(self, "_gdes", None) is not None:
            return self._gdes
        E, T, G = self.E, self.T, self.G
        e, t, g = np.meshgrid(np.arange(E), np.arange(T), np.arange(G), indexing="ij")
        e, t, g = e.ravel(), t.ravel(), g.ravel()
        k = self.grp[e]
        n = len(e)
        cols = [np.zeros(n, np.int64), self.goff["th_grp"] + k, self.goff["th_cat"] + e, self.goff["f_all"] + g,
                self.goff["f_grp"] + k * G + g, self.goff["h_all"] + t, self.goff["h_grp"] + k * T + t]
        if self.monthly:
            mo = self.moy[t]
            cols += [self.goff["c_all"] + mo, self.goff["c_grp"] + k * 12 + mo]
        rows = np.tile(np.arange(n), len(cols))
        self._gdes = sp.csr_matrix((np.ones(n * len(cols)), (rows, np.concatenate(cols))), shape=(n, self.ng))
        return self._gdes

    def assemble(self, f: Factors, vs) -> tuple[sp.csc_matrix, sp.csc_matrix, np.ndarray]:
        """The reduced Hessian over (ℓ, γ) in reduced coordinates: the data part, minus the v block's Schur update,
        plus the penalties; then the contrast bases."""
        t0 = time.time()
        m = self.m
        K, U = self.K, self.U
        d, inv_d, s, a1, q, alpha, zeta = vs
        feat = self._features(f)                                   # [K, U, nf]
        WPu = self._leaf_sums(f)[0]
        ix = f.act is not None
        if ix:
            df, G1, H1, AA, AA0 = self._active_terms(f, vs, feat)

        # ---- γγ: data (design over (e,t,g) cells weighted by Σ_u μ), minus Σ_k Mkᵀ(Σ_u q φφᵀ)Mk, θc terms
        D = self._global_design()
        Hgg = (D.T @ sp.diags(f.mubar.ravel()) @ D).toarray()
        fd = self._fmap_dense()
        for k in range(K):
            Sk = (feat[k] * q[k][:, None]).T @ feat[k]
            if ix:
                Sk = Sk + feat[k].T @ G1[k] + G1[k].T @ feat[k] + AA[k]
            Hgg -= fd[k].T @ Sk @ fd[k]
        # θc[e] (coupling m_e at each place) with the shared features: −Σ_u m_e ζ_e φ_{k(e),u}, and with the active
        # leaves' deviations; θc–θc: −Σ_u (m_e m_e' (δ_ee'/d_e − 1/(d_e d_e' s)))
        eta = zeta * f.m                                           # [E, U]
        md = f.m * inv_d
        oc = self.goff["th_cat"]
        for k in range(K):
            leaves = np.nonzero(self.grp == k)[0]
            cross = eta[leaves] @ feat[k]                              # [n_k, nf]
            if ix:
                cross = cross - (md[leaves] / s[k][None, :]) @ H1[k]
                act_k = np.nonzero(self.grp[f.act] == k)[0]
                if len(act_k):
                    pos = np.searchsorted(leaves, f.act[act_k])
                    cross[pos] += np.einsum("au,auf->af", md[f.act[act_k]] * f.LP[f.act[act_k]], df[act_k])
            cross = cross @ fd[k]                                      # [n_k, ng]
            Hgg[oc + leaves, :] -= cross
            Hgg[:, oc + leaves] -= cross.T
            diag = (md[leaves] * f.m[leaves]).sum(1)
            off = (md[leaves] / s[k][None, :]) @ md[leaves].T
            Hgg[np.ix_(oc + leaves, oc + leaves)] -= np.diag(diag) - off
        # penalties of the globals
        for n in self.gnames:
            if n == "b0":
                continue
            c = m.components[n]
            o = self.goff[n]
            nn = c.batch * c.shape.Q.shape[0]
            Hgg[o:o + nn, o:o + nn] += c.tau * sp.kron(sp.identity(c.batch), c.shape.Q).toarray()

        # ---- ℓℓ in reduced coordinates: per place Tbᵀ·block·Tb, plus the penalties written in reduced coordinates
        npl, npr = self.npl, self.npl_red
        blocks = np.zeros((U, npl, npl))
        Qpp = q * f.Pu ** 2                                                     # the place scalar's elimination
        if ix:
            Qpp = Qpp + 2.0 * f.Pu * G1[:, :, 0] + AA0[:, :, 0]
        a_tot = WPu.sum(0) - Qpp.sum(0)                                         # a–a
        ab = WPu - Qpp                                                          # a–b_k and b_k–b_k
        blocks[:, :2, :2] = a_tot[:, None, None]
        for k in range(K):
            for j in (2 + k, 2 + K + k):
                blocks[:, :2, j] = ab[k][:, None]
                blocks[:, j, :2] = ab[k][:, None]
                for jj in (2 + k, 2 + K + k):
                    blocks[:, j, jj] = ab[k]
        Tb = self.Tblock
        red = Tb.T[None] @ blocks @ Tb[None]                                  # [U, npr, npr]
        Al = self._block_diag(red) + self._place_penalty_reduced()
        Al = ((Al + Al.T) * 0.5).tocsc()
        dg = Al.diagonal()
        Al = (Al + sp.diags(RIDGE * np.maximum(dg, dg.max() * 1e-12))).tocsc()

        # ---- ℓγ dense in reduced place rows × x-space globals: per group the place rows vec·Mk plus θc, then the
        # contrasts; s_all/v_all read the sum over groups
        vec = f.W[:, :, None] * feat - (q * f.Pu)[:, :, None] * feat           # [K, U, nf]
        thc = f.m - eta * f.Pu[self.grp]                                     # [E, U]
        if ix:
            DA = np.zeros_like(feat)
            np.add.at(DA, self.grp[f.act], f.LP[f.act][:, :, None] * df)
            vec = vec + DA - f.Pu[:, :, None] * G1 - G1[:, :, :1] * feat - AA0
            thc = thc + md * (H1[self.grp][:, :, 0] / s[self.grp])
            thc[f.act] -= md[f.act] * f.LP[f.act] * f.dPu
        Gk = np.empty((K, U, self.ng))
        oc = self.goff["th_cat"]
        for k in range(K):
            Gk[k] = vec[k] @ fd[k]
            leaves = np.nonzero(self.grp == k)[0]
            Gk[k][:, oc + leaves] += thc[leaves].T
        Bl = np.empty((U, npr, self.ng))
        tot = Gk.sum(0)
        Bl[:, 0] = tot
        Bl[:, 1] = tot
        cg = np.tensordot(self.C, Gk, axes=([0], [0])).transpose(1, 0, 2)     # [U, K−1, ng]
        Bl[:, 2:2 + K - 1] = cg
        Bl[:, 2 + K - 1:] = cg
        Bl = Bl.reshape(U * npr, self.ng)
        self.timing["assemble"] = time.time() - t0
        return Al, Bl, Hgg

    def _block_diag(self, blocks: np.ndarray) -> sp.csr_matrix:
        U, n, _ = blocks.shape
        r = (np.arange(U)[:, None, None] * n + np.arange(n)[None, :, None]).repeat(n, axis=2)
        c = (np.arange(U)[:, None, None] * n + np.arange(n)[None, None, :]).repeat(n, axis=1)
        return sp.csr_matrix((blocks.ravel(), (r.ravel(), c.ravel())), shape=(U * n, U * n))

    def _place_penalty_reduced(self) -> sp.csr_matrix:
        """The place penalties in reduced coordinates: τ_s·Q_ICAR on s_all and on each of s_grp's K−1 contrasts
        (C is orthonormal, so Σ_k s_kᵀQs_k = Σ_j s'_jᵀQs'_j), τ_v·I on v_all and on v_grp's contrasts."""
        m = self.m
        U, K, npr = self.U, self.K, self.npl_red
        Q = sp.coo_matrix(m.components["s_all"].shape.Q)
        Qg = sp.coo_matrix(m.components["s_grp"].shape.Q)
        rows, cols, vals = [], [], []
        def add_graph(Qc, j, tau):
            rows.append(Qc.row * npr + j)
            cols.append(Qc.col * npr + j)
            vals.append(tau * Qc.data)
        def add_iid(j, tau, Qd):
            d = np.asarray(Qd.diagonal()) if sp.issparse(Qd) else np.diag(Qd)
            rows.append(np.arange(U) * npr + j)
            cols.append(np.arange(U) * npr + j)
            vals.append(tau * d)
        add_graph(Q, 0, m.components["s_all"].tau)
        add_iid(1, m.components["v_all"].tau, m.components["v_all"].shape.Q)
        for j in range(K - 1):
            add_graph(Qg, 2 + j, m.components["s_grp"].tau)
            add_iid(2 + K - 1 + j, m.components["v_grp"].tau, m.components["v_grp"].shape.Q)
        n = U * npr
        return sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))

    # ------------------------------------------------------------------ solves

    def factor(self, parts) -> Arrowhead:
        """Factor the arrowhead: CHOLMOD on the place system (supernodal, its symbolic analysis kept across steps), Y =
        L⁻¹PB for the globals' columns (B already in reduced global coordinates) by the supernodal solve, and the dense
        Cholesky of S = C − YᵀY."""
        from sksparse.cholmod import cho_factor
        Al, Bl, Hgg = parts
        t0 = time.time()
        if self._symbolic is None:
            # supernodal: 4.1 s against 12.9 s simplicial on SIM chapter I 2010-2023 (31 M non-zeros in L), the same
            # factor (2026-10-06)
            self._symbolic = cho_factor(Al, lower=True, supernodal_mode="supernodal")
        else:
            self._symbolic.factorize(Al)
        fa = self._symbolic
        t1 = time.time()
        B = Bl @ self.Cg                                              # [n_place_red, ng_red]
        p = np.asarray(fa.perm)
        L = Supernodal(fa.get_factor("LL"))
        Y = L.lower(B[p])
        t2 = time.time()
        # YᵀY by a symmetric rank-k update (half a general product's arithmetic), on Yᵀ's Fortran view: no copy
        from scipy.linalg.blas import dsyrk
        YtY = dsyrk(1.0, Y.T, trans=0, lower=0)
        YtY = np.triu(YtY) + np.triu(YtY, 1).T
        S = self.Cg.T @ ((Hgg + Hgg.T) * 0.5) @ self.Cg - YtY
        ds = np.diag(S)
        S = S + np.diag(RIDGE * np.maximum(ds, ds.max() * 1e-12))
        Sc = np.linalg.cholesky(S)
        self.timing.update(factor=t1 - t0, schur_solve=t2 - t1, schur=time.time() - t2)
        return Arrowhead(fa, Y, B, Sc, self.nl_red, L)

    def solve_full(self, fac, f: Factors, vs, b_v: np.ndarray, b_r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Solve H δ = b for (v, reduced (ℓ,γ)) right-hand sides: b_v [E, U, n], b_r [n_red, n]. The leaf-place parts
        run in the fused kernels of `_v_kernels`."""
        d, inv_d, s, a1, q, alpha, zeta = vs
        fmap = self._feature_map()
        feat = self._features(f)
        forward, thc_sum, back = _vk()
        gptr, gleaves = self._groups()
        b_v = np.ascontiguousarray(b_v, dtype=np.float64)
        n = b_v.shape[2]
        Zb = np.empty_like(b_v)
        lz = np.empty((self.K, self.U, n))
        forward(b_v, inv_d, s, f.LP, gptr, gleaves, Zb, lz)
        ix = f.act is not None
        lzA = f.LP[f.act][:, :, None] * Zb[f.act] if ix else None             # [A, U, n]
        red = self._shared_to_reduced(lz, feat, fmap, f, lzA)               # [n_red, n]
        thc = thc_sum(Zb, f.m, np.empty((self.E, n)))                        # [E, n]
        red += self._thc_to_reduced(thc)
        x_r = fac(b_r - red)
        # back-substitution: δ_v = Z(b_v − B δ_r), the active leaves' own part of Bδ taken off b_v first
        dot, dth = self._B_parts(f, feat, x_r)
        if ix:
            b_v = b_v.copy()
            b_v[f.act] -= f.LP[f.act][:, :, None] * self._active_dot(f, x_r, dth)
        x_v = back(b_v, inv_d, s, f.LP, f.Pu, self.grp, gptr, gleaves, dot, dth, np.empty_like(b_v))
        return x_v, x_r

    def _active_dot(self, f: Factors, x_r: np.ndarray, dth: np.ndarray) -> np.ndarray:
        """[A, U, n]: δφ_a·δ for each active leaf (its features' deviations against the global increments, its place
        scalar's against its group's place increments, and against its θc increment)."""
        U, K, npl = self.U, self.K, self.npl
        xl = self.Tplace @ x_r[: self.nl_red]
        xg = self.Cg @ x_r[self.nl_red:]
        fd = self._fmap_dense()
        df = self._dfeatures(f)
        rows = np.arange(U) * npl
        base = xl[rows + 0] + xl[rows + 1]
        out = np.empty((len(f.act), U, x_r.shape[1]))
        for i, (a, k) in enumerate(zip(f.act, self.grp[f.act], strict=True)):
            place = base + xl[rows + 2 + k] + xl[rows + 2 + K + k]
            out[i] = df[i] @ (fd[k] @ xg) + f.dPu[i][:, None] * (place + dth[a][None, :])
        return out

    def _groups(self):
        if getattr(self, "_gp", None) is None:
            order = np.argsort(self.grp, kind="stable")
            counts = np.bincount(self.grp, minlength=self.K)
            self._gp = (np.concatenate([[0], np.cumsum(counts)]).astype(np.int64), order.astype(np.int64))
        return self._gp

    def _B_parts(self, f: Factors, feat, x_r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """The pieces of Bδ: dot[k,u,:] = ω_ku·δ (shared features and the place's own effects) and dth[e,:] = δθc[e]."""
        U, K, npl = self.U, self.K, self.npl
        xl = self.Tplace @ x_r[: self.nl_red]
        xg = self.Cg @ x_r[self.nl_red:]
        fd = self._fmap_dense()
        dot = np.empty((K, U, x_r.shape[1]))
        rows = np.arange(U) * npl
        base = xl[rows + 0] + xl[rows + 1]
        for k in range(K):
            dot[k] = feat[k] @ (fd[k] @ xg) + f.Pu[k][:, None] * (base + xl[rows + 2 + k] + xl[rows + 2 + K + k])
        dth = np.ascontiguousarray(xg[self.goff["th_cat"]:self.goff["th_cat"] + self.E])
        return dot, dth

    def _shared_to_reduced(self, lz: np.ndarray, feat, fmap, f, lzA: np.ndarray | None = None) -> np.ndarray:
        """Σ_(k,u) lz[k,u,·] ω_ku mapped to the reduced coordinates (ℓ rows and γ columns), plus the active leaves'
        Σ_u lzA[a,u,·] δφ_a,u (lzA = LP·Zb of the active leaves)."""
        U, K, npl = self.U, self.K, self.npl
        n = lz.shape[2]
        xl = np.zeros((self.nl, n))
        # place rows: a[u] (s_all, v_all) gets Σ_k lz Pu ; b[k,u] gets lz Pu
        lp = lz * f.Pu[:, :, None]
        if lzA is not None:
            np.add.at(lp, self.grp[f.act], lzA * f.dPu[:, :, None])
        xl[np.arange(U) * npl + 0] = lp.sum(0)
        xl[np.arange(U) * npl + 1] = lp.sum(0)
        for k in range(K):
            xl[np.arange(U) * npl + 2 + k] = lp[k]
            xl[np.arange(U) * npl + 2 + K + k] = lp[k]
        xg = np.zeros((self.ng, n))
        for k in range(K):
            xg += fmap[k].T @ (feat[k].T @ lz[k])
        if lzA is not None:
            df = self._dfeatures(f)
            for i, k in enumerate(self.grp[f.act]):
                xg += fmap[k].T @ (df[i].T @ lzA[i])
        return np.vstack([self.Tplace.T @ xl, self.Cg.T @ xg])

    def _thc_to_reduced(self, thc: np.ndarray) -> np.ndarray:
        xg = np.zeros((self.ng, thc.shape[1]))
        xg[self.goff["th_cat"]:self.goff["th_cat"] + self.E] = thc
        return np.vstack([np.zeros((self.nl_red, thc.shape[1])), self.Cg.T @ xg])

    # ------------------------------------------------------------------ the Newton step with kriging

    def step(self, reuse: bool = False) -> tuple[dict[str, torch.Tensor], dict]:
        """The Newton direction at the current parameters, as increments of the raw parameters (in the centred
        subspace, so each equals its own centring), and diagnostics. ``reuse`` solves with the last step's factored
        Hessian (the chord method: no assembly or factorisation, only the gradient and two triangular solves)."""
        m = self.m
        t0 = time.time()
        x = {k: v.detach() for k, v in m.effects().items()}
        f = self.factors(x)
        g = self.gradient(x, f)
        self._last_reused = bool(reuse and getattr(self, "_last", None) is not None)
        if self._last_reused:
            fac, f, vs = self._last
        else:
            vs = self._v_stats(f)
            fac = self.factor(self.assemble(f, vs))
            self._last = (fac, f, vs)
        # right-hand side −g: v part [E,U,1], reduced (ℓ, γ)
        b_v = -g["v_cat"][..., None]
        gl = np.zeros(self.nl)
        U, K, npl = self.U, self.K, self.npl
        gl[np.arange(U) * npl + 0] = g["s_all"][0]
        gl[np.arange(U) * npl + 1] = g["v_all"][0]
        for k in range(K):
            gl[np.arange(U) * npl + 2 + k] = g["s_grp"][k]
            gl[np.arange(U) * npl + 2 + K + k] = g["v_grp"][k]
        gg = np.concatenate([g[n].ravel() for n in self.gnames])
        b_r = -np.concatenate([self.Tplace.T @ gl, self.Cg.T @ gg])[:, None]
        x_v, x_r = self.solve_full(fac, f, vs, b_v, b_r)
        x_v, x_r = self._krige(fac, f, vs, x_v, x_r)
        delta = self._to_effects(x_v[..., 0], x_r[:, 0])
        # predicted decrease ½ δᵀHδ = −½ gᵀδ (Newton)
        gdot = sum(float((g[n] * delta[n].reshape(g[n].shape)).sum()) for n in g)
        info = {"seconds": time.time() - t0, "predicted": -0.5 * gdot, "reused": bool(reuse), **self.timing}
        out = {}
        for n, val in delta.items():
            p = m.params[n]
            out[n] = torch.as_tensor(val.reshape(p.shape), dtype=p.dtype, device=p.device)
        return out, info

    def remaining(self) -> float:
        """What is left of the mean's optimisation: Newton's predicted decrease −½gᵀH⁻¹g from the current parameters
        with the last factor (one constrained solve). The strengths' LAML is read at the mode as −objective plus this;
        read at a mean that stopped below 1,000 units of predicted decrease, SIM II's LAML moved by 8 units between
        outers at the same strengths, and a 2-unit test then rejected sound steps (2026-10-06)."""
        _, info = self.step(reuse=True)
        self._last_reused = False
        return max(float(info["predicted"]), 0.0)

    def refactor(self) -> None:
        """Factor the Hessian at the model's current parameters (the last factor's point otherwise)."""
        x = {k: v.detach() for k, v in self.m.effects().items()}
        f = self.factors(x)
        vs = self._v_stats(f)
        self._last = (self.factor(self.assemble(f, vs)), f, vs)
        self._last_reused = False

    def _krige(self, fac, f, vs, x_v, x_r):
        """Impose the centrings across places: δ ← δ − V (A V)⁻¹ A δ, V = H⁻¹Aᵀ. Any V gives Aδ = 0 exactly; V from the
        Hessian of the first step of a mean fit is reused by its later steps (``refresh_krige``), which keeps the
        direction Newton's up to the change of H between steps, at a 117-column solve per fit instead of per step."""
        nc_l, nc_v = len(self.con_l), len(self.con_v)
        nc = nc_l + nc_v
        # V is recomputed for every new factor: reusing it across factors (with 8 trace probes) took IX from 6 outers to 29
        # (2026-10-06), so its exactness is worth the 1.8 s
        self._V_age = getattr(self, "_V_age", 0) + (getattr(self, "_V_fac", None) is not fac)
        if getattr(self, "_V", None) is None or (getattr(self, "_V_fac", None) is not fac and self._V_age >= 1):
            bv = np.zeros((self.E, self.U, nc))
            br = np.zeros((self.nl_red + self.ng_red, nc))
            for j, (idx, val) in enumerate(self.con_l):
                br[idx, j] = val
            for j, e in enumerate(self.con_v):
                bv[e, :, nc_l + j] = 1.0
            self._V = self.solve_full(fac, f, vs, bv, br)
            self._V_age = 0
        self._V_fac = fac
        Vv, Vr = self._V
        def apply_A(xv, xr):
            out = np.zeros((nc, xr.shape[1]))
            for j, (idx, val) in enumerate(self.con_l):
                out[j] = val @ xr[idx]
            for j, e in enumerate(self.con_v):
                out[nc_l + j] = xv[e].sum(0)
            return out
        AV = apply_A(Vv, Vr)
        Ad = apply_A(x_v, x_r)
        lam = np.linalg.lstsq(AV, Ad, rcond=None)[0]      # the leaf sums over a group repeat its within-group centring
        return x_v - Vv @ lam, x_r - Vr @ lam

    def _rhs(self, b: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
        """x-space right-hand sides (dict of [..., n] arrays shaped like the effects plus a trailing column axis) to the
        solver's (v [E,U,n], reduced (ℓ,γ) [n_red, n])."""
        U, K, npl = self.U, self.K, self.npl
        n = b["b0"].shape[-1]
        gl = np.zeros((self.nl, n))
        gl[np.arange(U) * npl + 0] = b["s_all"].reshape(U, n)
        gl[np.arange(U) * npl + 1] = b["v_all"].reshape(U, n)
        for k in range(K):
            gl[np.arange(U) * npl + 2 + k] = b["s_grp"][k]
            gl[np.arange(U) * npl + 2 + K + k] = b["v_grp"][k]
        gg = np.concatenate([b[nm].reshape(-1, n) for nm in self.gnames])
        return b["v_cat"], np.vstack([self.Tplace.T @ gl, self.Cg.T @ gg])

    def traces(self, probes: int = 32, seed: int = 0) -> dict[str, float]:
        """tr(Σ Q_j) for every component j, Σ the constrained Laplace covariance (H⁻¹ less the kriging term) at the
        current mean, with the strengths' Q_j unscaled (Fellner–Schall and LAML read τ_j·tr(ΣQ_j)). The globals
        exactly, from S⁻¹ and V; the place and leaf-place components by Hutchinson probes solved exactly with the
        factor: their matrices are large and nearly diagonal, so the trace's relative error is about
        √(2/probes)·‖M‖_F/tr(M) ≈ √(2/probes)/√n (well under 1 % here)."""
        m = self.m
        if getattr(self, "_last", None) is not None and getattr(m, "refit_converged", False):
            fac, f, vs = self._last            # the mean fit's last factor: within a converged step of the current mean
        else:
            x = {k: v.detach() for k, v in m.effects().items()}
            f = self.factors(x)
            vs = self._v_stats(f)
            fac = self.factor(self.assemble(f, vs))
        x = {k: v.detach() for k, v in m.effects().items()}
        # V for the kriging correction (kept when it was computed from this same factor)
        dummy_v = np.zeros((self.E, self.U, 1))
        dummy_r = np.zeros((self.nl_red + self.ng_red, 1))
        self._krige(fac, f, vs, dummy_v, dummy_r)
        Vv, Vr = self._V
        out: dict[str, float] = {}
        # globals: Σ_gg = Cg (S⁻¹ − Vg (AV)⁻¹ Vgᵀ) Cgᵀ
        Sinv = np.linalg.inv(fac.Sc @ fac.Sc.T)
        AV = self._apply_A(Vv, Vr)
        Vg = Vr[self.nl_red:]
        Sg = Sinv - Vg @ np.linalg.lstsq(AV, Vg.T, rcond=None)[0]
        Sx = self.Cg @ Sg @ self.Cg.T
        self._Sx = Sx
        for nm in self.gnames:
            if nm == "b0":
                continue
            c = m.components[nm]
            o = self.goff[nm]
            nn = c.batch * c.shape.Q.shape[0]
            Q = sp.kron(sp.identity(c.batch), c.shape.Q).toarray()
            out[nm] = float(np.sum(Sx[o:o + nn, o:o + nn] * Q))
        if probes == 0:
            return out
        # place and leaf-place: Hutchinson with exact solves of the constrained system
        rng = np.random.default_rng(seed)
        shapes = {nm: tuple(v.shape) for nm, v in x.items()}
        z = {nm: rng.choice([-1.0, 1.0], size=shapes[nm] + (probes,)) for nm in ("s_all", "v_all", "s_grp", "v_grp", "v_cat")}
        zz = {nm: np.zeros(shapes[nm] + (probes,)) for nm in self.gnames}
        zz.update(z)
        bv, br = self._rhs(zz)
        wv, wr = self.solve_full(fac, f, vs, bv, br)
        lam = np.linalg.lstsq(AV, self._apply_A(wv, wr), rcond=None)[0]
        wv, wr = wv - Vv @ lam, wr - Vr @ lam
        w = self._to_effects_multi(wv, wr)
        for nm in ("s_all", "v_all", "s_grp", "v_grp", "v_cat"):
            c = m.components[nm]
            zn = z[nm].reshape(c.batch, -1, probes)
            wn = w[nm].reshape(c.batch, -1, probes)
            Qw = np.stack([c.shape.Q @ wn[r] for r in range(c.batch)])
            out[nm] = float(np.einsum("bip,bip->", zn, Qw) / probes)
        self.timing["traces"] = time.time()
        return out

    def scoring(self, probes: int = 16, chunk: int = 16, seed: int = 1):
        """Everything a Newton step on ρ = log τ needs, at the current mean: the exact traces (as `traces`), the
        quadratic forms xᵀQ_jx, T_ij = tr(ΣQ_iΣQ_j) by probes z solved exactly (tr(ΣQ_iΣQ_j) = E[(Q_iΣz)ᵀ(ΣQ_jz)],
        in chunks so the leaf-place right-hand sides stay small), and R_ij = xᵀQ_iΣQ_jx from J exact solves."""
        m = self.m
        need_T = probes > 0    # a T reused across outers misdirected the weakly identified s/v strengths (2026-10-06)
        # the globals' traces exactly; the place components' from the same probes as T (their Σz), unless T is skipped
        tr = self.traces(probes=0 if need_T else 32)
        fac, f, vs = self._last
        Vv, Vr = self._V
        AV = self._apply_A(Vv, Vr)
        x = {k: v.detach() for k, v in m.effects().items()}
        # the base block's strengths (the interaction's, `ix_strengths`, are read from its own factor)
        names = [n for n, c in m.components.items() if c.rank > 0 and not c.fixed and not n.startswith("ix_")]
        shapes = {nm: tuple(v.shape) for nm, v in x.items() if not nm.startswith("ix_")}
        quad = {}
        for nm in names:
            c = m.components[nm]
            xv = _np(x[nm]).reshape(c.batch, -1)
            quad[nm] = float(sum(xv[b] @ (c.shape.Q @ xv[b]) for b in range(c.batch)))

        def apply_Q(nm, arr):
            c = m.components[nm]
            a = arr.reshape(c.batch, -1, arr.shape[-1])
            return np.stack([c.shape.Q @ a[b] for b in range(c.batch)]).reshape(arr.shape)

        def csolve(rhs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
            full = {nm: rhs.get(nm, np.zeros(shapes[nm] + (next(iter(rhs.values())).shape[-1],))) for nm in shapes}
            bv, br = self._rhs(full)
            wv, wr = self.solve_full(fac, f, vs, bv, br)
            lam = np.linalg.lstsq(AV, self._apply_A(wv, wr), rcond=None)[0]
            return self._to_effects_multi(wv - Vv @ lam, wr - Vr @ lam)

        rng = np.random.default_rng(seed)
        J = len(names)
        # the global pairs exactly from the globals' covariance block (as their traces); the probes only carry ΣQ_jz for
        # the place and leaf-place j, which also give every (global, place) pair: E[(Q_iΣz)ᵀ(ΣQ_jz)] for any i
        glob = [j for j, nm in enumerate(names) if nm in self.goff]
        plc = [j for j, nm in enumerate(names) if nm not in self.goff]
        Jp = len(plc)
        F = np.zeros((J, J))
        tr_acc, tr_sq = np.zeros(J), np.zeros(J)
        done = 0
        while done < probes and need_T:
            n = min(chunk, probes - done)
            z = {nm: rng.choice([-1.0, 1.0], size=shapes[nm] + (n,)) for nm in names}
            v = csolve(z)                                                     # Σz
            Qv = {nm: apply_Q(nm, v[nm].reshape(shapes[nm] + (n,))) for nm in names}
            for j in plc:
                per = (z[names[j]] * Qv[names[j]]).reshape(-1, n).sum(0)     # E[zᵀQ_jΣz] = tr(ΣQ_j), per probe
                tr_acc[j] += float(per.sum())
                tr_sq[j] += float((per * per).sum())
            # ΣQ_jz for every place j at once: Jp·n right-hand sides
            stacked = {nm: np.zeros(shapes[nm] + (Jp * n,)) for nm in names}
            for c, j in enumerate(plc):
                stacked[names[j]][..., c * n:(c + 1) * n] = apply_Q(names[j], z[names[j]])
            s_all = csolve(stacked)
            for i, ni in enumerate(names):
                si = s_all[ni].reshape(shapes[ni] + (Jp * n,))
                for c, j in enumerate(plc):
                    F[i, j] += float((Qv[ni] * si[..., c * n:(c + 1) * n]).sum())
            done += n
        if need_T:
            F /= probes
            self.trace_se = {}
            for j in plc:
                tr[names[j]] = tr_acc[j] / probes
                self.trace_se[names[j]] = float(np.sqrt(max(tr_sq[j] / probes - tr[names[j]] ** 2, 0.0) / max(probes - 1, 1)))
            for j in plc:
                for i in glob:
                    F[j, i] = F[i, j]
            Fp = F[np.ix_(plc, plc)]
            F[np.ix_(plc, plc)] = (Fp + Fp.T) / 2
            Sx = self._Sx
            def block(nm):
                c = m.components[nm]
                o = self.goff[nm]
                nn = c.batch * c.shape.Q.shape[0]
                return slice(o, o + nn), sp.kron(sp.identity(c.batch), c.shape.Q, format="csr")
            blocks = {j: block(names[j]) for j in glob}
            for i in glob:
                si, Qi = blocks[i]
                for j in glob:
                    if j < i:
                        continue
                    sj, Qj = blocks[j]
                    Sij = Sx[si, sj]
                    F[i, j] = F[j, i] = float(np.sum((Qi @ (Qj @ Sij.T).T) * Sij))
            self._T = F
        F = self._T if need_T else np.zeros((J, J))
        # R_ij = xᵀQ_i Σ Q_j x: one exact solve per component
        qx = {nm: np.zeros(shapes[nm] + (J,)) for nm in names}
        for j, nm in enumerate(names):
            qx[nm][..., j] = apply_Q(nm, _np(x[nm]).reshape(shapes[nm] + (1,)))[..., 0]
        u = csolve(qx)
        R = np.zeros((J, J))
        for i, ni in enumerate(names):
            ui = u[ni].reshape(shapes[ni] + (J,))
            R[i] = (qx[ni][..., i][..., None] * ui).reshape(-1, J).sum(0)
        R = (R + R.T) / 2
        return tr, quad, F, R, names

    def logdet_constrained(self) -> float:
        """log det of the Hessian on the constrained subspace, at the last factor (the Laplace marginal likelihood's
        determinant): the leaf-place blocks under their within-group centring, det(D)·(1ᵀD⁻¹1)/n per (group, place);
        the arrowhead; and the kriging term, log det(A H⁻¹ Aᵀ) over its non-zero spectrum (det NᵀHN = det H ·
        det AH⁻¹Aᵀ / det AAᵀ, the last constant in τ and dropped)."""
        fac, f, vs = self._last
        d, s = vs[0], vs[2]
        self._krige(fac, f, vs, np.zeros((self.E, self.U, 1)), np.zeros((self.nl_red + self.ng_red, 1)))
        n_k = np.bincount(self.grp, minlength=self.K)
        v_part = float(np.log(d).sum() + np.log(s).sum() - self.U * np.log(n_k).sum())
        AV = self._apply_A(*self._V)
        w = np.linalg.eigvalsh((AV + AV.T) / 2) if AV.size else np.zeros(0)
        krig = float(np.log(w[w > w.max() * 1e-12]).sum()) if w.size else 0.0
        return fac.logdet() + v_part + krig

    def _apply_A(self, xv: np.ndarray, xr: np.ndarray) -> np.ndarray:
        nc_l = len(self.con_l)
        out = np.zeros((nc_l + len(self.con_v), xr.shape[1]))
        for j, (idx, val) in enumerate(self.con_l):
            out[j] = val @ xr[idx]
        for j, e in enumerate(self.con_v):
            out[nc_l + j] = xv[e].sum(0)
        return out

    def _to_effects_multi(self, x_v: np.ndarray, x_r: np.ndarray) -> dict[str, np.ndarray]:
        """As `_to_effects` for n columns: each effect gets a trailing axis."""
        U, K, npl = self.U, self.K, self.npl
        xl = self.Tplace @ x_r[: self.nl_red]
        xg = self.Cg @ x_r[self.nl_red:]
        out = {"v_cat": x_v, "s_all": xl[np.arange(U) * npl + 0][None], "v_all": xl[np.arange(U) * npl + 1][None],
               "s_grp": np.stack([xl[np.arange(U) * npl + 2 + k] for k in range(K)]),
               "v_grp": np.stack([xl[np.arange(U) * npl + 2 + K + k] for k in range(K)])}
        for nm in self.gnames:
            o = self.goff[nm]
            nn = 1 if nm == "b0" else self.m.components[nm].batch * self.m.components[nm].shape.Q.shape[0]
            out[nm] = xg[o:o + nn]
        return out

    def _to_effects(self, x_v: np.ndarray, x_r: np.ndarray) -> dict[str, np.ndarray]:
        U, K, npl = self.U, self.K, self.npl
        xl = self.Tplace @ x_r[: self.nl_red]
        xg = self.Cg @ x_r[self.nl_red:]
        out = {"v_cat": x_v,
               "s_all": xl[np.arange(U) * npl + 0][None, :], "v_all": xl[np.arange(U) * npl + 1][None, :],
               "s_grp": np.stack([xl[np.arange(U) * npl + 2 + k] for k in range(K)]),
               "v_grp": np.stack([xl[np.arange(U) * npl + 2 + K + k] for k in range(K)])}
        for n in self.gnames:
            o = self.goff[n]
            nn = 1 if n == "b0" else self.m.components[n].batch * self.m.components[n].shape.Q.shape[0]
            out[n] = xg[o:o + nn]
        return out


    # ------------------------------------------------------------------ Laplace draws

    def nb_factors(self, x: dict[str, torch.Tensor], phi: float) -> Factors:
        """The negative binomial's expected information as cell weights, w = φμ/(φ + μ) over every cell (the
        Laplace posterior's, `laplace.Posterior`): not factorisable over the empty cells, so each leaf's slab
        [U, T, G] is streamed once and its sums kept as the leaf's own features (the mark models' path)."""
        m = self.m
        with torch.no_grad():
            LP = m._leaf_place(x)
            lin = m._time(x)[:, None, :] + (x["s_all"][0] + x["v_all"][0])[None, :, None] + (x["s_grp"] + x["v_grp"])[:, :, None]
            EX = torch.exp(lin)
            Fk = torch.exp(x["f_all"] + x["f_grp"])
            J = torch.exp(m._I(x)) if getattr(m, "ix_on", False) else None
            E, U, T, G = self.E, self.U, self.T, self.G
            mm = torch.empty((E, U), dtype=LP.dtype)
            dPk = torch.empty((E, U, T), dtype=LP.dtype)
            dR = torch.empty((E, U, G), dtype=LP.dtype)
            mubar = torch.empty((E, T, G), dtype=LP.dtype)
            pos = _np(m.ixpos) if J is not None else None
            for e in range(E):
                k = int(self.grp[e])
                xt = EX[k] if J is None or pos[e] < 0 else EX[k] * J[int(pos[e])]
                mu = LP[e][:, None, None] * xt[:, :, None] * m.N * Fk[k][None, None, :]
                w = mu if not np.isfinite(phi) else mu * (phi / (phi + mu))
                dPk[e] = w.sum(2)
                dR[e] = w.sum(1)
                mm[e] = dPk[e].sum(1)
                mubar[e] = w.sum(0)
        K = self.K
        return Factors(np.ones((E, U)), np.zeros((K, U, T)), np.zeros((K, G)),
                       np.bincount(self.grp, minlength=K)[:, None] * np.ones((1, U)), np.zeros((K, U, T)),
                       np.zeros((K, U)), np.zeros((K, U, G)), _np(mm), _np(mubar), float(mm.sum()),
                       act=np.arange(E, dtype=np.int64), dPk=_np(dPk), dPu=_np(mm), dR=_np(dR))

    def draws(self, f: Factors, n: int, seed: int) -> dict[str, np.ndarray]:
        """``n`` exact draws of the effects' displacement from N(0, H⁻¹) restricted to the centred subspace, H the
        Hessian whose cell weights ``f`` carries (`nb_factors`, or a mark model's own `factors`):
        - the place and global coordinates from their marginal precision (the Schur complement of the leaf-place
          block, which the arrowhead factors as MMᵀ, M = [[L, 0], [Yᵀ, L_S]]): x = M⁻ᵀz, one multi-RHS solve;
        - the leaf-place block given them: v = Z(D^½ z − Bx), Z the block's inverse under its centring (Var ZDZ = Z);
        - the centrings across places by conditioning by kriging, x − V(AV)⁻¹Ax.
        Returns effect-shaped arrays with a trailing axis of draws."""
        from scipy.linalg import solve_triangular
        rng = np.random.default_rng(seed)
        vs = self._v_stats(f)
        fac = self.factor(self.assemble(f, vs))
        d, inv_d, s = vs[0], vs[1], vs[2]
        z_l = rng.standard_normal((self.nl_red, n))
        z_g = rng.standard_normal((self.ng_red, n))
        x_g = solve_triangular(fac.Sc.T, z_g, lower=False)
        x_lp = fac.L.lower_t(z_l - fac.Y @ x_g)
        x_l = np.empty_like(x_lp)
        x_l[fac.p] = x_lp
        x_r = np.vstack([x_l, x_g])
        b_v = np.sqrt(d)[..., None] * rng.standard_normal((self.E, self.U, n))
        feat = self._features(f)
        _, _, back = _vk()
        gptr, gleaves = self._groups()
        dot, dth = self._B_parts(f, feat, x_r)
        if f.act is not None:
            b_v[f.act] -= f.LP[f.act][:, :, None] * self._active_dot(f, x_r, dth)
        x_v = back(np.ascontiguousarray(b_v), inv_d, s, f.LP, f.Pu, self.grp, gptr, gleaves, dot, dth, np.empty_like(b_v))
        x_v, x_r = self._krige(fac, f, vs, x_v, x_r)
        return self._to_effects_multi(x_v, x_r)


def fit_mean(model, iterations: int = 30, loglik_tol: float = 1e-3, log=None, solver: StructuredNewton | None = None) -> int:
    """The mean's MAP at fixed strengths by exact Newton (the v1 replacement of `Monolith._fit_mean`): a step from
    `StructuredNewton.step`, then Armijo backtracking on the model's own objective; stops when Newton's predicted
    decrease ½δᵀHδ falls below ``loglik_tol`` log-likelihood units. Returns the Newton steps taken."""
    nw = solver or StructuredNewton(model)
    model._solver_v1 = nw
    scale = model._objective_norm()
    steps = 0
    first = last = None
    model.refit_converged = False
    nw._last = None
    reuse = False
    refreshed = False
    streak = 0
    for _ in range(iterations):
        delta, info = nw.step(reuse=reuse)
        steps += 1
        if info["predicted"] <= 0:
            # the kriging directions (or a reused factor) are stale: refresh once, else converged
            if refreshed or (not reuse and nw._V is None):
                model.refit_converged = True
                break
            nw._V, nw._last, refreshed = None, None, True
            reuse = False
            continue
        with torch.no_grad():
            f0 = float(model.objective()) * scale
            first = f0 if first is None else first
            base = {k: v.detach().clone() for k, v in model.params.items()}
            slope = -2.0 * info["predicted"]                     # gᵀδ
            step = 1.0
            for _ in range(30):
                for k, v in model.params.items():
                    if k in delta:
                        v.copy_(base[k] + step * delta[k])
                f1 = float(model.objective()) * scale
                if np.isfinite(f1) and f1 <= f0 + 1e-4 * step * slope:
                    break
                step /= 2
            else:
                for k, v in model.params.items():
                    v.copy_(base[k])
                model.refit_converged = True
                break
        last = f1
        model.newton_log.append((f0 / scale, info["predicted"], 0, step, (f0 - f1) / scale))
        if log:
            log(f"  newton v1: objective {f1:.3f}, decrease {f0 - f1:.4g}, predicted {info['predicted']:.4g}, "
                f"step {step:g}, {info['seconds']:.2f}s (factor {info.get('factor', 0):.2f}s)")
        if info["predicted"] < loglik_tol:
            model.refit_converged = True
            break
        # chord: reuse the factor while a step delivers what it predicted
        ratio = (f0 - f1) / max(info["predicted"], 1e-300)
        streak = streak + 1 if info.get("reused") else 0
        reuse = step == 1.0 and 0.8 < ratio < 1.25 and streak < 4
    if getattr(nw, "_last", None) is not None and nw._last_reused:
        # the strengths read the factor (traces, T, the LAML's determinant): after chord steps it belongs to a point
        # up to four steps back, which put the LAML's derivative off by 10²-10³ on IX (2026-10-06); factor here
        nw.refactor()
    model.refit_decrement = 0.0 if last is None else (first - last) / scale
    return steps


# ---------------------------------------------------------------------------------------------- the interaction's factors

def _line_search(model, names: tuple[str, ...], delta: dict[str, np.ndarray], slope: float) -> float:
    """Armijo backtracking along ``delta`` (raw parameters of ``names``) on the model's own objective; returns the
    step taken (0 when none decreased it, the parameters then unchanged)."""
    scale = model._objective_norm()
    with torch.no_grad():
        f0 = float(model.objective()) * scale
        base = {n: model.params[n].detach().clone() for n in names}
        step = 1.0
        for _ in range(30):
            for n in names:
                model.params[n].copy_(base[n] + step * torch.as_tensor(delta[n].reshape(base[n].shape),
                                                                        dtype=base[n].dtype, device=base[n].device))
            f1 = float(model.objective()) * scale
            if np.isfinite(f1) and f1 <= f0 + 1e-4 * step * slope:
                return step
            step /= 2
        for n in names:
            model.params[n].copy_(base[n])
        return 0.0


def _constrained_solve(H: np.ndarray, g: np.ndarray, C: np.ndarray) -> np.ndarray:
    """δ minimising ½δᵀHδ + gᵀδ subject to Cδ = 0 (a small dense KKT system; C's rows may be redundant)."""
    n, c = H.shape[0], C.shape[0]
    K = np.zeros((n + c, n + c))
    K[:n, :n] = H
    K[:n, n:] = C.T
    K[n:, :n] = C
    rhs = np.concatenate([-g, np.zeros(c)])
    return np.linalg.lstsq(K, rhs, rcond=None)[0][:n]


def ix_sweep(model, log=None) -> float:
    """One pass of exact Newton steps over the interaction's three factors (ARCHITECTURE §4.2, ADR-0021), each given
    the other two and the base effects: η is linear in each factor alone, so each step is Newton's for a Poisson
    model with that factor's prior (the alternating fit of Goodman's row–column association models). ψ: an R × R
    block per active leaf, centred within each group's active leaves; τ: an R × R block per year plus its random
    walk and level prior; ω = os + ov: the per-place R × R data block shared by the ICAR and iid parts, a sparse
    system over 2R·U solved by CHOLMOD with the centrings imposed by kriging. Each step is line-searched on the
    model's objective. Returns the decrease of the objective (log-likelihood units)."""
    m = model
    scale = m._objective_norm()
    f_start = float(m.objective()) * scale
    R = m.rank
    with torch.no_grad():
        for factor in ("ix_psi", "ix_t", "ix_om"):
            x = m.effects()
            S = _np(m._cells(x))                                              # [A, U, T]
            G = S - _np(m.Y3)
            psi, om, tm = _np(x["ix_psi"]), _np(m._om(x)), _np(x["ix_t"])
            if factor == "ix_psi":
                c = om[:, :, None] * tm[:, None, :]                            # [R, U, T]
                A = psi.shape[1]
                comp = m.components["ix_psi"]
                g = np.einsum("aut,rut->ar", G, c) + comp.tau * psi.T            # Q = I within the groups
                Hb = np.einsum("aut,rut,sut->ars", S, c, c) + comp.tau * np.eye(R)[None]
                H = np.zeros((A * R, A * R))
                for a in range(A):
                    H[a * R:(a + 1) * R, a * R:(a + 1) * R] = Hb[a]
                labels = _np(m._labels["ix_psi"]).astype(np.int64)
                rows = []
                for grp in np.unique(labels):
                    for r in range(R):
                        row = np.zeros(A * R)
                        row[np.nonzero(labels == grp)[0] * R + r] = 1.0
                        rows.append(row)
                d = _constrained_solve(H, g.ravel(), np.array(rows)).reshape(A, R).T
                step = _line_search(m, ("ix_psi",), {"ix_psi": d}, float(g.ravel() @ d.T.ravel()))
            elif factor == "ix_t":
                b = psi[:, :, None] * om[:, None, :]                           # [R, A, U]
                T = tm.shape[1]
                comp = m.components["ix_t"]
                Q = comp.shape.Q.toarray()
                g = np.einsum("aut,rau->rt", G, b) + comp.tau * (tm @ Q.T)
                Ht = np.einsum("aut,rau,sau->trs", S, b, b)
                H = np.kron(np.eye(R), comp.tau * Q)                             # ordered (r, t)
                for t in range(T):
                    H[np.ix_(np.arange(R) * T + t, np.arange(R) * T + t)] += Ht[t]
                d = np.linalg.solve(H, -g.ravel()).reshape(R, T)
                step = _line_search(m, ("ix_t",), {"ix_t": d}, float(g.ravel() @ d.ravel()))
            else:
                dfac = psi[:, :, None] * tm[:, None, :]                        # [R, A, T]
                U = om.shape[1]
                os_, ov = m.components["ix_os"], m.components["ix_ov"]
                gu = np.einsum("aut,rat->ru", G, dfac)                            # [R, U] (the same for os and ov)
                Hu = np.einsum("aut,rat,sat->urs", S, dfac, dfac)                 # [U, R, R]
                xos, xov = _np(x["ix_os"]), _np(x["ix_ov"])
                Qs = os_.shape.Q
                g_os = gu + os_.tau * (Qs @ xos.T).T
                g_ov = gu + ov.tau * xov
                # variables ordered (u, [os_r..., ov_r...]): per place a 2R × 2R data block, ICAR coupling across places
                blk = np.zeros((U, 2 * R, 2 * R))
                blk[:, :R, :R] = Hu
                blk[:, :R, R:] = Hu
                blk[:, R:, :R] = Hu
                blk[:, R:, R:] = Hu + ov.tau * np.eye(R)[None]
                rr = (np.arange(U)[:, None, None] * 2 * R + np.arange(2 * R)[None, :, None]).repeat(2 * R, axis=2)
                cc = (np.arange(U)[:, None, None] * 2 * R + np.arange(2 * R)[None, None, :]).repeat(2 * R, axis=1)
                Hd = sp.csr_matrix((blk.ravel(), (rr.ravel(), cc.ravel())), shape=(2 * R * U, 2 * R * U))
                # the ICAR penalty on each os_r: P (2RU × RU) picks os_r[u] = variable u·2R + r
                P = sp.csr_matrix((np.ones(U * R), ((np.arange(U)[:, None] * 2 * R + np.arange(R)[None, :]).ravel(),
                                                    (np.arange(R)[None, :] * U + np.arange(U)[:, None]).ravel())),
                                  shape=(2 * R * U, R * U))
                H = (Hd + P @ sp.kron(sp.identity(R), os_.tau * Qs) @ P.T).tocsc()
                dg = H.diagonal()
                H = (H + sp.diags(RIDGE * np.maximum(dg, dg.max() * 1e-12))).tocsc()
                gvec = np.concatenate([g_os.T, g_ov.T], axis=1).ravel()           # (u, [os_r, ov_r])
                # centrings: os_r over each connected component, ov_r over all places
                comp_os = _np(m._labels["ix_os"].to(torch.float64)).astype(np.int64)
                cons = []
                for r in range(R):
                    for cpt in np.unique(comp_os):
                        idx = np.nonzero(comp_os == cpt)[0] * 2 * R + r
                        cons.append(idx)
                    cons.append(np.arange(U) * 2 * R + R + r)
                from sksparse.cholmod import cho_factor
                fa = cho_factor(H, lower=True)
                d0 = fa.solve(-gvec)
                At = np.zeros((2 * R * U, len(cons)))
                for j, idx in enumerate(cons):
                    At[idx, j] = 1.0
                V = fa.solve(At)
                AV = At.T @ V
                lam = np.linalg.lstsq(AV, At.T @ d0, rcond=None)[0]
                dvec = (d0 - V @ lam).reshape(U, 2 * R)
                d = {"ix_os": dvec[:, :R].T.copy(), "ix_ov": dvec[:, R:].T.copy()}
                step = _line_search(m, ("ix_os", "ix_ov"), d, float(gvec @ (d0 - V @ lam)))
                m._ix_omega = (fa, At, V, AV, U, R)                              # for the strengths' traces
            if factor in ("ix_psi", "ix_t") and step > 0:
                _normalise(m, factor)
            if log:
                log(f"    ix {factor}: step {step:g}")
    return f_start - float(m.objective()) * scale


def _normalise(m, factor: str) -> None:
    """ψ_r and τ_r rescaled to unit root mean square, ω_r (os and ov) taking the scale: the likelihood is invariant to
    (ψ·a, ω/(a·b), τ·b), and with ψ and τ's strengths fixed, a learned ω strength otherwise walks the scale ridge
    (v0's IX rank 3 ended with ψ at sd 5, τ at sd 13-22 and ω at sd 0.001, its strengths near 3·10⁵; v1 crept there
    at ×1.12 per outer). Normalising all factors but one is the identification of PARAFAC and of Goodman's
    association models; ω carries the amplitude, as ADR-0021 intends."""
    with torch.no_grad():
        rms = m.effects()[factor].pow(2).mean(dim=1).sqrt().clamp_min(1e-12)   # [R], of the (centred) effect
        m.params[factor].div_(rms[:, None])                                    # the centring is linear
        m.params["ix_os"].mul_(rms[:, None])
        m.params["ix_ov"].mul_(rms[:, None])


def ix_strengths(model, probes: int = 32, seed: int = 0) -> list[float]:
    """A Newton step on log τ for the ω strengths (ix_os, ix_ov), conditional on the other factors and the base, by the
    same formulas as `Monolith._score_taus`: g_j = ½(r_j − τ_j xᵀQ_jx − τ_j tr(ΣQ_j)) and the observed −H with
    tr(ΣQ_iΣQ_j) and xᵀQ_iΣQ_jx, Σ the ω block's constrained inverse (its factor from the last `ix_sweep`; traces by
    Hutchinson, solved exactly and kriged). Fellner–Schall alone crept (IX rank 1: ix_ov 100 → 531 in six outers).
    Steps clipped to ×100. Returns the |log τ| changes."""
    m = model
    fa, At, V, AV, U, R = m._ix_omega
    rng = np.random.default_rng(seed)

    def sigma(b):
        w = fa.solve(b)
        return w - V @ np.linalg.lstsq(AV, At.T @ w, rcond=None)[0]

    Qs = m.components["ix_os"].shape.Q
    Iu = sp.identity(U, format="csr")
    parts = (("ix_os", slice(0, R), Qs), ("ix_ov", slice(R, 2 * R), Iu))

    def applyQ(j, v):                                   # v [2RU, n] → Q_j v (zero outside component j)
        name, part, Q = parts[j]
        vv = v.reshape(U, 2 * R, -1)
        out = np.zeros_like(vv)
        for r in range(part.start, part.stop):
            out[:, r, :] = Q @ vv[:, r, :]
        return out.reshape(v.shape)

    z = rng.choice([-1.0, 1.0], size=(2 * R * U, probes))
    w = sigma(z)
    J = 2
    Qz = [applyQ(j, z) for j in range(J)]
    SQz = [sigma(q) for q in Qz]
    tr = np.array([float((z * applyQ(j, w)).sum()) / probes for j in range(J)])
    T = np.array([[float((applyQ(i, w) * SQz[j]).sum()) / probes for j in range(J)] for i in range(J)])
    T = (T + T.T) / 2
    x = m.effects()
    xvec = np.zeros((U, 2 * R))
    xvec[:, :R] = _np(x["ix_os"]).T
    xvec[:, R:] = _np(x["ix_ov"]).T
    xvec = xvec.reshape(-1, 1)
    Qx = [applyQ(j, xvec) for j in range(J)]
    q = np.array([float(xvec[:, 0] @ Qx[j][:, 0]) for j in range(J)])
    SQx = sigma(np.hstack(Qx))
    Rm = np.array([[float(Qx[i][:, 0] @ SQx[:, j]) for j in range(J)] for i in range(J)])
    Rm = (Rm + Rm.T) / 2
    comps = [m.components[n] for n, _, _ in parts]
    tau = np.array([c.tau for c in comps])
    rank = np.array([c.rank for c in comps])
    g = 0.5 * (rank - tau * q - tau * tr)
    tt = np.outer(tau, tau)
    negH = np.diag(0.5 * tau * (tr + q)) - 0.5 * tt * T - tt * Rm
    negH = (negH + negH.T) / 2
    dg = np.sqrt(np.maximum(np.abs(np.diag(negH)), 1e-12))
    ev, evec = np.linalg.eigh(negH / np.outer(dg, dg))
    step = (evec @ ((evec.T @ (g / dg)) / np.maximum(ev, 1e-2))) / dg
    fs = np.log(np.maximum(rank - tau * tr, 1e-12) / np.maximum(tau * q, 1e-300))
    bolder = (np.sign(fs) == np.sign(step)) & (np.abs(fs) > np.abs(step))
    step = np.clip(np.where(bolder, fs, step), -np.log(100.0), np.log(100.0))
    out = []
    for c, d in zip(comps, step, strict=True):
        new = float(c.tau * np.exp(d))
        out.append(abs(float(d)))
        c.tau = new
    return out

class Supernodal:
    """A sparse lower-triangular factor L (from CHOLMOD) cut into its fundamental supernodes, runs of columns with
    nested patterns, each stored as a dense block, for solves with many right-hand sides. A thread takes a chunk of
    the right-hand sides through every supernode: the diagonal block by substitution, the rows below by one matrix
    product. Against a column-by-column sweep: 3.75 s against 11.3 s for SIM chapter I's 1,179 Schur columns, 0.35 s
    against 0.83 s for IX's 537 (2026-10-06); CHOLMOD's own solve takes four right-hand sides at a time."""

    def __init__(self, L):
        L = sp.csc_matrix(L)
        L.sort_indices()
        self.n = L.shape[0]
        self.parts = _sn_kernels()[0](L.indptr.astype(np.int64), L.indices.astype(np.int64), L.data, self.n)

    def _run(self, B: np.ndarray, transpose: bool) -> np.ndarray:
        from numba import get_num_threads
        from threadpoolctl import threadpool_limits
        Y = np.array(B, dtype=np.float64, order="C", copy=True)
        chunk = max(1, -(-Y.shape[1] // get_num_threads()))
        with threadpool_limits(1, user_api="blas"):      # the products run inside numba's threads
            return _sn_kernels()[2 if transpose else 1](*self.parts, Y, chunk)

    def lower(self, B: np.ndarray) -> np.ndarray:
        """L⁻¹B."""
        return self._run(B, False)

    def lower_t(self, B: np.ndarray) -> np.ndarray:
        """L⁻ᵀB."""
        return self._run(B, True)


_SN = None


def _sn_kernels():
    global _SN
    if _SN is not None:
        return _SN
    from numba import njit, prange

    @njit(cache=True)
    def build(indptr, indices, data, n):
        starts = np.empty(n + 1, np.int64)
        starts[0] = 0
        ns = 1
        for j in range(1, n):
            a0, a1 = indptr[j - 1], indptr[j]
            b0, b1 = indptr[j], indptr[j + 1]
            same = (a1 - a0) == (b1 - b0) + 1 and indices[a0 + 1] == j
            if same:
                for q in range(b1 - b0):
                    if indices[a0 + 1 + q] != indices[b0 + q]:
                        same = False
                        break
            if not same:
                starts[ns] = j
                ns += 1
        starts[ns] = n
        starts = starts[:ns + 1]
        rowptr = np.empty(ns + 1, np.int64)
        valptr = np.empty(ns + 1, np.int64)
        rowptr[0] = 0
        valptr[0] = 0
        for sn in range(ns):
            nr = indptr[starts[sn] + 1] - indptr[starts[sn]]
            rowptr[sn + 1] = rowptr[sn] + nr
            valptr[sn + 1] = valptr[sn] + nr * (starts[sn + 1] - starts[sn])
        rows = np.empty(rowptr[ns], np.int64)
        vals = np.zeros(valptr[ns])
        for sn in range(ns):
            c0, c1 = starts[sn], starts[sn + 1]
            w = c1 - c0
            p0 = indptr[c0]
            for i in range(indptr[c0 + 1] - p0):
                rows[rowptr[sn] + i] = indices[p0 + i]
            for jj in range(w):                     # column c0+jj holds rows[jj:], in order
                q0 = indptr[c0 + jj]
                for i in range(indptr[c0 + jj + 1] - q0):
                    vals[valptr[sn] + (jj + i) * w + jj] = data[q0 + i]
        return starts, rowptr, rows, valptr, vals

    @njit(parallel=True, cache=True)
    def lower(starts, rowptr, rows, valptr, vals, Y, chunk):
        r = Y.shape[1]
        ns = len(starts) - 1
        for c in prange((r + chunk - 1) // chunk):
            lo, hi = c * chunk, min(r, (c + 1) * chunk)
            for sn in range(ns):
                c0, c1 = starts[sn], starts[sn + 1]
                w = c1 - c0
                r0, nr = rowptr[sn], rowptr[sn + 1] - rowptr[sn]
                v0 = valptr[sn]
                for i in range(w):
                    d = vals[v0 + i * w + i]
                    for k in range(lo, hi):
                        Y[c0 + i, k] /= d
                    for ii in range(i + 1, w):
                        lv = vals[v0 + ii * w + i]
                        if lv != 0.0:
                            for k in range(lo, hi):
                                Y[c0 + ii, k] -= lv * Y[c0 + i, k]
                nb = nr - w
                if nb == 0:
                    continue
                if w * nb >= 64:
                    T = np.dot(vals[v0 + w * w: v0 + nr * w].reshape(nb, w), np.ascontiguousarray(Y[c0:c1, lo:hi]))
                    for i in range(nb):
                        row = rows[r0 + w + i]
                        for k in range(hi - lo):
                            Y[row, lo + k] -= T[i, k]
                else:
                    for i in range(w, nr):
                        row = rows[r0 + i]
                        for jj in range(w):
                            lv = vals[v0 + i * w + jj]
                            for k in range(lo, hi):
                                Y[row, k] -= lv * Y[c0 + jj, k]
        return Y

    @njit(parallel=True, cache=True)
    def lower_t(starts, rowptr, rows, valptr, vals, Y, chunk):
        r = Y.shape[1]
        ns = len(starts) - 1
        for c in prange((r + chunk - 1) // chunk):
            lo, hi = c * chunk, min(r, (c + 1) * chunk)
            m = hi - lo
            for sn in range(ns - 1, -1, -1):
                c0, c1 = starts[sn], starts[sn + 1]
                w = c1 - c0
                r0, nr = rowptr[sn], rowptr[sn + 1] - rowptr[sn]
                v0 = valptr[sn]
                nb = nr - w
                if nb > 0:
                    if w * nb >= 64:
                        G = np.empty((nb, m))
                        for i in range(nb):
                            row = rows[r0 + w + i]
                            for k in range(m):
                                G[i, k] = Y[row, lo + k]
                        T = np.dot(vals[v0 + w * w: v0 + nr * w].reshape(nb, w).T, G)
                        for i in range(w):
                            for k in range(m):
                                Y[c0 + i, lo + k] -= T[i, k]
                    else:
                        for i in range(w, nr):
                            row = rows[r0 + i]
                            for jj in range(w):
                                lv = vals[v0 + i * w + jj]
                                for k in range(lo, hi):
                                    Y[c0 + jj, k] -= lv * Y[row, k]
                for i in range(w - 1, -1, -1):
                    for ii in range(i + 1, w):
                        lv = vals[v0 + ii * w + i]
                        if lv != 0.0:
                            for k in range(lo, hi):
                                Y[c0 + i, k] -= lv * Y[c0 + ii, k]
                    d = vals[v0 + i * w + i]
                    for k in range(lo, hi):
                        Y[c0 + i, k] /= d
        return Y

    _SN = (build, lower, lower_t)
    return _SN


def _v_kernels():
    """Fused numba kernels for the leaf-place block with many right-hand sides (b [E, U, n], C-contiguous): one pass
    each, parallel over places, instead of numpy's broadcast temporaries over E·U·n."""
    from numba import njit, prange

    @njit(parallel=True, cache=True)
    def forward(b, inv_d, s, LP, gptr, gleaves, Zb, lz):
        """Zb = Z b per (group, place); lz[k,u,:] = Σ_{e∈k} LP[e,u]·Zb[e,u,:]."""
        E, U, n = b.shape
        K = len(gptr) - 1
        for u in prange(U):
            acc = np.empty(n)
            for k in range(K):
                for c in range(n):
                    acc[c] = 0.0
                for q in range(gptr[k], gptr[k + 1]):
                    e = gleaves[q]
                    w = inv_d[e, u]
                    for c in range(n):
                        acc[c] += b[e, u, c] * w
                sk = s[k, u]
                for c in range(n):
                    acc[c] /= sk
                    lz[k, u, c] = 0.0
                for q in range(gptr[k], gptr[k + 1]):
                    e = gleaves[q]
                    w = inv_d[e, u]
                    lp = LP[e, u]
                    for c in range(n):
                        z = w * (b[e, u, c] - acc[c])
                        Zb[e, u, c] = z
                        lz[k, u, c] += lp * z
        return Zb, lz

    @njit(parallel=True, cache=True)
    def thc_sum(Zb, coef, out):
        """out[e,:] = Σ_u coef[e,u]·Zb[e,u,:]."""
        E, U, n = Zb.shape
        for e in prange(E):
            for c in range(n):
                out[e, c] = 0.0
            for u in range(U):
                w = coef[e, u]
                for c in range(n):
                    out[e, c] += w * Zb[e, u, c]
        return out

    @njit(parallel=True, cache=True)
    def back(b, inv_d, s, LP, Pu, grp, gptr, gleaves, dot, dth, x):
        """x = Z(b − Bδ) with Bδ[e,u,:] = LP[e,u]·(dot[k,u,:] + Pu[k,u]·dth[e,:])."""
        E, U, n = b.shape
        K = len(gptr) - 1
        for u in prange(U):
            acc = np.empty(n)
            for k in range(K):
                for c in range(n):
                    acc[c] = 0.0
                pu = Pu[k, u]
                for q in range(gptr[k], gptr[k + 1]):
                    e = gleaves[q]
                    lp = LP[e, u]
                    w = inv_d[e, u]
                    for c in range(n):
                        r = b[e, u, c] - lp * (dot[k, u, c] + pu * dth[e, c])
                        x[e, u, c] = r
                        acc[c] += r * w
                sk = s[k, u]
                for c in range(n):
                    acc[c] /= sk
                for q in range(gptr[k], gptr[k + 1]):
                    e = gleaves[q]
                    w = inv_d[e, u]
                    for c in range(n):
                        x[e, u, c] = w * (x[e, u, c] - acc[c])
        return x

    return forward, thc_sum, back


_VK = None


def _vk():
    global _VK
    if _VK is None:
        _VK = _v_kernels()
    return _VK
