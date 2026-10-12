"""Fast data-path tests on the shared store's cached objects (seconds each once cached): each guards a defect a study
run found on 2026-10-11/12, with the known answer it was checked against."""

from __future__ import annotations

import collections

import pytest

from pegasus_core import dependency, facility, gateway, study, tools

SEROLOGY = ["0202030768", "0202030873", "0213010577", "0202110150"]


def test_counts_from_an_extract():
    # a renamed manifest key (codes -> filters) failed every count from an extract
    c = gateway.event_counts("SIASUS-PA", "procedure", 2015, classifier="PA_PROC_ID", codes=SEROLOGY, support="PA_UFMUN",
                             cell=False)
    df = c.counts.to_pandas()
    assert int(df.y.sum()) == 4_792_984
    assert int(df[df.u == 431690].y.sum()) == 17_764                    # Santa Maria/RS


def test_a_foetal_death_is_counted_whatever_its_cell():
    # counted by sex-age cell, SIM-DOFET held no P37.1 and the hypothesis's own source was left out
    it = study.Item("SIM-DOFET", "foetal_death", ["*"], None, list(range(2010, 2024)), "", source={"codes": ["P371"]})
    assert study._records(it, it.years) > 100


def test_facility_codes_at_their_declared_width():
    # SINAN stores CNES as a number: "477" is 0000477, Hospital Oswaldo Cruz, Recife
    cube = facility.facility_cube("SINAN-TOXC", "notification", 2023).to_pandas()
    assert set(cube.facility.str.len()) == {7}
    assert int(cube[cube.facility == "0000477"].y.sum()) == 324


def test_group_columns_hold_no_administrative_fact():
    g = tools.group_columns("SIHSUS-RD", "hospitalisation")
    assert {"COBRANCA", "FAEC_TP", "NAT_JUR", "GESTOR_COD"}.isdisjoint(g) and {"MORTE", "INSTRU", "RACA_COR"} <= set(g)


def test_group_values_labelled_as_a_query_labels_them():
    it = study.Item("SINAN-TOXG", "notification", ["*"], None, list(range(2019, 2026)), "")
    assert study._group_text(it, ["EVOLUCAO=1"]) == "Evolução do Caso: Vivo (1)"


def test_triage_on_a_field_loaded_on_demand():
    # the evidence grid needed a stored fit's listing (`_per_year` unset), and a group answer without years failed
    s = tools.Session("SINAN-TOXC", "notification", list(range(2019, 2024)))
    assert s.triage() is not None and s._per_year == 1


def test_the_place_level_map_reads_a_field_once():
    topic = [("SINAN-TOXC", "notification", "*", None, list(range(2019, 2024)))] * 2 + [
        ("SIHSUS-RD", "hospitalisation", "*", {"codes": ["P371"]}, list(range(2015, 2024)))]
    rows = dependency.field_map(topic, ["sisagua_surveillance_ecoli_present"])
    assert len({r["x"] for r in rows}) == 2


@pytest.mark.parametrize("draw", [None, 0])
def test_a_cohorts_seeded_persons_are_the_whole_merges(draw):
    ds = ["SINAN-TOXC", "SIHSUS-RD", "SIM-DO"]
    _, ids = gateway.cohort_records("SINAN-TOXC", "notification", 2022, [])
    seeds = ("SINAN-TOXC", "patient", ids.to_numpy(zero_copy_only=False))

    def hits(ent):
        n = ent.nodes.to_pandas()
        mine = n[(n.dataset == seeds[0]) & (n.role == seeds[1]) & n.record.isin(set(seeds[2]))]
        return collections.Counter(n[n.person.isin(set(mine.person))].dataset)

    assert hits(gateway.persons(2022, draw=draw, datasets=ds)) == hits(gateway.persons(2022, draw=draw, datasets=ds,
                                                                                         seeds=seeds))


def test_a_study_area_holds_its_places_only(monkeypatch):
    # `where: RS`: a block is the area's 497 places, its events those of residents of the area
    from pegasus_core import monolith

    monkeypatch.setenv("PEGASUS_AREA", "43")
    d = monolith.assemble("SINAN-TOXC", "notification", "*", list(range(2019, 2024)))
    assert len(d.places) == 497 and {int(p) // 10000 for p in d.places} == {43}
    assert d.unallocated.get("outside the study area", 0) > 0
    assert study._area(["RS", "431690"]) == [43, 431690]


def test_the_place_level_map_leaves_out_a_field_without_events():
    # a SIH field on a column holding none of its codes raised, and the map of every other field died with it
    topic = [("SINAN-TOXC", "notification", "*", None, list(range(2019, 2024))),
             ("SIHSUS-RD", "hospitalisation", "*", {"classifier": "DIAG_SECUN", "codes": ["Z999"]}, list(range(2019, 2024)))]
    rows = dependency.field_map(topic, ["sisagua_surveillance_ecoli_present"])
    assert {r["x"] for r in rows} == {"SINAN-TOXC:*"}


def test_an_areas_graph_and_register_are_its_own(monkeypatch):
    monkeypatch.setenv("PEGASUS_AREA", "43")
    from pegasus_core import config, leads

    s = tools.Session("SINAN-TOXC", "notification", list(range(2019, 2024)))
    assert int(s.edges().max()) < 497                     # the graph over the area's 497 places, not Brazil's 5,570
    assert leads.Register().path.name == "leads_area_43" and config.area_suffix() == "_area_43"
