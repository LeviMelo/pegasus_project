"""Y35 Goiás test (ledger 3d787b765f614065), step 2: SIH-RD, hospital UF = GO, competence years 2012-2022, admissions
(IDENT=1) carrying a firearm external-cause code (W32-W34, X72-X74, X93-X95, Y22-Y24, Y35) in any diagnosis field
(DIAG_PRINC, DIAGSEC1-9, CID_ASSO, CID_MORTE; DIAG_SECUN is dead from 2014 and absent before?) -> data/y35_goias/sih_firearm.parquet."""
import sys, warnings, os, pyarrow as pa, pyarrow.parquet as pq, pyarrow.compute as pc
warnings.simplefilter("ignore")
import pegasus_data as pg
from pegasus_core import config
os.makedirs("data/y35_goias", exist_ok=True)
DIAG = ["DIAG_PRINC", "DIAG_SECUN", "DIAGSEC1", "DIAGSEC2", "DIAGSEC3", "DIAGSEC4", "DIAGSEC5", "DIAGSEC6", "DIAGSEC7", "DIAGSEC8", "DIAGSEC9", "CID_ASSO", "CID_MORTE"]
COLS = DIAG + ["IDENT", "DT_INTER", "ANO_CMPT", "SEXO", "IDADE", "COD_IDADE", "RACA_COR", "MUNIC_RES", "MUNIC_MOV", "MORTE", "PROC_REA"]
PFX = ("W32", "W33", "W34", "X72", "X73", "X74", "X93", "X94", "X95", "Y22", "Y23", "Y24", "Y35")
out = []
YEARS = [int(a) for a in sys.argv[1:]] or list(range(2012, 2023))
for y in YEARS:
    sel = list(COLS)
    while True:                      # drop the columns the year's schema generation does not carry (MissingColumnError names them)
        try:
            t = pg.query("SIHSUS_RD", period=y, geography="GO", select=sel, present="codes", root=config.data_root(), max_download=8 * 1024**3)
            break
        except pg.MissingColumnError as e:
            import re
            gone = re.findall(r"column '(\w+)'", str(e)) + [x.strip() for g in re.findall(r"also absent: ([^)]*)\)", str(e)) for x in g.split(",")]
            assert gone and all(g in sel for g in gone), str(e)
            sel = [c for c in sel if c not in gone]
    print("  columns used:", sel, flush=True)
    have = [c for c in DIAG if c in t.column_names]
    print(y, t.num_rows, "missing:", [c for c in COLS if c not in t.column_names], flush=True)
    if "IDENT" in t.column_names:
        t = t.filter(pc.equal(pc.cast(t["IDENT"], pa.string()), "1"))
    m = None
    for c in have:
        x = pc.is_in(pc.utf8_slice_codeunits(pc.fill_null(pc.cast(t[c], pa.string()), ""), 0, 3), value_set=pa.array(PFX))
        m = x if m is None else pc.or_(m, x)
    f = t.filter(m)
    out.append(f.append_column("cmpt_year", pa.array([y] * f.num_rows, pa.int16())))
    print("  firearm admissions:", f.num_rows, flush=True)
pq.write_table(pa.concat_tables(out, promote_options="default"), "data/y35_goias/sih_firearm" + ("" if len(YEARS) > 1 else f"_{YEARS[0]}") + ".parquet")
import psutil; print("peak RSS GB:", psutil.Process().memory_info().peak_wset / 1024**3)
print("done")
