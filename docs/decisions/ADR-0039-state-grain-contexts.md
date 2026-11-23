# ADR-0039: State-grain contexts are read at state level, with a state effect and their survey error

**Date:** 2026-11-23. **Status:** active. **Plan:** docs/plans/state-contexts.md.

**Context.** pegasus_data serves state-grain fields (`level: N3`: twelve PNS fields, counts and IBGE's published shares
with their limits and CV). Copied onto municipalities they would be pseudo-replication (27 measurements counted as
5,570) with the sampling error dropped; `gateway.rated` leaves them out of the municipal models.

**Decision.**
1. A state context enters a study only at state level: `study._state_contexts` reads it at the survey year nearest the
   period's middle, with each state's standard error from the published limits ((upper − lower) / 3.92, else the CV).
2. `study._ecological_state` fits each count field against it twice:
   - (a) a cross-level NB2 on the municipalities with a random intercept per state, glmmTMB through R
     (`rmodels.nb_random_intercept`, rpy2; established-packages rule, statsmodels has no NB GLMM);
   - (b) the events and expectations aggregated to the states, NB2 at the null model's dispersion, HC3.
3. The survey error is carried by multiple overimputation: 50 draws from Normal(estimate, se), both models refitted,
   Rubin's rules (Blackwell, Honaker and King 2017).
4. Inference counts states. The rows are `associations` with geography state, the number of states as denominator, the
   survey year, and the draws named.

**Evidence.** SIH-RD spine surgery (040803) per municipality of residence 2019 against PNS chronic spine problem 2019:
- cross-level rate ratio 1.06 per SD (0.77-1.47), aggregated 0.995 (0.77-1.29), both null as the study's own state-level
  read (Spearman 0.02 over 27 states);
- the overimputation widens the intervals against the fixed estimate (1.45 → 1.47, 1.28 → 1.29);
- 148 s for 50 draws of one field and context.

**Consequences.** R 4.4.1 with glmmTMB and rpy2 join the compute stack beside statsmodels. A study with many count
fields and state contexts pays about 2.5 minutes per pair.
