"""Fill the gateway cache for one event type over a range of years.

Usage: python scripts/warm_gateway.py DATASET EVENT FIRST_YEAR LAST_YEAR [month]

Prints one line per year (allocated and unallocated events, seconds), so a
detached run can be watched; a failed year is reported and the next one tried.
"""

from __future__ import annotations

import sys
import time

import pyarrow.compute as pc

from pegasus_core import gateway


def main(dataset: str, event: str, first: int, last: int, grain: str = "year") -> None:
    reader = gateway.monthly_counts if grain == "month" else gateway.event_counts
    places = gateway.population(range(first, last + 1)).column("u").unique()
    print(f"population ready: {len(places)} municipalities", flush=True)
    for year in range(first, last + 1):
        t = time.time()
        try:
            ec = reader(dataset, event, year, places=places)
            print(f"YEAR {year} allocated {pc.sum(ec.counts['y']).as_py()} "
                  f"unallocated {pc.sum(ec.unallocated['y']).as_py() or 0} cells {ec.counts.num_rows} "
                  f"{time.time() - t:.0f}s", flush=True)
        except Exception as exc:  # noqa: BLE001 - reported, next year tried
            print(f"FAIL {year} {type(exc).__name__}: {exc}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), *(sys.argv[5:6]))
