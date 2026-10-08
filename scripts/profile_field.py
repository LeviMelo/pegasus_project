"""The question pass on one field, profiled (ARCHITECTURE §5.8: a chapter survey's speed target).

    PYTHONUTF8=1 $PY scripts/profile_field.py SIH-RD hospitalisation X J09-J18 --years 2010-2023

Asks every question of `questions.QUESTIONS` of one field, as `Session.survey_questions` does (one surprise memo for
the field), on a sandbox ledger. Prints seconds per question and the functions with the most cumulative time, and
writes the profile to ``data/probes/profile/<dataset>_<node>.pstats``.
"""

from __future__ import annotations

import argparse
import cProfile
import pstats
import time
from pathlib import Path

from pegasus_core import config, control, questions, tools


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("event")
    ap.add_argument("block")
    ap.add_argument("node")
    ap.add_argument("--years", default="2010-2023")
    ap.add_argument("--graph", default="contiguity")
    ap.add_argument("--questions", default=",".join(questions.QUESTIONS))
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args()
    y0, y1 = (int(x) for x in a.years.split("-"))
    s = tools.Session(a.dataset, a.event, list(range(y0, y1 + 1)), a.graph,
                      ledger=control.Ledger(config.home() / "harness" / "profile_ledger"))
    s.expectations.model(a.block)
    out = Path("data/probes/profile")
    out.mkdir(parents=True, exist_ok=True)
    prof = cProfile.Profile()
    s._local.memo = {}
    seconds = {}
    prof.enable()
    for qn in a.questions.split(","):
        t0 = time.perf_counter()
        answers = s.ask(qn, a.node)
        seconds[qn] = (time.perf_counter() - t0, len(answers))
    prof.disable()
    s._local.memo = None
    for qn, (sec, n) in seconds.items():
        print(f"{qn:12s} {sec:8.1f} s  {n} answers")
    print(f"{'total':12s} {sum(x for x, _ in seconds.values()):8.1f} s")
    path = out / f"{a.dataset}_{a.node}.pstats"
    prof.dump_stats(path)
    pstats.Stats(str(path)).sort_stats("cumulative").print_stats(a.top)


if __name__ == "__main__":
    main()
