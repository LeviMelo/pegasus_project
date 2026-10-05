"""Step 4: counts by year of named ICD-10 category sets in a unit (reads the cached events; nothing else)."""
import sys, duckdb, pandas as pd
con = duckdb.connect(); con.execute("create table ev as select * from 'data/replicated_claims/events.parquet'")
def S(uf, cats):
    cs = ",".join(f"'{c}'" for c in cats)
    d = con.execute(f"select year, sum(y) y from ev where u//10000={uf} and c3 in ({cs}) group by 1 order by 1").fetchdf().set_index("year").y
    return [int(d.get(y, 0)) for y in range(2010, 2024)]
def rg(a, b):
    allc = [r[0] for r in con.execute("select distinct c3 from ev").fetchall()]
    return sorted(c for c in allc if a <= c <= b)
def show(uf, name, cats):
    print(f"{uf} {name:14}", " ".join(f"{v:5d}" for v in S(uf, cats)))
print("years         ", " ".join(f"{y:5d}" for y in range(2010, 2024)))
for c in ("X93", "X94", "X95"): show(50, c, [c])
show(50, "X85-Y09", rg("X85", "Y09")); show(50, "Y10-Y34", rg("Y10", "Y34")); show(50, "R95-R99", rg("R95", "R99")); show(50, "all R", rg("R00", "R99"))
for c in ("X93", "X95", "Y09", "Y35"): show(52, c, [c])
show(52, "X85-Y09", rg("X85", "Y09")); show(52, "Y10-Y34", rg("Y10", "Y34")); show(52, "R95-R99", rg("R95", "R99")); show(52, "R00-R09", rg("R00", "R09")); show(52, "R50-R69", rg("R50", "R69"))
for c in rg("I60", "I69"): show(43, c, [c])
show(43, "R99", ["R99"]); show(43, "R98", ["R98"]); show(43, "R95-R97", rg("R95", "R97")); show(43, "all R", rg("R00", "R99"))
for c in ("I10", "I11", "I12", "I13", "I15"): show(32, c, [c])
for c in rg("W00", "W19"): show(27, c, [c])
for c in rg("R95", "R99"): show(21, c, [c])
show(26, "W18", ["W18"]); show(26, "W19", ["W19"]); show(26, "W00-W19", rg("W00", "W19")); show(26, "S72-fract", ["S72"])
show(23, "all R", rg("R00", "R99")); show(23, "J18", ["J18"]); show(23, "J69", ["J69"]); show(23, "J60-J70", rg("J60", "J70")); show(23, "J12-J18", rg("J12", "J18")); show(23, "I60-I69", rg("I60", "I69"))
for uf in (35, 41, 43, 31): show(uf, "V01-V99", rg("V01", "V99")); show(uf, "V89+V99", ["V89", "V99"]); show(uf, "V87", ["V87"])
show(35, "X85-Y09", rg("X85", "Y09"))
