"""Sequential Monte Carlo tests (Besag and Clifford 1991, "Sequential Monte Carlo p-values", Biometrika 78:301).

One mechanism for every test whose null is simulated (the scans, the corroboration of a lead, the propagation of a
wave). Replicates of the statistic are drawn in blocks, on demand; a test stops at the ``h``-th replicate at or above the
observed statistic, the ``n``-th, and its p-value is h/n, valid whatever the stopping (Besag and Clifford's theorem). A
statistic that the cap ``n_max`` leaves with fewer than ``h`` of them has the usual (hits + 1)/(n + 1) and is *not*
settled: the caller refines it (a fitted tail) or reads it as it is. Far from significant, a test costs about h/p
replicates instead of ``n_max``: under a null, p is uniform and a cap of 200 needs about 55 replicates on average.

The drawn replicates are kept (`Draws`), so a second statistic of the same null (the scan's next cluster, another
source's test of the same place sets) extends the same sequence instead of redrawing it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

#: replicates at or above the observed at which a test stops: it is then far from significant (Besag and Clifford)
EXCEEDANCES = 10


@dataclass(frozen=True)
class Sequential:
    """A sequential test's reading: ``p``, the replicates ``n`` it used, the ``hits`` among them at or above the
    observed statistic, and whether it ``settled`` (``hits`` reached ``h``: p = h/n) or the cap ended it first
    (p = (hits + 1)/(n + 1))."""
    p: float
    n: int
    hits: int
    settled: bool


class Draws:
    """The replicates of one null, drawn in blocks and kept. ``draw(start, count)`` returns ``count`` replicates, the
    ones numbered ``start`` on: a block's seed is its own start, so the sequence does not depend on where tests stopped."""

    def __init__(self, draw: Callable[[int, int], np.ndarray], block: int = 100):
        self.draw, self.block = draw, int(block)
        self.values = np.zeros(0)

    def __len__(self) -> int:
        return len(self.values)

    def more(self, upto: int | None = None) -> bool:
        """Draw the next block (``upto``: the last replicate wanted, which trims it); False when none is left."""
        count = self.block if upto is None else min(self.block, int(upto) - len(self.values))
        if count <= 0:
            return False
        self.values = np.concatenate([self.values, np.asarray(self.draw(len(self.values), count), dtype=float)])
        return True

    def extend(self, upto: int) -> None:
        """Draw until ``upto`` replicates are held."""
        while len(self.values) < upto:
            self.more(upto)

    def test(self, observed: float, h: int = EXCEEDANCES, n_max: int = 1000) -> Sequential:
        """The statistic ``observed`` against the null's upper tail: replicates are drawn (and kept) until the ``h``-th
        at or above it, or ``n_max`` of them. A longer sequence already held is read from its start."""
        while True:
            hits = np.flatnonzero(self.values[:n_max] >= observed)
            if len(hits) >= h:
                n = int(hits[h - 1]) + 1
                return Sequential(h / n, n, h, True)
            if not self.more(n_max):
                n = min(len(self.values), n_max)
                return Sequential((len(hits) + 1) / (n + 1), n, len(hits), False)


def sequential_p(draw: Callable[[int, int], np.ndarray], observed: float, h: int = EXCEEDANCES, n_max: int = 1000,
                 block: int = 100) -> Sequential:
    """One sequential test of ``observed`` against replicates drawn by ``draw(start, count)`` (module docstring)."""
    return Draws(draw, block).test(observed, h, n_max)
