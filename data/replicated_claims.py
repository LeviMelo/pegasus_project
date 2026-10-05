"""Step 2: read the 57 replicated national-trend unit claims (R2, ADR-0015) of the SIM survey <= 2019 against four rival
explanations. Input: the register pegasus_home/leads_T2019 (claims) and data/replicated_claims/*.parquet (step 1).
Output: data/replicated_claims/claims.json and a table on stdout.

Indirect standardisation as the survey: E_t = sum over sex x 18 age bands of the national rate of year t times the unit's
population; O/E over 2010-2019 is fitted by a quasi-Poisson log-linear slope on the standardised year (the lens's beta).
"""
import json, re, warnings
from pathlib import Path
from types import SimpleNamespace
import duckdb, numpy as np, pandas as pd
import statsmodels.api as sm
warnings.simplefilter("ignore")
from pegasus_core import leads, gateway, config
from pegasus_core.tools import kinds_of

D = "data/replicated_claims/"
YEARS = list(range(2010, 2024)); TRAIN = list(range(2010, 2020))
con = duckdb.connect()
con.execute(f"create table ev as select * from '{D}events.parquet'")
con.execute(f"create table pop_popsvs as select * from '{D}pop_popsvs.parquet'")
con.execute(f"create table pop_account3 as select * from '{D}pop_account-3.parquet'")
codes3 = sorted(r[0] for r in con.execute("select distinct c3 from ev").fetchall())
tree = gateway.code_structure("ICD10").to_pandas().set_index("code")


def rng(lo, hi):
    return [c for c in codes3 if lo <= c <= hi]


def cats(node):
    m = re.fullmatch(r"([A-Z]\d\d)-([A-Z]\d\d)", node)
    return rng(*m.groups()) if m else [node]


def block_of(node):
    """The ICD-10 block that holds the node's siblings (the tree's parent is too wide for V and W)."""
    first = cats(node)[0]
    if first[0] == "V":
        return "V01-V99"
    if first[0] == "W" and first <= "W19":
        return "W00-W19"
    if first[0] == "W" and "W75" <= first <= "W84":
        return "W75-W84"
    p = tree.loc[node, "parent"] if node in tree.index else None
    return p if isinstance(p, str) else None


def oe(places, cset, src):
    """O_t and E_t (t in YEARS) for the code set in the unit's places, E from the national rates of the year."""
    pl = ",".join(str(int(u)) for u in places)
    cs = ",".join(f"'{c}'" for c in cset)
    pt = "pop_" + src.replace("-", "")
    q = f"""
    with nat as (select e.year, e.sex, e.band, sum(e.y) y from ev e where e.c3 in ({cs}) group by all),
    npop as (select year, sex, band, sum(n) n from {pt} group by all),
    rate as (select p.year, p.sex, p.band, coalesce(nat.y,0)/p.n r from npop p left join nat using (year, sex, band)),
    up as (select year, sex, band, sum(n) n from {pt} where u in ({pl}) group by all),
    exp_ as (select up.year, sum(up.n*rate.r) E from up join rate using (year, sex, band) group by all),
    obs as (select year, sum(y) O from ev where c3 in ({cs}) and u in ({pl}) group by all)
    select exp_.year, coalesce(O,0) O, E from exp_ left join obs using (year) order by 1"""
    df = con.execute(q).fetchdf()
    return df.O.to_numpy(float), df.E.to_numpy(float)


def slope(O, E, years=TRAIN):
    """Quasi-Poisson log-linear slope of O/E on the standardised years: (beta per sd-year, se, per year)."""
    k = [YEARS.index(y) for y in years]
    o, e = O[k], E[k]
    if o.sum() < 5 or (e <= 0).any():
        return (np.nan, np.nan, np.nan)
    t = np.array(years, float)
    sd = t.std()
    x = sm.add_constant((t - t.mean()) / sd)
    r = sm.GLM(o, x, family=sm.families.Poisson(), offset=np.log(e)).fit(scale="X2")
    return float(r.params[1]), float(r.bse[1]), float(r.params[1] / sd)


def dexcess(O, E):
    """Change in excess deaths (O-E): mean of 2018-19 minus mean of 2010-11, per year, and as a share of E."""
    ex = O - E
    i = {y: YEARS.index(y) for y in YEARS}
    d = ex[[i[2018], i[2019]]].mean() - ex[[i[2010], i[2011]]].mean()
    e = E[[i[2018], i[2019]]].mean()
    return float(d), float(d / e) if e > 0 else np.nan


comp = None


def completeness(uf):
    global comp
    if comp is None:
        from pegasus_data.modelled import read_modelled
        t, _ = read_modelled("system_completeness", "system-completeness-2",
                             settings=SimpleNamespace(lake_dir=Path(config.data_root()) / "lake"))
        comp = t.to_pandas()
        comp = comp[comp.system == "SIM"]
    return comp[comp.uf == uf].set_index("year")


def tot(table, places=None):
    w = "where u in (%s)" % ",".join(str(int(u)) for u in places) if places else ""
    return con.execute(f"select year, sum(n) n from {table} {w} group by 1 order by 1").fetchdf().n.to_numpy()


def run(x):
    node = x.fields[0].split(":")[-1]
    places = x.locus["places"]
    uf = int(x.locus["unit"])
    own = cats(node)
    blk = block_of(node)
    bset = [c for c in cats(blk) if c not in own] if blk and re.fullmatch(r"[A-Z]\d\d-[A-Z]\d\d", blk) else []
    R = rng("R00", "R99")
    out = dict(id=x.id, node=node, uf=uf, block=blk, claim_beta=x.provenance["stats"]["beta"], z=x.effect)
    sets = {"node": own, "sib": bset, "R": [c for c in R if c not in own], "all": codes3,
            "other": [c for c in codes3 if c not in own]}
    res = {src: {nm: oe(places, cs, src) for nm, cs in sets.items() if cs} for src in ("popsvs", "account3")}
    O, E = res["popsvs"]["node"]
    O2, E2 = res["account3"]["node"]
    out["beta_pop"], out["se_pop"], out["yr_pop"] = slope(O, E)
    out["beta_acc"], out["se_acc"], out["yr_acc"] = slope(O2, E2)
    rel = (tot("pop_account3", places) / tot("pop_popsvs", places)) / (tot("pop_account3") / tot("pop_popsvs"))
    out["pop_rel_2010"], out["pop_rel_2019"] = float(rel[0]), float(rel[9])
    for nm in ("sib", "R", "all", "other"):
        if nm in res["popsvs"]:
            Ox, Ex = res["popsvs"][nm]
            out[f"beta_{nm}"] = slope(Ox, Ex)[0]
            out[f"dex_{nm}"], out[f"dexpct_{nm}"] = dexcess(Ox, Ex)
    out["dex_node"], out["dexpct_node"] = dexcess(O, E)
    for nm in ("node", "sib", "R", "all"):
        if nm in res["popsvs"]:
            out["O_" + nm], out["E_" + nm] = res["popsvs"][nm][0].tolist(), res["popsvs"][nm][1].tolist()
    cu = completeness(uf)["completeness"]
    cn = comp.groupby("year").completeness.mean()
    out["comp_unit_2010"], out["comp_unit_2019"] = float(cu[2010]), float(cu[2019])
    out["comp_dlog_rel"] = float(np.log(cu[2019] / cu[2010]) - np.log(cn[2019] / cn[2010]))
    out["comp_basis_2019"] = str(completeness(uf).loc[2019, "basis"])
    p = x.replications["prospective"]
    out["obs_exp_2020_23"] = p["observed"] / p["expected"]
    out["oe_2020_23_mine"] = float(O[10:].sum() / E[10:].sum())
    return out


if __name__ == "__main__":
    reg = leads.Register(Path("pegasus_home/leads_T2019"))
    mine = [x for x in reg.current() if x.estimand == "trend_divergence" and x.locus.get("scale")
            and leads.trend_reference(x) == "national" and kinds_of(x) >= {"temporal", "spatial"}]
    mine.sort(key=lambda x: (x.fields[0], x.locus["unit"]))
    rows = [run(x) for x in mine]
    json.dump(rows, open(D + "claims.json", "w"), indent=1, default=float)
    pd.set_option("display.width", 250)
    df = pd.DataFrame(rows)
    print(df[["node", "uf", "claim_beta", "beta_pop", "beta_acc", "beta_sib", "beta_R", "beta_all", "dex_node", "dex_sib",
              "dex_R", "dex_other", "comp_dlog_rel", "obs_exp_2020_23", "oe_2020_23_mine"]].round(2).to_string())
