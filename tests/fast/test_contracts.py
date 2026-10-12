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
