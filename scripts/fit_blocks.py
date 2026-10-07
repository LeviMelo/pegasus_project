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

from pegasus_core import update


def main(dataset: str, event: str, first: int, last: int, graph: str, blocks: list[str]) -> None:
    source = json.loads(os.environ.get("PEGASUS_SOURCE", "{}"))
    for block in blocks:
        start = time.time()
        try:
            model = update.fit_block(dataset, event, block, list(range(first, last + 1)), graph,
                                     device=os.environ.get("PEGASUS_DEVICE", "cpu"), source=source,
                                     warm=None if os.environ.get("PEGASUS_FIT_COLD") else "auto",
                                     log=lambda line: print(f"  {line}", flush=True))
            print(f"BLOCK {block} {json.dumps(model.summary(), default=float)} {time.time() - start:.0f}s", flush=True)
        except Exception as exc:  # noqa: BLE001 - reported, next block fitted
            print(f"FAIL {block} {type(exc).__name__}: {exc}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sys.argv[6:])
