"""Code meanings through pegasus_data.translate (never guessed): the SIM.DO codelists of ATESTANTE, LOCOCOR, CIRCOBITO, FONTE,
RACACOR, TPPOS, FONTEINV, TPNIVELINV, NECROPSIA, ASSISTMED, and the ICD-10 firearm codes. -> data/y35_goias/labels.json"""
import warnings, json, pyarrow as pa
warnings.simplefilter("ignore")
import pegasus_data as pg
from pegasus_core import config
cols = {"ATESTANTE": list("12345") + ["9"], "LOCOCOR": list("123456") + ["9"], "CIRCOBITO": list("1234") + ["9"], "FONTE": list("1234") + ["9"],
        "RACACOR": list("12345"), "TPPOS": ["N", "S"], "FONTEINV": list("12345"), "TPNIVELINV": ["M", "E", "S"], "NECROPSIA": ["1", "2", "9"], "ASSISTMED": ["1", "2", "9"],
        "CAUSABAS": ["Y350", "Y351", "Y352", "Y353", "Y354", "Y355", "Y356", "Y357", "Y358", "Y359", "X950", "X954", "Y240", "X930", "W330", "X720", "X940", "Y220", "Y229"]}
n = max(len(v) for v in cols.values())
tab = pa.table({k: pa.array(v + [None] * (n - len(v)), pa.string()) for k, v in cols.items()})
res, rep = pg.translate(tab, system="SIM", series="DO", year=2018, report=True, root=config.data_root(), render={k: "label" for k in cols} if False else None)
d = res.to_pylist()
print(res.column_names)
for k in cols:
    names = [c for c in res.column_names if c.startswith(k)]
    print(k, names)
    for r in d[:len(cols[k])]:
        print("   ", {c: r[c] for c in names})
print(rep)
