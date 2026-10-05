"""Rio Doce confirmatory test (ledger 49f1626af33f4867): the monthly BP trained through 2015-10.

BP (ADR-0009) trains on whole years; the declaration trains through October 2015, so the training assembly is
truncated to months 2010-01..2015-10 (70 months) and stored under its own key ("through": 201510). Files 2010-2016
feed the training months (an October 2015 admission may be filed in 2016); the test assembly reads files 2015-2017
(an admission of December 2016 may be filed in 2017). Usage: python data/rio_doce_bp.py fit X|XI
"""
import json
import os
import sys

from pegasus_core import graphs, monolith

THROUGH, T0 = 201510, 70                      # 2010-01 .. 2015-10
TRAIN_YEARS = list(range(2010, 2015))         # the label BP's `train_last = 2014` gives the truncated training set
_assemble = monolith.assemble


def truncated(dataset, event, block, years, *a, **kw):
    years = list(years)
    if kw.get("grain") == "month" and years == TRAIN_YEARS:
        d = _assemble(dataset, event, block, range(2010, 2017), *a, **kw)
        keep = d.t < T0
        d.e, d.u, d.t, d.g, d.y = d.e[keep], d.u[keep], d.t[keep], d.g[keep], d.y[keep]
        d.N = d.N[:, :T0]
        d.month_of_year = d.month_of_year[:T0]
        d.key = {**d.key, "through": THROUGH, "years": TRAIN_YEARS}
        return d
    return _assemble(dataset, event, block, years, *a, **kw)


monolith.assemble = truncated


def fit(block: str) -> None:
    data = monolith.assemble("SIH-RD", "hospitalisation", block, TRAIN_YEARS, grain="month")
    print(f"ASSEMBLED {block} T {data.N.shape[1]} nnz {len(data.y)} events {data.y.sum():.0f} {data.key}", flush=True)
    for device in (os.environ.get("PEGASUS_DEVICE", "cpu"), "cpu"):
        try:
            model = monolith.Monolith(data, graphs.graph(data.places, "contiguity"), "contiguity", device=device)
            model.fit(outer=40, log=lambda line, b=block: print(f"  {b} {line}", flush=True))
            model.save()
            print(f"BLOCK {block} {json.dumps(model.summary(), default=float)}", flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL on {device}: {type(exc).__name__}: {exc}", flush=True)
    raise SystemExit("fit failed")


if __name__ == "__main__":
    if sys.argv[1] == "fit":
        for b in sys.argv[2:]:
            fit(b)
