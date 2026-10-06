"""Fit and store monolith blocks (detached runs).

Usage: python scripts/fit_blocks.py DATASET EVENT FIRST_YEAR LAST_YEAR GRAPH BLOCK [BLOCK ...]

``PEGASUS_FIT_COLD=1`` starts from nothing instead of a related stored fit. ``PEGASUS_DEVICE=cuda`` fits the mean on the GPU. ``PEGASUS_SOURCE`` (JSON) chooses a
non-default reader, e.g. ``{"source": "mark", "mark": "PESO", "bounds": [200, 7000]}`` or
``{"source": "code_list", "column": "CODANOMAL"}``; block ``*`` is an event type without a tree. One summary line per block (``BLOCK <name> <json>``), so a detached run can be
watched; a failed block is reported and the next one fitted.
"""

from __future__ import annotations

import json
import os
import sys
import time

from pegasus_core import graphs, monolith


def main(dataset: str, event: str, first: int, last: int, graph: str, blocks: list[str]) -> None:
    for block in blocks:
        start = time.time()
        try:
            source = json.loads(os.environ.get("PEGASUS_SOURCE", "{}"))
            if "bounds" in source:
                source["bounds"] = tuple(source["bounds"])
            data = monolith.assemble(dataset, event, block, range(first, last + 1), **source)
            events = data.n.sum() if data.n is not None else data.y.sum()
            print(f"ASSEMBLED {block} nnz {len(data.y)} events {events:.0f} {time.time() - start:.0f}s", flush=True)
            cls = monolith.model_class(source)
            model = cls(data, graphs.graph(data.places, graph), graph,
                                      device=os.environ.get("PEGASUS_DEVICE", "cpu"))
            # warm start from the best related stored fit (``PEGASUS_FIT_COLD=1``: none); the outers' inner tolerance is
            # the monolith's own (`Monolith._loop`)
            model.fit(outer=40, warm=None if os.environ.get("PEGASUS_FIT_COLD") else "auto", mean_tol=1.0,
                      log=lambda line, b=block: print(f"  {b} {line}", flush=True))
            model.save()
            print(f"BLOCK {block} {json.dumps(model.summary(), default=float)}", flush=True)
        except Exception as exc:  # noqa: BLE001 - reported, next block fitted
            print(f"FAIL {block} {type(exc).__name__}: {exc}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sys.argv[6:])
