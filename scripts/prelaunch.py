"""The gate before a study launch (author, 2026-10-12): the fast contract and data-path tests (tests/fast, a few minutes
on the shared store's cached objects), then, with ``--slices``, every slice study of `studies/slices/` (each preset on
one state and a few years, and another condition than the reference topic), each within twice its own estimate, each
folder holding the analytic body (`study.body`: incidence with denominators and intervals, figures, classified
findings, relations, persons, quality, hypotheses, the report; no failed step). The body must come out of every preset
and scope; a national run is launched only on a commit every slice passes on (thirteen national runs had served as the
debugging loop, 2-3 hours a defect). ``--slices NAME ...`` runs only those slices.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLICES = ROOT / "studies" / "slices"


def run_slice(path: Path) -> tuple[bool, str]:
    import yaml

    from pegasus_core import study

    decl = study.load(path)
    folder = study.folder_of(decl)
    scope = subprocess.run([sys.executable, "-m", "pegasus_core.cli", "scope", str(path)], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    if scope.returncode:
        # the scope's own error, where "its scope failed" had sent the reader to rerun it (the review of the study,
        # 2026-10-14)
        return False, "its scope failed: " + (scope.stderr or scope.stdout).strip()[-1500:]
    estimate = float(yaml.safe_load((folder / "scope.yml").read_text(encoding="utf-8"))["estimated_minutes"])
    # twice the estimate, at least 20 min: an estimate measured on a cached run prices no refit (slice5, 2026-10-12)
    cap = max(2 * estimate, 20.0) * 60
    t0 = time.time()
    run = subprocess.Popen([sys.executable, "-m", "pegasus_core.cli", "study", str(path)], cwd=ROOT)
    try:
        run.wait(timeout=cap)
    except subprocess.TimeoutExpired:
        subprocess.call(["taskkill", "/T", "/F", "/PID", str(run.pid)] if os.name == "nt" else ["kill", str(run.pid)])
        return False, f"over its cap of {cap / 60:.0f} min (twice its estimate of {estimate:.1f})"
    minutes = (time.time() - t0) / 60
    if run.returncode:
        return False, f"the study exited {run.returncode} after {minutes:.1f} min"
    body = study.body(folder)           # once: it reads every table of the folder
    missing = [r for r in body if r["status"] != "met"]
    for r in body:
        print(f"  {r['part']}: {r['status']} | {r['evidence'][:160]}")
    # an estimate is the scope's promise to the person who declared it: one far above the run is as wrong as one below,
    # and only the cap saw the latter (the review of the study, 2026-10-14); said, not failed, as a cached run is rightly
    # faster than a cold estimate
    ratio = minutes / estimate if estimate > 0 else float("inf")
    off = "" if 0.5 <= ratio <= 1.5 else f" (the estimate off: the run took {ratio:.2f}x it)"
    return not missing, (f"{minutes:.1f} min against an estimate of {estimate:.1f}{off}; "
                         + (f"body missing {[r['part'] for r in missing]}" if missing else "the body whole"))


def main() -> int:
    code = subprocess.call([sys.executable, "-m", "pytest", "-q", "tests/fast", "-p", "no:cacheprovider", "-W", "ignore",
                            "-x"], cwd=ROOT)
    if code or "--slices" not in sys.argv:
        return code
    names = sys.argv[sys.argv.index("--slices") + 1:]
    paths = [p for p in sorted(SLICES.glob("*.yml")) if not names or p.stem in names]
    results = []
    for path in paths:
        print(f"slice {path.stem}:", flush=True)
        ok, why = run_slice(path)
        results.append((path.stem, ok, why))
        print(f"slice {path.stem}: {'passed' if ok else 'FAILED'}: {why}", flush=True)
    print("slices: " + "; ".join(f"{n} {'passed' if ok else 'FAILED'}" for n, ok, _ in results))
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
