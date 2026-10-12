"""The fast tests read the shared store and data root as they are: they never download (`gateway.max_download`). A test
reaching past the lake fails at once; one had fetched SIA-PA's files for minutes (2026-10-12)."""

import os

os.environ.setdefault("PEGASUS_MAX_DOWNLOAD", "0")
