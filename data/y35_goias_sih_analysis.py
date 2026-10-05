"""Y35 Goiás test (ledger 3d787b765f614065), step 4: SIH firearm admissions (hospital UF = GO) by intent and admission year."""
import json, numpy as np, pandas as pd, warnings
warnings.simplefilter("ignore")
s = pd.read_parquet("data/y35_goias/sih_firearm.parquet")
DIAG = [c for c in s.columns if c.startswith(("DIAG", "CID_"))]
PFX = {"Y35": ("Y35",), "assault": ("X93", "X94", "X95"), "undet": ("Y22", "Y23", "Y24"), "suicide": ("X72", "X73", "X74"), "accident": ("W32", "W33", "W34")}
for k, v in PFX.items():
    s[k] = s[DIAG].apply(lambda col: col.astype(str).str[:3].isin(v)).any(axis=1)
s["intent"] = np.select([s.Y35, s.assault, s.undet, s.suicide, s.accident], ["Y35", "assault", "undet", "suicide", "accident"], "other")
s["year"] = s.DT_INTER.astype(str).str[:4].astype(int)
s["res_go"] = s.MUNIC_RES.astype(str).str[:2].eq("52")
s["death"] = s.MORTE.astype(str).eq("1")
print("which field carries the firearm code (any intent), by year (share of rows):")
print(pd.DataFrame({c: s.groupby("year").apply(lambda d: d[c].astype(str).str[:3].isin(sum(PFX.values(), ())).mean()) for c in DIAG}).round(3))
t = s[s.year.between(2012, 2021)].groupby(["year", "intent"]).size().unstack(fill_value=0)
for c in ("assault", "undet", "suicide", "accident", "Y35"):
    if c not in t: t[c] = 0
t["pooled"] = t[["assault", "undet", "suicide", "accident", "Y35"]].sum(axis=1); t["Y35 share"] = (t.Y35 / t.pooled).round(3)
print("\nSIH-RD admissions (IDENT=1) in Goias hospitals with a firearm external cause, by admission year\n", t)
r = s[s.res_go & s.year.between(2012, 2021)].groupby(["year", "intent"]).size().unstack(fill_value=0); r["pooled"] = r.sum(axis=1)
print("\nsame, Goias residents\n", r)
d = s[s.year.between(2014, 2021)].groupby(["year", "intent"]).death.agg(["sum", "size"]).unstack(fill_value=0)
print("\nin-hospital deaths / admissions by intent\n", d.loc[:, [("sum", "Y35"), ("size", "Y35"), ("sum", "assault"), ("size", "assault")]] if ("sum", "Y35") in d else d)
s["age"] = np.where(s.COD_IDADE.astype(str).eq("4"), pd.to_numeric(s.IDADE, errors="coerce"), 0)
s["per"] = pd.cut(s.year, [2013, 2016, 2018, 2022], labels=["2014-16", "2017-18", "2019-22"])
P = s[s.intent.isin(["Y35", "assault", "undet"]) & s.per.notna()].groupby(["intent", "per"], observed=True).apply(lambda x: pd.Series({"n": len(x), "male": x.SEXO.astype(str).eq("1").mean(), "age_median": x.age.median(), "age_12_29": x.age.between(12, 29).mean(), "death": x.death.mean()})).round(3)
print("\nprofiles\n", P)
json.dump({"by_year": t.reset_index().to_dict("records")}, open("data/y35_goias/sih_results.json", "w"), default=str)
