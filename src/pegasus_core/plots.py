"""Plots and maps a person crafts from a study's tables (ARCHITECTURE §10.6; pegasus_app ADR-0001): Vega-Lite
specifications saved in the study's folder, rendered headless for a paper.

A plot is a file, ``<folder>/plots/<id>.vl.json``: a Vega-Lite specification whose data is a query of the folder's own
tables, kept in ``usermeta.pegasus`` (``table``, ``where``, ``order``, ``columns``; with ``geometry`` a map: the
folder's municipal boundaries joined to the rows by ``key``). Any Vega tool reads the file; `resolve` puts the rows in,
`render` writes PNG, SVG or PDF through vl-convert, and `data` gives the plotted rows. The window's plot editor and the
``pegasus plot`` commands write the same files. The report's own figures are the study's products (`study`); these are
the person's.
"""

from __future__ import annotations

import copy
import json
import re
import time
from pathlib import Path

from . import workspace

__keyless__ = True

#: rows a plot may hold: a plot of more is a query to narrow (a municipality-year table of Brazil is 55,700 rows)
MAX_ROWS = 200_000
#: the Vega-Lite the files are written for and drawn with (vl-convert; the window draws with the same)
VL_VERSION = "6.4"
SCHEMA = "https://vega.github.io/schema/vega-lite/v6.json"
FORMATS = ("png", "svg", "pdf")
TYPES = {"q": "quantitative", "n": "nominal", "o": "ordinal", "t": "temporal"}


def _dir(name: str) -> Path:
    return workspace.folder(name) / "plots"


def _path(name: str, plot_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", plot_id):
        raise ValueError(f"plot id {plot_id!r}: letters, digits, '-' and '_' only")
    return _dir(name) / f"{plot_id}.vl.json"


def query_of(spec: dict) -> dict:
    q = (spec.get("usermeta") or {}).get("pegasus")
    if not isinstance(q, dict) or not q.get("table"):
        raise ValueError("a plot's data is a query of the study's tables: usermeta.pegasus.table is required")
    return q


def plots(name: str) -> list[dict]:
    """A study's plots: id, title, mark, the table it reads, whether a map, when written."""
    out = []
    for f in sorted(_dir(name).glob("*.vl.json")):
        try:
            spec = json.loads(f.read_text(encoding="utf-8"))
            q = query_of(spec)
        except (OSError, ValueError) as exc:
            out.append({"id": f.name.removesuffix(".vl.json"), "error": f"{type(exc).__name__}: {exc}"})
            continue
        mark = spec.get("mark")
        out.append({"id": f.name.removesuffix(".vl.json"), "title": _title(spec), "table": q["table"],
                    "mark": mark.get("type") if isinstance(mark, dict) else mark, "map": bool(q.get("geometry")),
                    "modified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime))})
    return out


def _title(spec: dict) -> str | None:
    t = spec.get("title")
    return t.get("text") if isinstance(t, dict) else t


def get(name: str, plot_id: str) -> dict:
    path = _path(name, plot_id)
    if not path.exists():
        raise LookupError(f"{name} has no plot {plot_id!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, spec: dict) -> dict:
    """A plot's specification checked against the study: its query's table and columns exist, its geometry is a file of
    the folder; and resolved, so a specification Vega-Lite cannot compile is refused before it is saved."""
    if not isinstance(spec, dict):
        raise ValueError("a plot is a Vega-Lite specification (a JSON object)")
    q = query_of(spec)
    listed = {t["table"]: t for t in workspace.tables(name)}
    if q["table"] not in listed:
        raise ValueError(f"{name} has no table {q['table']!r}: {', '.join(sorted(listed))}")
    if listed[q["table"]].get("error"):
        raise ValueError(listed[q["table"]]["error"])
    known = {k: {c["name"] for c in v["columns"]} for k, v in listed.items()}
    for c in [*(q.get("columns") or []), *(w["column"] for w in q.get("where") or [])]:
        if c not in known[q["table"]]:
            raise ValueError(f"{q['table']} has no column {c!r}")
    if q.get("geometry"):
        workspace.file(name, q["geometry"])
    full = resolve(name, spec)
    if not data(name, spec)["total"]:
        # an empty plot must never look like a legitimate one (a stratum named wrong drew an empty axis)
        raise ValueError(f"the plot's query matches no rows of {q['table']}: "
                         + "; ".join(f"{w['column']} {w.get('op', '=')} {w.get('value')!r}" for w in q.get("where") or []))
    return full


def save(name: str, plot_id: str, spec: dict) -> dict:
    """Write a plot (checked first, `check`); returns its listing row."""
    check(name, spec)
    path = _path(name, plot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = {"$schema": SCHEMA, **{k: v for k, v in spec.items() if k not in ("$schema", "data")},
              "data": {"name": "pegasus"}}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(stored, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return next(p for p in plots(name) if p["id"] == plot_id)


def delete(name: str, plot_id: str) -> None:
    path = _path(name, plot_id)
    if not path.exists():
        raise LookupError(f"{name} has no plot {plot_id!r}")
    path.unlink()


def data(name: str, spec: dict) -> dict:
    """The rows a plot draws: its query run over the study's table, all of them up to `MAX_ROWS`."""
    q = query_of(spec)
    out = workspace.rows(name, q["table"], q.get("where"), q.get("order"), q.get("columns") or None,
                         limit=MAX_ROWS + 1)
    if out["total"] > MAX_ROWS:
        raise ValueError(f"the plot's query matches {out['total']:,} rows of {q['table']}, more than {MAX_ROWS:,}: "
                         "filter it")
    return out


def resolve(name: str, spec: dict) -> dict:
    """The specification with its data in: the query's rows as values; a map's main data the folder's geometry, its
    rows joined by ``key`` (a lookup transform placed first)."""
    q = query_of(spec)
    out = data(name, spec)
    values = [dict(zip(out["columns"], r, strict=True)) for r in out["rows"]]
    full = copy.deepcopy({k: v for k, v in spec.items() if k != "data"})
    full["$schema"] = SCHEMA
    if q.get("geometry"):
        key = q.get("key") or "u"
        geo = json.loads(workspace.file(name, q["geometry"]).read_text(encoding="utf-8"))
        # the join compares text: the folder's tables hold the municipality as text, its boundaries as a number
        gkey = q.get("geometry_key") or key
        for f in geo.get("features", []):
            props = f.setdefault("properties", {})
            props[gkey] = None if props.get(gkey) is None else str(props[gkey])
            _rewind(f.get("geometry") or {})
        for v in values:
            v[key] = None if v.get(key) is None else str(v[key])
        fields = [c for c in out["columns"] if c != key]
        full["data"] = {"values": geo.get("features", []), "format": {"type": "json"}}
        full["transform"] = [{"lookup": f"properties.{q.get('geometry_key') or key}",
                              "from": {"data": {"values": values}, "key": key, "fields": fields}},
                             *(full.get("transform") or [])]
    else:
        full["data"] = {"values": values}
    return full


def _rewind(geometry: dict) -> None:
    """Rings wound as d3 (which Vega draws maps with) reads them: outer rings clockwise, holes counter-clockwise.
    GeoJSON (RFC 7946) winds them the other way, and d3 read each municipality as the globe less the municipality."""
    def area(ring) -> float:
        return sum(x0 * y1 - x1 * y0 for (x0, y0, *_), (x1, y1, *_) in zip(ring, ring[1:], strict=False))

    def fix(polygon: list) -> None:
        for i, ring in enumerate(polygon):
            if (area(ring) > 0) == (i == 0):        # outer counter-clockwise, or a hole clockwise
                ring.reverse()
    if geometry.get("type") == "Polygon":
        fix(geometry["coordinates"])
    elif geometry.get("type") == "MultiPolygon":
        for polygon in geometry["coordinates"]:
            fix(polygon)


def render(name: str, spec: dict, fmt: str = "png", scale: float = 2.0) -> bytes:
    """A plot drawn headless (vl-convert): PNG at ``scale``, SVG or PDF."""
    import vl_convert as vlc

    if fmt not in FORMATS:
        raise ValueError(f"format {fmt!r}: one of {', '.join(FORMATS)}")
    full = resolve(name, spec)
    # no data from any URL: the rows are the folder's, and the instrument reaches no other server
    common = {"vl_version": VL_VERSION, "allowed_base_urls": []}
    if fmt == "png":
        return vlc.vegalite_to_png(full, scale=scale, **common)
    if fmt == "svg":
        return vlc.vegalite_to_svg(full, **common).encode("utf-8")
    return vlc.vegalite_to_pdf(full, **common)


def _encoding(text: str) -> dict:
    """``field:type`` (q, n, o, t), ``agg(field):type`` (sum, mean, median, min, max, count), or ``count()``."""
    text = text.strip()
    if text == "count()":
        return {"aggregate": "count", "type": "quantitative"}
    m = re.fullmatch(r"(?:(\w+)\((\w+)\)|(\w+))(?::([qnot]))?", text, re.IGNORECASE)
    if not m:
        raise ValueError(f"{text!r}: write field:type (q, n, o, t), agg(field):type, or count()")
    agg, field_a, field_b, kind = m.groups()
    enc = {"field": field_a or field_b, "type": TYPES[(kind or ("q" if agg else "n")).lower()]}
    if agg:
        enc["aggregate"] = agg.lower()
    return enc


def build(table: str, mark: str, encodings: dict[str, str], where: list[dict] | None = None,
          title: str | None = None, geometry: str | None = None, key: str = "u") -> dict:
    """A plot from a table, a mark and encodings by channel (``x``, ``y``, ``color``, ``size``, ``shape``,
    ``column``, ``row``, ``tooltip``): what ``pegasus plot new`` writes and the editor starts from. With ``geometry``
    the mark is a ``geoshape`` and the channels read the joined rows."""
    enc = {}
    for channel, text in encodings.items():
        if not text:
            continue
        if channel == "tooltip":
            enc["tooltip"] = [_encoding(t) for t in text.split(",")]
        else:
            enc[channel] = _encoding(text)
    used = sorted({e["field"] for v in enc.values() for e in (v if isinstance(v, list) else [v]) if "field" in e})
    spec = {"$schema": SCHEMA, "title": title or table, "mark": {"type": "geoshape" if geometry else mark,
                                                                   **({"tooltip": True} if not geometry else {})},
            "encoding": enc, "width": 640, "height": 400,
            "usermeta": {"pegasus": {"table": table, "where": where or [],
                                     "columns": sorted({*used, key}) if geometry else used}}}
    if geometry:
        spec["usermeta"]["pegasus"].update(geometry=geometry, key=key)
        spec["projection"] = {"type": "mercator"}
    return spec
