## ADR-0003: Compute stack: PyTorch on CUDA, scipy sparse, Arrow and DuckDB; no dense object larger than the population tensor

**Date:** 2026-10-04. **Status:** active.

**Context.**
- **Machine:** 32 GB RAM, 20 logical cores, an NVIDIA RTX 4050 laptop GPU (6 GB), Windows.
- **Measured in the `pegasus` environment (2026-10-04):**
  - PyTorch 2.5.1 sees the GPU with CUDA 12.1;
  - JAX is not installed, and JAX's GPU builds are not available natively on Windows;
  - scikit-sparse (CHOLMOD) is not installed;
  - present: numpy 2.4, scipy 1.17, pyarrow 24, duckdb 1.5, polars 1.41, numba 0.67, statsmodels 0.14, geopandas 1.1.
- **The 2026 engine failed on memory** by building dense objects: p × n² kernels (48–107 GB), dense precision matrices, a materialised 135-million-row tensor. Its "GPU" paths had run on a CPU-only torch.

**Decision.**
1. **PyTorch (CUDA)** for automatic differentiation, dense contractions and Gram matrices. float32 on the GPU, with float64 accumulation over cells; work chunked to 4 GB.
2. **numpy/scipy** for GMRF algebra: sparse matrices, SuperLU. CHOLMOD through scikit-sparse where it installs.
3. **pyarrow, DuckDB and polars** for I/O and aggregation. **numba** for scan loops.
4. **statsmodels** for reference fits in checks. R-INLA only as an optional external reference.
5. **P10 is binding** (ARCHITECTURE §5.5): no array larger than the population tensor × the profile nodes of one block. The likelihood is factorised (§5.1); the surprise cube is virtual (§6.3).

**Consequences.**
- Every budget is measured in phase 1 and recorded as an evaluation entry.
- An approximation is adopted only after a measured comparison with an exact fit, across scopes.
