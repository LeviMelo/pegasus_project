# State-grain contexts in a study's ecological models (plan, 2026-11-23; built, ADR-0039)

**Why.** pegasus_data now serves state-grain fields (`level: N3`: twelve PNS fields, counts and IBGE's published shares,
each with its 95% limits and CV; pegasus_data 4e8d168c, 2f67854c). A study of places (t06 helmets, t08 chronic spine
problems) wants them beside its municipal contexts. `gateway.rated` leaves them out of the municipal model with a
reason (9f9eb3c): copied onto 5,570 municipalities they would be pseudo-replication, 27 measurements counted as
thousands, with the survey's sampling error dropped. Today the studies read them by hand in state-level analyses.

**Rules (decided).**
- A state context is a property of 27 units. Inference on it counts states, never municipalities.
- It enters a model only with the state as a level of the model: a random intercept per state, or the outcome
  aggregated to states.
- It carries its sampling error. IBGE publishes each estimate with limits and a CV; a model that treats the
  estimate as known is overconfident.
- A share or rate enters as a covariate (the `_percent` fields, or a count with its `over`); a bare count never does.
- Established implementations only (established-packages rule): glmmTMB through R for the mixed model, statsmodels
  for the aggregated GLM, Rubin's rules for combining.

**Design.** `_ecological` (study.py) keeps its municipal NB2 models unchanged. A new step `_ecological_state` runs per
count field and per state context:
1. *Cross-level model (primary).* Municipal events `y_ij`, NB2 (glmmTMB `nbinom2`), offset log of the events expected
   at the area's own age-sex rates (as `_ecological`), the state context `z_j` standardised over the states, and a
   random intercept per state `(1 | state)`. The coefficient of `z_j` is a ratio per standard deviation of the
   state characteristic. Its interval is Wald from glmmTMB, read with 27 groups in mind (reported beside the number of
   states).
2. *Aggregated model (check).* Events and expectations summed to the 27 states; NB2 GLM of `Y_j` on `z_j` with offset
   log `E_j`, HC3 interval. Agreement in direction and size between 1 and 2 is reported; a disagreement is a finding.
3. *Survey error (multiple overimputation; Blackwell, Honaker and King 2017, Sociological Methods & Research).* M =
   50 draws `z_j^(m) ~ Normal(estimate_j, se_j)`, with `se_j` from the published limits ((upper − lower) / 3.92) or
   from the CV (CV × estimate / 100) when limits are absent. Each draw is refitted (both models); the coefficients
   are combined with Rubin's rules (within + (1 + 1/M) × between variance). The rows say "50 overimputations".
4. *Years.* A survey publishes some years (PNS 2013, 2019). A study period takes the survey year nearest its middle;
   a period spanning both may use each year for its own half, as two rows. The year read is written on the row.
5. *Guard.* Fewer than 20 states with a value: not modelled, said in the log and the codebook.

**Output.** Rows of the one estimate schema (study-estimates.md): `measure` rate_ratio, `model` "cross-level NB2,
state random intercept (glmmTMB)" or "state-aggregated NB2", `geography` state, `interval` "Wald, Rubin over 50
overimputations" / "HC3, Rubin over 50 overimputations", with the number of states as the `n` of the row. The
ecological-fallacy sentence of `_ecological` applies twice over: an association between states.

**Done when.**
- abnc_t08 (chronic spine-problem share against SUS spine surgery) and abnc_t06 (helmet use against head-injury
  admissions) write state-context rows from their scopes.
- The direction of each matches the studies' own state-level reads (t08: Spearman 0.02 over 27 states).
- The aggregated and cross-level models are reported side by side, and the overimputation widens the interval
  against the fixed-estimate fit by a measured amount.
- Then an ADR records the decision, and `gateway.rated`'s reason names the new step.

**Status (2026-11-23).** Built (`study._state_contexts`, `study._ecological_state`, `rmodels`) and decided (ADR-0039) on the
spine-surgery x PNS spine check above; the abnc_t08 and abnc_t06 rows come with their next study runs.
