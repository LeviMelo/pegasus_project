"""EPI-04: where cardio-obstetric admissions happen relative to residence, SIH-RD Brazil 2022."""
import json
import warnings
from importlib.resources import files
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

import pegasus_data as pd

warnings.simplefilter("ignore")
OUT = Path(__file__).parent
UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
DX = ["DIAG_PRINC", "DIAG_SECUN"] + [f"DIAGSEC{i}" for i in range(1, 10)]
CARD = "I0[5-9]|I3[4-9]|Q2[0-8]|I42|I50|O903|I27|I4[7-9]|I2[0-5]|I71|O994"
con = duckdb.connect()
parts = []
for uf in UFS:
    s = pd.query("SIH-RD", period="2022", geography=uf, select=DX + ["MUNIC_RES", "MUNIC_MOV", "CNES", "MORTE",
                 "UTI_MES_TO", "IDENT", "N_AIH"], present="codes", allow_partial=True)
    con.register("s", s)
    alldx = " || ' ' || ".join(f"coalesce({c},'')" for c in DX)
    parts.append(con.execute(f"""SELECT MUNIC_RES, MUNIC_MOV, CNES, MORTE, try_cast(UTI_MES_TO AS INT) AS uti, N_AIH,
        regexp_matches({alldx}, '(^| )({CARD})') AS card
        FROM s WHERE regexp_matches({alldx}, '(^| )O') AND IDENT = '1'""").fetch_arrow_table())
    con.unregister("s")
    print(uf, parts[-1].num_rows, flush=True)
t = pa.concat_tables(parts)
geo = pq.read_table(str(files("pegasus_data.resources") / "geography.parquet"),
                    columns=["municipality", "classification", "member_code", "member_label"]).to_pandas()
hr = geo[geo.classification == "health_region"][["municipality", "member_code"]].rename(columns={"member_code": "hr"})
mun = pq.read_table(str(files("pegasus_data.resources") / "municipalities.parquet"),
                    columns=["code6", "name", "uf_sigla"]).to_pandas()
con.register("t", t)
con.register("hr", hr)
con.register("mun", mun)
con.execute("""CREATE TABLE a AS SELECT t.*, h1.hr AS hr_res, h2.hr AS hr_mov, substr(MUNIC_RES,1,2) AS uf_res, substr(MUNIC_MOV,1,2) AS uf_mov
    FROM t LEFT JOIN hr h1 ON h1.municipality = t.MUNIC_RES LEFT JOIN hr h2 ON h2.municipality = t.MUNIC_MOV""")
res = {}
for label, where in [("cardio_obstetric", "card"), ("other_obstetric", "NOT card")]:
    r = con.execute(f"""SELECT count(*), avg((MUNIC_RES <> MUNIC_MOV)::DOUBLE), avg((hr_res <> hr_mov)::DOUBLE),
        avg((uf_res <> uf_mov)::DOUBLE), avg((MORTE='1')::DOUBLE), avg((coalesce(uti,0)>0)::DOUBLE),
        count(DISTINCT CNES), count(DISTINCT MUNIC_MOV) FROM a WHERE {where}""").fetchone()
    res[label] = dict(zip(["admissions", "outside_municipality", "outside_health_region", "outside_state",
                           "in_hospital_death", "icu", "hospitals", "destination_municipalities"], r))
# concentration: share of cardio-obstetric admissions in top hospitals, HHI of hospitals
r = con.execute("""WITH h AS (SELECT CNES, count(*) n FROM a WHERE card GROUP BY 1), tot AS (SELECT sum(n) s FROM h),
    ranked AS (SELECT n, row_number() OVER (ORDER BY n DESC) k FROM h)
    SELECT (SELECT sum(n) FROM ranked WHERE k <= 50) / (SELECT s FROM tot),
           (SELECT sum(power(n / (SELECT s FROM tot), 2)) FROM h),
           (SELECT count(*) FROM h)""").fetchone()
res["cardio_top50_hospital_share"], res["cardio_hhi_hospitals"], res["cardio_hospitals"] = r
res["cardio_hospitals_needed_for_half"] = con.execute("""WITH h AS (SELECT CNES, count(*) n FROM a WHERE card GROUP BY 1),
    c AS (SELECT n, sum(n) OVER (ORDER BY n DESC ROWS UNBOUNDED PRECEDING) cum, sum(n) OVER () tot FROM h)
    SELECT count(*) FROM c WHERE cum - n < tot / 2""").fetchone()[0]
res["cardio_by_region_outside_hr"] = [list(x) for x in con.execute("""SELECT substr(MUNIC_RES,1,1) reg, count(*),
    avg((hr_res <> hr_mov)::DOUBLE), avg((uf_res <> uf_mov)::DOUBLE) FROM a WHERE card GROUP BY 1 ORDER BY 1""").fetchall()]
res["cardio_top_destinations"] = [list(x) for x in con.execute("""SELECT m.name || ', ' || m.uf_sigla, count(*) n,
    avg((a.MUNIC_RES <> a.MUNIC_MOV)::DOUBLE) FROM a JOIN mun m ON m.code6 = a.MUNIC_MOV WHERE card GROUP BY 1 ORDER BY 2 DESC LIMIT 10""").fetchall()]
(OUT / "epi04_results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps(res, indent=1, ensure_ascii=False, default=str))
