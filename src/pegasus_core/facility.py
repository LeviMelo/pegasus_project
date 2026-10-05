"""The institution behind an event: which facility recorded it (ARCHITECTURE §7.7, §9.1).

A lead that is one hospital's coding looks like a place effect at municipal grain. This module reads the
facility column of the event type (pegasus_data's `institution` role: SIH-RD `CNES`, SIM-DO `CODESTAB`)
and serves the cube (residence municipality, facility, 3-character code, year) -> events, from which
`explain.facility_concentration` judges a lead. The cube is a gateway-level cache, one table per year.

SIH names the facility of every admission. SIM names it only for deaths certified in an establishment
(`CODESTAB` is empty for a death at home or in the street): a lead's SIM facility coverage is reported
beside its verdict, and a place whose deaths have no facility cannot be judged here.
"""

from __future__ import annotations

import warnings

import duckdb
import numpy as np
import pyarrow as pa

from . import config, gateway, store

CODE_CHARS = 3     # the classifier's category level; subcodes are not kept (a 4-character coding habit is seen at 3)


def facility_column(dataset: str) -> tuple[str, str | None]:
    """(facility column, the facility's own municipality column or None) from pegasus_data's roles."""
    import pegasus_data as pg

    roles = pg.roles(dataset)
    fac = [r for r in roles if r.get("model") == "institution" and r.get("property") == "facility"]
    if not fac:
        raise LookupError(f"{dataset}: no facility among its institution roles")
    where = [r for r in roles if r.get("model") == "where" and r.get("property") in ("facility_municipality", "municipality")]
    return fac[0]["column"], where[0]["column"] if where else None


def facility_cube(dataset: str, event: str, year: int) -> pa.Table:
    """Events of one year by (u residence, facility, code3). ``facility`` is the CNES code as text, '' when the
    record names none; ``fm`` the facility's municipality as the data gives it ('' if the dataset has none)."""
    import pegasus_data as pg

    strata = gateway._strata(dataset)
    spec = next(e for e in pg.event_types(dataset) if e["name"] == event)
    classifier = next((c["column"] for c in spec["classifiers"] if c["role"] == "primary"), None)
    if classifier is None:
        raise LookupError(f"{dataset}/{event}: no primary classifier, no facility cube")
    fcol, mcol = facility_column(dataset)
    key = {"what": "facility_cube", "dataset": dataset, "event": event, "year": year, "classifier": classifier,
           "facility": fcol, "data": config.data_version(), "v": 1, **gateway._df_key(dataset, year)}
    hit = store.get_table("gateway", key)
    if hit is not None:
        return hit
    by = [strata["residence"], fcol, classifier] + ([mcol] if mcol else [])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pg.count_events(dataset, event, period=year, geography="BR", by=by, root=config.data_root(),
                              allow_partial=False, max_download=8 * 1024**3)
    con = duckdb.connect()
    con.register("r", raw)
    fm = f"coalesce(left(trim(CAST(\"{mcol}\" AS VARCHAR)), 6), '')" if mcol else "''"
    out = con.execute(f"""SELECT CAST({gateway._residence_sql(strata['residence'])} AS INTEGER) AS u,
            coalesce(trim(CAST("{fcol}" AS VARCHAR)), '') AS facility, {fm} AS fm,
            left(upper(trim(CAST("{classifier}" AS VARCHAR))), {CODE_CHARS}) AS code,
            CAST({year} AS SMALLINT) AS year, CAST(sum(events) AS INTEGER) AS y
        FROM r WHERE "{classifier}" IS NOT NULL GROUP BY ALL""").fetch_arrow_table()
    store.put_table("gateway", key, out, {"source": f"pegasus_data.count_events({dataset}, {event}) by residence, {fcol}, {classifier}"})
    return out


class Facilities:
    """A session's facility cube as integer columns, indexed for the lead-level reads of `tally`.

    ``places``/``years`` are the evidence grid's. Rows are (place index, facility id, year index, events), once for
    events of any cause and, per block, for the block's codes. Both are sorted by place; the block rows are also
    ranged by facility for the residents of other places."""

    def __init__(self, dataset: str, event: str, years: list[int], places: np.ndarray, grid_years: np.ndarray):
        self.dataset, self.event, self.years = dataset, event, [int(y) for y in years]
        self.places, self.grid_years = np.asarray(places), np.asarray(grid_years)
        self._blocks: dict[str, tuple] = {}
        names: set[str] = set()
        for y in self.years:
            names.update(facility_cube(dataset, event, y).column("facility").unique().to_pylist())
        self.names = np.array(sorted(names), dtype=object)               # '' (no facility) sorts first
        self._by_name = {n: i for i, n in enumerate(self.names)}
        self.none = self._by_name.get("", -1)
        self._total = self._read(None)

    def _read(self, codes: list[str] | None) -> tuple[np.ndarray, ...]:
        """(place idx, facility id, year idx, code idx, events) summed over the cube, for ``codes`` (None: every code,
        code idx 0)."""
        con = duckdb.connect()
        fac = pa.table({"facility": pa.array(self.names.tolist(), pa.string()), "f": pa.array(range(len(self.names)), pa.int32())})
        con.register("fac", fac)
        con.register("pl", pa.table({"u": pa.array(self.places.astype(np.int32)), "p": pa.array(range(len(self.places)), pa.int32())}))
        if codes is not None:
            con.register("cd", pa.table({"code": pa.array(codes, pa.string()), "c": pa.array(range(len(codes)), pa.int32())}))
        out = []
        for y in self.years:
            t = facility_cube(self.dataset, self.event, y)
            con.register("t", t)
            code = "JOIN cd USING (code)" if codes is not None else ""
            sel = "cd.c" if codes is not None else "0"
            out.append(con.execute(f"""SELECT pl.p AS p, fac.f AS f, {sel} AS c, CAST(sum(t.y) AS DOUBLE) AS y
                FROM t JOIN pl USING (u) JOIN fac USING (facility) {code} GROUP BY ALL""").fetch_arrow_table())
        cols = []
        for k, ty in (("p", np.int32), ("f", np.int32), ("c", np.int32), ("y", np.float64)):
            cols.append(np.concatenate([o.column(k).to_numpy().astype(ty) for o in out]))
        tix = np.concatenate([np.full(o.num_rows, i, np.int16) for i, o in enumerate(out)])
        p, f, c, y = cols
        t_idx = np.searchsorted(self.grid_years, np.array(self.years))[tix]       # the year's column on the grid
        order = np.argsort(p, kind="stable")
        return p[order], f[order], t_idx[order].astype(np.int16), c[order], y[order]

    def block(self, key: str, codes: list[str]) -> tuple:
        """The block's rows (cached by ``key``): sorted by place, plus the offsets by place and the order by facility."""
        if key not in self._blocks:
            p, f, t, c, y = self._read(codes)
            starts = np.searchsorted(p, np.arange(len(self.places) + 1))
            by_f = np.argsort(f, kind="stable")
            f_starts = np.searchsorted(f[by_f], np.arange(len(self.names) + 1))
            self._blocks[key] = (p, f, t, c, y, starts, by_f, f_starts, {code: i for i, code in enumerate(codes)})
        return self._blocks[key]

    @staticmethod
    def _gather(starts: np.ndarray, rows: np.ndarray) -> np.ndarray:
        return np.concatenate([np.arange(starts[r], starts[r + 1]) for r in rows]) if len(rows) else np.zeros(0, dtype=np.int64)

    def tally(self, key: str, block_codes: list[str], lead_codes: list[str], rows: np.ndarray):
        """The lead's events by facility: the `explain.FacilityTally` of residents of ``rows`` (grid place indices)
        for the codes of the lead and of its block."""
        from .scans import explain

        p, f, t, c, y, starts, by_f, f_starts, cidx = self.block(key, block_codes)
        T = len(self.grid_years)
        sel = self._gather(starts, rows)
        tp, tf, tt, _, ty, *_ = self._total
        tstarts = np.searchsorted(tp, np.arange(len(self.places) + 1))
        tsel = self._gather(tstarts, rows)
        used = np.unique(np.concatenate([f[sel], tf[tsel]]))
        if used.size == 0:
            return None
        local = np.full(len(self.names), -1, dtype=np.int64)
        local[used] = np.arange(used.size)
        is_lead = np.zeros(len(block_codes), bool)
        is_lead[[cidx[c_] for c_ in lead_codes if c_ in cidx]] = True
        F = used.size

        def fold(fl, tl, w):
            return np.bincount(fl * T + tl, weights=w, minlength=F * T).reshape(F, T)

        lead = fold(local[f[sel]][is_lead[c[sel]]], t[sel][is_lead[c[sel]]], y[sel][is_lead[c[sel]]])
        block = fold(local[f[sel]], t[sel], y[sel])
        total = fold(local[tf[tsel]], tt[tsel], ty[tsel])
        inside = np.zeros(len(self.places), bool)
        inside[rows] = True

        def outside(top: np.ndarray):
            lo, bl = np.zeros((len(top), T)), np.zeros((len(top), T))
            for j, i in enumerate(top):
                g = by_f[f_starts[used[i]]:f_starts[used[i] + 1]]
                g = g[~inside[p[g]]]
                np.add.at(bl[j], t[g], y[g])
                m = is_lead[c[g]]
                np.add.at(lo[j], t[g][m], y[g][m])
            return lo, bl

        return explain.FacilityTally(self.names[used], lead, block, total, outside)
