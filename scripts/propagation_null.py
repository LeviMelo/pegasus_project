"""Calibration and power of the propagation test on the real geography (BACKLOG 3.3, ARCHITECTURE §7.2 component 7).

    PYTHONUTF8=1 $PY scripts/propagation_null.py --places 300 --worlds 30

Onsets are placed on ``--places`` municipalities drawn at random from Brazil's, with their population-centre distances,
and `propagation.waves` is run on each world with both nulls, at q = 0.05:

    blocks    every state starts at a random period (a random order of the states) and its places are jittered by 1: onsets
              clustered in space with no ordering around any source. The share of worlds in which a wave is reported is
              the false-discovery rate under the clustered null; it must be at most q for a null to be usable.
    shuffle   the same onsets shuffled over places: no clustering, no ordering.
    planted   onset = distance from a random source / speed + noise (sd 0, 1, 2 periods): the share of worlds in which the
              wave is reported, and the median ratio of the estimated to the planted speed.

Writes ``data/probes/propagation/null.json``. The worlds are synthetic: they calibrate the test, they do not validate a
finding (CLAUDE.md §1.0, question 8); the findings are judged on documented events (evaluation 2026-10-10-propagation).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from pegasus_core import config, gateway, propagation


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--places", type=int, default=300)
    ap.add_argument("--worlds", type=int, default=30)
    ap.add_argument("--q", type=float, default=0.05)
    ap.add_argument("--surrogates", type=int, default=199)
    ap.add_argument("--speed", type=float, default=100.0, help="planted speed, km per period")
    a = ap.parse_args()
    table = gateway.proximity_graph("contiguity")
    codes = np.unique(np.concatenate([table.column("a").to_numpy(), table.column("b").to_numpy()]))
    rng = np.random.default_rng(2026)
    places = np.sort(rng.choice(codes, a.places, replace=False))
    pts = gateway.municipality_points(places)
    dist = propagation.great_circle(pts, pts)
    uf = places // 10000
    out: dict = {"places": a.places, "worlds": a.worlds, "q": a.q, "surrogates": a.surrogates, "speed": a.speed}
    for null in ("spectral", "permutation"):
        row: dict = {}

        def blocks() -> np.ndarray:
            off = dict(zip(np.unique(uf), rng.permutation(len(np.unique(uf))) * 2.0, strict=True))
            t = np.round(np.array([off[u] for u in uf]) + rng.normal(0, 1.0, a.places))
            return t - t.min() + 1

        row["blocks_false"] = sum(bool(propagation.waves(blocks(), dist, a.q, null, ("blocks", w, null), a.surrogates, 1))
                                  for w in range(a.worlds)) / a.worlds
        row["shuffle_false"] = sum(bool(propagation.waves(rng.permutation(blocks()), dist, a.q, null, ("shuffle", w, null),
                                                          a.surrogates, 1)) for w in range(a.worlds)) / a.worlds
        for noise in (0.0, 1.0, 2.0):
            hit, ratio = 0, []
            for w in range(a.worlds):
                src = int(rng.integers(a.places))
                t = np.round(dist[src] / a.speed + rng.normal(0, noise, a.places))
                ws = propagation.waves(t - t.min() + 1, dist, a.q, null, ("planted", w, noise, null), a.surrogates, 1)
                hit += bool(ws)
                ratio += [1.0 / ws[0]["slope"] / a.speed] if ws else []
            row[f"planted_noise{noise:g}"] = {"detected": hit / a.worlds,
                                              "speed_ratio_median": round(float(np.median(ratio)), 3) if ratio else None}
        out[null] = row
        print(null, json.dumps(row), flush=True)
    path = Path(config.REPO) / "data" / "probes" / "propagation"
    path.mkdir(parents=True, exist_ok=True)
    (path / "null.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
