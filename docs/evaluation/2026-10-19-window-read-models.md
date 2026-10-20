# The window's read models after the redesign: what a reader sees, and how fast

**Regime.** pegasus_project `scope-v2` (f1134ea and the ledger change), pegasus_data `pegasus-core-fixes` (2333540), the
workspace's real studies (21 declarations) and stores; the service on 127.0.0.1:8765; 2026-10-19. Measured with
`time.time()` around single calls, after a service restart; `scratchpad/routes_smoke.py` hit every route on every
study (556 requests, 0 failed).

**What the reader sees.**
- `summary`/`cards`: a study's title in words: a single SINAN agravo's name ("Dengue", not "Dengue [dengue clássico],
  Febre hemorrágica…"), else its codes' labels or their smallest ICD-10 group. A folder without an `estimates`
  table says so in words; it had shown a database error on its card (toxoplasmosis_smoke, the standard slice).
- `datasets`:
  - The catalog lists 154 datasets: 11 SIA datasets, published both on the FTP and as Dados Abertos exports, are
    one row each, with their other publication in `also`.
  - A dataset is "study" only when a study can place and standardise its events (`gateway._strata`): 100 now. SIH-SP
    is "incomplete": its procedure lines carry no age (OQ 23).
  - Its texts are read without the curation's history or record references (`reader_text`): 41 such fragments in
    `what_it_is` and `why_no_event_type` before, 0 after.
- `search`: a notifiable disease is found by its name in English or Portuguese ("violência", "trabalho" and
  "sifilis" had found nothing), and named.
- `contexts`: each of the 108 fields has a label. A context field's key leaves out its words (`FIELD_WORDS`), so
  adding the labels recomputed nothing beyond the once-only change of the key.

**How fast** (after a restart):

| call | before | after | what changed |
|---|---|---|---|
| `cards()`, 21 studies | 16.2 s | 1.6 s (0.7 s in memory) | summaries kept on disk under the declaration, folder, last run and code; declaration names read once per file version (`find` had parsed every YAML on each call, 579 parses) |
| `ledger()` | 22.0 s | 3.6 s, same output | the 1,441,753 rows counted in Arrow instead of as Python dicts |
| `leads()`, first read | 27.5 s | unchanged | 169,806 leads decoded from JSON once per process (10.9 s in `json.loads`); 0.7 s after. Not changed in this pass; the window says the first read is slow. Open: a register read without decoding every lead's JSON (a columnar register, or reading only the page's leads) |
