# Code keys audited by running, narrowed, and the store migrated (2026-10-14)

**Why.** The gateway review measured that `event_counts`'s key closed over 574 definitions, and every structural fix
of the review (one reader template, a cached store, splitting gateway.py) would re-key the whole store. Narrowing keys
by reasoning alone risks the worse error: a key that misses code its result depends on serves stale results silently.

**How.** `config.key_audit_start` (``PEGASUS_KEY_AUDIT=<dir>``) profiles a process and its lanes: inside each keyed
function's run, every package function outside its key's closure is recorded with its call path. Regime: PegaSUS
19a9828 plus the change (ADR-0037), pegasus_data 2e09a61; the toxoplasmosis survey slice (RS 2019-2023) cold on a scratch
`PEGASUS_HOME` (the lanes' 4 audit files; the products' were not awaited), and one cold block fit (SIM-DO I21-I22,
Alagoas) with call paths. Keys before: `keys_19a9828.json`, 43 entries recorded under `code_keys/`.

| rule | `event_counts` closure | median of 43 | recorded calls outside their key |
|---|---|---|---|
| before (every `x.name` to every method) | 574 | 575 | 55: `ask` 28, `survey_questions` 27 (the lenses, by `getattr(lenses, lens)`) |
| every `x.name` to reached classes (the review's proposal) | 65 | 67 | 57 pairs; `ask` 231 functions |
| ambiguous names narrowed, a lens registry, literal `getattr` followed (adopted) | 88 | see below | 2: `fit_block`'s log lambdas in `Monolith.fit`, no result depends on them |

**Found.** The old keys were unsound where it mattered most: stored answers were keyed by `code_key(qs.ask)`, which
never covered the lens that made them, so a lens edit (the scan nulls' spatial dependence, 662a3c7, the same day)
left earlier answers served as current. Those entries (`ask`, `Session.survey_questions`, `Session.train`) are not
migrated: their artefacts are computed again.

**Migration.** Value to value (``keys migrate``): 24 of 40 entries' keys changed; 26,277 entries moved (23,263 of 206,878
gateway tables, 449 of 3,407 fits), no address taken, in 3.5 min. It was wrong for most of them: under the broad rule 17
entries shared one key (289cb9982ec18b89: the counts, the assembly, the fit), so one old value stood for 17 new ones, and
16 of every 17 entries holding it went where nothing asks. Nothing wrong could be served (a misplaced entry is a miss),
but the warm Alagoas study then refitted 15 blocks: 1,489 s for about 180. Replaced by adoption on request (ADR-0037 §5:
a read that misses adopts the entry of the same identity whose code values are all of the window). The leptospirosis
slice with the window open refitted 7 blocks, all stored under an earlier commit (f6f71b1) that the broad rule had
already re-keyed (an edit of tools.py re-keyed nearly every artefact): outside the window, refitted under either rule.
The store's other entries (about 180,000 gateway tables and 2,900 fits) are of code states no key computes again.
