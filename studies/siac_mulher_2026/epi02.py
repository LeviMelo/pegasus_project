"""EPI-02: cardiovascular maternal deaths before and after investigation (SIM-DO 2014-2023)."""
import json
import warnings
from pathlib import Path

import duckdb

import pegasus_data as pd

warnings.simplefilter("ignore")
OUT = Path(__file__).parent
cols = ["DTOBITO", "SEXO", "IDADE", "RACACOR", "CAUSABAS", "CAUSABAS_O", "ALTCAUSA", "OBITOGRAV", "OBITOPUERP",
        "TPMORTEOCO", "LINHAA", "LINHAB", "LINHAC", "LINHAD", "LINHAII", "CODMUNRES", "FONTEINV", "TPNIVELINV"]
t = pd.query("SIM-DO", period=("2014", "2023"), geography="BR", select=cols, present="codes", allow_partial=True, max_download=2 * 1024**3)
con = duckdb.connect()
con.register("t", t)
con.execute("""CREATE TABLE d AS SELECT *, CAST(substr(DTOBITO, 5, 4) AS INT) AS ano,
    trim(CAUSABAS) AS cb, trim(CAUSABAS_O) AS cbo,
    coalesce(LINHAA,'') || coalesce(LINHAB,'') || coalesce(LINHAC,'') || coalesce(LINHAD,'') || coalesce(LINHAII,'') AS linhas
    FROM t WHERE SEXO = '2'""")

MATERNAL = "(regexp_matches({c}, '^O(0[0-9]|[1-8][0-9]|9[0-5]|9[89])') OR regexp_matches({c}, '^(A34|F53|M830|D392|E230)'))"
CVD = "regexp_matches({c}, '^(O994|O903|O223|O225|O871|O873|O882)')"          # structural/vascular, pregnancy-coded
HDP = "regexp_matches({c}, '^O1[0-6]')"
ANYCVD_LINES = "regexp_matches(linhas, '(\\*I[0-9]|\\*O994|\\*O903|\\*O223|\\*O225|\\*O871|\\*O873|\\*O882)')"


def cat(c):
    return f"""CASE WHEN {c} IS NULL OR {c} = '' THEN 'sem registro'
        WHEN {CVD.format(c=c)} THEN 'cardiovascular'
        WHEN {HDP.format(c=c)} THEN 'hipertensiva'
        WHEN {MATERNAL.format(c=c)} THEN 'materna, outra'
        WHEN regexp_matches({c}, '^I') THEN 'circulatória não materna (I00-I99)'
        ELSE 'não materna, outra' END"""


con.execute(f"""CREATE TABLE m AS SELECT *, {cat('cb')} AS final, {cat('cbo')} AS original,
    {MATERNAL.format(c='cb')} AS mat_final,
    coalesce({MATERNAL.format(c='cbo')}, false) AS mat_orig,
    {ANYCVD_LINES} AS cvd_linhas
    FROM d WHERE ano BETWEEN 2014 AND 2023""")
res = {}
res["deaths_women"] = con.execute("SELECT count(*) FROM m").fetchone()[0]
res["maternal_final"] = con.execute("SELECT count(*) FROM m WHERE mat_final").fetchone()[0]
res["maternal_final_by_year"] = dict(con.execute("SELECT ano, count(*) FROM m WHERE mat_final GROUP BY 1 ORDER BY 1").fetchall())
res["causabas_o_filled_in_maternal"] = con.execute("SELECT avg((cbo IS NOT NULL AND cbo <> '')::INT) FROM m WHERE mat_final").fetchone()[0]
res["changed_in_maternal"] = con.execute("SELECT avg((cbo IS NOT NULL AND cbo <> '' AND cbo <> cb)::INT) FROM m WHERE mat_final").fetchone()[0]
res["entered_maternal_after_investigation"] = con.execute("SELECT count(*) FROM m WHERE mat_final AND cbo IS NOT NULL AND cbo <> '' AND NOT mat_orig").fetchone()[0]
res["left_maternal_after_investigation"] = con.execute("SELECT count(*) FROM m WHERE NOT mat_final AND mat_orig").fetchone()[0]
res["transition_original_to_final_maternal_or_cvd"] = [
    list(r) for r in con.execute("""SELECT original, final, count(*) FROM m
        WHERE mat_final OR mat_orig OR final='cardiovascular' OR original='cardiovascular'
        GROUP BY 1,2 ORDER BY 3 DESC""").fetchall()]
res["cvd_final"] = con.execute("SELECT count(*) FROM m WHERE final='cardiovascular'").fetchone()[0]
res["cvd_original"] = con.execute("SELECT count(*) FROM m WHERE original='cardiovascular'").fetchone()[0]
res["cvd_revealed"] = con.execute("SELECT count(*) FROM m WHERE final='cardiovascular' AND original <> 'cardiovascular' AND original <> 'sem registro'").fetchone()[0]
res["cvd_removed"] = con.execute("SELECT count(*) FROM m WHERE original='cardiovascular' AND final <> 'cardiovascular'").fetchone()[0]
res["cvd_final_codes"] = [list(r) for r in con.execute("SELECT substr(cb,1,4), count(*) FROM m WHERE final='cardiovascular' GROUP BY 1 ORDER BY 2 DESC").fetchall()]
res["maternal_noncvd_with_cvd_in_lines"] = con.execute("SELECT count(*) FROM m WHERE mat_final AND final <> 'cardiovascular' AND cvd_linhas").fetchone()[0]
res["maternal_noncvd"] = con.execute("SELECT count(*) FROM m WHERE mat_final AND final <> 'cardiovascular'").fetchone()[0]
# pregnant/puerperal women whose underlying cause is circulatory but not coded maternal
res["pregnant_puerperal_underlying_I_not_maternal"] = con.execute("""SELECT count(*) FROM m
    WHERE NOT mat_final AND regexp_matches(cb, '^I') AND (OBITOGRAV = '1' OR OBITOPUERP IN ('1','2'))""").fetchone()[0]
res["cvd_share_final_by_year"] = [list(r) for r in con.execute("""SELECT ano, count(*) FILTER (WHERE final='cardiovascular'),
    count(*) FROM m WHERE mat_final GROUP BY 1 ORDER BY 1""").fetchall()]
(OUT / "epi02_results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps({k: v for k, v in res.items() if not isinstance(v, list)}, indent=1, ensure_ascii=False, default=str))
