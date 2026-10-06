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
    m: np.ndarray         # [E, U]   LP · Pu[k(e)]
    mubar: np.ndarray     # [E, T, G] Σ_u μ
    total: float


class Arrowhead:
    """A factored arrowhead [[A, B],[Bᵀ, C]] (place system, globals in reduced coordinates). With LLᵀ = PAPᵀ
    (CHOLMOD) and Y = L⁻¹PB: S = C − YᵀY = L_S L_Sᵀ, and a solve is one forward and one back substitution with L
    plus a dense solve with L_S."""

    def __init__(self, fa, Y: np.ndarray, B: np.ndarray, Sc: np.ndarray, nl: int, L: sp.csc_matrix | None = None):
        self.fa, self.Y, self.B, self.Sc, self.nl, self.L = fa, Y, B, Sc, nl, L
        self.p = np.asarray(fa.perm)

    def __call__(self, b: np.ndarray) -> np.ndarray:
        one = b.ndim == 1
        b = b[:, None] if one else b
        bl, bg = b[: self.nl], b[self.nl:]
        many = self.L is not None and b.shape[1] >= 8
        yl = lower_solve(self.L, bl[self.p]) if many else self.fa.solve(bl[self.p], system="L")
        rhs = bg - self._Yt_times(yl, many)
        xg = np.linalg.solve(self.Sc.T, np.linalg.solve(self.Sc, rhs))
        z = lower_solve_t(self.L, yl - self._Y_times(xg, many)) if many else self.fa.solve(yl - self.Y @ xg, system="Lt")
        xl = np.empty_like(z)
        xl[self.p] = z
        out = np.vstack([xl, xg])
        return out[:, 0] if one else out

    def _gpu_Y(self):
        """Y on the GPU (float64), uploaded once per factorisation, for the many-column products: Yᵀy and Y·x cost
        2·n_place·n_global per column, about 27 GFLOP for the kriging's 117 columns (2026-10-06)."""
        if getattr(self, "_Yg", None) is None:
            try:
                import cupy as cp
                self._cp = cp
                self._Yg = cp.asarray(self.Y)
            except Exception:  # noqa: BLE001 - no GPU: the CPU products
                self._Yg = False
        return self._Yg

    def _Yt_times(self, y: np.ndarray, many: bool) -> np.ndarray:
        Yg = self._gpu_Y() if many else False
        if Yg is False or Yg is None:
            return self.Y.T @ y
        return self._cp.asnumpy(Yg.T @ self._cp.asarray(y))

    def _Y_times(self, x: np.ndarray, many: bool) -> np.ndarray:
        Yg = self._gpu_Y() if many else False
        if Yg is False or Yg is None:
            return self.Y @ x
        return self._cp.asnumpy(Yg @ self._cp.asarray(x))

    def logdet(self) -> float:
        return float(self.fa.logdet()) + 2.0 * float(np.log(np.diag(self.Sc)).sum())


class StructuredNewton:
    """Exact Newton steps for one fitted `Monolith` (count block, no interaction)."""

    def __init__(self, model):
        if getattr(model, "ix_on", False) or getattr(model, "rank", 0):
            raise NotImplementedError("the v1 solver does not carry the low-rank interaction yet")
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
        # the projector of the global effects: the Jacobian of each component's own centring (`Monolith._centred`)
        P = np.zeros((self.ng, self.ng))
        P[0, 0] = 1.0
        m = self.m
        for n in names[1:]:
            p = m.params[n].detach()
            J = torch.autograd.functional.jacobian(lambda r, n=n: m._centred(n, r).reshape(-1), p)
            o = self.goff[n]
            P[o:o + sizes[n], o:o + sizes[n]] = _np(J.reshape(sizes[n], sizes[n]))
        w, v = np.linalg.eigh((P + P.T) / 2)
        self.Cg = v[:, w > 0.5]                       # orthonormal basis of range(P)
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
        s_all and s_grp's contrasts per connected component of the graph; v_all and v_grp's contrasts over all
        places; each leaf of v_cat over all places."""
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
        rows_l.append((allp * self.npl_red + 1, np.ones(U)))
        for j in range(K - 1):
            rows_l.append((allp * self.npl_red + 2 + (K - 1) + j, np.ones(U)))
        self.con_l = rows_l
        self.con_v = list(range(self.E))                 # one per leaf: Σ_u v[e, u] = 0

    # ------------------------------------------------------------------ factors and gradient

    def factors(self, x: dict[str, torch.Tensor]) -> Factors:
        m = self.m
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
            total = float((W * Pu).sum())
        f = Factors(_np(LP), _np(EX), _np(Fk), _np(W), _np(Pk), _np(Pu), _np(R), _np(mm), _np(mubar), total)
        self.timing["factors"] = time.time() - t0
        return f

    def gradient(self, x: dict[str, torch.Tensor], f: Factors) -> dict[str, np.ndarray]:
        """∂(−log L + penalty)/∂x for every effect (x-space, unscaled: log-likelihood units)."""
        m = self.m
        WPu = f.W * f.Pu
        Ht = (f.W[:, :, None] * f.Pk).sum(1)
        Fg = (f.W[:, :, None] * f.R).sum(1)
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
        WPu = f.W * f.Pu

        # ---- γγ: data (design over (e,t,g) cells weighted by Σ_u μ), minus Σ_k Mkᵀ(Σ_u q φφᵀ)Mk, θc terms
        D = self._global_design()
        Hgg = (D.T @ sp.diags(f.mubar.ravel()) @ D).toarray()
        fd = self._fmap_dense()
        for k in range(K):
            Sk = (feat[k] * q[k][:, None]).T @ feat[k]
            Hgg -= fd[k].T @ Sk @ fd[k]
        # θc[e] with the shared features: −Σ_u η_eu φ_{k(e),u}; θc–θc: −Σ_u Pu²(α LP δ − α α'/s)
        eta = zeta * f.LP * f.Pu[self.grp]                         # [E, U]
        oc = self.goff["th_cat"]
        for k in range(K):
            leaves = np.nonzero(self.grp == k)[0]
            cross = (eta[leaves] @ feat[k]) @ fd[k]                    # [n_k, ng]
            Hgg[oc + leaves, :] -= cross
            Hgg[:, oc + leaves] -= cross.T
            pu2 = f.Pu[k] ** 2
            a = alpha[leaves]
            diag = (a * f.LP[leaves]) @ pu2
            off = (a * (pu2 / s[k])[None, :]) @ a.T
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
        a_tot = WPu.sum(0) - np.einsum("ku,ku->u", q, f.Pu ** 2)                 # a–a
        ab = WPu - q * f.Pu ** 2                                                # a–b_k and b_k–b_k
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
        """Factor the arrowhead: CHOLMOD on the place system (its symbolic analysis kept across steps), Y = L⁻¹PB for
        the globals' columns (B already in reduced global coordinates), and the dense Cholesky of S = C − YᵀY."""
        from sksparse.cholmod import cho_factor
        Al, Bl, Hgg = parts
        t0 = time.time()
        if self._symbolic is None:
            self._symbolic = cho_factor(Al, lower=True)
        else:
            self._symbolic.factorize(Al)
        fa = self._symbolic
        t1 = time.time()
        B = Bl @ self.Cg                                              # [n_place_red, ng_red]
        p = np.asarray(fa.perm)
        L = sp.csc_matrix(fa.get_factor("LL"))
        L.sort_indices()
        Y = lower_solve(L, B[p])
        t2 = time.time()
        S = self.Cg.T @ ((Hgg + Hgg.T) * 0.5) @ self.Cg - Y.T @ Y
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
        red = self._shared_to_reduced(lz, feat, fmap, f)                    # [n_red, n]
        thc = thc_sum(Zb, f.LP * f.Pu[self.grp], np.empty((self.E, n)))     # [E, n]
        red += self._thc_to_reduced(thc)
        x_r = fac(b_r - red)
        # back-substitution: δ_v = Z(b_v − B δ_r)
        dot, dth = self._B_parts(f, feat, x_r)
        x_v = back(b_v, inv_d, s, f.LP, f.Pu, self.grp, gptr, gleaves, dot, dth, np.empty_like(b_v))
        return x_v, x_r

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

    def _shared_to_reduced(self, lz: np.ndarray, feat, fmap, f) -> np.ndarray:
        """Σ_(k,u) lz[k,u,·] ω_ku mapped to the reduced coordinates (ℓ rows and γ columns)."""
        U, K, npl = self.U, self.K, self.npl
        n = lz.shape[2]
        xl = np.zeros((self.nl, n))
        # place rows: a[u] (s_all, v_all) gets Σ_k lz Pu ; b[k,u] gets lz Pu
        lp = lz * f.Pu[:, :, None]
        xl[np.arange(U) * npl + 0] = lp.sum(0)
        xl[np.arange(U) * npl + 1] = lp.sum(0)
        for k in range(K):
            xl[np.arange(U) * npl + 2 + k] = lp[k]
            xl[np.arange(U) * npl + 2 + K + k] = lp[k]
        xg = np.zeros((self.ng, n))
        for k in range(K):
            xg += fmap[k].T @ (feat[k].T @ lz[k])
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
        if reuse and getattr(self, "_last", None) is not None:
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

    def scoring(self, probes: int = 16, chunk: int = 4, seed: int = 1):
        """Everything a Newton step on ρ = log τ needs, at the current mean: the exact traces (as `traces`), the
        quadratic forms xᵀQ_jx, T_ij = tr(ΣQ_iΣQ_j) by probes z solved exactly (tr(ΣQ_iΣQ_j) = E[(Q_iΣz)ᵀ(ΣQ_jz)],
        in chunks so the leaf-place right-hand sides stay small), and R_ij = xᵀQ_iΣQ_jx from J exact solves."""
        m = self.m
        tr = self.traces(probes=int(__import__("os").environ.get("PEGASUS_TRACE_PROBES", "32")))   # exact globals; probes for the rest
        fac, f, vs = self._last
        need_T = probes > 0    # a T reused across outers misdirected the weakly identified s/v strengths (2026-10-06)
        Vv, Vr = self._V
        AV = self._apply_A(Vv, Vr)
        x = {k: v.detach() for k, v in m.effects().items()}
        names = [n for n, c in m.components.items() if c.rank > 0 and not c.fixed]
        shapes = {nm: tuple(v.shape) for nm, v in x.items()}
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
        F = np.zeros((J, J))
        done = 0
        while done < probes:
            n = min(chunk, probes - done)
            z = {nm: rng.choice([-1.0, 1.0], size=shapes[nm] + (n,)) for nm in names}
            v = csolve(z)                                                     # Σz
            Qv = {nm: apply_Q(nm, v[nm].reshape(shapes[nm] + (n,))) for nm in names}
            if not need_T:
                done += n
                continue
            # ΣQ_jz for every j at once: J·n right-hand sides
            stacked = {nm: np.zeros(shapes[nm] + (J * n,)) for nm in names}
            for j, nm in enumerate(names):
                stacked[nm][..., j * n:(j + 1) * n] = apply_Q(nm, z[nm])
            s_all = csolve(stacked)
            for i, ni in enumerate(names):
                for j in range(J):
                    sj = s_all[ni].reshape(shapes[ni] + (J * n,))[..., j * n:(j + 1) * n]
                    F[i, j] += float((Qv[ni] * sj).sum())
            done += n
        if need_T:
            F /= probes
            F = (F + F.T) / 2
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
    model.refit_decrement = 0.0 if last is None else (first - last) / scale
    return steps


def _lower_solve_kernel():
    from numba import njit, prange

    @njit(parallel=True, cache=True, fastmath=False)
    def solve(indptr, indices, data, Y, chunk):
        """Y ← L⁻¹Y in place, L lower triangular CSC with the diagonal first in each column; Y [n, r] row-major. The
        right-hand sides are split into chunks of columns solved in parallel; within a chunk each column of L
        updates contiguous rows of Y."""
        n, r = Y.shape
        nchunks = (r + chunk - 1) // chunk
        for c in prange(nchunks):
            lo, hi = c * chunk, min(r, (c + 1) * chunk)
            for j in range(n):
                p0, p1 = indptr[j], indptr[j + 1]
                d = data[p0]
                for k in range(lo, hi):
                    Y[j, k] /= d
                for p in range(p0 + 1, p1):
                    i = indices[p]
                    lij = data[p]
                    for k in range(lo, hi):
                        Y[i, k] -= lij * Y[j, k]
        return Y

    @njit(parallel=True, cache=True, fastmath=False)
    def solve_t(indptr, indices, data, Y, chunk):
        """Y ← L⁻ᵀY in place (back substitution over the columns of L, last first)."""
        n, r = Y.shape
        nchunks = (r + chunk - 1) // chunk
        for c in prange(nchunks):
            lo, hi = c * chunk, min(r, (c + 1) * chunk)
            for j in range(n - 1, -1, -1):
                p0, p1 = indptr[j], indptr[j + 1]
                for p in range(p0 + 1, p1):
                    i = indices[p]
                    lij = data[p]
                    for k in range(lo, hi):
                        Y[j, k] -= lij * Y[i, k]
                d = data[p0]
                for k in range(lo, hi):
                    Y[j, k] /= d
        return Y

    return solve, solve_t


_LSOLVE = None


def lower_solve(L: sp.csc_matrix, B: np.ndarray, chunk: int = 32) -> np.ndarray:
    """L⁻¹B for a sparse lower-triangular L (CSC, diagonal stored first) and many right-hand sides: the numba kernel of
    `_lower_solve_kernel` (CHOLMOD's factor here is simplicial, and its multi-RHS solve ran at about 4 GFLOP/s)."""
    return _tri(L, B, chunk, transpose=False)


def lower_solve_t(L: sp.csc_matrix, B: np.ndarray, chunk: int = 32) -> np.ndarray:
    """L⁻ᵀB, as `lower_solve`."""
    return _tri(L, B, chunk, transpose=True)


def _tri(L, B, chunk, transpose):
    global _LSOLVE
    if _LSOLVE is None:
        _LSOLVE = _lower_solve_kernel()
    if not (sp.issparse(L) and L.format == "csc" and L.has_sorted_indices):
        L = sp.csc_matrix(L)
        L.sort_indices()
    Y = np.array(B, dtype=np.float64, order="C", copy=True)
    args = (L.indptr.astype(np.int64, copy=False), L.indices.astype(np.int64, copy=False), L.data, Y, chunk)
    return _LSOLVE[1](*args) if transpose else _LSOLVE[0](*args)


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
