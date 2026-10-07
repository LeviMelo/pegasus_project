# Fields from pegasus_data's roles

**Status:** building (S1, 2026-10-07). Built: the registry (`fields.declared`), measures (`fields.measure_source`, readers with declared missing codes and domains; pegasus_data ADR-0154), compositions (`fields.share_sources`, `gateway.composition_counts`), institutions as the `institution` question, methods declaring the field kinds they read, measures and compositions in `update` plans. Since built: SIM's and SINASC's missing codes and measurement domains (pegasus_data ADR-0154 addenda); intervals, every declared date against the event's own (`fields.interval_source`, the sign read from the data). A measure whose declared domain admits zero is read by the count family (`monolith.CountModel`). Other classifiers' trees are read through `gateway.code_tree`'s canonical levels; the count family's surprise is the randomised PIT of the place-year sum under its NB predictive (finite at zero). Pending: the first end-to-end readings (plans/s1_*.yml). It replaces the hand-named mark of today's code (`source="mark"`, `PESO`) and my earlier proposal to "add marks as questions" by naming variables, which the author rejected as a breach of the data-agnostic principle.

## The problem

pegasus_data types every column it serves. Each has:
- `role`: the entity and property it states;
- `kind`: number, category, code_tree, date, place, institution, identifier or text;
- `model`: what a model may do with it (stratum, dimension, mark, when, where, institution, event_type, link_only, excluded).

| system | mark | dimension | institution | stratum |
|---|---|---|---|---|
| SIH-RD | 92 | 5 | 3 | 5 |
| SIM-DO | 56 | 15 | 1 | 5 |
| SINASC-DN | 52 | 10 | 1 | 4 |
| SINAN-DENG | 154 | 15 | 1 | 4 |

PegaSUS reads three things only:
- the event types;
- their primary classifier (the count fields of the ICD tree);
- the strata (residence, sex, age).

Every mark, dimension and institution column is unread, except one column named by hand. A system newly declared in pegasus_data yields counts and nothing else.

## The principle

**A field is derived from declarations, never named in pegasus_core.**

A field is an (event type, a declared column, a statistic) over the place × period × strata lattice. Its expectation model, its departure models and its questions are chosen from the column's declared `model` and `kind`.

## The field kinds, by declaration

| declared | field | stage B (the structure of §4.2, plus) | what a departure means |
|---|---|---|---|
| event type × classifier node (`code_tree`, primary) | counts (built) | the monolith | more or fewer events |
| `model: mark`, `kind: number` | a measurement per event | §4.4 by its declared measurement scale, with case-mix from the classifier and the institution effect | the events themselves differ (longer, costlier, lighter) |
| `model: mark`, `kind: category` | the events' composition over the column's codes | a share model per category (beta-binomial), or multinomial | what the events are made of changes |
| `kind: date` (a mark, or a `when` other than the event's own) | an interval: days from the event's own date (no pairing declared: every date is paired with the event's) | a positive measurement | the system's timing changes |
| `model: dimension` | the events split by a declared non-stratum attribute | composition, as above | a dimension's share moves |
| `model: institution` | the facility lattice (§4.5) | the institution effect inside the likelihood | one institution departs |
| `model: stratum` race | an axis of G (O3) | the race-aware population account | disparities |
| linkage roles (pegasus_data `roles.yml`), event type A linked to B | B following A within a declared window | a share of A's events (per person) | outcomes after events change (§7.8) |

Every field kind is then asked the same questions (excess, step, trend, cluster), through methods that declare which field kinds they read. A count method reads counts; a location method reads a measurement's cell moments. The `share` question built today is the composition row, read only for the ill-defined chapter. Here it becomes general.

## What pegasus_data must declare, not pegasus_core decide

Asked through `docs/handoffs/`, never guessed here:
- **A number's measurement scale:** a positive continuous quantity, a count, a bounded score, or an identifier-like number that is not a measurement. `kind: number` does not say which, and the model family depends on it.
- **Order for categories that have one** (scores, schooling), so an ordinal model is chosen and not a multinomial.

## How it changes the existing objects

- `fields.Registry` lists fields from `pegasus_data.roles()` and `event_types()` for every served system. `pegasus-core fields` shows them, with the reason any field is not modelled (a role missing a declaration).
- `gateway` reads moments (n, Σm, Σm²) and compositions by declared role. The `source="mark"` path naming a column goes.
- The questions registry: each `Method` declares the field kinds it reads, and `ask` refuses a mismatch instead of misreading it.
- The survey asks every field of every kind. Its families are (question, kind, block).
- Linkage: `cohort()` in the API, over pegasus_data's persons and link draws. Outcome-after-event fields come from declared links, and per-person corroboration of aggregate leads enters stage E.

## Acceptance (real data)

- **The registry.** For SIH-RD, SIM-DO, SINASC-DN and every SINAN agravo, the listed fields match pegasus_data's declarations. Every column is either a field or carries a stated reason it is not one.
- **One chapter's marks.** Fitted from declarations alone, with no column named in pegasus_core. Calibrated by the PIT of its cell means.
- **Documented positives,** declared before running, for at least one measurement and one composition field. Candidates come from the literature (a known change in practice or in a measured outcome); I will propose them, and you judge them.
