"""Held-out model choice (ARCHITECTURE §5.4): fit on the training years, score the later ones.

Usage: python scripts/measure_heldout.py DATASET EVENT TRAIN_FIRST TRAIN_LAST TEST_LAST BLOCK CONFIG [CONFIG ...]

A CONFIG is GRAPH/PROFILE, e.g. ``contiguity/group`` or ``knn6/category``. One line per
configuration: ``HELDOUT <json>``. A fit already in the store is reused.
"""

from __future__ import annotations

import json
import os
import sys
import time

from pegasus_core import graphs, monolith, store


def main(dataset: str, event: str, first: int, last: int, test_last: int, block: str, configs: list[str]) -> None:
    train, test = range(first, last + 1), range(last + 1, test_last + 1)
    device = os.environ.get("PEGASUS_DEVICE", "cpu")
    for config in configs:
        graph, profile = config.split("/")
        start = time.time()
        try:
            data = monolith.assemble(dataset, event, block, train, profile)
            model = monolith.Monolith(data, graphs.graph(data.places, graph), graph, device=device)
            if store.manifest("monolith", model.key()) is None:
                model.fit(outer=40, log=lambda line, c=config: print(f"  {block} {c} {line}", flush=True))
                model.save()
            else:
                model = monolith.Monolith.load(dataset, event, block, train, graph, profile)
            score = monolith.heldout(model, monolith.assemble(dataset, event, block, test, profile))
            score.update({"block": block, "config": config, "phi": model.phi, "seconds": time.time() - start})
            print(f"HELDOUT {json.dumps(score, default=float)}", flush=True)
        except Exception as exc:  # noqa: BLE001 - reported, next configuration scored
            print(f"FAIL {block} {config} {type(exc).__name__}: {exc}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], int(a[3]), int(a[4]), int(a[5]), a[6], a[7:])
