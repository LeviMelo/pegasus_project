# ADR-0037: A key covers what its result depends on, checked by running; plumbing is keyless; a change of keys alone migrates the store

**Date:** 2026-10-14. **Status:** active. **Amends:** ARCHITECTURE §11.3 (code keys).

**Context.** `config.code_key` hashes the definitions an entry reaches. Two defects, one in each direction:
- *Too broad.* ``x.name`` reached every method of that name in the package, so ``set.add`` reached the lead register's
  ``add``: `gateway.event_counts`, which counts records, closed over 574 definitions (the solver, the register, the
  ledger, corroboration), the same as the model fit; the median of the 43 entries keyed was 575. Every edit re-keyed
  nearly everything, and moving plumbing or code (the gateway review's reader template, splitting gateway.py) would
  have thrown the store away.
- *Too narrow, unseen.* `tools.Session.scan` found a lens by its name at run time (``getattr(lenses, lens)``) and the
  lenses read their null's ``loc`` and ``scale`` by ``getattr(nul, "loc")``: no static walk follows either. Stored
  answers (keyed by ``code_key(qs.ask)``) never covered the lens that made them; a lens edit (the scan nulls' spatial
  share, 2026-10-14) left the answers made before it served as current.

**Evidence.** `config.key_audit_start` (``PEGASUS_KEY_AUDIT=<dir>``) profiles every process, lanes included: inside each
keyed function's execution, any package function its key's closure lacks is recorded with its call path. A cold run of
the toxoplasmosis survey slice on a scratch home: `questions.ask` and `Session.survey_questions` ran 28 and 27 functions
their keys lacked under the old rule; restricting every ``x.name`` to the classes a closure reaches (the review's
proposal) left 57 pairs out, `ask` 231 functions; the rule below leaves none but two log callbacks (lambdas `fit_block`
passes into `Monolith.fit`, which change no result).

**Decision.**
1. ``x.name`` reaches every method of that name in the package, unless the name is ambiguous, one the builtin types or
   the array libraries (numpy, pyarrow, pandas, torch) also carry (``add``, ``get``, ``lower``, ``rank``): then only the
   method of the classes the closure reaches. ``getattr(x, "name")`` and ``hasattr`` with a literal are ``x.name``.
2. A lens is reached through a declared registry (`scans.lenses.LENSES`), never by a name looked up at run time.
3. Plumbing is `keyless`, declared at the definition: the store module, and in config the paths, versions, devices and
   the keys' own machinery. Seeds, the study's area, replicate scale and population choice stay keyed.
4. A random draw is seeded by what is drawn, never by the code's version: a key given to `config.seed` is read without
   its code keys (`config.identity`).
5. A change that alters what keys cover and no result is migrated on request, not recomputed: `pegasus-core keys
   snapshot` before it, ``keys window`` after it writes the code-key values of both states, and while ``PEGASUS_ADOPT``
   names that file a read that misses adopts the entry of the same identity (`config.identity`: the key without its code
   values) whose every code value is of the window (`store._entry`): moved to the address the new code asks for. A
   value-to-value migration (``keys migrate``) cannot do it alone: under the broad rule 17 entries shared one key
   (289cb9982ec18b89: the counts, the assembly, the fit), so one old value stood for 17 new ones; it moved 26,277 entries
   and 16 of every 17 of those it could not resolve went where nothing asks (Alagoas then refitted 15 blocks, 25 min). An
   entry whose old key was shown unsound is outside the window (`ask`, `Session.survey_questions`, `Session.train`:
   they missed the lenses): its artefacts are computed again. Adopted artefacts keep the random draws they were made
   with: equal in law to a fresh computation, not in their bits.

**Consequence.** `event_counts`'s key covers 88 definitions (574), `ask`'s 747 (the lenses now in it); the closures'
median falls from 575. A plumbing or code-moving refactor costs a migration, not a recomputation; a key's soundness is a
measurement to repeat on new paths (`key_audit_start` on a cold study), not a property assumed.

**What would reverse it.** An audit finding a function a key lacks through a path the rule cannot see: the fix is a
declaration (a registry, an annotation of the class received), never a broader rule.
