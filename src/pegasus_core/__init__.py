"""PegaSUS: one hierarchical model of Brazil's health events, read for leads.

The architecture is ``ARCHITECTURE.md`` at the repository root; the module map
is its §11.1.
"""

# pyarrow's dataset layer must load before duckdb and torch: with both of those
# already loaded, importing it segfaults in the shared environment (measured
# 2026-10-04: pyarrow 24.0.0, duckdb 1.5.5, torch 2.5.1, Windows).
import pyarrow.dataset  # noqa: F401  (import order, see above)

__version__ = "0.0.1"
