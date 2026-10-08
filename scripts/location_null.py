"""Null worlds of a location field (a measure's mean, a share's logit): does each location method hold q with no minimum
effect (work plan S1.1, ARCHITECTURE §13.2's `LOCATION_EFFECT` row)?

    PYTHONUTF8=1 $PY scripts/location_null.py SIH-RD hospitalisation X J09-J18 DIAS_PERM --worlds 20

Each world replaces the field's observed locations by a draw from its own predictive with its noise structure
(`surprise.field_replicate`, N1 included) and runs every method that reads a location at relevance 0 (rate ratio 1)
and at the current `surprise.LOCATION_EFFECT`, on a sandbox ledger. A world "holds" when a method reports nothing; the
share of worlds with a finding is the method's false-discovery rate under the complete null (it must be at most q).
Writes ``data/probes/location_null/<field>.json``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

import numpy as np
from scipy import special

from pegasus_core import config, control, fields, questions, surprise, tools


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("event")
    ap.add_argument("block")
    ap.add_argument("node")
    ap.add_argument("measure")
    ap.add_argument("--worlds", type=int, default=20)
    ap.add_argument("--years", default="2010-2023")
    a = ap.parse_args()
    y0, y1 = (int(x) for x in a.years.split("-"))
    src = fields.measure_source(a.dataset, a.event, a.measure)
    s = tools.Session(a.dataset, a.event, list(range(y0, y1 + 1)), "contiguity", source=src,
                      ledger=control.Ledger(config.home() / "harness" / "location_null_ledger"))
    s.expectations.model(a.block)
    base = s.expectations.surprise(a.node, "B1")
    methods = sorted({m.lens or m.id for q in questions.QUESTIONS.values() for m in q.methods
                      if "mark" in m.kinds and tools.LENS_TIERS.get(m.lens or m.id) == "B1"})   # read against B1
    effect = surprise.location_rate_ratio(base)
    rng = np.random.default_rng(config.seed("location_null", base.field.id))
    rows = []
    for w in range(a.worlds):
        y = surprise.field_replicate(base, base.noise, rng)
        has = base.w > 0
        z = np.where(has, (np.where(has, y, 0.0) - np.where(has, base.mu, 0.0)) * np.sqrt(np.where(has, base.w, 0.0)), 0.0)
        world = dataclasses.replace(base, y=np.where(has, y, np.nan), z=z, u=special.ndtr(z))   # its own scores
        world.__dict__.pop("_memo", None)
        s._local.memo = {(a.node, "B1", None): world}
        for lens in methods:
            for label, rr in (("relevance 0", 1.0), ("LOCATION_EFFECT", effect)):
                try:
                    found = s.scan(a.node, lens, rate_ratio=rr)
                except Exception as exc:  # noqa: BLE001 - a method that cannot read the world is recorded
                    rows.append({"world": w, "method": lens, "effect": label, "error": f"{type(exc).__name__}: {exc}"})
                    continue
                rows.append({"world": w, "method": lens, "effect": label, "findings": len(found)})
        print(f"world {w}: " + ", ".join(f"{r['method']}/{r['effect']}={r.get('findings', 'err')}"
                                         for r in rows if r["world"] == w), flush=True)
    s._local.memo = None
    summary = {}
    for r in rows:
        if "findings" in r:
            k = f"{r['method']} at {r['effect']}"
            n, hit = summary.get(k, (0, 0))
            summary[k] = (n + 1, hit + (r["findings"] > 0))
    out = {"field": base.field.id, "measure": a.measure, "worlds": a.worlds, "noise": dataclasses.asdict(base.noise),
           "location_effect": surprise.LOCATION_EFFECT, "rate_ratio": effect,
           "worlds_with_findings": {k: {"worlds": n, "with_findings": h} for k, (n, h) in summary.items()}, "rows": rows}
    path = Path("data/probes/location_null") / f"{a.dataset}_{a.node}_{a.measure}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    for k, (n, h) in sorted(summary.items()):
        print(f"{k}: {h} of {n} null worlds with a finding")


if __name__ == "__main__":
    main()
