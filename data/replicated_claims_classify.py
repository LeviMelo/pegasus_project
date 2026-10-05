"""Step 3: features and rule-based first pass over data/replicated_claims/claims.json (rules fixed here, before the table is read
claim by claim). att: the claim's slope under direct standardisation (year-specific national rates) over the survey's;
den: change of the slope with account-3 instead of POPSVS; comp: share of the slope carried by the unit's all-cause SMR slope;
mirror_sib / mirror_R: share of the node's change in excess deaths (2010-11 -> 2018-19) offset by the opposite change in its
ICD block / in R00-R99."""
import json
import numpy as np
import pandas as pd

rows = json.load(open("data/replicated_claims/claims.json"))
SD = np.std(np.arange(2010, 2020))
UF = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
      28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF"}


def mirror(d_other, d_node):
    if d_other is None or d_node is None or not np.isfinite(d_other) or d_node == 0 or np.sign(d_other) == np.sign(d_node):
        return 0.0
    return float(abs(d_other) / abs(d_node))


out = []
for r in rows:
    cb, bp = r["claim_beta"], r["beta_pop"]
    r["uf_name"] = UF[r["uf"]]
    r["att"] = bp / cb if cb else np.nan
    r["den"] = abs(r["beta_acc"] - bp) / abs(bp) if bp else np.nan
    r["comp"] = max(0.0, r["beta_all"] / bp) if np.sign(r["beta_all"]) == np.sign(bp) and bp else 0.0
    r["mirror_sib"] = mirror(r.get("dex_sib"), r["dex_node"])
    r["mirror_R"] = mirror(r.get("dex_R"), r["dex_node"])
    r["yr"] = bp / SD
    r["change9"] = float(np.exp(9 * bp / SD))
    if not np.isfinite(r["att"]) or r["att"] < 0.5:
        cls = "artefact: national course (offset)"
    elif r["mirror_sib"] >= 0.5:
        cls = "artefact: coding, sibling substitution"
    elif r["mirror_R"] >= 0.5:
        cls = "artefact: coding, ill-defined exchange"
    elif r["comp"] >= 0.5:
        cls = "artefact: completeness"
    else:
        cls = "to read"
    r["first_pass"] = cls
    out.append(r)
df = pd.DataFrame(out)
pd.set_option("display.width", 250)
print(df[["node", "uf_name", "claim_beta", "beta_pop", "att", "den", "comp", "mirror_sib", "mirror_R", "change9", "dexpct_node", "dexpct_R", "first_pass"]].round(2).to_string())
print(df.first_pass.value_counts())
df.to_pickle("data/replicated_claims/features.pkl")
