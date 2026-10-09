"""Throughput from a plan's stamped log (work plan S0.8): the seconds each field's fit and each of its questions took.

    python scripts/throughput.py data/probes/s6_0_sim_all.log [more logs]

`update` stamps every line with the clock (`cli.update`). A question line ("[hh:mm:ss] DS:EVENT:BLOCK:LEVEL question:
N answers") closes the interval since the previous stamped line, so its seconds are that question's. A fit's seconds
run from its block's first stamped line to the first question of the field. Lines the console wrapped are joined
before reading. The clock wraps at midnight. Prints per question the median and total seconds a field, then the totals
by stage, which give the exhaustive survey's time (fields × seconds a field).
"""
from __future__ import annotations

import re
import statistics
import sys
from collections import defaultdict

STAMP = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\] (.*)$")
QUESTION = re.compile(r"^(\S+:\S+:\S+:\S+) (\w+): (\d+) answers")
FIT = re.compile(r"^(\S+) (\S+) (outer \d+|φ =|robust)")


def records(path: str) -> list[tuple[int, str]]:
    """(seconds since the log's first day began, text) per stamped line, wrapped lines joined."""
    out: list[tuple[int, str]] = []
    day = 0
    last = -1
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            m = STAMP.match(line)
            if m:
                s = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
                if last >= 0 and s + day < last - 3600:      # the clock passed midnight
                    day += 86400
                last = s + day
                out.append((last, m[4]))
            elif out and line.startswith(" ") is False and line and not line.startswith("["):
                out[-1] = (out[-1][0], out[-1][1] + " " + line.strip())
    return out


def main(paths: list[str]) -> None:
    per_q: dict[str, list[float]] = defaultdict(list)
    fits: list[float] = []
    fields: set[str] = set()
    for path in paths:
        recs = records(path)
        fit_start: dict[str, int] = {}
        prev = None
        for t, text in recs:
            q = QUESTION.match(text)
            f = FIT.match(text)
            if f:
                fit_start.setdefault(f"{f[1]}:{f[2]}", t)
            if q:
                field, question = q[1], q[2]
                key = ":".join(field.split(":")[:3])
                if field not in fields:
                    fields.add(field)
                    start = next((v for k, v in fit_start.items() if key.endswith(k.split(":")[-1]) and key.startswith(k.split(":")[0])), None)
                    if start is not None and prev is not None:
                        fits.append(prev - start)
                if prev is not None:
                    per_q[question].append(t - prev)
            prev = t
    print(f"{len(fields)} fields; {len(fits)} fits timed")
    total = 0.0
    for question, secs in sorted(per_q.items(), key=lambda kv: -sum(kv[1])):
        total += sum(secs)
        print(f"  {question:12s} n {len(secs):4d}  median {statistics.median(secs):7.1f} s  total {sum(secs) / 3600:6.2f} h")
    if fits:
        print(f"  {'fit':12s} n {len(fits):4d}  median {statistics.median(fits):7.1f} s  total {sum(fits) / 3600:6.2f} h")
        total += sum(fits)
    if fields:
        print(f"seconds a field: {total / len(fields):.0f} (questions and fits, {total / 3600:.2f} h over {len(fields)} fields)")


if __name__ == "__main__":
    main(sys.argv[1:])
