"""Step 1 of the replicated-claims reading: SIM.DO death 2010-2023 (never 2024) as (u, year, sex, band, code3, y), and
both populations as (u, year, sex, band, n), cached under data/replicated_claims/. Bands are POPSVS's 18 (age_edges)."""
import warnings, duckdb, numpy as np, pyarrow as pa, pyarrow.parquet as pq, pyarrow.compute as pc
warnings.simplefilter("ignore")
from pegasus_core import gateway
YEARS = list(range(2010, 2024))
edges = np.array(gateway.age_edges("popsvs")); print(edges)
out = "data/replicated_claims/"
ev = []
for y in YEARS:
    c = gateway.event_counts("SIM.DO", "death", y).counts
    con = duckdb.connect(); con.register("c", c)
    ev.append(con.execute(f"""select u, year, sex, (select max(e) from unnest({edges.tolist()}) t(e) where e <= least(greatest(age,0),120))::smallint band,
        substr(code,1,3) c3, sum(y)::int y from c group by all""").fetch_arrow_table())
pq.write_table(pa.concat_tables(ev), out + "events.parquet")
for src in ("popsvs", "account-3"):
    p = gateway.population(YEARS, source=src)
    con = duckdb.connect(); con.register("p", p)
    t = con.execute(f"""select u, year, sex, (select max(e) from unnest({edges.tolist()}) t(e) where e <= greatest(age,0))::smallint band, sum(n) n
        from p group by all""").fetch_arrow_table()
    pq.write_table(t, out + f"pop_{src}.parquet"); print(src, t.num_rows, pc.sum(t.column("n")))
print(pa.concat_tables(ev).num_rows)
