"""EPI-01: maternal heart disease phenotypes and maternal/neonatal outcomes, SIH-SINASC linked births, Brazil 2022.

Pairs: pegasus_data deterministic link sinasc_births_to_delivery_admission (BR 2022; 1,515,701 births,
0.53% chance pairs). SIH read state by state and kept only where linked.
"""
import json
import warnings
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

import pegasus_data as pd

warnings.simplefilter("ignore")
OUT = Path(__file__).parent
PAIRS = Path(r"C:\Users\Galaxy\LEVI\projects\pegasus_data\data\probes\linkage\national"
             r"\sinasc_births_to_delivery_admission_deterministic_BR_2022.parquet")
UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
DX = ["DIAG_PRINC", "DIAG_SECUN"] + [f"DIAGSEC{i}" for i in range(1, 10)]


def ids(t):
    return pc.binary_join_element_wise(pc.cast(t["_blob_sha256"], pa.string()), pc.cast(t["_row"], pa.string()), ":")


pairs = pq.read_table(PAIRS).select(["l", "r"])
con = duckdb.connect()
con.register("pairs", pairs)
CACHE = OUT / "epi01_births.parquet"
sih_parts, sn_parts = [], []
for uf in ([] if CACHE.exists() else UFS):
    s = pd.query("SIH-RD", period="2022", geography=uf, select=DX + ["IDADE", "COD_IDADE", "MORTE", "UTI_MES_TO",
                 "MARCA_UTI", "DIAS_PERM", "CNES", "MUNIC_RES", "MUNIC_MOV", "PROC_REA"],
                 present="codes", provenance="all", allow_partial=True)
    s = s.append_column("rid", ids(s)).drop_columns([c for c in s.column_names if c.startswith("_")])
    con.register("s", s)
    sih_parts.append(con.execute("SELECT s.* FROM s WHERE rid IN (SELECT r FROM pairs)").fetch_arrow_table())
    con.unregister("s")
    print(uf, "sih", sih_parts[-1].num_rows, flush=True)
if CACHE.exists():
    con.execute(f"CREATE TABLE b AS SELECT * FROM read_parquet('{CACHE.as_posix()}')")
else:
  sih = pa.concat_tables(sih_parts, promote_options="default")
  sn = pd.query("SINASC-DN", period="2022", geography="BR", select=["SEMAGESTAC", "PESO", "APGAR5", "IDANOMAL", "PARTO",
                "GRAVIDEZ", "IDADEMAE", "RACACORMAE", "ESCMAE2010", "CODMUNRES"], present="codes", provenance="all",
                allow_partial=True)
  sn = sn.append_column("lid", ids(sn)).drop_columns([c for c in sn.column_names if c.startswith("_")])
  con.register("sih", sih)
  con.register("sn", sn)
  alldx = " || ' ' || ".join(f"coalesce({c},'')" for c in DX)
  con.execute(f"""CREATE TABLE b AS SELECT p.l, p.r, {alldx} AS dx, s.MORTE, try_cast(s.UTI_MES_TO AS INT) AS uti_dias,
      try_cast(s.DIAS_PERM AS INT) AS los, s.CNES, s.MUNIC_RES, s.MUNIC_MOV,
      try_cast(n.SEMAGESTAC AS INT) AS sem, try_cast(n.PESO AS INT) AS peso, try_cast(n.APGAR5 AS INT) AS apgar5,
      n.IDANOMAL, n.PARTO, n.GRAVIDEZ, try_cast(n.IDADEMAE AS INT) AS idademae, n.RACACORMAE
      FROM pairs p JOIN sih s ON s.rid = p.r JOIN sn n ON n.lid = p.l""")
  con.execute(f"COPY b TO '{CACHE.as_posix()}' (FORMAT parquet)")
PHEN = {
    "valvopatia": "I0[5-9]|I3[4-9]",
    "cardiopatia congênita": "Q2[0-8]",
    "cardiomiopatia/IC (inclui O90.3)": "I42|I50|O903",
    "hipertensão pulmonar": "I27",
    "arritmia": "I4[7-9]",
    "doença isquêmica": "I2[0-5]",
    "aortopatia": "I71",
    "O99.4 sem outro código cardíaco": None,
}
anycard = "|".join(v for v in PHEN.values() if v)
con.execute(f"""CREATE TABLE c AS SELECT *,
    regexp_matches(dx, '(^| )({anycard})') AS card_specific,
    regexp_matches(dx, '(^| )O994') AS o994,
    regexp_matches(dx, '(^| )O1[0-6]') AS hdp,
    (MORTE = '1') AS obito, (coalesce(uti_dias,0) > 0) AS uti,
    (sem < 37) AS prematuro, (peso < 2500) AS bpn, (apgar5 < 7) AS apgar_baixo, (IDANOMAL = '1') AS anomalia
    FROM b""")
con.execute("CREATE TABLE c2 AS SELECT *, (card_specific OR o994) AS cardiopatia FROM c")
res = {"linked_births": con.execute("SELECT count(*) FROM c2").fetchone()[0],
       "linked_admissions": con.execute("SELECT count(DISTINCT r) FROM c2").fetchone()[0]}
OUTS = ["obito", "uti", "prematuro", "bpn", "apgar_baixo", "anomalia"]


def summary(where):
    row = con.execute(f"""SELECT count(*), count(DISTINCT r), {", ".join(f"avg({o}::DOUBLE)" for o in OUTS)},
        {", ".join(f"count({o})" for o in OUTS)}, median(los) FROM c2 WHERE {where}""").fetchone()
    n, nadm = row[0], row[1]
    rates = dict(zip(OUTS, row[2:8]))
    counts = dict(zip(OUTS, row[8:14]))
    return {"births": n, "admissions": nadm, "rates": rates, "n_nonnull": counts, "los_median": row[14]}


res["no_heart_disease"] = summary("NOT cardiopatia")
res["any_heart_disease"] = summary("cardiopatia")
res["hdp_without_heart"] = summary("hdp AND NOT cardiopatia")
res["phenotypes"] = {}
for name, rx in PHEN.items():
    where = f"regexp_matches(dx, '(^| )({rx})')" if rx else "o994 AND NOT card_specific"
    res["phenotypes"][name] = summary(where)
# Poisson regression (robust) for any heart disease vs none, adjusted for maternal age group, HDP, twin, region
import numpy as np  # noqa: E402
import statsmodels.api as sm  # noqa: E402

df = con.execute("""SELECT cardiopatia::INT AS card, hdp::INT AS hdp, (GRAVIDEZ IN ('2','3'))::INT AS multipla,
    CASE WHEN idademae < 20 THEN 'lt20' WHEN idademae < 35 THEN '20_34' ELSE 'ge35' END AS idade,
    substr(MUNIC_RES, 1, 1) AS regiao, obito::INT AS obito, uti::INT AS uti, prematuro::INT AS prematuro,
    bpn::INT AS bpn, apgar_baixo::INT AS apgar_baixo FROM c2 WHERE idademae IS NOT NULL""").df()
X = pd_dummies = None
import pandas  # noqa: E402

X = pandas.get_dummies(df[["idade", "regiao"]], drop_first=True).astype(float)
X["card"] = df["card"].astype("float64")
X["hdp"] = df["hdp"].astype("float64")
X["multipla"] = df["multipla"].astype("float64")
X = sm.add_constant(X)
res["adjusted_rr_any_heart_disease"] = {}
for o in ["obito", "uti", "prematuro", "bpn", "apgar_baixo"]:
    y = df[o].astype("float64")
    ok = y.notna() & X.notna().all(axis=1)
    m = sm.GLM(y[ok].to_numpy(), X[ok].astype("float64"), family=sm.families.Poisson()).fit(cov_type="HC1")
    b, se = m.params["card"], m.bse["card"]
    res["adjusted_rr_any_heart_disease"][o] = [float(np.exp(b)), float(np.exp(b - 1.96 * se)), float(np.exp(b + 1.96 * se))]
    print(o, res["adjusted_rr_any_heart_disease"][o], flush=True)
(OUT / "epi01_results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps({k: res[k] for k in ["linked_births", "linked_admissions", "any_heart_disease", "no_heart_disease"]},
                 indent=1, ensure_ascii=False, default=str))
