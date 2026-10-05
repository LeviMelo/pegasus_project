"""The cached BlockData equals a fresh assembly, field by field (and re-keys identically)."""
import sys
import time

import numpy as np

from pegasus_core import monolith, store

CASES = [("SINAN-LEPT", "case", "*", range(2010, 2024), {"grain": "month"}),
         ("SIM.DO", "death", "III", range(2010, 2024), {}),
         ("SIM.DO", "death", "IX", range(2010, 2020), {"population": "account-3"}),
         ("SINASC-DN", "birth", "*", range(2010, 2024), {"source": "mark", "mark": "PESO", "bounds": (200, 7000)})]
for ds, ev, block, years, kw in CASES:
    t = time.time()
    fresh = monolith.assemble(ds, ev, block, years, cache=False, **kw)
    t_fresh = time.time() - t
    monolith.assemble(ds, ev, block, years, **kw)           # writes (or reads)
    t = time.time()
    cached = monolith.assemble(ds, ev, block, years, **kw)
    t_cached = time.time() - t
    bad = []
    for name in ("years", "places", "leaf_group", "N", "e", "u", "t", "g", "y", "S", "n", "l2", "month_of_year"):
        a, b = getattr(fresh, name), getattr(cached, name)
        if (a is None) != (b is None) or (a is not None and (a.dtype != b.dtype or not np.array_equal(a, b))):
            bad.append(name)
    for name in ("dataset", "event", "block", "leaves", "groups", "unallocated", "grain", "population"):
        if getattr(fresh, name) != getattr(cached, name):
            bad.append(name)
    same_key = store.address("monolith", fresh.key) == store.address("monolith", cached.key)
    print(f"{ds} {block} {kw.get('grain', 'year')}: fresh {t_fresh:.1f}s cached {t_cached:.1f}s, differences {bad or 'none'}, "
          f"monolith address identical {same_key}", flush=True)
    sys.stdout.flush()
