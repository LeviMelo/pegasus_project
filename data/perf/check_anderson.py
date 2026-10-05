"""The accelerator on a synthetic Fellner-Schall-like map: same fixed point, fewer iterations (no data needed)."""
import numpy as np

from pegasus_core.monolith import _Anderson

rng = np.random.default_rng(1)
# g(u) = u + J (u* - u) with a spread spectrum (a slow mode 0.03, fast modes 0.7-1.0) plus noise: linear convergence like FS
J = np.diag([0.03, 0.05, 0.2, 0.7, 1.0, 0.9])
star = np.array([1.0, -2.0, 0.5, 3.0, 0.0, -1.0])
for noise in (0.0, 1e-4):
    for use in (False, True):
        u = np.zeros(6)
        acc = _Anderson() if use else None
        for k in range(1, 2001):
            g = u + J @ (star - u) + noise * rng.standard_normal(6)
            res = np.abs(g - u).max()
            if res < 5e-4:
                break
            u = acc.step(u, g) if use else g
        print(f"noise {noise:g} accelerated {use}: {k} iterations, error to the fixed point {np.abs(u - star).max():.2e}")
