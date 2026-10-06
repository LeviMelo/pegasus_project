"""Run a heavy job under the machine-wide heavy-job queue.

    python scripts/heavy.py [--label NAME] -- <command ...>

Several agents share one machine (31.6 GB RAM, of which about 20 GB is usable, and one 6 GB GPU).
A job waits for one of PEGASUS_HEAVY_SLOTS machine-wide slots (default 6), then for free memory
to reach PEGASUS_HEAVY_MIN_FREE_GB (default 4), and only then starts. The slot is held until the
job exits, and is released if the job dies. It reuses pegasus_data's decode admission (OS file
locks) with its own slot directory, so heavy-job slots and decode slots are separate pools. The
child gets the caller's environment, so its own decodes still queue on the decode pool, plus explicit thread counts
(--threads, default half the logical cores: OMP, MKL, OpenBLAS, numba). A GPU job (--gpu, or PEGASUS_DEVICE=cuda) also
takes the single GPU slot, so two jobs never share the 6 GB card."""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--label", default="")
parser.add_argument("--gpu", action="store_true", help="also take the single GPU slot (or set PEGASUS_DEVICE=cuda)")
parser.add_argument("--threads", type=int, default=0, help="threads for the child's BLAS, OpenMP, numba and torch (default: half the logical cores)")
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
command = args.command[1:] if args.command[:1] == ["--"] else args.command
if not command:
    sys.exit("usage: heavy.py [--label NAME] -- <command ...>")

child_env = dict(os.environ)
# explicit thread counts: six jobs of 2-4 implicit threads each competing for the cores made every one of them 5-20x
# slower (2026-10-06); a job states its share
threads = str(args.threads or max(2, (os.cpu_count() or 4) // 2))
for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMBA_NUM_THREADS"):
    child_env.setdefault(var, threads)
gpu = args.gpu or child_env.get("PEGASUS_DEVICE") == "cuda"
os.environ.update(
    PEGASUS_MIN_FREE_GB=os.environ.get("PEGASUS_HEAVY_MIN_FREE_GB", "4"),
    PEGASUS_ADMISSION_WAIT=os.environ.get("PEGASUS_HEAVY_WAIT", "21600"),
)
from contextlib import nullcontext  # noqa: E402

from pegasus_data.decode.admission import admitted  # noqa: E402 - reads the environment at each call

label = args.label or " ".join(command)[:80]
# Surveys hold a slot for hours on one core and about 4 GB each (2026-10-05: five at once starved
# fourteen fits and left 0.3 GB free). They first take one of PEGASUS_SURVEY_SLOTS (default 2)
# slots of their own pool, then a general slot, so they never hold more than two of the six.
survey = "survey" in label.lower() or any("survey" in part for part in command)


def pool(directory: str, slots: str):
    os.environ.update(PEGASUS_DECODE_SLOT_DIR=str(Path(tempfile.gettempdir()) / directory), PEGASUS_DECODE_SLOTS=slots)
    return admitted(label)


queued = time.time()
print(f"[heavy] queued{' (survey pool)' if survey else ''}: {label}", flush=True)
with pool("pegasus_survey_slots", os.environ.get("PEGASUS_SURVEY_SLOTS", "2")) if survey else nullcontext(), \
        pool("pegasus_gpu_slots", "1") if gpu else nullcontext(), \
        pool("pegasus_heavy_slots", os.environ.get("PEGASUS_HEAVY_SLOTS", "6")):
    print(f"[heavy] admitted after {time.time() - queued:.0f}s: {label}", flush=True)
    code = subprocess.call(command, env=child_env)
print(f"[heavy] exit {code}: {label}", flush=True)
sys.exit(code)
