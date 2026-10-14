"""Fast contract tests, run before every study launch (`scripts/prelaunch.py`): each guards a defect a study run found
on 2026-10-11/12, failing in seconds what had failed twenty minutes into a run. Pure logic on small inputs; the data
paths in `test_data_paths.py` read the shared store's cached objects."""

from __future__ import annotations

from pathlib import Path

import pytest

from pegasus_core import control, gateway, leads, study, tools

ROOT = Path(__file__).resolve().parents[2]


def test_every_effect_scale_a_lens_declares_is_a_lead_scale():
    # the propagation question's km per month made `Lead` refuse every answer of an item (smoke study)
    scales = {v for m in vars(tools).values() if isinstance(m, dict) and "propagation" in m
              for v in m.values() if isinstance(v, str) and not v.startswith("B")}
    assert scales <= set(leads.SCALES), scales - set(leads.SCALES)


def test_rows_table_keeps_columns_only_later_rows_carry():
    # pyarrow takes the first row's columns: institution facts and cohort estimates were dropped
    t = study._rows_table([{"a": 1}, {"a": 2, "facts": "x"}])
    assert t.column_names == ["a", "facts"] and t.column("facts").to_pylist() == [None, "x"]


@pytest.mark.parametrize("name,entry,expected", [
    ("SIM-DO", "SIM.DO", True), ("SIM-DOFET", "SIM.DO", False), ("SIASUS-PA", "SIASUS", True),
    ("SIASUS-AN", "SIASUS-PA", False), ("SIHSUS-RD", "SIH-RD", True), ("CIHA-CIHA", "SIH-RD", False)])
def test_dataset_matching_any_spelling(name, entry, expected):
    assert study._dataset_matches(name, entry) is expected


def test_reserve_by_dataset_not_spelling():
    # the reserve was keyed by spelling: SIM-DO studies read SIM 2024
    assert control.reserved("SIM-DO") == control.reserved("SIM.DO") == [2024]
    assert control.reserved("SIM-DOFET") == []
    with pytest.raises(control.ReservedPeriod):
        control.check_reserved("SIM-DO", [2024])


def test_links_touching_the_reserve_and_outside_a_study():
    assert "sih_deaths_to_sim" in gateway.reserved_links(2024)
    assert not gateway.reserved_links(2022)
    assert gateway.run_touches_reserve("sinan_toxc_to_sim", 2023)       # its SIM side is padded into 2024
    kept = set(gateway.link_specs()) - gateway.links_outside(["SINAN-TOXC", "SIHSUS-RD", "SIM-DO"])
    assert "sinan_toxc_to_sih_admission" in kept and "sim_infant_deaths_to_sinasc" not in kept


@pytest.mark.parametrize("path", sorted((ROOT / "studies").glob("toxoplasmosis*.yml")) + sorted((ROOT / "studies" / "slices").glob("*.yml")))
def test_every_reference_declaration_loads(path):
    d = study.load(path)
    assert d.years and d.depth in study.DEPTHS


def test_a_declaration_never_ignores_a_key(tmp_path):
    # topic.include was accepted and never applied: a key not built is refused, not ignored
    p = tmp_path / "s.yml"
    p.write_text("study: s\ntopic: {seeds: {icd10: [B58]}, include: [SIM-DO]}\n", encoding="utf-8")
    with pytest.raises(study.DeclarationError, match="include"):
        study.load(p)
    p.write_text("study: s\ntopic: {seeds: {icd10: [B58]}}\nquestions: [nonsense]\n", encoding="utf-8")
    with pytest.raises(study.DeclarationError, match="questions"):
        study.load(p)


def test_one_item_per_field():
    # a code set on the primary classifier is the code set: the report listed each finding twice
    a = study.Item("SIHSUS-RD", "hospitalisation", ["*"], None, [2010, 2011], "topic", source={"codes": ["B58"]})
    b = study.Item("SIHSUS-RD", "hospitalisation", ["*"], None, [2010], "related",
                   source={"classifier": "DIAG_PRINC", "codes": ["B58"]})
    out = study._one_per_field([a, b])
    assert out == [a]


def test_a_code_set_field_is_named_with_its_codes():
    it = study.Item("SIHSUS-RD", "hospitalisation", ["*"], None, [2010], "", source={"codes": ["B58", "P371"]})
    assert study._codes_text(it) == ": B58 Toxoplasmose, P371 Toxoplasmose congênita"


def test_related_reads_the_strongest_n_and_prices_the_next(monkeypatch, tmp_path):
    # `time: minutes` was a budget no person could choose by; `related: N` is a count, the next ones shown with costs
    p = tmp_path / "s.yml"
    p.write_text("study: s\ntopic: {seeds: {icd10: [B58]}}\nrelated: 2\n", encoding="utf-8")
    decl = study.load(p)
    monkeypatch.setattr(study, "_estimate", lambda d, items: [setattr(i, "est_seconds", 60.0) for i in items])
    extra = [(float(w), study.Item("SIM-DO", "death", ["*"], None, [2020], "related code", source={"codes": [c]}))
             for w, c in [(1, "A"), (5, "B"), (3, "C"), *((0.5, f"Z{k}") for k in range(30))]]
    out = study._strongest(decl, extra)
    read = [i.source["codes"][0] for i in out if i.status == "in"]
    assert sorted(read) == ["B", "C"] and len(out) == 2 + study.RELATED_SHOWN
    # a code is read wherever it is recorded: its places count once
    extra += [(5.0, study.Item("SIH-RD", "hospitalisation", ["*"], None, [2020], "related code", source={"codes": ["B"]}))]
    out = study._strongest(decl, extra)
    assert sorted(i.source["codes"][0] for i in out if i.status == "in") == ["B", "B", "C"]
    for bad in ("-1", "true", "some"):
        p.write_text(f"study: s\ntopic: {{seeds: {{icd10: [B58]}}}}\nrelated: {bad}\n", encoding="utf-8")
        with pytest.raises(study.DeclarationError, match="related"):
            study.load(p)


def test_a_depth_is_a_preset_of_the_declarations_choices(tmp_path):
    keys = set(study.PRESETS["survey"])
    assert all(set(v) == keys for v in study.PRESETS.values()) and keys <= study.KEYS
    p = tmp_path / "s.yml"
    p.write_text("study: s\ntopic: {seeds: {icd10: [B58]}}\ndepth: deep\npersons: false\nrelations: [fields]\n",
                 encoding="utf-8")
    d = study.load(p)
    assert d.choice("persons") is False and d.choice("relations") == ["fields"] and d.choice("replicate") is True
    p.write_text("study: s\ntopic: {seeds: {icd10: [B58]}}\nrelations: [everything]\n", encoding="utf-8")
    with pytest.raises(study.DeclarationError, match="relations"):
        study.load(p)


def test_capture_recovers_a_known_population():
    # three independent lists of 1,000 with capture 0.5, 0.4, 0.3: the expected cells give back 1,000 (210 unseen)
    import itertools

    from pegasus_core import capture

    p = (0.5, 0.4, 0.3)
    cells = {c: 1000 * float(__import__("numpy").prod([q if b else 1 - q for q, b in zip(p, c, strict=True)]))
             for c in itertools.product([False, True], repeat=3) if any(c)}
    est = capture.loglinear(cells)
    assert est["model"] == "independence" and abs(est["estimate"] - 1000) < 1e-6 and est["low"] < 1000 < est["high"]
    two = capture.chapman(500, 400, 200)
    assert abs(two["estimate"] - (501 * 401 / 201 - 1)) < 1e-9


def test_a_paused_lane_resumes_when_nothing_else_computes():
    # deep8 waited with two lanes paused: the pool's idle workers counted as active, and 8.4 GB free never reached 12
    assert study._may_resume(8.4, 6.1, others_working=False)
    assert not study._may_resume(8.4, 6.1, others_working=True)
    assert study._may_resume(14.0, 6.1, others_working=True)


def test_a_code_sets_categories_are_its_codes():
    # a code set's node is "*": SIH's P37.1 admissions had been corroborated under every code SIH records
    from pegasus_core import corroborate

    assert corroborate.categories_of(None, "*", "SIHSUS-RD", ["P37.1", "B58"]) == ["B58", "P371"]
    assert study._corroboration_text({"tested": False, "reason": "no independent field holds its codes"}).startswith("no")
    assert "p 0.001" in study._corroboration_text({"tested": True, "label": "SIM-DO death", "observed": 3.0,
                                                  "null_median": 1.0, "p": 0.001, "q": 0.02})


def test_a_quality_field_is_asked_of_recording_only():
    # a column's completeness asked of propagation, share, group, seasonality held the TOXC item half an hour
    from pegasus_core import questions

    class S:
        source = {"quality": True, "indicator": "ID_PAIS"}

    out = questions._ask(S(), "propagation", "*")
    assert out == [] and "quality field" in out.failed["*"] and set(questions.QUALITY_QUESTIONS) <= set(questions.QUESTIONS)


def test_a_small_corroboration_p_is_read_from_the_tail():
    # a promising lead was redrawn at 99,999 replicates for Benjamini-Hochberg to reach it; its null's fitted tail
    # gives the small p (Knijnenburg et al. 2009) and matches the exact one where the null is known
    import numpy as np
    from scipy import stats

    from pegasus_core import corroborate

    null = np.random.default_rng(1).standard_normal(4999)
    p, how = corroborate.tail_p(null, 4.0)
    assert "tail" in how and 0.2 < p / stats.norm.sf(4.0) < 5
    assert corroborate.tail_p(null, 1.0)[1] == "permutation"


def test_a_later_years_test_reads_its_own_fields_leads_only():
    # the training register is one per dataset: every code set's node is "*", and B58's leads were tested on P37.1's
    def lead(codes):
        return leads.Lead(kind="answer", estimand="excess", tier="B1", fields=["SIHSUS-RD:hospitalisation:*"],
                          locus={}, effect=1.0, scale="rate_ratio", interval=None, p=0.01, q=0.01, family="f",
                          null="", calibrated=True, provenance={"source": {"codes": codes}})

    class S:
        dataset, event, source = "SIHSUS-RD", "hospitalisation", {"codes": ["P371"]}
        _own = tools.Session._own

    assert S()._own(lead(["P371"])) and not S()._own(lead(["B58"]))


def test_a_related_field_is_asked_what_the_declaration_says(tmp_path):
    # a related code is read to relate it to the topic: asked all eleven questions, 160 of them made the exhaustive
    # scope's hours; the preset asks none, `related_questions` asks more
    p = tmp_path / "s.yml"
    p.write_text("study: s\ntopic: {seeds: {icd10: [B58]}}\ndepth: exhaustive\n", encoding="utf-8")
    assert study.load(p).choice("related_questions") == []
    p.write_text("study: s\ntopic: {seeds: {icd10: [B58]}}\nrelated_questions: [excess]\n", encoding="utf-8")
    assert study.load(p).choice("related_questions") == ["excess"]


def test_a_triage_without_an_institution_is_read():
    # a triage's facility is False where none was found: deep17's products died reading it as a dict
    class X:
        def __init__(self, fac):
            self.robustness = {"triage": {"facility": fac}}

    assert study._one_institution(X(False)) is None and study._one_institution(X({"one_institution": "0000477"})) == "0000477"


def test_capture_gives_no_total_on_links_not_viable(monkeypatch):
    # TOXC x SIH 2019-2021 through links "use with caution" gave 47,029 cases against some 8.4 M births: the pairs
    # the link misses count persons twice; where links are not viable the overlap is reported, not a total
    from pegasus_core import capture

    lists = {"A": {"deaths": False}, "B": {"deaths": False}}
    monkeypatch.setattr(capture, "lists_of", lambda d, c: {"capture": "x", "lists": lists, "links": []})
    monkeypatch.setattr(capture, "patterns", lambda *a, **k: (["A", "B"], {(True, False): 50, (False, True): 40,
                                                                            (True, True): 10}))
    caution = capture.capture(["A", "B"], ["P371"], [2021], lambda links, y: "use with caution", log=lambda *a: None)
    viable = capture.capture(["A", "B"], ["P371"], [2021], lambda links, y: "viable", log=lambda *a: None)
    assert caution[0]["estimate"] is None and "no total" in caution[0]["note"] and caution[0]["patterns"]
    assert viable[0]["estimate"] is not None


def test_a_compacted_register_keeps_every_state(tmp_path):
    # 1,941 parts were read on every write (deep18): merged into one, the latest state of each lead is unchanged
    reg = leads.Register(tmp_path / "leads")

    def lead(i, status="open"):
        return leads.Lead(kind="answer", estimand="excess", tier="B1", fields=[f"X:e:{i % 7}"], locus={"places": [i]},
                          effect=1.0 + i, scale="rate_ratio", interval=None, p=0.01, q=0.01, family=f"f{i % 3}",
                          null="", calibrated=True, status=status)

    reg.COMPACT_AT = 10**6
    for i in range(30):
        reg.add([lead(i)])
    reg.add([lead(3, "retired")])
    before = {x.id: x.status for x in reg.current()}
    assert reg.compact() == 31 and len(list(reg.path.glob("part-*.parquet"))) == 1
    assert {x.id: x.status for x in reg.current()} == before and before[lead(3).id] == "retired"
    assert len(reg.current(family="f1")) == 10


def test_the_audit_reads_a_findings_places_as_written(tmp_path):
    # the findings table writes places as text; the audit read them as a list and missed Santa Maria's 2018 signal
    import pyarrow as pa
    import pyarrow.parquet as pq

    pq.write_table(pa.table({"places": ["430010, 431690 (+17)"], "class": ["signal"], "first_year": [2018],
                             "last_year": [2018], "label": ["serology"]}), tmp_path / "findings.parquet")
    (tmp_path / "study.yml").write_text(
        "hypotheses:\n  - {component: transient, where: [4316907], when: 2018-01..2018-06, note: outbreak}\n",
        encoding="utf-8")
    item9 = next(r for r in study.audit(tmp_path) if r["item"] == 9)
    assert item9["status"] == "met" and "outbreak: 1 signals" in item9["evidence"]


def test_levels_below_the_whole_are_regions_then_states(monkeypatch):
    """The descriptive tables' geographies (`study._levels_below`, over municipalities): macro-regions when the study
    spans several, then states; below an area that is one state, no state row (it would repeat the area's) but its
    health macro-regions and health regions. Its patch had made it call itself (2026-10-13)."""
    import numpy as np

    from pegasus_core import study

    monkeypatch.delenv("PEGASUS_AREA", raising=False)
    # Porto Alegre, Caxias do Sul, Florianópolis, São Paulo, Porto Velho
    levels = study._levels_below(np.array([431490, 430510, 420540, 355030, 110020]))
    assert [x[0] for x in levels] == ["region"] * 3 + ["state"] * 4
    assert levels[0][1] == "1 Norte" and levels[-1][1] == "43"
    monkeypatch.setenv("PEGASUS_AREA", "43")
    below = study._levels_below(np.array([431490, 430510]))
    assert {x[0] for x in below} == {"health macro-region", "health region"}
    assert all(sel.sum() == 1 for level, _, sel in below if level == "health region")
