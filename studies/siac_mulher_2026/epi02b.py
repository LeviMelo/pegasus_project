"""EPI-02, refinements: CVD mentions without modes of dying; early vs late puerperium; region, race, age."""
import json
import warnings
from pathlib import Path

import duckdb

import pegasus_data as pd

warnings.simplefilter("ignore")
OUT = Path(__file__).parent / "results"
cols = ["DTOBITO", "SEXO", "IDADE", "RACACOR", "CAUSABAS", "CAUSABAS_O", "OBITOGRAV", "OBITOPUERP",
        "LINHAA", "LINHAB", "LINHAC", "LINHAD", "LINHAII", "CODMUNRES", "TPNIVELINV", "FONTEINV"]
t = pd.query("SIM-DO", period=("2014", "2023"), geography="BR", select=cols, present="codes", allow_partial=True,
             max_download=2 * 1024**3)
con = duckdb.connect()
con.register("t", t)
MAT = "(regexp_matches({c}, '^O(0[0-9]|[1-8][0-9]|9[0-5]|9[89])') OR regexp_matches({c}, '^(A34|F53|M830|D392|E230)'))"
CVD = "regexp_matches({c}, '^(O994|O903|O223|O225|O871|O873|O882)')"
# a cardiovascular mention: I00-I99 except modes of dying (I46 cardiac arrest, I95 hypotension, I99 other)
# and the pregnancy-coded circulatory codes above
LINES_CVD = "regexp_matches(linhas, '\\*(I(0[0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-5]|4[7-9]|[5-8][0-9]|9[0-4]|9[6-8])|O994|O903|O223|O225|O871|O873|O882)')"
con.execute(f"""CREATE TABLE m AS SELECT *, CAST(substr(DTOBITO,5,4) AS INT) ano, trim(CAUSABAS) cb, trim(CAUSABAS_O) cbo,
    coalesce(LINHAA,'')||coalesce(LINHAB,'')||coalesce(LINHAC,'')||coalesce(LINHAD,'')||coalesce(LINHAII,'') linhas
    FROM t WHERE SEXO = '2'""")
con.execute(f"""CREATE TABLE k AS SELECT *, {MAT.format(c='cb')} mat, coalesce({MAT.format(c='cbo')}, false) mat_o,
    {CVD.format(c='cb')} cvd, coalesce({CVD.format(c='cbo')}, false) cvd_o, {LINES_CVD} cvd_lines,
    regexp_matches(coalesce(cbo,''), '^I') circ_o FROM m WHERE ano BETWEEN 2014 AND 2023""")
res = {}
q = lambda s: con.execute(s).fetchall()  # noqa: E731
res["maternal_noncvd_with_cvd_lines_refined"] = q("SELECT count(*) FILTER (WHERE cvd_lines), count(*) FROM k WHERE mat AND NOT cvd")[0]
res["maternal_all_with_cvd_anywhere"] = q("SELECT count(*) FILTER (WHERE cvd OR cvd_lines), count(*) FROM k WHERE mat")[0]
res["preg_puerp_I_underlying_not_maternal_by_period"] = q("""SELECT OBITOGRAV, OBITOPUERP, count(*) FROM k
    WHERE NOT mat AND regexp_matches(cb,'^I') AND (OBITOGRAV='1' OR OBITOPUERP IN ('1','2')) GROUP BY 1,2 ORDER BY 3 DESC""")
res["cvd_final_origin"] = q("""SELECT CASE WHEN cvd_o THEN 'cvd originally' WHEN circ_o THEN 'non-maternal circulatory (I) originally'
    WHEN mat_o THEN 'other maternal originally' WHEN cbo IS NULL OR cbo='' THEN 'no original' ELSE 'other non-maternal originally' END, count(*)
    FROM k WHERE cvd GROUP BY 1 ORDER BY 2 DESC""")
res["cvd_by_region"] = q("""SELECT substr(CODMUNRES,1,1) reg, count(*) FILTER (WHERE cvd), count(*) FILTER (WHERE mat),
    count(*) FILTER (WHERE cvd AND NOT cvd_o) FROM k WHERE mat GROUP BY 1 ORDER BY 1""")
res["cvd_by_race"] = q("""SELECT RACACOR, count(*) FILTER (WHERE cvd), count(*) FILTER (WHERE mat) FROM k WHERE mat GROUP BY 1 ORDER BY 1""")
res["age_median_cvd_vs_other"] = q("""SELECT cvd, median(try_cast(substr(IDADE,2,2) AS INT)) FROM k
    WHERE mat AND substr(IDADE,1,1)='4' GROUP BY 1""")
res["investigation_level_filled_maternal"] = q("SELECT TPNIVELINV, count(*) FROM k WHERE mat GROUP BY 1 ORDER BY 2 DESC")
res["revealed_share_by_period"] = q("""SELECT CASE WHEN ano<=2019 THEN '2014-2019' WHEN ano<=2021 THEN '2020-2021' ELSE '2022-2023' END p,
    count(*) FILTER (WHERE cvd), count(*) FILTER (WHERE cvd AND NOT cvd_o), count(*) FILTER (WHERE mat), count(*) FILTER (WHERE mat AND NOT mat_o)
    FROM k WHERE mat GROUP BY 1 ORDER BY 1""")
(OUT / "epi02b_results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps(res, indent=1, ensure_ascii=False, default=str))
