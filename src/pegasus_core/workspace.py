"""The workspace as a person sees it (ARCHITECTURE §10.6; ADR-0038): the read models the ``pegasus`` command line and the
desktop window (pegasus_app) share, so neither computes what the other lacks.

The workspace is a directory (`jobs.workspace`): ``studies/`` holds the declarations and their folders, ``runs/`` the
runs (`jobs`). Everything here reads those files and the engine's own functions; nothing is held only in memory.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import config, jobs

__keyless__ = True


def studies_dir() -> Path:
    path = jobs.workspace() / "studies"
    path.mkdir(parents=True, exist_ok=True)
    return path


def declarations() -> list[Path]:
    """Every study declaration in the workspace: ``studies/*.yml`` and one level of grouping (``studies/slices/``); a
    study folder's own copy (``study.yml``, ``scope.yml``) and a priced scope (``<name>.scope.yml``) are not."""
    grouped = [p for p in studies_dir().glob("*/*.yml") if not (p.parent / "study.yml").exists()]
    found = [p for p in [*studies_dir().glob("*.yml"), *grouped] if not p.name.endswith(".scope.yml")]
    return sorted(found,
                  key=lambda p: (len(p.relative_to(studies_dir()).parts), p.name))


def body(folder: Path) -> list[dict] | None:
    """A folder's analytic body (`study.body`), kept in ``body.json`` beside its provenance and made again when the
    folder is newer: 0.9 s a folder made the list of studies wait."""
    from . import study

    prov, cached = folder / "provenance.json", folder / "body.json"
    if not prov.exists():
        return None
    if cached.exists() and cached.stat().st_mtime >= prov.stat().st_mtime:
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except ValueError:
            pass
    try:
        parts = study.body(folder)
    except Exception as exc:  # noqa: BLE001 - a folder whose check fails is shown with why, never hidden
        return [{"part": "check", "status": "missing", "evidence": f"{type(exc).__name__}: {exc}"}]
    jobs._write_json(cached, parts)
    return parts


def _summary(path: Path) -> dict:
    import yaml

    from . import study

    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError) as exc:
        doc = {"error": f"{type(exc).__name__}: {exc}"}
    name = doc.get("study") or path.stem
    folder = path.parent / name
    prov = {}
    if (folder / "provenance.json").exists():
        try:
            prov = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
        except ValueError:
            prov = {}
    parts = body(folder)
    last = jobs.runs(limit=1, study=name)
    return {"name": name, "declaration": str(path.resolve()), "folder": str(folder.resolve()),
            "group": str(path.parent.relative_to(studies_dir())).replace("\\", "/").strip(".") or None,
            "depth": doc.get("depth") or ("survey" if "error" not in doc else None), "where": doc.get("where"),
            "period": None if doc.get("period") is None else str(doc.get("period")),
            "topic": (doc.get("topic") or {}).get("seeds"), "error": doc.get("error"),
            "written": prov.get("written"), "seconds": prov.get("seconds"),
            "estimated_minutes": prov.get("estimated_minutes"), "code_version": prov.get("code_version"),
            "body": None if parts is None else {"met": sum(p["status"] == "met" for p in parts), "total": len(parts)},
            "last_run": last[0] if last else None, "depths": list(study.DEPTHS)}


def studies() -> list[dict]:
    """Every study in the workspace: its declaration's choices, its folder's last writing and analytic body, its last
    run."""
    return [_summary(p) for p in declarations()]


def find(name: str) -> Path:
    """A study's declaration by its name (``infarto_alagoas``), its file name or its path."""
    p = Path(name)
    if p.suffix in (".yml", ".yaml") and p.exists():
        return p.resolve()
    hits = [d for d in declarations() if d.stem == name or _summary_name(d) == name]
    if not hits:
        raise LookupError(f"no study {name!r} in {studies_dir()}")
    return hits[0].resolve()


def _summary_name(path: Path) -> str:
    import yaml

    try:
        return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("study") or path.stem
    except (OSError, ValueError):
        return path.stem


def study_detail(name: str) -> dict:
    """One study: its summary, its declaration's text, its scope (what it reads, from ``scope.yml``), its analytic body
    part by part, its folder's files and its runs."""
    import yaml

    path = find(name)
    s = _summary(path)
    folder = Path(s["folder"])
    scope = None
    if (folder / "scope.yml").exists():
        try:
            scope = yaml.safe_load((folder / "scope.yml").read_text(encoding="utf-8"))
        except ValueError:
            scope = None
    files = []
    if folder.exists():
        for f in sorted(folder.rglob("*")):
            if f.is_file() and not f.name.endswith(".tmp"):
                files.append({"path": f.relative_to(folder).as_posix(), "bytes": f.stat().st_size,
                              "modified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime))})
    return {**s, "text": path.read_text(encoding="utf-8"), "scope": scope, "parts": body(folder), "files": files,
            "runs": jobs.runs(study=s["name"])}


def scope(name: str) -> dict:
    """What a study's declaration resolves to (`study.resolve`): the sources it reads and why, their years and minutes,
    what is deferred or not read and why, what each choice costs; written beside the declaration
    (``<name>.scope.yml``). A study's folder is written by its runs alone: a pricing written into it had replaced the
    scope its finished report was made from."""
    import yaml

    from . import study

    path = find(name)
    decl = study.load(path)
    resolved = study.resolve(decl)
    out = resolved.to_dict()
    target = path.with_name(f"{path.stem}.scope.yml")
    # written, not printed: the console wraps long lines and the printed YAML did not parse (2026-10-12)
    target.write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {**out, "written": str(target),
            "nothing_read": None if out["read"] else study.nothing_read(resolved)}


def start_study(name: str, products_only: bool = False) -> dict:
    """Run a study (`jobs.submit`): a detached run, admitted by memory beside the others."""
    from . import study

    path = find(name)
    decl = study.load(path)
    return jobs.submit("study", f"study {decl.study}" + (" (products)" if products_only else ""),
                       declaration=str(path), study=decl.study, folder=str(study.folder_of(decl)),
                       options={"products_only": products_only})


def context(name: str | None = None, commands: list[dict] | None = None) -> str:
    """What an assistant outside PegaSUS (a chatbot the person consults) needs to read and propose work on this
    workspace, as Markdown: what PegaSUS is and the rules it keeps, its commands, the declaration's keys and presets,
    the studies and runs, and with ``name`` one study's declaration, scope, body and tables. Nothing in PegaSUS calls an
    assistant; the person pastes this, and runs what is proposed."""
    from . import study

    out = ["# PegaSUS workspace context",
           "",
           f"Generated {time.strftime('%Y-%m-%d %H:%M')} from `{jobs.workspace()}` (code {config.code_version()}).",
           "",
           "PegaSUS produces epidemiological studies of Brazil's public health data (DATASUS: SIM deaths, SINASC "
           "births, SIH admissions, SINAN notifications, SIA outpatient care, CNES establishments and more) from one "
           "YAML declaration per study. A run reads what the declaration's scope names, fits models and writes a "
           "study folder: tables (Parquet, and `study.duckdb` holding them as views), `report.html`, `METHODS.md`, "
           "figures and `provenance.json`. A person designs, runs and judges every study; you advise them.",
           "",
           "## Rules any proposal must keep",
           "",
           "- Never guess what a code means: read its label from the data (`pegasus data show DATASET`); an unlabelled "
           "code is undecoded.",
           "- Missing is not zero; a source that could not be read is a recorded gap.",
           "- Personal identifiers (roles of kind `identifier`) are never copied out of the workspace.",
           "- The confirmation reserve (`pegasus explore confirm`) spends a finite error budget: propose a claim, never "
           "spend it.",
           "- Every number in a study folder has its provenance (`provenance.json`, `METHODS.md`); cite them.",
           "- Each command takes `--json` for machine-readable output.",
           ""]
    if commands:
        out += ["## Commands", ""]
        out += [f"- `pegasus {c['path']}`: {c['help']}" for c in commands]
        out += [""]
    out += ["## The declaration", "",
            f"Keys: {', '.join(sorted(study.KEYS))}. `topic.seeds` names the topic in any of "
            f"{', '.join(study.SEED_SYSTEMS)}; `topic.only`, `include`, `exclude` restrict its sources. "
            f"`depth` is one of {', '.join(study.DEPTHS)}, each a preset of the choices below; a key the declaration "
            "sets overrides its depth's.", "",
            "| choice | " + " | ".join(study.DEPTHS) + " |", "|---|" + "---|" * len(study.DEPTHS)]
    for k in study.PRESETS["survey"]:
        out.append(f"| {k} | " + " | ".join(json.dumps(study.PRESETS[d][k]) for d in study.DEPTHS) + " |")
    out += ["", "`pegasus study new NAME --icd10 CODES --where UF --period FIRST-LAST` writes a commented "
            "declaration; `pegasus study scope NAME` prices it before it runs.", "", "## Studies", "",
            "| study | where | period | depth | body | last run |", "|---|---|---|---|---|---|"]
    for s in studies():
        b = f"{s['body']['met']}/{s['body']['total']}" if s["body"] else "not run"
        r = s["last_run"]
        out.append(f"| {s['name']} | {s['where']} | {s['period']} | {s['depth']} | {b} | "
                   + (f"{r['state']} {r['ended'] or r['created']}" if r else "none") + " |")
    if name:
        d = study_detail(name)
        out += ["", f"## Study {d['name']}", "", "### Declaration", "", "```yaml", d["text"].rstrip(), "```"]
        if d["scope"]:
            out += ["", "### What it reads", ""]
            for i in d["scope"].get("read") or []:
                out.append(f"- {i['dataset']} {i['event']} {i['years'][0] if i['years'] else ''}-"
                           f"{i['years'][-1] if i['years'] else ''}: {i.get('reason', '')}")
            for i in (d["scope"].get("deferred") or []) + (d["scope"].get("not_read") or []):
                out.append(f"- not read: {i.get('dataset', i.get('seed', ''))}: "
                           f"{i.get('why') or i.get('note') or i.get('reason') or ''}")
        if d["parts"]:
            out += ["", "### Analytic body", ""]
            out += [f"- {p['part']}: {p['status']} ({p['evidence']})" for p in d["parts"]]
        tables = _tables(Path(d["folder"]))
        if tables:
            out += ["", "### Tables (views of study.duckdb)", ""]
            out += [f"- `{t}` ({n:,} rows): {', '.join(cols)}" for t, (n, cols) in tables.items()]
        from . import plots

        out += ["", "### Plots", "",
                "A plot is a Vega-Lite 6 file in the folder (`plots/ID.vl.json`) whose data is a query of the tables "
                "above, kept in `usermeta.pegasus`: `{table, where: [{column, op, value}], columns: [...]}`; a map adds "
                "`geometry: municipalities.geojson, key: u` and uses mark `geoshape`. Propose one as a file the person "
                "saves with `pegasus plot save NAME ID --spec FILE`, or as `pegasus plot new` options; a query that "
                "matches no rows is refused. Rows that share one x and colour pile up: filter `stratum`, "
                "`denominator_kind` and `field` in `rates`."]
        for p in plots.plots(d["name"]):
            out.append(f"- `{p['id']}`: {p.get('title') or ''} ({p.get('mark')} of `{p.get('table')}`)")
    return "\n".join(out) + "\n"


def _tables(folder: Path) -> dict[str, tuple[int, list[str]]]:
    import pyarrow.parquet as pq

    out = {}
    for f in sorted(folder.glob("*.parquet")):
        try:
            meta = pq.read_metadata(f)
            out[f.stem] = (meta.num_rows, meta.schema.to_arrow_schema().names)
        except (OSError, ValueError):
            continue
    return out


# ------------------------------------------------------------------------------------------------- a study's folder


def folder(name: str) -> Path:
    """A study's folder (beside its declaration), whether written or not."""
    from . import study

    return study.folder_of(study.load(find(name)))


def file(name: str, path: str) -> Path:
    """A file of a study's folder by its path inside it; a path that leaves the folder is refused."""
    root = folder(name).resolve()
    target = (root / path).resolve()
    if root != target and root not in target.parents:
        raise PermissionError(f"{path} is outside the study's folder")
    if not target.is_file():
        raise FileNotFoundError(f"no file {path} in {root}")
    return target


def _connect(name: str):
    import duckdb

    db = folder(name) / "study.duckdb"
    if not db.exists():
        raise FileNotFoundError(f"{name} has no study.duckdb: run it first")
    return duckdb.connect(str(db), read_only=True)


def tables(name: str) -> list[dict]:
    """The tables of a study (the views of its ``study.duckdb``): rows and columns with their types."""
    with _connect(name) as con:
        out = []
        for (t,) in con.execute("SELECT table_name FROM information_schema.tables ORDER BY table_name").fetchall():
            cols = [{"name": c, "type": ty} for c, ty, *_ in con.execute(f'DESCRIBE "{t}"').fetchall()]
            out.append({"table": t, "rows": con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0], "columns": cols})
        return out


#: the comparisons a filter may use (`rows`)
FILTER_OPS = ("=", "!=", "<", "<=", ">", ">=", "in", "like", "is null", "is not null")


def rows(name: str, table: str, where: list[dict] | None = None, order: list[str] | None = None,
         columns: list[str] | None = None, limit: int = 200, offset: int = 0) -> dict:
    """Rows of a study's table: ``where`` a list of ``{column, op, value}`` (`FILTER_OPS`; ``in`` takes a list),
    ``order`` columns (``-col`` descending), ``columns`` those kept. Every name is checked against the table, every
    value is a parameter. Returns the columns, the rows, and the count before ``limit``."""
    with _connect(name) as con:
        known = {t for (t,) in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        if table not in known:
            raise LookupError(f"{name} has no table {table!r}: {', '.join(sorted(known))}")
        cols = [c for c, *_ in con.execute(f'DESCRIBE "{table}"').fetchall()]

        def col(c: str) -> str:
            if c not in cols:
                raise ValueError(f"{table} has no column {c!r}")
            return f'"{c}"'
        clauses, params = [], []
        for w in where or []:
            op = str(w.get("op", "=")).lower()
            if op not in FILTER_OPS:
                raise ValueError(f"filter {op!r}: one of {', '.join(FILTER_OPS)}")
            if op in ("is null", "is not null"):
                clauses.append(f"{col(w['column'])} {op.upper()}")
            elif op == "in":
                values = list(w["value"]) if isinstance(w["value"], list | tuple) else [w["value"]]
                clauses.append(f"{col(w['column'])} IN ({', '.join('?' for _ in values)})")
                params += values
            else:
                clauses.append(f"{col(w['column'])} {op.upper()} ?")
                params.append(w["value"])
        sql_where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        keys = [f"{col(o.lstrip('-'))} {'DESC' if o.startswith('-') else 'ASC'}" for o in order or []]
        if keys:
            # ties broken by every other column, so a page never repeats or skips a row of tied values
            named = {o.lstrip("-") for o in order or []}
            keys += [f'"{c}" ASC NULLS LAST' for c in cols if c not in named]
        sql_order = f" ORDER BY {', '.join(keys)}" if keys else ""
        keep = ", ".join(col(c) for c in columns) if columns else "*"
        total = con.execute(f'SELECT count(*) FROM "{table}"{sql_where}', params).fetchone()[0]
        cur = con.execute(f'SELECT {keep} FROM "{table}"{sql_where}{sql_order} LIMIT ? OFFSET ?',
                          [*params, int(limit), int(offset)])
        names = [d[0] for d in cur.description]
        data = [list(r) for r in cur.fetchall()]
    return {"table": table, "columns": names, "rows": data, "total": total, "limit": limit, "offset": offset}


# -------------------------------------------------------------------------------------------------------- the data


def datasets(refresh: bool = False) -> dict:
    """What DATASUS publishes, as pegasus_data's catalog lists it: its systems and their datasets (files, gigabytes,
    years, states), each with the event types a study can read of it. Kept in ``PEGASUS_HOME/workspace/datasets.json``
    for the catalog's crawl: listing the 24 systems' datasets takes seconds."""
    import pegasus_data as pg

    from . import gateway

    root = config.data_root()
    top = pg.explore(root=root)
    cache = config.home() / "workspace" / "datasets.json"
    stamp = {"as_of": str(top.as_of), "data_version": config.data_version()}
    if cache.exists() and not refresh:
        try:
            kept = json.loads(cache.read_text(encoding="utf-8"))
            if {k: kept.get(k) for k in stamp} == stamp:
                return kept
        except ValueError:
            pass
    readable: dict[str, list[str]] = {}
    for ds in gateway.event_datasets():
        readable[gateway.dataset_key(ds)] = [e["name"] for e in gateway.event_types(ds)]
    rows = []
    for s in top.rows:
        for r in pg.explore(s["system"], root=root).rows:
            key = gateway.dataset_key(r["dataset"])
            rows.append({"system": s["system"], "dataset": r["dataset"], "code": key, "name": r.get("name"),
                         "files": r.get("files"), "gigabytes": r.get("gigabytes"), "years": r.get("years"),
                         "ufs": r.get("ufs"), "event_types": readable.get(key, [])})
    out = {**stamp, "systems": [{k: s.get(k) for k in ("system", "name", "files", "gigabytes", "datasets", "years")}
                                for s in top.rows], "datasets": rows}
    cache.parent.mkdir(parents=True, exist_ok=True)
    jobs._write_json(cache, out)
    return out


def dataset(code: str) -> dict:
    """One dataset's anatomy: what the catalog lists by year, what the lake holds (whole years, partitions, rows), the
    confirmation reserve's years, its event types, its columns' roles (meaning, kind, codelists, the years each is
    valid, the codes that mean not recorded) and the links it is a side of."""
    import pegasus_data as pg

    from . import control, gateway

    root = config.data_root()
    key = gateway.dataset_key(code)
    listed = next((d for d in datasets()["datasets"] if d["code"] == key), None)
    if listed is None:
        raise LookupError(f"no dataset {code!r} in the catalog (`pegasus data datasets`)")
    lake = {int(y): v for y, v in pg.lake_coverage(key, root=root).items()}
    try:
        whole = sorted(gateway.lake_whole_years(key))
    except Exception:  # noqa: BLE001 - a dataset with no lake rule holds no whole year
        whole = []
    try:
        events = gateway.event_types(key)
    except Exception:  # noqa: BLE001 - a dataset with no event types: none to read
        events = []
    try:
        roles = pg.roles(key)
    except Exception:  # noqa: BLE001 - a dataset whose columns pegasus_data has not declared
        roles = []
    links = [{"link": name, "left": s.left.dataset, "right": s.right.dataset, "description": s.description}
             for name, s in gateway.link_specs().items()
             if key in (gateway.dataset_key(s.left.dataset), gateway.dataset_key(s.right.dataset))]
    keep = ("column", "role", "entity", "property", "kind", "model", "name", "codelists", "first_year", "last_year",
            "missing", "unit", "measure", "note", "derived", "reviewed")
    return {**listed, "published": pg.explore(key, root=root).rows,
            "lake": [{"year": y, **lake[y]} for y in sorted(lake)],
            "whole_years": whole, "reserved_years": control.reserved(key),
            "event_types": [{k: e.get(k) for k in ("name", "kind", "grain", "classifiers", "marks", "status", "note")}
                            for e in events],
            "roles": [{k: r.get(k) for k in keep} for r in roles], "links": links}


#: role kinds hidden in the record viewer until revealed (author, 2026-10-15)
HIDDEN_KINDS = ("identifier",)
_RECORDS: dict[tuple, object] = {}


def records(code: str, year: int, partition: str | None = None, rows_filter: dict[str, list[str]] | None = None,
            condition: list[dict] | None = None, limit: int = 200, offset: int = 0, reveal: bool = False) -> dict:
    """Records of a dataset as filed, each value with its label (pegasus_data `query`, from the lake only: nothing is
    downloaded). ``partition`` is a partition the lake holds for the year (BR for a national file, else a state; the
    first held by default); ``rows_filter`` keeps records whose columns start with given codes (residence 27...),
    ``condition`` is a condition on roles. Columns whose role is an identifier (`HIDDEN_KINDS`) are left out unless
    ``reveal``. The confirmation reserve's years are refused."""
    import warnings

    import pegasus_data as pg

    from . import control, gateway

    key = gateway.dataset_key(code)
    control.check_reserved(key, [year])
    held = {int(y): v for y, v in pg.lake_coverage(key, root=config.data_root()).items()}.get(int(year))
    if not held:
        raise LookupError(f"{key} {year} is not in the lake: a study that reads it builds it (`pegasus study run`)")
    parts = held.get("uf_codes") or []
    partition = partition or ("BR" if "BR" in parts else (parts[0] if parts else "BR"))
    if parts and partition not in parts:
        raise LookupError(f"{key} {year}: the lake holds {', '.join(parts)}, not {partition}")
    ask = (key, int(year), partition, json.dumps(rows_filter, sort_keys=True), json.dumps(condition, sort_keys=True))
    table = _RECORDS.get(ask)
    if table is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            table = pg.query(key, period=int(year), geography=partition, max_download=0, root=config.data_root(),
                             rows=rows_filter or None, condition=condition or None)
        _RECORDS.clear()                         # one read kept: a person pages one at a time
        _RECORDS[ask] = table
    hidden_cols = {r["column"] for r in pg.roles(key) if r.get("kind") in HIDDEN_KINDS}
    hidden = [c for c in table.column_names if c in hidden_cols or any(c.endswith(f"({h})") for h in hidden_cols)]
    shown = [c for c in table.column_names if reveal or c not in hidden]
    page = table.select(shown).slice(int(offset), int(limit))
    return {"dataset": key, "year": int(year), "partition": partition, "partitions": parts, "total": table.num_rows,
            "columns": shown, "rows": [list(r.values()) for r in page.to_pylist()], "hidden": [] if reveal else hidden,
            "limit": limit, "offset": offset}


# ------------------------------------------------------------------------------------------------- the declaration


def _problems(text: str) -> tuple[list[str], dict | None]:
    """A draft declaration's problems as `study.load` reports them, and its effective choices (each preset key's value
    after its depth), from a file of its own so nothing in the workspace changes."""
    import tempfile

    from . import study

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "draft.yml"
        path.write_text(text, encoding="utf-8")
        try:
            decl = study.load(path)
        except study.DeclarationError as exc:
            lines = [ln.strip("- ").strip().replace(str(path), "the declaration") for ln in str(exc).splitlines()]
            lines = [ln.removeprefix("the declaration: ") for ln in lines if ln and not ln.endswith(":")]
            return lines, None
        except Exception as exc:  # noqa: BLE001 - YAML that does not parse is a problem of the draft, said as such
            return [f"{type(exc).__name__}: {exc}"], None
    effective = {d["key"]: decl.choice(d["key"]) for d in study.DECLARATION if d.get("preset")}
    return [], effective


def declaration(name: str) -> dict:
    """A study's declaration as the window's form edits it: its text (the file, comments and all), the keys it sets,
    its problems, the value each choice takes after its depth, and the description of every key
    (`study.DECLARATION`), the depths' presets and the questions."""
    import yaml

    from . import questions, study

    path = find(name)
    text = path.read_text(encoding="utf-8")
    problems, effective = _problems(text)
    try:
        doc = yaml.safe_load(text) or {}
    except ValueError:
        doc = None
    return {"name": _summary_name(path), "path": str(path), "text": text, "doc": doc, "problems": problems,
            "effective": effective, "keys": study.DECLARATION, "presets": study.PRESETS,
            "questions": [{"id": q.id, "estimand": q.estimand} for q in questions.QUESTIONS.values()]}


def check(text: str) -> dict:
    """A draft's problems and effective choices, nothing written."""
    problems, effective = _problems(text)
    return {"problems": problems, "effective": effective}


def set_key(text: str, key: str, value) -> str:
    """The draft with one key set (``topic.seeds.icd10``), its comments and order kept (ruamel.yaml's round trip);
    ``value`` None removes the key. What the window's form does to the file the person also edits by hand."""
    import io

    from ruamel.yaml import YAML

    from . import study

    if key not in {d["key"] for d in study.DECLARATION}:
        raise ValueError(f"{key!r} is not a declaration key: {', '.join(d['key'] for d in study.DECLARATION)}")
    y = YAML()
    y.preserve_quotes = True
    y.width = 120
    doc = y.load(text) or {}
    *parents, last = key.split(".")
    node = doc
    for p in parents:
        if node.get(p) is None:
            if value is None:
                return text
            node[p] = {}
        node = node[p]
    if value is None:
        node.pop(last, None)
    else:
        node[last] = _flow(value)
    out = io.StringIO()
    y.dump(doc, out)
    return out.getvalue()


def _flow(value):
    """A list or mapping written inline (``[I21, I22]``, ``{dataset: SINASC-DN, ...}``), as declarations are."""
    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    if isinstance(value, list):
        seq = CommentedSeq([_flow(v) for v in value])
        seq.fa.set_flow_style()
        return seq
    if isinstance(value, dict):
        m = CommentedMap({k: _flow(v) for k, v in value.items()})
        m.fa.set_flow_style()
        return m
    return value


def save_declaration(name: str, text: str) -> dict:
    """Write a study's declaration once it has no problem; returns its detail as `declaration` gives it."""
    problems, _ = _problems(text)
    if problems:
        raise ValueError("the declaration has problems, not written: " + "; ".join(problems))
    path = find(name)
    tmp = path.with_suffix(".yml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return declaration(name)


def new_study(name: str, icd10: list[str] | None = None, sinan: list[str] | None = None,
              terms: list[str] | None = None, where: str | list[str] = "BR", period: str = "2014-2023",
              depth: str = "standard", only: list[str] | None = None, contexts: list[str] | None = None,
              records: list[dict] | None = None, scratch: bool = False) -> dict:
    """A new study's declaration, written in the workspace and validated (`study.new`); ``scratch`` keeps it in
    ``studies/scratch/``, a quick look kept as a study of its own until `promote` makes it one of the workspace's."""
    from . import study

    study.new(name, icd10, sinan, terms, where, period, depth, only, contexts,
              scratch_dir() if scratch else studies_dir(), records)
    return declaration(name)


def search(query: str) -> dict:
    """What a study of ``query`` would seed on (`study.search`): ICD-10 codes, SINAN agravos, contexts, roles."""
    from . import study

    return study.search(query)


def price(name: str) -> dict:
    """Price a study's declaration as a run (`jobs.submit`): its scope is resolved in seconds to minutes, beside the
    window, and written to its folder's ``scope.yml``."""
    from . import study

    path = find(name)
    decl = study.load(path)
    return jobs.submit("scope", f"scope {decl.study}", declaration=str(path), study=decl.study,
                       folder=str(study.folder_of(decl)))


# ----------------------------------------------------------------------------- exploration (hypothesis-generating)


_REGISTER: dict[str, tuple] = {}


def _register() -> list:
    """The lead register, read once per state of its part files (27 s for 169,805 leads, 2026-10-15)."""
    from . import leads

    reg = leads.Register()
    names = tuple(sorted(p.name for p in reg.path.glob("part-*.parquet")))
    kept = _REGISTER.get("leads")
    if kept is None or kept[0] != names:
        _REGISTER["leads"] = (names, reg.current())
    return _REGISTER["leads"][1]


#: the filters of the lead register (`tools.find_leads`)
LEAD_FILTERS = ("cls", "tier", "place", "code", "estimand", "min_replication", "status", "direction", "year",
                "min_effect", "max_q")


def leads(filters: dict | None = None, limit: int = 100, offset: int = 0) -> dict:
    """The lead register, best rank first (evidence x effect x replication), filtered (`LEAD_FILTERS`): leads are
    hypothesis-generating, never findings of a study."""
    from . import tools

    filters = {k: v for k, v in (filters or {}).items() if v not in (None, "")}
    unknown = set(filters) - set(LEAD_FILTERS)
    if unknown:
        raise ValueError(f"lead filters {sorted(unknown)}: one of {', '.join(LEAD_FILTERS)}")
    register = _register()
    hits = tools.find_leads(register, **filters)
    return {"register": len(register), "matched": len(hits), "limit": limit, "offset": offset,
            "rows": [tools.lead_row(x) for x in hits[offset: offset + limit]]}


def lead(lead_id: str) -> dict:
    """One lead in full: its lens's statistics and null, its triage with evidence, each replication, its siblings and
    its story."""
    from . import tools

    register = _register()
    x = next((y for y in register if y.id == lead_id), None)
    if x is None:
        raise LookupError(f"no lead {lead_id!r} in the register")
    return {**tools.explain_lead(x, register), "tier": x.tier}


def stories(cls: str | None = None, place: int | None = None, limit: int = 30) -> dict:
    """The leads grouped by place or subset, best story first; ``place`` keeps that place's."""
    from . import leads as leads_mod
    from . import tools

    register = _register()
    if cls:
        register = tools.find_leads(register, cls=cls)
    found = leads_mod.stories(register)
    if place is not None:
        found = [s for s in found if place in s.places]
    return {"matched": len(found), "stories": [
        {"key": s.key, "places": s.places[:20], "rank": s.rank, "fields": s.fields, "flags": s.flags,
         "n_leads": len(s.leads), "leads": [tools.lead_row(m) for m in s.leads[:8]]} for s in found[:limit]]}


def ledger() -> dict:
    """The ledger, the denominator of every error rate: tests by family and actor, and the confirmation reserve."""
    from . import tools

    return tools.ledger_status()


def methods() -> dict:
    """Every method's measured record: the documented events it found, its findings in null worlds."""
    from . import tools

    return tools.method_status()


# ------------------------------------------------------------------------------------ comparison and scratch studies


def compare(names: list[str], table: str, where: list[dict] | None = None, columns: list[str] | None = None,
            order: list[str] | None = None, limit: int = 5000, offset: int = 0) -> dict:
    """One query of a table run over several studies' folders, the rows of each led by its study's name: studies,
    places, periods or case definitions side by side. A column one of them lacks is refused, naming the study."""
    if len(names) < 2:
        raise ValueError("a comparison takes two studies or more")
    out_cols, found, totals = None, [], {}
    for name in names:
        try:
            part = rows(name, table, where, order, columns, limit=limit + offset, offset=0)
        except ValueError as exc:
            raise ValueError(f"{name}: {exc}") from exc
        if out_cols is None:
            out_cols = part["columns"]
        elif part["columns"] != out_cols:
            missing = sorted(set(out_cols) ^ set(part["columns"]))
            raise ValueError(f"{name}'s {table} differs in its columns ({', '.join(missing)}): choose the columns")
        totals[name] = part["total"]
        found += [[name, *r] for r in part["rows"]]
    return {"table": table, "studies": names, "columns": ["study", *out_cols], "totals": totals,
            "total": sum(totals.values()), "rows": found[offset: offset + limit], "limit": limit, "offset": offset}


def scratch_dir() -> Path:
    path = studies_dir() / "scratch"
    path.mkdir(parents=True, exist_ok=True)
    return path


def promote(name: str) -> dict:
    """A scratch study (``studies/scratch/``) made a study of the workspace: its declaration and its folder moved to
    ``studies/``, as they are. A study of that name already there is refused."""
    import shutil

    path = find(name)
    if path.parent != scratch_dir().resolve():
        raise ValueError(f"{name} is not a scratch study ({path})")
    target = studies_dir().resolve() / path.name
    if target.exists() or (studies_dir() / path.stem).exists():
        raise ValueError(f"studies/{path.name} or its folder exists: rename the scratch study first")
    if any(r.get("declaration") == str(path) for r in jobs.active()):
        raise RuntimeError(f"{name} is being run: promote it when its run ends")
    folder = path.parent / _summary_name(path)
    shutil.move(str(path), str(target))
    if folder.exists():
        shutil.move(str(folder), str(studies_dir() / folder.name))
    return study_detail(target.stem)
