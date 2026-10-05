"""Re-run the 57 replicated state national-trend claims (evaluation 2026-10-05-replicated-claims-read.md) through the
artefact-aware replication (`replication.audit`, ADR-0019). Events: SIM.DO deaths 2010-2023 (never 2024) by 4-character code,
sex and age; person-years POPSVS. Output: data/artefact_replication/audit.json and a table on stdout.

    python scripts/heavy.py --label artefact-audit -- python data/artefact_replication.py
"""
import json
import os
import warnings
from pathlib import Path

os.chdir(Path(__file__).resolve().parents[1])
warnings.simplefilter("ignore")
import numpy as np
import pandas as pd

from pegasus_core import gateway, leads, replication
from pegasus_core.tools import kinds_of

D = Path("data/artefact_replication")
D.mkdir(exist_ok=True)
YEARS = list(range(2010, 2024))
TRAIN = list(range(2010, 2020))
LATER = list(range(2020, 2024))

if (D / "events.parquet").exists():
    ev, pop = pd.read_parquet(D / "events.parquet"), pd.read_parquet(D / "pop.parquet")
    edges = np.array(gateway.age_edges("popsvs"))
    st = replication.Strata(ev, pop, edges)
else:
    import duckdb

    edges = np.array(gateway.age_edges("popsvs"))
    rows = []
    for y in YEARS:
        con = duckdb.connect()
        con.register("c", gateway.event_counts("SIM.DO", "death", y).counts)
        rows.append(con.execute(f"""select u, year, sex, (select max(e) from unnest({edges.tolist()}) t(e)
            where e <= least(greatest(age, 0), 120))::smallint band, code, sum(y)::int y from c group by all""").fetchdf())
    ev = pd.concat(rows)
    con = duckdb.connect()
    con.register("p", gateway.population(YEARS, source="popsvs"))
    pop = con.execute(f"""select u, year, sex, (select max(e) from unnest({edges.tolist()}) t(e)
        where e <= greatest(age, 0))::smallint band, sum(n) n from p group by all""").fetchdf()
    ev.to_parquet(D / "events.parquet")
    pop.to_parquet(D / "pop.parquet")
    st = replication.Strata(ev, pop, edges)
print("strata", st.shape, len(st.y), "event rows", flush=True)

tree = gateway.code_structure("ICD10").to_pandas().set_index("code")
reg = leads.Register(Path("pegasus_home/leads_T2019"))
mine = [x for x in reg.current() if x.estimand == "trend_divergence" and x.locus.get("scale")
        and leads.trend_reference(x) == "national" and kinds_of(x) >= {"temporal", "spatial"}]
mine.sort(key=lambda x: (x.fields[0], x.locus["unit"]))
out = []
for i, x in enumerate(mine):
    node = x.fields[0].split(":")[-1]
    r = replication.audit(st, x.locus["places"], node, x.locus["scale"], x.provenance["stats"]["beta"],
                          replication.span_direction(x)[1], TRAIN, tree, later_years=LATER)
    r.update(id=x.id, uf=int(x.locus["unit"]))
    out.append(r)
    print(i + 1, node, r["uf"], r["verdict"], flush=True)
json.dump(out, open(D / "audit.json", "w"), indent=1, default=float)
