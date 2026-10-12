"""The gate before a study launch (author, 2026-10-12): the fast contract and data-path tests (tests/fast, a few minutes
on the shared store's cached objects), then, with ``--slice``, the slice study (`studies/toxoplasmosis_slice.yml`: every
path the deep preset runs, on one state and eight years) within twice its own estimate, and its audit. A national run
is launched only on a commit both pass on: thirteen national runs had served as the debugging loop, 2-3 hours a defect.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLICE = ROOT / "studies" / "toxoplasmosis_slice.yml"


def main() -> int:
    code = subprocess.call([sys.executable, "-m", "pytest", "-q", "tests/fast", "-p", "no:cacheprovider", "-W", "ignore",
                            "-x"], cwd=ROOT)
    if code or "--slice" not in sys.argv:
        return code
    import yaml

    scope = subprocess.run([sys.executable, "-m", "pegasus_core.cli", "scope", str(SLICE)], cwd=ROOT)
    if scope.returncode:
        return scope.returncode
    folder = SLICE.parent / "toxoplasmosis_slice"
    estimate = float(yaml.safe_load((folder / "scope.yml").read_text(encoding="utf-8"))["estimated_minutes"])
    cap = max(2 * estimate, 10.0) * 60
    t0 = time.time()
    run = subprocess.Popen([sys.executable, "-m", "pegasus_core.cli", "study", str(SLICE)], cwd=ROOT)
    try:
        run.wait(timeout=cap)
    except subprocess.TimeoutExpired:
        subprocess.call(["taskkill", "/T", "/F", "/PID", str(run.pid)] if os.name == "nt" else ["kill", str(run.pid)])
        print(f"slice: over its cap of {cap / 60:.0f} min (twice its estimate): a defect of the run, not a wait")
        return 1
    if run.returncode:
        return run.returncode
    prov = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    failed = [k for k, v in (prov.get("steps") or {}).items() if isinstance(v, dict) and "error" in v]
    print(f"slice: {(time.time() - t0) / 60:.1f} min against an estimate of {estimate:.1f}; {len(failed)} steps failed")
    for k in failed:
        print(f"  failed: {k}: {str(prov['steps'][k].get('error'))[:200]}")
    subprocess.call([sys.executable, "-m", "pegasus_core.cli", "audit", str(folder)], cwd=ROOT)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
