# Status

**2026-10-04.** Design v0.2 written, for the author's review; handoff to
pegasus_data written; the project's documentary history gathered.

- `docs/design/DESIGN.md` v0.2: PegaSUS as one hierarchical model of
  Brazil's health events ("normal Brazil"), read for leads. It covers:
  - the boundary with pegasus_data (§2);
  - the ontology and event types (§3);
  - space (§4);
  - the population account and race measurement (§5);
  - the monolith (§6);
  - surprises and scans (§7–8);
  - error control and leads (§9);
  - use as a survey (§10);
  - computation (§11).
  
  The least certain calls are §16 O1–O6.
- `docs/handoffs/2026-10-04-pegasus_data.md`: what pegasus_data should
  build for this design, in priority order: storage, roles for every column,
  event types, aggregation, code structures, proximity graphs, the modelled
  tier.
- `docs/history/`: the earlier PegaSUS documents (April plans, May
  formalisation, the June–July engine), as frozen copies.
- `docs/discussion/2026-10-03-what-was-built.md`: what the earlier engine
  actually ran.
- `OPEN_QUESTIONS.md`: Q1–Q15, each pointing to its proposed answer.
- `studies/siac_mulher_2026/`: three abstracts for SIAC Mulher 2026.

**Next:**
1. The author's review.
2. pegasus_data works through the handoff.
3. Phase 0: the validation harness.
4. Two first measurements: ICD tree pooling, chapter by chapter; which
   proximity graph explains between-municipality variation.
