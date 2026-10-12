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


@pytest.mark.parametrize("path", sorted((ROOT / "studies").glob("toxoplasmosis*.yml")))
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
