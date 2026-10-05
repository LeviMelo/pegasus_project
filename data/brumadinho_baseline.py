"""Brumadinho test, step 3 (ledger d5938be360254838): the facility shares of the TRAINING baseline, reported before testing.
Brumadinho residents (MUNIC_RES 310900), principal diagnosis J20-J22, 2016-01..2018-12 (files 2016-2019, dates <= 2018-12);
the pooled secondary places the same way. Writes data/logs/brumadinho_baseline.json. Reads no month after 2018-12.
Burst rule (fixed here, before the shares are seen): the baseline is burst-free if no facility holding >= 50% of the
admissions has >= 50% of its admissions in 3 months or fewer. If it is not burst-free the test is not run: stop and report.
"""
import json

import duckdb
import pyarrow as pa

from pegasus_core import gateway

DATASET, EVENT = "SIH-RD", "hospitalisation"
PRIMARY = [310900]
SECONDARY = [int(m["code6"]) for m in json.load(open("data/brumadinho_locus.json", encoding="utf-8"))["municipalities"]]


_RAW: dict = {}


def facility_records(places: list[int], codes: list[str], files: range, lo: int, hi: int) -> list[dict]:
    """(facility, hospital municipality, year-month, count) of residents of ``places`` with a principal diagnosis in ``codes``."""
    import pegasus_data as pg

    strata = gateway._strata(DATASET)
    roles = pg.roles(DATASET)
    fcol = next(r["column"] for r in roles if r.get("model") == "institution" and r.get("property") == "facility")
    mcol = next(r["column"] for r in roles if r.get("property") == "facility_municipality")
    spec = next(e for e in pg.event_types(DATASET) if e["name"] == EVENT)
    cls = next(c["column"] for c in spec["classifiers"] if c["role"] == "primary")
    when = gateway._when(DATASET)
    rows = []
    for year in files:
        key = (year, strata["residence"], when, fcol, mcol, cls)
        if key not in _RAW:       # the same year is read by every place/code job: read it once
            _RAW[key] = gateway._records(DATASET, EVENT, year, list(key[1:]))
        raw = _RAW[key]
        con = duckdb.connect()
        con.register("r", raw)
        con.register("loc", pa.table({"u": pa.array(places, pa.int32())}))
        rows += con.execute(f"""SELECT u, left(coalesce(trim(CAST("{fcol}" AS VARCHAR)), ''), 7) AS fac,
                left(coalesce(trim(CAST("{mcol}" AS VARCHAR)), ''), 6) AS mov, year(d) * 100 + month(d) AS ym, count(*) AS y FROM (
              SELECT CAST({gateway._residence_sql(strata['residence'])} AS INTEGER) AS u, "{fcol}", "{mcol}",
                     {gateway._date_sql(when)} AS d, upper(trim(CAST("{cls}" AS VARCHAR))) AS c FROM r)
            WHERE u IN (SELECT u FROM loc) AND left(c, 3) IN ({", ".join(repr(c) for c in codes)}) AND d IS NOT NULL
              AND year(d) * 100 + month(d) BETWEEN {lo} AND {hi}
            GROUP BY ALL""").fetch_arrow_table().to_pylist()
    return rows


def shares(rows: list[dict]) -> dict:
    fac: dict = {}
    for r in rows:
        f = fac.setdefault(r["fac"], {"n": 0, "months": {}, "mov": {}})
        f["n"] += r["y"]
        f["months"][r["ym"]] = f["months"].get(r["ym"], 0) + r["y"]
        f["mov"][r["mov"]] = f["mov"].get(r["mov"], 0) + r["y"]
    tot = sum(f["n"] for f in fac.values())
    out = []
    for k, f in fac.items():
        top3 = sum(sorted(f["months"].values(), reverse=True)[:3])
        out.append({"facility": k, "n": f["n"], "share": f["n"] / tot, "hospital_municipality": max(f["mov"], key=f["mov"].get),
                    "by_year": {y: sum(v for m, v in f["months"].items() if m // 100 == y) for y in (2016, 2017, 2018)},
                    "months_with_admissions": len(f["months"]), "top3_months_share": top3 / f["n"]})
    out.sort(key=lambda o: -o["n"])
    burst = [o for o in out if o["share"] >= 0.5 and o["top3_months_share"] >= 0.5 and o["months_with_admissions"] > 0]
    return {"total": tot, "n_facilities": len(out), "facilities": out[:15], "burst_flagged": [o["facility"] for o in burst],
            "months_with_any_admission": len({m for f in fac.values() for m in f["months"]})}


def main() -> None:
    res = {}
    for name, places in (("primary_310900", PRIMARY), ("secondary_25_pooled", SECONDARY)):
        res[name] = {}
        for label, codes in (("J20-J22", ["J20", "J21", "J22"]), ("XI_K", [f"K{i:02d}" for i in range(0, 94)])):
            res[name][label] = shares(facility_records(places, codes, range(2016, 2020), 201601, 201812))
    json.dump(res, open("data/logs/brumadinho_baseline.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=float)
    for name in res:
        for label, r in res[name].items():
            print(name, label, "total", r["total"], "facilities", r["n_facilities"], "burst_flagged", r["burst_flagged"])
            for o in r["facilities"][:6]:
                print("   ", o["facility"], "mov", o["hospital_municipality"], "n", o["n"], f"share {o['share']:.3f}", o["by_year"],
                      f"top3-months {o['top3_months_share']:.2f}")


if __name__ == "__main__":
    main()
