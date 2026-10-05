"""Y35 Goiás test (ledger 3d787b765f614065), step 3: the analysis of the declared predictions. Reads data/y35_goias/*.parquet
(sim_firearm, sim_totals, sih_firearm), fbsp.json; prints the tables and writes data/y35_goias/results.json."""
import json, numpy as np, pandas as pd, duckdb
from scipy import stats
DIR = "data/y35_goias/"
Y = list(range(2012, 2022))
sim = pd.read_parquet(DIR + "sim_firearm.parquet")
tot = pd.read_parquet(DIR + "sim_totals.parquet")
fb = json.load(open(DIR + "fbsp.json", encoding="utf-8"))
sim["c3"] = sim.CAUSABAS.astype(str).str[:3]
sim["c4"] = sim.CAUSABAS.astype(str).str[:4]
sim["uf_res"] = sim.CODMUNRES.astype(str).str[:2]
sim["uf_oc"] = sim.CODMUNOCOR.astype(str).str[:2]
def grp(c3, c4):
    if c3 in ("X93", "X94", "X95"): return "assault"
    if c3 in ("Y22", "Y23", "Y24"): return "undet"
    if c3 in ("X72", "X73", "X74"): return "suicide"
    if c3 in ("W32", "W33", "W34"): return "accident"
    if c4 == "Y350": return "Y350"
    return "Y35other"
sim["g"] = [grp(a, b) for a, b in zip(sim.c3, sim.c4)]
out = {}
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 50)

def table(df):
    t = df.groupby(["year", "g"]).size().unstack(fill_value=0).reindex(Y, fill_value=0)
    for g in ("assault", "undet", "suicide", "accident", "Y350", "Y35other"):
        if g not in t: t[g] = 0
    t["Y35"] = t.Y350 + t.Y35other
    t["pooled_decl"] = t.assault + t.undet + t.suicide + t.accident + t.Y35
    t["pooled_fire"] = t.assault + t.undet + t.suicide + t.accident + t.Y350
    t["assault+undet"] = t.assault + t.undet
    return t[["assault", "undet", "assault+undet", "suicide", "accident", "Y350", "Y35other", "Y35", "pooled_fire", "pooled_decl"]]
go = table(sim[sim.uf_res == "52"]); br = table(sim); rest = br - go
go_oc = table(sim[sim.uf_oc == "52"])
print("GOIAS (residence)\n", go, "\nGOIAS (occurrence)\n", go_oc, "\nBRAZIL\n", br, "\nBRAZIL ex GO\n", rest)
out["go"] = go.to_dict("index"); out["br"] = br.to_dict("index"); out["go_occ"] = go_oc.to_dict("index")

# ---------------------------------------------------------------- labels / derived (pegasus_data.translate, never guessed)
import pyarrow as pa, warnings
warnings.simplefilter("ignore")
import pegasus_data as pg
from pegasus_core import config
cols = ["IDADE", "SEXO", "RACACOR", "LOCOCOR", "ATESTANTE", "CIRCOBITO", "FONTE", "TPPOS", "NECROPSIA", "CAUSABAS"]
parts = []
for y in Y:
    x = sim[sim.year == y][cols].reset_index(drop=True)
    r = pg.translate(pa.Table.from_pandas(x), system="SIM", series="DO", year=y, derived=True, root=config.data_root())
    parts.append(r.to_pandas()[["IDADE_anos"] + [c + "_label" for c in cols if c not in ("IDADE", "CAUSABAS")]])
lab = pd.concat(parts, ignore_index=True); lab.index = sim.sort_values("year", kind="stable").index
sim = sim.join(lab)
sim["age"] = sim.IDADE_anos
# ---------------------------------------------------------------- B. the national course and the conservation counterfactual
def ratio_cf(a, b, base=range(2012, 2017)):
    """expected a_t = (mean over base of a/b) * b_t."""
    r0 = np.mean([a[y] / b[y] for y in base]); return r0 * b
res = {}
for name in ("assault+undet", "pooled_fire", "pooled_decl"):
    exp = ratio_cf(go[name], rest[name]); res[name] = pd.DataFrame({"obs": go[name], "expected": exp.round(0), "deficit": (exp - go[name]).round(0), "Y35": go.Y35, "Y350": go.Y350,
        "ratio_def_to_Y35excess": ((exp - go[name]) / (go.Y35 - go.Y35[list(range(2012, 2017))].mean())).round(2)})
    print("\nCOUNTERFACTUAL (Goias at its 2012-16 share of the rest of Brazil):", name, "\n", res[name])
out["counterfactual"] = {k: v.to_dict("index") for k, v in res.items()}
# index to 2012-2016 mean
idx = pd.DataFrame({"GO_pooled_fire": go.pooled_fire / go.pooled_fire.loc[2012:2016].mean(), "exGO_pooled_fire": rest.pooled_fire / rest.pooled_fire.loc[2012:2016].mean(),
                    "GO_assault+undet": go["assault+undet"] / go["assault+undet"].loc[2012:2016].mean(), "exGO_assault+undet": rest["assault+undet"] / rest["assault+undet"].loc[2012:2016].mean()}).round(3)
print("\nINDEX (2012-16 mean = 1)\n", idx); out["index"] = idx.to_dict("index")
# across states: change in assault+undet against change in Y35, relative to the state's 2012-16 assault+undet
sim["au"] = sim.g.isin(["assault", "undet"])
P = sim.groupby(["uf_res", "year"]).agg(au=("au", "sum"), y35=("g", lambda s: s.isin(["Y350", "Y35other"]).sum())).reset_index()
P = P[P.uf_res.str.match(r"^\d\d$")]
base = P[P.year.between(2012, 2016)].groupby("uf_res")[["au", "y35"]].mean()
late = P[P.year.between(2018, 2021)].groupby("uf_res")[["au", "y35"]].mean()
S = pd.DataFrame({"base_au": base.au, "d_au": late.au - base.au, "d_y35": late.y35 - base.y35}).dropna()
S = S[S.base_au >= 100]
S["x"] = S.d_y35 / S.base_au; S["y"] = S.d_au / S.base_au
nat = (rest.loc[2018:2021, "assault+undet"].mean() / rest.loc[2012:2016, "assault+undet"].mean()) - 1
for label, d in (("all UFs", S), ("ex GO", S.drop("52"))):
    sl = stats.linregress(d.x, d.y); print(f"\nacross-UF regression ({label}, n={len(d)}): d_au/base_au = a + b * d_y35/base_au ; b = {sl.slope:.2f} (se {sl.stderr:.2f}), a = {sl.intercept:.2f}, r = {sl.rvalue:.2f}")
    out[f"uf_reg_{label}"] = {"b": sl.slope, "se": sl.stderr, "a": sl.intercept, "r": sl.rvalue, "n": len(d)}
print(S.loc[["52"]].round(3).to_string()); out["uf_GO"] = S.loc["52"].to_dict()
print("rank of GO by x (Y35 rise / base):", int(S.x.rank(ascending=False)["52"]), "of", len(S), "; rank by y (fall):", int(S.y.rank()["52"]))
print(S.sort_values("x", ascending=False).head(6).round(3).to_string())
# ---------------------------------------------------------------- C. all violent deaths, any means (sim_totals)
tot["uf"] = tot.uf.astype(str); T = tot[tot.uf == "52"].copy()
def cat(c4):
    c1 = c4[:1]; n = int(c4[1:3]) if c4[1:3].isdigit() else -1
    if c1 == "X" and n >= 85 or c1 == "Y" and n <= 9: return "assault_all"
    if c1 == "Y" and 10 <= n <= 34: return "undet_all"
    if c1 == "Y" and n in (35, 36): return "legal_war"
    if c1 == "R": return "illdefined"
    return "other_ext" if c1 in "VWXY" else "natural"
T["cat"] = T.c4.map(cat)
Tc = T.groupby(["year", "cat"]).n.sum().unstack(fill_value=0).reindex(Y)
Tc["violent_Y36"] = Tc.assault_all + Tc.undet_all + Tc.legal_war
Tc["all"] = Tc.sum(axis=1) - Tc.violent_Y36
y35all = go.Y35; Tc["Y35"] = y35all
print("\nGOIAS, all causes by category (residence)\n", Tc); out["go_cat"] = Tc.to_dict("index")
fb_mvi = {2012: 2588, 2013: 2774, 2014: 2851, 2015: 3054, 2016: 3014, 2017: 2676, 2018: 2616, 2019: 2251, 2020: 2167, 2021: 1881}
Tc["FBSP_MVI"] = pd.Series(fb_mvi); Tc["SIM_violent/MVI"] = (Tc.violent_Y36 / Tc.FBSP_MVI).round(3)
print(Tc[["violent_Y36", "assault_all", "undet_all", "legal_war", "illdefined", "FBSP_MVI", "SIM_violent/MVI"]])
# ---------------------------------------------------------------- D. SIM vs FBSP
rows = []
for y in range(2015, 2022):
    f = fb["GO"][str(y)]; rows.append({"year": y, "SIM_Y35_res": int(go.Y35[y]), "SIM_Y35_occ": int(go_oc.Y35[y]), "SIM_Y35+assault_excess": None,
        "FBSP_first": f["first"], "FBSP_latest": f["latest"], "ratio_res": round(go.Y35[y] / f["latest"], 3), "ratio_occ": round(go_oc.Y35[y] / f["latest"], 3)})
R = pd.DataFrame(rows).drop(columns="SIM_Y35+assault_excess"); print("\nSIM Y35 / FBSP, Goias\n", R); out["go_ratio"] = R.to_dict("records")
rb = []
for y in range(2015, 2022):
    f = fb["BR"][str(y)]; rb.append({"year": y, "SIM_Y35": int(br.Y35[y]), "FBSP_latest": f["latest"], "ratio": round(br.Y35[y] / f["latest"], 3)})
RB = pd.DataFrame(rb); print("\nSIM Y35 / FBSP, Brazil\n", RB); out["br_ratio"] = RB.to_dict("records")
print("\nSIM Y35 + (FBSP-free) : does Goias SIM Y35 follow FBSP direction? corr(2015-2021) =", round(np.corrcoef(R.SIM_Y35_res, R.FBSP_latest)[0, 1], 3),
      " spearman", round(stats.spearmanr(R.SIM_Y35_res, R.FBSP_latest)[0], 3), " | FBSP rise 2015->2020 %+d ; SIM Y35 rise %+d" % (631 - 141, go.Y35[2020] - go.Y35[2015]))

# ---------------------------------------------------------------- E. which labels are right? CIRCOBITO and LOCOCOR against the cause (Brazil, all years)
sim["fam"] = sim.g.map({"assault": "X93-95 assault", "undet": "Y22-24 undetermined", "suicide": "X72-74 suicide", "accident": "W32-34 accident", "Y350": "Y35 legal", "Y35other": "Y35 legal"})
for c in ("CIRCOBITO", "LOCOCOR"):
    ct = pd.crosstab(sim.fam, sim[c].fillna("NA"), normalize="index").round(3)
    print(f"\n{c} (raw code) by cause family, Brazil 2012-21, row shares\n", ct)
    out[f"xtab_{c}"] = ct.to_dict("index")
# ---------------------------------------------------------------- F. certifier, by year, Goias and Brazil
sim["per"] = pd.cut(sim.year, [2011, 2015, 2016, 2018, 2019, 2021], labels=["2012-15", "2016", "2017-18", "2019", "2020-21"])
def share(df, col, by, keep=None):
    t = pd.crosstab(df[by], df[col].fillna("(blank)"), normalize="index").round(3)
    n = df.groupby(by).size(); t.insert(0, "n", n); return t
fam3 = {"Y35 legal": "Y35", "X93-95 assault": "X93-95", "Y22-24 undetermined": "Y22-24"}
for scope, df in (("GOIAS", sim[sim.uf_res == "52"]), ("BRAZIL ex GO", sim[sim.uf_res != "52"])):
    d = df[df.fam.isin(fam3)].copy(); d["fam3"] = d.fam.map(fam3)
    for col, title in (("ATESTANTE_label", "ATESTANTE (certifier)"),):
        for f in ("Y35", "X93-95", "Y22-24"):
            t = share(d[d.fam3 == f], col, "year"); print(f"\n{scope} {title}, {f}, row shares by year\n", t)
            out[f"cert_{scope}_{f}"] = t.to_dict("index")
d = sim[(sim.uf_res == "52") & sim.fam.isin(fam3)].copy(); d["fam3"] = d.fam.map(fam3)
d["P"] = d.per
for col in ("ATESTANTE_label", "CIRCOBITO_label", "FONTE_label", "TPPOS_label", "NECROPSIA_label", "LOCOCOR_label"):
    for f in ("Y35", "X93-95", "Y22-24"):
        t = share(d[d.fam3 == f], col, "P"); print(f"\nGOIAS {col}, {f}, by period (translate labels)\n", t)
        out[f"go_{col}_{f}"] = t.to_dict("index")
# IML share of the whole assault family in Goias by year, with UF context
im = sim[sim.fam.isin(["X93-95 assault", "Y22-24 undetermined", "Y35 legal"])].assign(iml=lambda x: x.ATESTANTE.eq("3"), svo=lambda x: x.ATESTANTE.eq("4"))
print("\nShare certified by IML (ATESTANTE=3) among X93-95+Y22-24+Y35, by year: GO vs Brazil ex GO")
print(pd.DataFrame({"GO": im[im.uf_res == "52"].groupby("year").iml.mean(), "exGO": im[im.uf_res != "52"].groupby("year").iml.mean()}).round(3))
# ---------------------------------------------------------------- G. victims' profiles
def prof(df):
    a = df.age.astype(float)
    known = df.RACACOR_label.notna()
    return pd.Series({"n": len(df), "male": (df.SEXO_label == "M").mean(), "age_median": a.median(), "age_12_29": ((a >= 12) & (a < 30)).mean(),
                      "age_30plus": (a >= 30).mean(), "negro(pret+parda)/known": df.RACACOR_label.isin(["Preta", "Parda"])[known].mean(),
                      "hospital": (df.LOCOCOR == "1").mean(), "loc4": (df.LOCOCOR == "4").mean(), "loc3": (df.LOCOCOR == "3").mean(), "loc2": (df.LOCOCOR == "2").mean(), "loc5": (df.LOCOCOR == "5").mean(),
                      "svo/iml_cert": df.ATESTANTE.isin(["3", "4"]).mean(), "attending(1)": df.ATESTANTE.eq("1").mean()})
d = sim[(sim.uf_res == "52") & sim.fam.isin(fam3)].copy(); d["fam3"] = d.fam.map(fam3)
d["P"] = pd.cut(d.year, [2011, 2015, 2018, 2021], labels=["2012-15", "2016-18", "2019-21"])
PR = d.groupby(["fam3", "P"], observed=True).apply(prof).round(3); print("\nPROFILES, Goias\n", PR); out["profiles_go"] = {f"{a}|{b}": v for (a, b), v in PR.to_dict("index").items()}
PRb = sim[(sim.uf_res != "52") & sim.fam.isin(fam3)].assign(fam3=lambda x: x.fam.map(fam3), P=lambda x: pd.cut(x.year, [2011, 2015, 2018, 2021], labels=["2012-15", "2016-18", "2019-21"])).groupby(["fam3", "P"], observed=True).apply(prof).round(3)
print("\nPROFILES, Brazil ex GO\n", PRb); out["profiles_exgo"] = {f"{a}|{b}": v for (a, b), v in PRb.to_dict("index").items()}
# distance between Y35 and X93-95 age x sex profiles (same period), total variation, Goias
d["ageb"] = pd.cut(d.age.astype(float), [-1, 11, 17, 24, 29, 39, 49, 200], labels=["0-11", "12-17", "18-24", "25-29", "30-39", "40-49", "50+"])
for P in ("2012-15", "2016-18", "2019-21"):
    x = d[d.P == P]
    pa_ = x[x.fam3 == "Y35"].ageb.value_counts(normalize=True).reindex(d.ageb.cat.categories, fill_value=0)
    pb_ = x[x.fam3 == "X93-95"].ageb.value_counts(normalize=True).reindex(d.ageb.cat.categories, fill_value=0)
    print(P, "TV(age Y35, age X93-95) =", round(0.5 * (pa_ - pb_).abs().sum(), 3), "n Y35", int((x.fam3 == "Y35").sum()))
    if P != "2012-15":
        base = d[(d.P == "2012-15") & (d.fam3 == "X93-95")].ageb.value_counts(normalize=True).reindex(d.ageb.cat.categories, fill_value=0)
        print("    TV(age Y35 this period, age X93-95 baseline 2012-15)=", round(0.5 * (pa_ - base).abs().sum(), 3))
pd.Series(out).to_json(DIR + "results.json", default_handler=str, force_ascii=False)

# ---------------------------------------------------------------- H. decomposition, triangulation with FBSP, the ledger test
F = {y: fb["GO"][str(y)]["latest"] for y in range(2015, 2022)}
ratio_ = {y: go.Y35[y] / F[y] for y in F}
print("\nDECOMPOSITION of the Y35 rise 2015->2020 (Y35 = c * FBSP): c0=%.3f c1=%.3f F0=%d F1=%d" % (ratio_[2015], ratio_[2020], F[2015], F[2020]))
c0, c1, F0, F1 = ratio_[2015], ratio_[2020], F[2015], F[2020]
dec = {"real_only (c0*dF)": c0 * (F1 - F0), "coding_only (F0*dc)": F0 * (c1 - c0), "interaction (dF*dc)": (F1 - F0) * (c1 - c0), "total": go.Y35[2020] - go.Y35[2015]}
print({k: round(v, 1) for k, v in dec.items()}); out["decomposition_2015_2020"] = dec
c0b = ratio_[2016]; decb = {"real_only (c0*dF)": c0b * (F1 - F[2016]), "coding_only (F0*dc)": F[2016] * (c1 - c0b), "interaction": (F1 - F[2016]) * (c1 - c0b), "total": go.Y35[2020] - go.Y35[2016]}
print("from 2016:", {k: round(v, 1) for k, v in decb.items()}); out["decomposition_2016_2020"] = decb
# non-police violent deaths: SIM (assault_all + undet_all) vs FBSP (MVI - MDIP)
np_ = pd.DataFrame({"SIM_nonlegal_violent": Tc.assault_all + Tc.undet_all, "FBSP_MVI": Tc.FBSP_MVI, "FBSP_MDIP": pd.Series({y: F.get(y) for y in Y})})
np_["FBSP_nonpolice"] = np_.FBSP_MVI - np_.FBSP_MDIP; np_["SIM/FBSP_nonpolice"] = (np_.SIM_nonlegal_violent / np_.FBSP_nonpolice).round(3)
print("\nNON-POLICE VIOLENT DEATHS, Goias\n", np_.loc[2015:2021]); out["nonpolice"] = np_.loc[2015:2021].to_dict("index")
print("change 2015->2019: SIM nonlegal violent %.1f%%, FBSP nonpolice %.1f%%; SIM assault+undet firearm %.1f%%" % (
    100 * (np_.SIM_nonlegal_violent[2019] / np_.SIM_nonlegal_violent[2015] - 1), 100 * (np_.FBSP_nonpolice[2019] / np_.FBSP_nonpolice[2015] - 1), 100 * (go["assault+undet"][2019] / go["assault+undet"][2015] - 1)))
# bootstrap: is the 2017-21 deficit of assault+undet (against Goias's 2012-16 share of the rest of Brazil) equal to the Y35 excess?
rng = np.random.default_rng(20261005)
au, ex = go["assault+undet"], rest["assault+undet"]
base = list(range(2012, 2017)); late = list(range(2017, 2022))
D = sum(ratio_cf(au, ex)[y] - au[y] for y in late); E = sum(go.Y35[y] for y in late) - 5 * go.Y35[base].mean()
sims = []
for _ in range(20000):
    b = rng.poisson(au[base].values).sum() / ex[base].sum()
    sims.append(sum(b * ex[y] - rng.poisson(au[y]) for y in late))
sims = np.array(sims); p_eq = 2 * min((sims <= E).mean(), (sims >= E).mean())
print("\nDEFICIT 2017-21 of X93-95+Y22-24 vs national-course counterfactual D=%.0f (bootstrap sd %.0f); Y35 excess E=%.0f; D/E=%.2f; P(D<=E) = %.4f, two-sided p(D=E) = %.4f" % (D, sims.std(), E, D / E, (sims <= E).mean(), p_eq))
out["deficit_test"] = {"D": D, "E": E, "sd": sims.std(), "p_two_sided": p_eq, "share_explainable_by_recode_max": E / D}
# the pooled firearm count: Goias against the rest of Brazil
pf = go.pooled_decl; pr = rest.pooled_decl
r0 = pf[base].sum() / pr[base].sum()
Dp = sum(r0 * pr[y] - pf[y] for y in [2017, 2018, 2019]); print("pooled_decl 2017-19: observed %d expected %.0f (deficit %.0f, share of rest-of-Brazil %.4f -> %.4f)" % (pf[[2017, 2018, 2019]].sum(), sum(r0 * pr[y] for y in [2017, 2018, 2019]), Dp, r0, pf[[2017, 2018, 2019]].sum() / pr[[2017, 2018, 2019]].sum()))
pd.Series(out).to_json(DIR + "results.json", default_handler=str, force_ascii=False)
