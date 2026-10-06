"""Run a heavy job under the machine-wide heavy-job queue.

    python scripts/heavy.py [--label NAME] -- <command ...>

Several agents share one machine (31.6 GB RAM, of which about 20 GB is usable, and one 6 GB GPU).
A job waits for one of PEGASUS_HEAVY_SLOTS machine-wide slots (default 6), then for free memory
to reach PEGASUS_HEAVY_MIN_FREE_GB (default 4), and only then starts. The slot is held until the
job exits, and is released if the job dies. It reuses pegasus_data's decode admission (OS file
locks) with its own slot directory, so heavy-job slots and decode slots are separate pools. The
child gets the caller's environment unchanged, so its own decodes still queue on the decode pool."""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--label", default="")
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
command = args.command[1:] if args.command[:1] == ["--"] else args.command
if not command:
    sys.exit("usage: heavy.py [--label NAME] -- <command ...>")

child_env = dict(os.environ)
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
        pool("pegasus_heavy_slots", os.environ.get("PEGASUS_HEAVY_SLOTS", "6")):
    print(f"[heavy] admitted after {time.time() - queued:.0f}s: {label}", flush=True)
    code = subprocess.call(command, env=child_env)
print(f"[heavy] exit {code}: {label}", flush=True)
sys.exit(code)
