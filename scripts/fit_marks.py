"""Fit and read the SIH marks (ARCHITECTURE §4.4): length of stay, cost, death in hospital, ICU days.

    python scripts/fit_marks.py fit  MARK BLOCK FIRST LAST     fit one mark of one chapter (stores the model, the facility effects)
    python scripts/fit_marks.py read MARK BLOCK FIRST LAST     calibration of the tiers, the lenses, negatives, top leads with their triage

Run under scripts/heavy.py. Records go to data/marks/<mark>_<block>.json (gitignored).
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from pegasus_core import control, harness, marks, tools
from pegasus_core.scans import lenses, pairs

DATASET, EVENT = "SIH-RD", "hospitalisation"
WORLDS = 20
REPLICATES = 100


def tag(mark: str, block: str) -> str:
    return f"{mark}_{block}"


def fit(mark: str, block: str, first: int, last: int) -> None:
    years = list(range(first, last + 1))
    record = marks.fit_chapter(mark, block, years, graph="contiguity", log=lambda s: print(s, flush=True))
    path = marks.save_record(record, tag(mark, block))
    print(f"DONE {mark} {block} -> {path}", flush=True)


def place_name(names: dict, code: int) -> str:
    m = names.get(str(int(code)).zfill(6)) or names.get(str(int(code)))
    return f"{m['name']}/{m['uf_sigla']}" if m else str(code)


def read(mark: str, block: str, first: int, last: int) -> None:
    import pegasus_data.geography as geo

    years = list(range(first, last + 1))
    rec = json.loads(Path(marks.HOME, f"{tag(mark, block)}.json").read_text(encoding="utf-8"))
    fx = rec.get("final_reader_effects")
    source = marks.reader(mark, fx)
    sess = tools.Session(DATASET, EVENT, years, source=source)
    node = block
    out: dict = {"mark": mark, "block": block, "years": [first, last], "tiers": {}, "lenses": {}, "negatives": {}}
    surprises = {}
    for tier in ("B0", "B1", "B2"):
        s = sess.surprise(node, tier)
        surprises[tier] = s
        cal = {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in s.calibration.items()
               if isinstance(v, (int, float, np.floating, bool, str))}
        out["tiers"][tier] = cal
        print(tier, json.dumps(cal, default=float), flush=True)
    edges = sess.edges()
    ledger = control.Ledger(Path(tempfile.mkdtemp(prefix="marks_ledger_")))
    runners = {"outbreak": ("B2", lambda s: lenses.outbreak(s, ledger)),
               "space_time": ("B1", lambda s: lenses.space_time(s, edges, ledger, replicates=REPLICATES))}
    names = geo.municipalities()
    model = sess.expectations.model(block)
    leads = []
    for lens, (tier, fn) in runners.items():
        t0 = time.time()
        found = fn(surprises[tier])
        out["lenses"][lens] = {"findings": len(found), "seconds": round(time.time() - t0)}
        print(lens, tier, len(found), "findings", f"{time.time() - t0:.0f}s", flush=True)
        for f in sorted(found, key=lambda f: f.p)[:5]:
            leads.append((lens, f))
    # negatives: the worlds the lens must stay quiet on (the floor of 1.5 % was set on PESO; here on this mark's own residuals)
    gen = pairs.MoranBasis(surprises["B1"].places, "knn8")
    for lens, (tier, fn) in runners.items():
        for kind in ("nb", "space_ns", "time_ns"):
            counts = [len(fn(harness.lens_world(surprises[tier], kind, i, gen))) for i in range(WORLDS)]
            out["negatives"][f"{lens}|{kind}"] = {"worlds": WORLDS, "any": int(sum(c > 0 for c in counts)), "mean": float(np.mean(counts))}
            print("negatives", lens, kind, f"any {sum(c > 0 for c in counts)}/{WORLDS} mean {np.mean(counts):.2f}", flush=True)
    # the top leads: the place, the window, the size, and (log-normal marks) the recording facilities' share of it
    out["leads"] = []
    for lens, f in leads:
        places = f.locus["places"]
        desc = {"lens": lens, "places": [place_name(names, p) for p in places[:4]] + ([f"+{len(places) - 4}"] if len(places) > 4 else []),
                "years": f.locus["years"], "effect": float(f.effect), "p": float(f.p), "direction": f.locus.get("direction")}
        if "casemix" in marks.SPECS[mark]:
            desc["triage"] = marks.triage_lead(model, mark, years, np.array(places), f.locus["years"], fx, names)
        out["leads"].append(desc)
        print("LEAD", json.dumps(desc, default=float, ensure_ascii=False), flush=True)
    Path(marks.HOME, f"{tag(mark, block)}_read.json").write_text(json.dumps(out, indent=1, default=float, ensure_ascii=False), encoding="utf-8")
    print(f"DONE read {mark} {block}", flush=True)


if __name__ == "__main__":
    cmd, mark, block, first, last = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
    {"fit": fit, "read": read}[cmd](mark, block, first, last)
