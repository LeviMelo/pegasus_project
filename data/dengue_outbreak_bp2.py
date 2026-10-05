"""The state-level outbreak lens on the two prospective objects (ADR-0012) for dengue, against the states' epidemic
years (incidence ≥ 300 per 100,000), at origins 2014 (2015–16) and 2018 (2019–23): the calibrated expectation
(purpose="expectation", ADR-0009: regime mixture, φ_extra, climatology; tier BP) and the alarm baseline
(purpose="alarm": level36 with φ_extra; tier BPA). Artefact data/logs/dengue_outbreak_alarm.json (the earlier
data/logs/dengue_outbreak_bp2.json, histories level36/auto, is the same two runs before the purpose existed).
Usage: python data/dengue_outbreak_bp2.py   (under scripts/heavy.py)"""
import json
import sys

import numpy as np

sys.path.insert(0, "data")
import dengue_eval as de  # noqa: E402

from pegasus_core import control, gateway  # noqa: E402

with open("data/logs/dengue_eval_lens_bp14.json", encoding="utf-8") as fh:
    extra = json.load(fh)["state_month_phi_extra"]
ex = de.expectations()
m = ex.model("*")
uf = gateway.regions(m.data.places, "uf")
pop_year = m.data.N.sum(axis=2).reshape(len(m.data.places), -1, 12).sum(2)
y_year = m.observed(np.array([0])).reshape(len(m.data.places), -1, 12).sum(2)
keys = np.unique(uf)
inc = np.array([y_year[uf == k].sum(0) / pop_year[uf == k].sum(0) * 1e5 for k in keys])
ledger = control.Ledger()
out = {"state_month_phi_extra": extra, "runs": {}}
for origin, last in ((2014, 2016), (2018, 2023)):
    for purpose in ("alarm", "expectation"):
        e = de.expectations(list(range(2010, last + 1)))
        s = e.prospective("*", origin, purpose=purpose)
        rec = de.recovery(s, uf, keys, extra, inc, ledger)
        rec["observed"], rec["expected"] = float(s.y.sum()), float(s.mu.sum())
        rec["municipal_ks"] = s.calibration["ks"]
        rec["ks_by_macroregion"] = s.calibration["ks_by_macroregion"]
        out["runs"][f"{origin}:{purpose}"] = rec
        print(origin, purpose, s.tier, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in rec.items()
                                if k in ("observed", "expected", "flagged_state_years", "epidemic_state_years",
                                         "recall_incidence_300", "precision_incidence_300", "recall_incidence_150",
                                         "municipal_ks", "state_month_ks")}, flush=True)
        print("   missed", rec["missed_epidemics"], flush=True)
        with open("data/logs/dengue_outbreak_alarm.json", "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1, default=float, ensure_ascii=False)
