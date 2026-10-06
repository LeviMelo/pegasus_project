# ADR-0021: The low-rank place × time interaction acts on the active leaves, with two of its three scales fixed; its rank is chosen per block on held-out data

**Date.** 2026-10-05 (built); written 2026-10-06. **Status.** Active for the design. The rank is not chosen: the held-out measurement continues on the v1 solver (ARCHITECTURE §12, O2).

**Evidence.**
- Rank sweep on SIM.DO IX, trained 2010–2021, scored on 2022–2023 (787,877 deaths; `data/lowrank/rank_select.py` in the worktree, results `rank_SIM.DO_IX.jsonl`). Deviance per held-out death, and the NB log-likelihood per death at the fitted φ:

  | R | deviance | NB log-likelihood | φ | seconds |
  |---|---|---|---|---|
  | 0 | 2.2185 | −1.6378 | 6.55 | 191 |
  | 1 | 2.1938 | −1.6297 | 7.44 | 1,219 |
  | 2 | 2.1840 | −1.6279 | 8.04 | 1,336 |
  | 3 | 2.1799 | −1.6262 | 8.44 | 1,177 |

- R = 4 and 5 and the SIH chapter X sweep (R = 0–3) were still running when this was written.

## Decision

1. **The term.** Σ_r ψ[r,e] ω[r,u] τ[r,t] in η (`Monolith(rank=R)`, annual grain).
2. **It acts on the active leaves** only: those holding at least 0.1 % of the block's events. The others have ψ = 0, so the cube is |E_active|·U·T.
3. **Identification fixes two of the three scales.** Otherwise the three factors' scales form a ridge.
   - ψ ~ N(0, 1), with its strength fixed, centred within each group's active leaves. This makes the term orthogonal to the effects the leaves of a group share.
   - ω = scaled ICAR + iid, both centred over the places, with learned strengths. The amplitude lives here.
   - τ = RW1, scaled like the other shapes, plus a unit prior on its level; strength fixed.
4. **The start.** The base model is fitted first, because a zero interaction is a saddle. The interaction then starts from a weighted alternating least squares on the base fit's working-residual cube, and the same mean fit and strength updates continue. The Gauss–Newton diagonals of the three factors replace the first-derivative mass.
5. **The forecast.** ω and ψ as fitted; τ flat at its last value (the RW1 mean).
6. **What it carries.** The term is never part of a tier. It is read as patterns (§7.4). It is *within the block*: a place level shared by whole chapters is the block's main place effect and cannot be separated here.
7. **The rank is chosen per block** by held-out deviance and LAML (§5.6). It is not fixed in advance.

## Alternatives

- **All leaves** active: the cost is E·U·T per Hessian–vector product, for loadings that rare leaves cannot identify.
- **All three scales learned**: the scale ridge.
- **A cross-block shared ω**: needs the top model (§5.6), not built.

## Limits

- No Laplace draws for the term.
- The R = 1–3 fits took 6–7 times the base fit on the v0 solver. Their rank choice waits for the v1 solver (O1), where the factors' Gauss–Newton blocks join the place and global classes of §5.3.
- Held-out deviance kept improving through R = 3 on IX. Where it stops is not yet known.
