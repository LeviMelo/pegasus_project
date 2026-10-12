"""The gate before a study launch: the fast contract and data-path tests (tests/fast, a few minutes on the shared
store's cached objects). A run is launched only on a commit they pass on (author, 2026-10-12: tests where they
guarantee working code faster than a run finds the defect)."""

import subprocess
import sys

sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", "tests/fast", "-p", "no:cacheprovider", "-W", "ignore",
                          "-x"]))
