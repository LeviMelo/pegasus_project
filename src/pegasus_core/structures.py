"""Precisions per shape (ARCHITECTURE §4.3), and the graphs and trees they act on.

Every structured effect is a Gaussian Markov random field ``x ~ N(0, (τ Q)⁻)``.
This module builds Q for each shape, scaled so that τ means the same thing
across shapes: an intrinsic field (RW, ICAR) is scaled to unit generalised
variance (Sørbye & Rue 2014), so its τ is comparable with an iid effect's.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class Shape:
    """A precision Q (n × n, sparse, scaled) with its rank and its null space treatment."""

    name: str
    Q: sp.csr_matrix
    rank: int
    centred: bool  # the effect is constrained to sum to zero (per connected component)
    components: np.ndarray | None = None  # component label per index, for per-component centring


def iid(n: int) -> Shape:
    return Shape("iid", sp.identity(n, format="csr"), n, centred=True)


def random_walk(n: int, order: int = 2, cyclic: bool = False) -> Shape:
    """RW1/RW2 on an ordered index, or its cyclic version (seasons)."""
    if cyclic:
        D = sp.lil_matrix((n, n))
        for i in range(n):
            if order == 1:
                D[i, i], D[i, (i + 1) % n] = -1, 1
            else:
                D[i, i], D[i, (i + 1) % n], D[i, (i + 2) % n] = 1, -2, 1
        D = D.tocsr()
        rank = n - 1
    else:
        D = sp.diags([1.0, -1.0], [0, 1], shape=(n - 1, n))
        if order == 2:
            D = sp.diags([1.0, -1.0], [0, 1], shape=(n - 2, n - 1)) @ D
        rank = n - order
    Q = (D.T @ D).tocsr()
    return Shape(f"rw{order}{'c' if cyclic else ''}", _scaled(Q, np.zeros(n, dtype=int)), rank, centred=True,
                 components=np.zeros(n, dtype=int))


def icar(edges: np.ndarray, weights: np.ndarray | None, n: int) -> Shape:
    """Intrinsic CAR on a weighted graph, scaled per connected component.

    Isolated nodes (islands) have no spatial neighbours; they get a unit iid
    precision instead of a degenerate row.
    """
    w = np.ones(len(edges)) if weights is None else np.asarray(weights, dtype=float)
    A = sp.coo_matrix((w, (edges[:, 0], edges[:, 1])), shape=(n, n)).tocsr()
    A = A.maximum(A.T)
    degree = np.asarray(A.sum(axis=1)).ravel()
    Q = (sp.diags(degree) - A).tocsr()
    ncomp, labels = connected_components(A, directed=False)
    isolated = degree == 0
    Q = Q + sp.diags(isolated.astype(float))
    rank = n - int(np.sum(np.bincount(labels)[np.unique(labels[~isolated])] > 0))
    return Shape("icar", _scaled(Q, labels, isolated), rank, centred=True, components=labels)


def knn_graph(points: np.ndarray, k: int = 6) -> np.ndarray:
    """Symmetric k-nearest-neighbour edges between points (lon, lat → local km)."""
    lat0 = np.deg2rad(np.mean(points[:, 1]))
    xy = np.column_stack([points[:, 0] * 111.32 * np.cos(lat0), points[:, 1] * 110.57])
    _, idx = cKDTree(xy).query(xy, k=k + 1)
    rows = np.repeat(np.arange(len(points)), k)
    cols = idx[:, 1:].ravel()
    edges = np.unique(np.sort(np.column_stack([rows, cols]), axis=1), axis=0)
    return edges


def centre(x: np.ndarray, shape: Shape) -> np.ndarray:
    """Remove the mean per connected component (the sum-to-zero constraint)."""
    if not shape.centred:
        return x
    labels = shape.components if shape.components is not None else np.zeros(x.shape[-1], dtype=int)
    out = x.copy()
    for c in np.unique(labels):
        m = labels == c
        out[..., m] -= out[..., m].mean(axis=-1, keepdims=True)
    return out


def _scaled(Q: sp.csr_matrix, labels: np.ndarray, isolated: np.ndarray | None = None) -> sp.csr_matrix:
    """Scale each intrinsic component to unit geometric mean of its generalised marginal variances."""
    Q = Q.tocsr().astype(float)
    isolated = np.zeros(Q.shape[0], dtype=bool) if isolated is None else isolated
    s = np.ones(Q.shape[0])
    for c in np.unique(labels):
        idx = np.nonzero((labels == c) & ~isolated)[0]
        if len(idx) < 2:
            continue
        Qc = Q[idx][:, idx].toarray()
        n = len(idx)
        if n <= 3000:
            # exact generalised inverse: valid whatever the null space (RW2 has two dimensions)
            inv = np.linalg.pinv(Qc, hermitian=True)
        else:
            # one-dimensional null space (a connected ICAR): (Q + 11ᵀ/n)⁻¹ − 11ᵀ/n
            inv = np.linalg.inv(Qc + np.ones((n, n)) / n) - np.ones((n, n)) / n
        s[idx] = float(np.exp(np.mean(np.log(np.clip(np.diag(inv), 1e-12, None)))))
    # components share no edges, so scaling rows and columns by √s scales each block by its own s
    root = sp.diags(np.sqrt(s))
    return (root @ Q @ root).tocsr()


def tree_paths(leaves: list[str], parent: dict[str, str | None], levels: dict[str, str],
               keep: list[str]) -> dict[str, dict[str, str]]:
    """For each leaf, its ancestor at each kept level ({leaf: {level: node}})."""
    out: dict[str, dict[str, str]] = {}
    for leaf in leaves:
        path: dict[str, str] = {}
        node: str | None = leaf
        while node is not None:
            if levels.get(node) in keep:
                path[levels[node]] = node
            node = parent.get(node)
        out[leaf] = path
    return out
