"""Size and power of the artefact-aware tests on negative-binomial worlds (ADR-0019): the shape test, conservation and
the profile test. Output data/artefact_replication/sim.json."""
import json
import os
import sys
from pathlib import Path

os.chdir(Path(__file__).resolve().parents[1])
sys.path.insert(0, "src")
from pegasus_core import replication

out = {"shape": {}, "exchange": {}, "profile": {}}
for level in (30, 200, 2000):
    for size in (10, 50):
        for effect in (0.1, 0.3, 0.6):
            for delta in (3.0, 6.0, 10.0):
                r = replication.simulate_shape(level, size, effect, 400, delta)
                out["shape"][f"level={level} size={size} effect={effect} delta={delta}"] = r
                print("shape", level, size, effect, delta, {k: round(v["step"], 3) for k, v in r.items()}, flush=True)
for level in (30, 200, 1000):
    for codes in (3, 10, 60):
        for effect in (0.1, 0.3, 0.6):
            r = replication.simulate_exchange(level, 3000.0, 50.0, effect, codes, 200)
            out["exchange"][f"level={level} codes={codes} effect={effect}"] = r
            print("exchange", level, codes, effect, r, flush=True)
for cells in (12, 24, 200):
    for n in (50, 200, 1000):
        r = replication.simulate_profile(cells, n)
        out["profile"][f"cells={cells} n={n}"] = r
        print("profile", cells, n, {k: round(v, 3) for k, v in r.items()}, flush=True)
json.dump(out, open("data/artefact_replication/sim.json", "w"), indent=1)
