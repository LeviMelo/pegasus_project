# Choices a person makes, and the exhaustive scope's size (2026-10-12)

**What changed.** A depth is a preset of the declaration's own keys (`study.PRESETS`; ARCHITECTURE §3.3): `readers`
(with `linked`), `related` (a count of codes), `relations`, `chapters`, `persons`, `replicate`, `download`, `draws`,
beside `where`, `period`, `topic.only`/`exclude`, `questions` and `nulls`. `time: minutes` is withdrawn: no one
chooses a study by a related-field time budget. `pegasus-core scope` writes `scope.yml` (it had printed it through
the console, which wrapped it unparseable) and shows `minutes_by_choice`.

**Measured.** The win condition's declaration at exhaustive depth (`studies/toxoplasmosis.yml`, depth exhaustive),
resolved on the shared store; read items and the scope's estimate:

| code | read | estimate | why it fell |
|---|---|---|---|
| presets, `related` counting fields | 725 | 1,878 min | — |
| related codes in one fitted block one item | 345 | 773 min | 504 chapter-node items were 124 blocks |
| one field per related code per source | 202 | 455 min | each code had been read on every classifier and certificate line |

Of the 202, 42 are the topic's own and 160 related (20 codes in up to 8 sources). The estimate prices every item at
about 2 minutes of questions, the median of measured steps; the national smoke study's code-set items took 50–60 s,
its topic items 3–9 min.

**Defects found by reading the scope.** SIM-DOREXT declared no group for its certificate lines (each line was a
field; pegasus_data now declares `death.causes`, as SIM-DO's); a code-list item was counted with its field's name as
a column (deep7's probes failed on it); B58 deaths' share linked to dengue notifications was a field (a linked share
is now read only to a system the study reads).
