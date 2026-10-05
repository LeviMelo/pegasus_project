"""Scales: the unit a per-place lens reads (ARCHITECTURE §7.1).

A lens that contrasts a place with its neighbours, or its groups with each other, sees a divergence
that is shared by a whole state only at the state's scale: municipality against neighbouring
municipality, a state-wide trend cancels. A **scale** is a partition of the places into units (the
municipality itself, an IBGE immediate region, a state); a lens run over several scales tests every
unit of every scale in one family (one Benjamini–Hochberg over all of them), so the number of scales
is paid in the multiplicity, and a finding's locus is the unit's member places.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Scale:
    name: str
    labels: np.ndarray            # one label per place

    def __post_init__(self):
        self.units, self.index = np.unique(np.asarray(self.labels).astype(str), return_inverse=True)

    @property
    def n(self) -> int:
        return len(self.units)

    def members(self, k: int) -> np.ndarray:
        return np.nonzero(self.index == k)[0]

    def sum(self, a: np.ndarray) -> np.ndarray:
        """Sum the places' rows of ``a`` [U, ...] into the units' [n, ...]."""
        out = np.zeros((self.n,) + a.shape[1:])
        np.add.at(out, self.index, a)
        return out

    def edges(self, edges: np.ndarray) -> np.ndarray:
        """The units' graph: two units are adjacent when any pair of their places is."""
        a, b = self.index[edges[:, 0]], self.index[edges[:, 1]]
        keep = a != b
        pairs = np.unique(np.sort(np.stack([a[keep], b[keep]], 1), axis=1), axis=0)
        return pairs.reshape(-1, 2)


def municipality(places: np.ndarray) -> Scale:
    return Scale("municipality", np.asarray(places).astype(int))


def standard(places: np.ndarray) -> list[Scale]:
    """Municipality, IBGE immediate region (about 500 units) and state (27)."""
    from .. import gateway

    return [municipality(places), Scale("region", gateway.regions(places, "ibge_immediate_region")),
            Scale("state", gateway.regions(places, "uf"))]
