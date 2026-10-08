"""The machine a computation runs on (ARCHITECTURE §5.7, §9.3): one job runner for every heavy computation.

A heavy computation (a fit, a plan's update, a measurement script) takes a **machine-wide slot** before it starts
(`slot`: OS file locks shared by every process on the machine, through pegasus_data's admission), and the GPU job also
the single **GPU slot**, so two jobs never share the 6 GB card. It then states its **threads** (`threads`: BLAS,
OpenMP, numba, torch), because six jobs of implicit threads each made every one of them 5–20× slower (2026-10-06).
`pegasus-core update` holds them itself; anything else runs through `pegasus-core run`, alone or as a sequence of
commands under one slot (`run`). It replaces `scripts/heavy.py`, `data/chain.py` and the ad hoc queues (survey
2026-10-07, work plan S0.3).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

#: machine-wide heavy slots (``PEGASUS_HEAVY_SLOTS``): one heavy job at a time within RAM unless raised
HEAVY_SLOTS = int(os.environ.get("PEGASUS_HEAVY_SLOTS", "1"))


def default_threads() -> int:
    """Half the logical cores (at least 2), or ``PEGASUS_THREADS``."""
    return int(os.environ.get("PEGASUS_THREADS") or max(2, (os.cpu_count() or 4) // 2))


@contextmanager
def slot(label: str, gpu: bool = False) -> Iterator[None]:
    """Hold the machine's heavy slot (and the GPU slot with ``gpu``) while the block runs; waits for both, and for
    free memory (pegasus_data's admission: ``PEGASUS_HEAVY_MIN_FREE_GB``, default 4)."""
    from . import gateway

    if os.environ.get("PEGASUS_SLOT_HELD") == "1":         # a child of a job that holds them
        yield
        return
    queued = time.time()
    with ExitStack() as stack:
        if gpu:
            stack.enter_context(gateway.machine_slot("pegasus_gpu_slots", 1, label))
        stack.enter_context(gateway.machine_slot("pegasus_heavy_slots", HEAVY_SLOTS, label))
        print(f"[jobs] admitted after {time.time() - queued:.0f}s: {label}", flush=True)
        os.environ["PEGASUS_SLOT_HELD"] = "1"
        try:
            yield
        finally:
            os.environ.pop("PEGASUS_SLOT_HELD", None)


def threads(n: int | None = None) -> int:
    """Limit this process's BLAS, OpenMP, numba and torch threads to ``n`` (default `default_threads`)."""
    n = n or default_threads()
    from threadpoolctl import threadpool_limits

    threadpool_limits(limits=n)
    try:
        import numba

        numba.set_num_threads(min(n, numba.config.NUMBA_NUM_THREADS))
    except ImportError:
        pass
    import torch

    torch.set_num_threads(n)
    return n


def run(commands: list[list[str]], logs: list[str | None] | None = None, gpu: bool = False,
        n_threads: int | None = None, label: str = "") -> int:
    """Run ``commands`` one after another under one slot, each to its log (or this process's output), with explicit
    thread counts in their environment; returns the last non-zero exit, or 0. A shell is never used (`bash` started
    from Windows Python is WSL's, which cannot see C: paths)."""
    n = str(n_threads or default_threads())
    env = dict(os.environ, PYTHONUTF8="1", PEGASUS_SLOT_HELD="1", PEGASUS_THREADS=n)
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMBA_NUM_THREADS"):
        env.setdefault(var, n)
    logs = logs or [None] * len(commands)
    worst = 0
    with slot(label or " ; ".join(" ".join(c) for c in commands)[:80], gpu=gpu):
        for cmd, log in zip(commands, logs, strict=True):
            cmd = [sys.executable, "-u", *cmd[1:]] if cmd[0] in ("python", "py") else cmd
            print(f"{time.strftime('%H:%M')} START {' '.join(cmd)[:120]}", flush=True)
            if log:
                Path(log).parent.mkdir(parents=True, exist_ok=True)
                with open(log, "w", encoding="utf-8") as fh:
                    code = subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env)
            else:
                code = subprocess.call(cmd, env=env)
            print(f"{time.strftime('%H:%M')} EXIT {code} {log or ''}", flush=True)
            worst = code or worst
    return worst
