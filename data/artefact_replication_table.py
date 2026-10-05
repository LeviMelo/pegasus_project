"""The 57 claims through the artefact-aware audit: one row each, and the cross-tab of the old reading's class against the new
verdict. Reads data/artefact_replication/audit.json (data/artefact_replication.py) and data/replicated_claims/final.pkl."""
import json
import os
from pathlib import Path

os.chdir(Path(__file__).resolve().parents[1])
import pandas as pd

audit = json.load(open("data/artefact_replication/audit.json"))
old = pd.read_pickle("data/replicated_claims/final.pkl").set_index("id")
rows = []
for r in audit:
    o = old.loc[r["id"]]
    ex = r["explanations"]
    best = {}
    for e in ex:
        best.setdefault(e["grade"], []).append(f"{e['kind']}:{e['outcome']}" + (f"<={e['bound']:.2f}" if e.get("bound") else ""))
    lv = [x for x in r.get("rescope", [])]
    rows.append({
        "lifted": "; ".join(f"{x['level']}: b={x['beta']:+.3f} x{x['ratio_over_period']:.2f} p={x['p']:.3f} {'OK' if x['ok'] else 'no'} nodeshare={x['node_share_of_deaths']:.2f} {x['jurisdiction']['scope']}" for x in lv),
        "n_lifted_ok": sum(x["ok"] for x in lv),
        "node": r["node"], "uf": r["uf"], "old": o["cls"], "verdict": r["verdict"],
        "att": round(r["national"]["attenuation"] or 0, 2), "nat_ok": r["national"]["ok"],
        "all_cause": round(r["all_cause"]["beta"], 3), "ac_share": round(r["all_cause"]["share_of_claim"], 2),
        "shape": r["shape"]["shape"], "jump": round(r["shape"]["jump"], 2),
        "scope": r["jurisdiction"]["scope"], "k": len(r["jurisdiction"].get("states_holding", [])),
        "tested": "; ".join(best.get("tested", [])), "bound": "; ".join(best.get("bound", [])),
        "consistent": "; ".join(best.get("consistent", [])),
    })
df = pd.DataFrame(rows)
pd.set_option("display.width", 300, "display.max_colwidth", 70, "display.max_rows", 100)
print(df.drop(columns=["tested", "bound", "consistent", "lifted"]).to_string())
print(df.groupby(["old", "verdict"]).size().unstack(fill_value=0))
print(df.verdict.value_counts())
print(df.scope.value_counts())
print(df["shape"].value_counts())
df.to_csv("data/artefact_replication/table.csv", index=False)
