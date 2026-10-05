"""Y35 Goiás test: the result row of ledger id 3d787b765f614065 (written once; the pending row was registered by the declaration)."""
import json
from pegasus_core import control
r = json.load(open("data/y35_goias/results.json", encoding="utf-8"))
dt = r["deficit_test"]
L = control.Ledger()
ids = {x["id"] for x in L.table().to_pylist() if x["kind"] == "pending"}
assert "3d787b765f614065" in ids
done = {x["id"] for x in L.table().to_pylist() if x["kind"] == "result"}
assert "3d787b765f614065" not in done, "result already written"
verdict = {"verdict": "both: real rise in police killings (FBSP 141->631, tested direction, bound size) and a coding catch-up (Y35/FBSP 0.01->0.30); recode of ordinary firearm deaths into Y35 rejected as the main account",
           "primary_test": "recode-2: deficit of X93-95+Y22-24 2017-21 against Goias's 2012-16 share of the rest of Brazil vs Y35 excess; two-sided bootstrap p(D=E), 20000 Poisson draws, floor 1/20001",
           "D": dt["D"], "E": dt["E"], "recode_share_upper_bound": dt["share_explainable_by_recode_max"],
           "grades": {"real-1": "tested: no", "real-2": "tested/bound: fall exceeds rise", "real-3": "consistent", "real-4": "tested (weak)", "recode-1": "tested: no", "recode-2": "bound: <=34%",
                      "recode-3": "tested: no", "recode-4": "tested (general), unidentified (police variant)", "coverage-1": "tested: yes, ratio 0.01->0.30"},
           "entry": "docs/evaluation/2026-10-05-y35-goias-declaration.md#result"}
L.complete("3d787b765f614065", p=max(float(dt["p_two_sided"]), 1 / 20001), effect=float(dt["share_explainable_by_recode_max"]), result=verdict)
print("written")
