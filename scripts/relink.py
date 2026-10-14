"""Re-run the stored national link runs a study needs, one at a time: python scripts/relink.py LINK FIRST LAST.

The years whose runs cover a side's records of FIRST..LAST (`gateway.covering_runs`) are listed first; each is then made
by pegasus_data's `link` (the national run PegaSUS's `gateway.stored_pairs` reads), so a run of hours depends on
pegasus_data's code only, not on PegaSUS's being unchanged meanwhile. A stored run of the current fingerprint is reused
(pegasus_data's store); a run that touches the confirmation reserve is never made. One line per run.
"""

from __future__ import annotations

import sys
import time


def main(link: str, first: int, last: int) -> None:
    from pegasus_core import config, gateway

    years = sorted({int(z) for side in ("left", "right") for y in range(first, last + 1)
                    for z in gateway.covering_runs(link, side, y)})
    reserved = {z for z in years if gateway.run_touches_reserve(link, z)}
    method = __import__("pegasus_data.linkage.engine", fromlist=["link_method"]).link_method(link)
    root = config.data_root()
    print(f"{link} ({method}): runs {years}; reserve, not made: {sorted(reserved)}", flush=True)
    import pegasus_data as pg

    for z in (y for y in years if y not in reserved):
        t = time.time()
        try:
            result = pg.link(link, period=z, geography="BR", method=method, root=root)
            verdict = (getattr(result, "report", None) or {}).get("verdict") if isinstance(
                getattr(result, "report", None), dict) else getattr(result, "verdict", None)
            print(f"{link} {z}: {result.pairs.num_rows} pairs, verdict {verdict}, {time.time() - t:.0f} s", flush=True)
        except Exception as exc:  # noqa: BLE001 - one year's failure is said, the others still run
            print(f"{link} {z}: failed after {time.time() - t:.0f} s: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
