"""Power curves of the lenses at the admission reference (ARCHITECTURE section 8.4, ADR-0022).

For each lens, a rate ratio of 1.5 planted over one macro-region and window of years into the fields pickled by
``data/harness_gate/extract.py`` (chapter IX groups and Q02), each also thinned to rarer fields; the production
lens runs, and a locus is detected when a finding lies at least half inside it (``harness.region_power``). The
result is the lens's curve of power against the locus's expected count, written to
``src/pegasus_core/admission_curves.json``, which ``fields.admission`` reads.

    python scripts/measure_admission.py <lens>          # one lens's curves at each theta (data/harness_gate/admission_curve_<lens>.json)
    python scripts/measure_admission.py merge          # the shipped admission_curves.json
    python scripts/measure_admission.py coverage        # nodes each lens scans, against the former 1,000 events / 5 % rule
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

from pegasus_core import config, control, gateway, harness
from pegasus_core.scans import lenses

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "data" / "harness_gate"
OUT = ROOT / "src" / "pegasus_core" / "admission_curves.json"
FIELDS = ["IX_I05-I09", "IX_I10-I15", "IX_I20-I25", "IX_I26-I28", "IX_I60-I69", "Q02_Q02"]
THIN = (1.0, 0.3, 0.1, 0.03, 0.01)
THETAS = (1.5, 2.0, 3.0)    # 1.5 is the reference (section 8.4); the others are read only for a lens that cannot reach 0.5 at 1.5
REPLICATES = 100
RECENT = 3          # years of the change point's window: the last RECENT years, as the window the lens reads at B2


def lens_table(edges, ledger):
    """lens -> (tier, runner, windows(T), what the locus's expected count is)."""
    return {
        "outbreak": ("B2", lambda s: lenses.outbreak(s, ledger), lambda T: [(t, t + 1) for t in range(T)], "region-year"),
        "change_point": ("B2", lambda s: lenses.change_point(s, ledger), lambda T: [(T - RECENT, T)], "region, last 3 years"),
        "space_time": ("B1", lambda s: lenses.space_time(s, edges, ledger, replicates=REPLICATES),
                       lambda T: [(t, t + 1) for t in range(T)], "region-year"),
        "spatial_cluster": ("B0", lambda s: lenses.spatial_cluster(s, edges, ledger, replicates=REPLICATES),
                            lambda T: [(0, T)], "region, whole period"),
    }


def coverage() -> None:
    """The nodes of every fitted SIM.DO and SIH-RD block that each lens admits (`Session.admission`), the union, and the
    former provisional rule (at least 1,000 events over the window and events in 5 % of the units) on the same nodes."""
    from pegasus_core import fields, tools

    out: dict = {}
    for dataset, event in (("SIM.DO", "death"), ("SIH-RD", "hospitalisation")):
        sess = tools.Session(dataset, event, tools.FIT_YEARS)
        rows = {"nodes": 0, "union": 0, "former": 0, **dict.fromkeys(fields.COUNT_LENSES, 0), "blocks": {}}
        for block in sess._blocks():
            m = sess.expectations.model(block)
            reg = sess.expectations.registry
            leaf_index = {c: i for i, c in enumerate(m.data.leaves)}
            e, u, y = getattr(m, "full_counts", (m.data.e, m.data.u, m.data.y))
            totals = np.bincount(e, weights=y, minlength=len(m.data.leaves))
            verdict = sess.admission(block)

            def reachable(ok, block=block, reg=reg):
                seen, frontier = set(), [block]
                while frontier:
                    node = frontier.pop()
                    if ok(node):
                        seen.add(node)
                        if reg.level.get(node) != "category":
                            frontier.extend(reg.children.get(node, []))
                return seen

            def former(node, reg=reg, leaf_index=leaf_index, e=e, u=u, totals=totals, m=m):
                idx = [leaf_index[c] for c in reg.leaves(node) if c in leaf_index]
                return bool(idx) and totals[idx].sum() >= 1000 and np.unique(u[np.isin(e, idx)]).size >= 0.05 * len(m.data.places)

            per = {lens: reachable(lambda n, lens=lens, verdict=verdict: verdict[n][lens][0]) for lens in fields.COUNT_LENSES}
            union = set().union(*per.values())
            old = reachable(former)
            rows["nodes"] += len(verdict)
            rows["union"] += len(union)
            rows["former"] += len(old)
            for lens in fields.COUNT_LENSES:
                rows[lens] += len(per[lens])
            rows["blocks"][block] = {"nodes": len(verdict), "union": len(union), "former": len(old),
                                     **{lens: len(per[lens]) for lens in fields.COUNT_LENSES}}
            print(dataset, block, rows["blocks"][block], flush=True)
        out[dataset] = rows
    (GATE / "admission_coverage.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "blocks"} for k, v in out.items()}, indent=1))


def main() -> None:
    if sys.argv[1:] == ["coverage"]:
        return coverage()
    if sys.argv[1:] == ["merge"]:
        return merge()
    lens = sys.argv[1]
    ledger = control.Ledger(GATE / f"ledger_admission_{lens}")
    rows: dict[float, list] = {t: [] for t in THETAS}
    for name in FIELDS:
        with open(GATE / f"{name}.pkl", "rb") as fh:
            d = pickle.load(fh)
        tier, run, windows, _ = lens_table(d["edges"], ledger)[lens]
        region = gateway.regions(d["B1"].places, "ibge_macroregion")
        for theta in THETAS:
            for thin in THIN:
                t0 = time.time()
                got = harness.region_power(d[tier], run, region, theta, windows(d[tier].y.shape[1]), thin)
                rows[theta] += got
                print(name, lens, theta, thin, f"{np.mean([h for _, h in got]):.2f} of {len(got)}", f"{time.time() - t0:.0f}s",
                      flush=True)
    edges_ = np.array([0, 3, 10, 30, 100, 300, 1000, 3000, 10000, 30000, 1e5, np.inf])
    out = {"locus": lens_table(None, ledger)[lens][3], "theta": {}}
    for theta, r in rows.items():
        m, h = np.array([x[0] for x in r]), np.array([x[1] for x in r], dtype=float)
        bins = []
        for lo, hi in zip(edges_[:-1], edges_[1:], strict=True):
            sel = (m >= lo) & (m < hi)
            if sel.sum() >= 5:
                bins.append({"lo": float(lo), "hi": None if np.isinf(hi) else float(hi), "n": int(sel.sum()),
                             "median_m": float(np.median(m[sel])), "power": round(float(h[sel].mean()), 3)})
        out["theta"][str(theta)] = {"bins": bins}
    (GATE / f"admission_curve_{lens}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out))


def merge() -> None:
    """Assemble the shipped curves from the per-lens measurements."""
    result = {"reference_theta": 1.5, "fields": FIELDS, "thin": list(THIN), "replicates": REPLICATES,
              "code_version": config.code_version(), "lenses": {}}
    for lens in ("outbreak", "change_point", "space_time", "spatial_cluster"):
        f = GATE / f"admission_curve_{lens}.json"
        if f.exists():
            result["lenses"][lens] = json.loads(f.read_text(encoding="utf-8"))
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
