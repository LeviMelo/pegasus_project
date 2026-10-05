"""Y35 Goiás test (ledger 3d787b765f614065), step 1: SIM.DO 2012-2021 (never 2024), Brazil, firearm-related rows
(W32-W34, X72-X74, X93-X95, Y22-Y24, Y35) with explicit select list -> data/y35_goias/sim_firearm.parquet;
plus the death count by (UF of residence, 4-character cause) and year, all causes -> sim_totals.parquet."""
import warnings, pyarrow as pa, pyarrow.parquet as pq, pyarrow.compute as pc, os
warnings.simplefilter("ignore")
import pegasus_data as pg
from pegasus_core import config
os.makedirs("data/y35_goias", exist_ok=True)
COLS = ["CAUSABAS", "CAUSABAS_O", "ATESTANTE", "CIRCOBITO", "FONTE", "LOCOCOR", "IDADE", "SEXO", "RACACOR", "CODMUNRES",
        "CODMUNOCOR", "TIPOBITO", "NECROPSIA", "ASSISTMED", "FONTEINV", "TPPOS", "DTOBITO", "COMUNSVOIM", "ESC", "ACIDTRAB", "TPNIVELINV", "DTCADASTRO", "ATESTADO"]
PFX = ("W32", "W33", "W34", "X72", "X73", "X74", "X93", "X94", "X95", "Y22", "Y23", "Y24", "Y35")
out, tot = [], []
for y in range(2012, 2022):
    t = pg.query("SIM_DO", period=y, geography="BR", select=[c for c in COLS if y >= 2014 or c not in ("ATESTADO", "TPNIVELINV")], present="codes", root=config.data_root(), max_download=8 * 1024**3)
    print(y, t.num_rows, [c for c in COLS if c not in t.column_names], flush=True)
    c3 = pc.utf8_slice_codeunits(pc.cast(t["CAUSABAS"], pa.string()), 0, 3)
    uf = pc.utf8_slice_codeunits(pc.cast(t["CODMUNRES"], pa.string()), 0, 2)
    import duckdb; con = duckdb.connect()
    con.register("u", pa.table({"uf": uf, "c4": pc.utf8_slice_codeunits(pc.cast(t["CAUSABAS"], pa.string()), 0, 4)}))
    r = con.execute("select uf, c4, count(*) n from u group by all").fetch_arrow_table()
    tot.append(r.append_column("year", pa.array([y] * r.num_rows, pa.int16())))
    m = pc.is_in(c3, value_set=pa.array(PFX))
    f = t.filter(m).append_column("year", pa.array([y] * int(pc.sum(m).as_py()), pa.int16()))
    out.append(f)
pq.write_table(pa.concat_tables(out, promote_options="default"), "data/y35_goias/sim_firearm.parquet")
pq.write_table(pa.concat_tables(tot), "data/y35_goias/sim_totals.parquet")
print("done")
