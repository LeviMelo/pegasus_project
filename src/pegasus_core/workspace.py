"""The workspace as a person sees it (ARCHITECTURE §10.6; ADR-0038): the read models the ``pegasus`` command line and the
desktop window (pegasus_app) share, so neither computes what the other lacks.

The workspace is a directory (`jobs.workspace`): ``studies/`` holds the declarations and their folders, ``runs/`` the
runs (`jobs`). Everything here reads those files and the engine's own functions; nothing is held only in memory.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import config, jobs

__keyless__ = True


#: seconds a large read is kept in memory after its last use (`_kept`): a national year of records (1.5 million rows)
#: and the lead register (169,805 leads) had stayed in the window's service for good, beside the machine's other work
IDLE_S = 600
_KEPT: dict[str, tuple] = {}            # name -> (key, value, last used)
_SWEEPER: list = []


def _kept(name: str, key, make):
    """``make()``'s value for ``key``, kept in memory while it is used and released `IDLE_S` seconds after its last
    use; one value per ``name`` (a person reads one partition, one register, at a time)."""
    import threading

    held = _KEPT.get(name)
    if held is None or held[0] != key:
        _KEPT.pop(name, None)                 # the earlier read released before the next is made
        held = (key, make(), time.time())
    _KEPT[name] = (held[0], held[1], time.time())
    if not _SWEEPER:
        def sweep():
            while True:
                time.sleep(60)
                for n, (_, _, used) in list(_KEPT.items()):
                    if time.time() - used > IDLE_S:
                        _KEPT.pop(n, None)
        _SWEEPER.append(threading.Thread(target=sweep, daemon=True, name="workspace-idle"))
        _SWEEPER[0].start()
    return held[1]


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


#: each part of the analytic body as a reader names it: a title and what it means for a paper
PARTS = {
    "scope": ("Sources and their reasons", "Each source read says why, and each left out says why not"),
    "descriptive epidemiology": ("Rates with intervals", "Rates with their 95 % intervals and denominators"),
    "descriptive: geography": ("Rates by place", "The whole area and its regions"),
    "descriptive: case definition": ("Case definition", "Confirmed cases rated apart where a source records them"),
    "descriptive: perinatal denominators": ("Perinatal denominators", "Pregnancy and perinatal events rated per live birth"),
    "descriptive: period": ("Whole-period estimates", "Each rate over the whole period as well as by year"),
    "trends": ("Trends", "Annual percent changes with their intervals, crude and age-sex adjusted"),
    "seasons": ("Seasonality", "The monthly pattern with its intervals"),
    "places": ("Municipalities", "Rates and smoothed standardised ratios for every municipality"),
    "associations": ("Associations with contexts", "How the rates relate to municipal contexts"),
    "case fatality": ("Case fatality", "Deaths among the cases, crude and adjusted, with its trend"),
    "groups": ("Case mix", "Who the cases are: their characteristics, with intervals"),
    "measures": ("Measures", "The topic's own quantities, such as age or length of stay"),
    "persons": ("Persons", "Linked persons and what happened to them"),
    "completeness": ("Completeness", "How many events could be placed and counted"),
    "completeness across systems": ("Completeness across sources", "Cases found in one source and missed by another"),
    "data quality": ("Data quality", "What the sources fail to record, year by year"),
    "linkage": ("Record linkage", "The links between sources, with their false-match rates"),
    "hypotheses": ("Declared hypotheses", "Answers to the tests declared before looking"),
    "relations": ("Relations between fields", "How the topic's fields move together"),
    "screen": ("Relations screen", "The topic's fields against every other field"),
    "findings": ("Exploratory findings", "Signals worth a look, each checked against recording artefacts"),
    "figures": ("Figures", "A series and a map for each field"),
    "methods": ("Methods", "The methods text"),
    "codebook": ("Codebook", "Every table's columns described"),
    "report": ("Report", "The study's report"),
    "every step ran": ("Every step ran", "No step of the analysis failed"),
}


def _titled(parts: list[dict]) -> list[dict]:
    return [{**p, "title": PARTS.get(p["part"], (p["part"].capitalize(), ""))[0],
             "about": PARTS.get(p["part"], ("", ""))[1]} for p in parts]


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
    decls = declarations()
    hits = [d for d in decls if d.stem == name] or [d for d in decls if _summary_name(d) == name]
    if not hits:
        raise LookupError(f"no study {name!r} in {studies_dir()}")
    return hits[0].resolve()


def _summary_name(path: Path) -> str:
    """A declaration's study name (its ``study:``, else its file name), read once per version of the file: `find` asks
    it of every declaration, and parsing them all on each call took 4 of the cards' 5.5 s (2026-10-19)."""
    import yaml

    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return path.stem
    if key not in _NAMES:
        try:
            _NAMES[key] = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("study") or path.stem
        except (OSError, ValueError):
            _NAMES[key] = path.stem
    return _NAMES[key]


_NAMES: dict[tuple[str, int], str] = {}


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
            scope = yaml.load((folder / "scope.yml").read_text(encoding="utf-8"),
                              Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
        except ValueError:
            scope = None
    files = []
    if folder.exists():
        for f in sorted(folder.rglob("*")):
            if f.is_file() and not f.name.endswith(".tmp"):
                files.append({"path": f.relative_to(folder).as_posix(), "bytes": f.stat().st_size,
                              "modified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime))})
    parts = body(folder)
    return {**s, "text": path.read_text(encoding="utf-8"), "scope": scope, "parts": _titled(parts) if parts else parts,
            "files": files,
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


#: what a folder whose study.duckdb cannot be read needs: before 2026-10-14 its tables were views of files by their
#: path on the machine that wrote them, and a folder moved or written elsewhere reads none
UNREADABLE = ("its study.duckdb reads files this folder does not hold (written before 2026-10-14, when its tables were "
              "views of paths elsewhere): write its products again, `pegasus study run {name} --products-only`")


def tables(name: str) -> list[dict]:
    """The tables of a study (the views of its ``study.duckdb``): rows and columns with their types; a table that
    cannot be read is listed with why, so the rest of the folder is still read."""
    import duckdb

    with _connect(name) as con:
        out = []
        for (t,) in con.execute("SELECT table_name FROM information_schema.tables ORDER BY table_name").fetchall():
            try:
                cols = [{"name": c, "type": ty} for c, ty, *_ in con.execute(f'DESCRIBE "{t}"').fetchall()]
                out.append({"table": t, "rows": con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0],
                            "columns": cols})
            except duckdb.Error as exc:
                out.append({"table": t, "rows": None, "columns": [],
                            "error": UNREADABLE.format(name=name) if isinstance(exc, duckdb.IOException)
                            else f"{type(exc).__name__}: {exc}"})
        return out


#: the comparisons a filter may use (`rows`)
FILTER_OPS = ("=", "!=", "<", "<=", ">", ">=", "in", "like", "is null", "is not null")


def rows(name: str, table: str, where: list[dict] | None = None, order: list[str] | None = None,
         columns: list[str] | None = None, limit: int = 200, offset: int = 0) -> dict:
    """Rows of a study's table: ``where`` a list of ``{column, op, value}`` (`FILTER_OPS`; ``in`` takes a list),
    ``order`` columns (``-col`` descending), ``columns`` those kept. Every name is checked against the table, every
    value is a parameter. Returns the columns, the rows, and the count before ``limit``."""
    import duckdb

    with _connect(name) as con:
        known = {t for (t,) in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        if table not in known:
            raise LookupError(f"{name} has no table {table!r}: {', '.join(sorted(known))}")
        try:
            cols = [c for c, *_ in con.execute(f'DESCRIBE "{table}"').fetchall()]
        except duckdb.IOException as exc:
            raise ValueError(UNREADABLE.format(name=name)) from exc

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


#: the version of a catalog row's fields, in the kept catalog's stamp: a row that gains a field is listed again
CATALOG_SHAPE = 2


def datasets(refresh: bool = False) -> dict:
    """What DATASUS publishes, as pegasus_data's catalog lists it: its systems and their datasets (files, gigabytes,
    years, states), each with the event types a study can read of it. Kept in ``PEGASUS_HOME/workspace/datasets.json``
    for the catalog's crawl: listing the 24 systems' datasets takes seconds."""
    import pegasus_data as pg

    from . import gateway

    root = config.data_root()
    top = pg.explore(root=root)
    cache = config.home() / "workspace" / "datasets.json"
    # pegasus_data's commit, not its version: a dataset described or given an event type is a commit
    stamp = {"as_of": str(top.as_of), "data_version": config.data_code_version(), "shape": CATALOG_SHAPE}
    if cache.exists() and not refresh:
        try:
            kept = json.loads(cache.read_text(encoding="utf-8"))
            if {k: kept.get(k) for k in stamp} == stamp:
                return kept
        except ValueError:
            pass
    readable: dict[str, list[str]] = {}
    unready: dict[str, str] = {}
    for ds in gateway.event_datasets():
        key = gateway.dataset_key(ds)
        readable[key] = [e["name"] for e in gateway.event_types(ds)]
        why = _unreadable(ds, readable[key])
        if why:
            unready[key] = why
    rows: dict[str, dict] = {}
    for s in top.rows:
        for r in pg.explore(s["system"], root=root).rows:
            key = gateway.dataset_key(r["dataset"])
            published = {"system": s["system"], "files": r.get("files"), "gigabytes": r.get("gigabytes"), "years": r.get("years"),
                         "ufs": r.get("ufs")}
            if key in rows:
                # one dataset published twice (SIA's APAC on the FTP and as Dados Abertos exports): one row, under its own
                # system, the other publication beside it
                kept = rows[key]
                if s["system"] == str(r["dataset"]).split(".")[0] and kept["system"] != s["system"]:
                    rows[key] = {**kept, **published, "also": [*kept["also"], {k: kept[k] for k in published}]}
                else:
                    kept["also"].append(published)
                continue
            desc = _description(r["dataset"])
            events = readable.get(key, [])
            rows[key] = {**published, "dataset": r["dataset"], "code": key, "name": r.get("name"),
                         "official_name": desc.get("official_name"), "event_types": events,
                         "also": [], "what_it_is": desc.get("what_it_is"),
                         "use": ("incomplete" if key in unready else "study") if events else desc.get("use") or
                         ("described" if desc.get("what_one_row_is") else "undescribed"),
                         "why_no_event_type": unready.get(key) if events else desc.get("why_no_event_type")}
    rows = list(rows.values())
    out = {**stamp, "systems": [{k: s.get(k) for k in ("system", "name", "files", "gigabytes", "datasets", "years")}
                                for s in top.rows], "datasets": rows}
    cache.parent.mkdir(parents=True, exist_ok=True)
    jobs._write_json(cache, out)
    return out


def _unreadable(dataset: str, events: list[str]) -> str | None:
    """Why no study can read any of a dataset's event types, in words, or None when one can: a study places and
    standardises events by their residence, sex and age (`gateway._strata`), and a dataset whose roles do not say which
    columns hold them has event types a study cannot use (SISCAN's 15 had no age, 2026-10-19)."""
    import re

    from . import gateway

    whys = []
    for event in events:
        try:
            gateway._strata(dataset, event)
            return None
        except LookupError as e:
            text = re.sub(r"^[\w.-]+: ", "", str(e))
            m = re.match(r"no (\w+) stratum in pegasus_data's roles", text)
            whys.append(f"No column of its records is known to hold the {m.group(1)}, so a study cannot place or "
                        "standardise its events yet" if m else text)
    return whys[0] if whys else None


#: what pegasus_data says of a dataset in words (`pg.info`): its names, what it is, what one row is, its unit of
#: analysis, its known biases and gotchas, and what PegaSUS can use it for when it holds no event type
DESCRIPTION_KEYS = ("official_name", "translated_name", "what_it_is", "what_one_row_is", "unit_of_analysis",
                    "known_biases", "gotchas", "use", "why_no_event_type")


def _description(dataset: str) -> dict:
    """What pegasus_data says of a dataset (`DESCRIPTION_KEYS`), each text as a reader of the window takes it
    (`reader_text`); `pg.info` and the command line keep the curation's full text."""
    import pegasus_data as pg

    try:
        info = pg.info(dataset).as_dict()
    except Exception:  # noqa: BLE001 - a dataset pegasus_data does not describe is said so, not hidden
        return {}
    merged = {**(info.get("identity") or {}), **(info.get("documentation") or {})}
    out = {k: merged[k] for k in DESCRIPTION_KEYS if merged.get(k) not in (None, "", [])}
    return {k: ([reader_text(x) for x in v] if isinstance(v, list) else reader_text(v) if isinstance(v, str) else v)
            for k, v in out.items()}


#: a sentence of a curation's history: "Corrected 2026-10-08: ...", "Until 2026-10-08 it was an alias ..."
_HISTORY = re.compile(r"^(?:Corrected|Until|Since|Before|Renamed|Earlier)\b[^.]*?\b20\d\d-\d\d-\d\d\b")
#: a reference to the project's own records inside a text: (ADR-0077), OQ-90, a bare date in brackets
_RECORD = re.compile(r"\s*\b(?:ADR|OQ)-?\d+\b[;,]?|\s*\(\s*20\d\d-\d\d-\d\d\s*\)")


def reader_text(text: str) -> str:
    """A curation text as the window shows it: without the sentences of its own history (when an entry was
    corrected, what it said before) and without references to the project's decision and question records, which
    belong to the record of the work, not to what a researcher reads about a dataset (2026-10-19)."""
    text = _RECORD.sub("", text)
    text = re.sub(r"\s*\(\s*[;,]?\s*\)", "", re.sub(r"\(\s*[;,]\s*", "(", text))
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    return " ".join(x for x in sentences if not _HISTORY.match(x)).strip()


def dataset(code: str) -> dict:
    """One dataset's anatomy: what it is in words (`_description`), what the catalog lists by year, what the lake holds
    (whole years, partitions, rows), the confirmation reserve's years, its event types, its columns' roles (meaning,
    kind, codelists, the years each is valid, the codes that mean not recorded) and the links it is a side of."""
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
    return {**listed, "description": _description(listed["dataset"]), "published": pg.explore(key, root=root).rows,
            "lake": [{"year": y, **lake[y]} for y in sorted(lake)],
            "whole_years": whole, "reserved_years": control.reserved(key),
            "event_types": [{k: e.get(k) for k in ("name", "kind", "grain", "classifiers", "marks", "status", "note")}
                            for e in events],
            "roles": [{k: r.get(k) for k in keep} for r in roles], "links": links}


#: role kinds hidden in the record viewer until revealed (author, 2026-10-15)
HIDDEN_KINDS = ("identifier",)


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
    def read():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return pg.query(key, period=int(year), geography=partition, max_download=0, root=config.data_root(),
                            rows=rows_filter or None, condition=condition or None)
    table = _kept("records", ask, read)
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
    """A draft's problems, its keys as parsed (the engine's reading, so the window parses no YAML of its own) and its
    effective choices; nothing written."""
    import yaml

    problems, effective = _problems(text)
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        doc = None
    return {"problems": problems, "doc": doc, "effective": effective}


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


def _register() -> list:
    """The lead register, read once per state of its part files (27 s for 169,805 leads, 2026-10-15) and released
    when unused (`_kept`)."""
    from . import leads

    reg = leads.Register()
    names = tuple(sorted(p.name for p in reg.path.glob("part-*.parquet")))
    return _kept("leads", names, reg.current)


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
    """The ledger, the denominator of every error rate: tests by family and actor, and the confirmation reserve; read
    once per state of its part files (16 s for 716,134 tests, 2026-10-17) and released when unused (`_kept`)."""
    from . import control, tools

    parts = tuple(sorted(p.name for p in control.Ledger().path.glob("part-*.parquet")))
    return _kept("ledger", parts, tools.ledger_status)


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


# ------------------------------------------------------------------------- codes, contexts and the priced scope


def codes(code: str, column: str, year: int, partition: str | None = None) -> dict:
    """A column's values in one year as the lake holds them, each with the label pegasus_data gives it for that year
    (its codelist's validity window; an undecoded code shows as itself), the records holding it, and the records with
    none: what a code means in that vintage, and how complete the column is. From the lake only; the reserve's years
    are refused, an identifier column is refused."""
    import re
    import warnings

    import pegasus_data as pg
    import pyarrow.compute as pc

    from . import control, gateway

    key = gateway.dataset_key(code)
    control.check_reserved(key, [year])
    roles = {r["column"]: r for r in pg.roles(key)}
    if roles.get(column, {}).get("kind") in HIDDEN_KINDS:
        raise PermissionError(f"{column} identifies people or records: its values are not listed")
    held = {int(y): v for y, v in pg.lake_coverage(key, root=config.data_root()).items()}.get(int(year))
    if not held:
        raise LookupError(f"{key} {year} is not in the lake")
    parts = held.get("uf_codes") or []
    partition = partition or ("BR" if "BR" in parts else (parts[0] if parts else "BR"))

    def read():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return pg.query(key, period=int(year), geography=partition, select=[column], max_download=0,
                            root=config.data_root())
    table = _kept("codes", (key, int(year), partition, column), read)
    name = next((c for c in table.column_names if c == column or c.endswith(f"({column})")), None)
    if name is None:
        raise LookupError(f"{key} {year} holds no column {column}")
    counts = pc.value_counts(table.column(name)).to_pylist()
    rows, empty = [], 0
    for c in counts:
        value = c["values"]
        if value is None or value == "":
            empty += c["counts"]
            continue
        m = re.fullmatch(r"(.*) \(([^()]*)\)", str(value))
        rows.append({"value": str(value), "code": m.group(2) if m else str(value),
                     "label": m.group(1) if m else None, "records": c["counts"]})
    rows.sort(key=lambda r: -r["records"])
    total = table.num_rows
    role = roles.get(column) or {}
    return {"dataset": key, "column": column, "name": role.get("name"), "kind": role.get("kind"),
            "codelists": role.get("codelists"), "missing": role.get("missing"), "year": int(year),
            "partition": partition, "records": total, "empty": empty,
            "filled_share": round(1 - empty / total, 4) if total else None, "values": rows}


def contexts() -> list[dict]:
    """The municipal contexts a study can relate its rates to (pegasus_data's declared fields): its short name, what it
    measures, its unit, years, denominator and source."""
    from . import gateway

    out = []
    for name, spec in sorted(gateway.declared_fields().items()):
        out.append({"context": name, "label": spec.get("label"), "what": spec.get("what") or spec.get("description"),
                    "unit": spec.get("unit"), "years": spec.get("years"), "over": spec.get("over"),
                    "source": spec.get("source") or (f"IBGE SIDRA table {spec['table']}" if spec.get("table") else None),
                    "verified": spec.get("verified")})
    return out


def priced(name: str) -> dict | None:
    """A study's last priced scope (`scope`, beside its declaration), else the scope its last run read, with when it
    was written: what the study reads and why, and the minutes behind each choice."""
    import yaml

    path = find(name)
    for source, f in (("priced", path.with_name(f"{path.stem}.scope.yml")),
                      ("run", path.parent / _summary_name(path) / "scope.yml")):
        if f.exists():
            return {"source": source, "path": str(f),
                    "written": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime)),
                    # the C parser: a national exhaustive scope is megabytes, 7 s in the pure-Python one
                    "scope": yaml.load(f.read_text(encoding="utf-8"), Loader=getattr(yaml, "CSafeLoader",
                                                                                      yaml.SafeLoader))}
    return None


def methods_of(name: str, table: str) -> dict:
    """How a study's table's numbers were made: the method of every measure it holds (`study.MEASURES`, the sentence
    the report and METHODS.md print), found as a column of the table or a value of its `measure` column, and the
    folder's provenance (when, on which code and data)."""
    from . import study

    listed = {t["table"]: t for t in tables(name)}
    if table not in listed:
        raise LookupError(f"{name} has no table {table!r}")
    if listed[table].get("error"):
        raise ValueError(listed[table]["error"])
    known = {t: [c["name"] for c in v["columns"]] for t, v in listed.items()}
    import re

    held = set(known[table])
    # a view's columns name the measure they are filtered on in its own SQL (study.RATES_VIEW: `max(estimate) FILTER
    # (WHERE measure = 'rate_ratio' ...) AS ratio_to_brazil`): read from there, never from the column's spelling
    view = getattr(study, f"{table.upper()}_VIEW", "")
    columns = {col: m for m, col in re.findall(r"FILTER \(WHERE measure = '(\w+)'[^)]*\) AS (\w+)", view)}
    held |= set(columns.values())
    if "measure" in held:
        with _connect(name) as con:
            held |= {m for (m,) in con.execute(f'SELECT DISTINCT measure FROM "{table}"').fetchall() if m}
    measures = [{"measure": m, "method": text, "columns": sorted(c for c, x in columns.items() if x == m)}
                for m, text in study.MEASURES.items() if m in held]
    prov = {}
    path = folder(name) / "provenance.json"
    if path.exists():
        p = json.loads(path.read_text(encoding="utf-8"))
        prov = {k: p.get(k) for k in ("written", "code_version", "data_version", "depth", "seconds")}
    return {"study": name, "table": table, "measures": measures, "provenance": prov}


# ------------------------------------------------------------------------------------- a study as the window draws it


STATES = {"RO": "Rondônia", "AC": "Acre", "AM": "Amazonas", "RR": "Roraima", "PA": "Pará", "AP": "Amapá",
          "TO": "Tocantins", "MA": "Maranhão", "PI": "Piauí", "CE": "Ceará", "RN": "Rio Grande do Norte",
          "PB": "Paraíba", "PE": "Pernambuco", "AL": "Alagoas", "SE": "Sergipe", "BA": "Bahia", "MG": "Minas Gerais",
          "ES": "Espírito Santo", "RJ": "Rio de Janeiro", "SP": "São Paulo", "PR": "Paraná", "SC": "Santa Catarina",
          "RS": "Rio Grande do Sul", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "GO": "Goiás",
          "DF": "Distrito Federal", "BR": "Brazil"}
_STATE_CODES = {"11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA",
                "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA",
                "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
                "51": "MT", "52": "GO", "53": "DF"}


def place_name(where) -> str:
    """A declaration's ``where`` as a person reads it: Brazil, a state's name, or the states named."""
    items = where if isinstance(where, list) else [where]
    names = []
    for w in items:
        w = str(w)
        code = _STATE_CODES.get(w, w) if w.isdigit() and len(w) == 2 else w
        names.append(STATES.get(code.upper(), f"municipality {w}" if w.isdigit() else w))
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _icd10():
    """The ICD-10 tree as {code: (label, parent)}, read once."""
    if "icd10" not in _TREE:
        from . import gateway

        _TREE["icd10"] = {r["code"]: (r["label"], r["parent"]) for r in gateway.code_tree("ICD10").to_pylist()}
    return _TREE["icd10"]


_TREE: dict = {}


def _agravo_name(agravo: str) -> str | None:
    """A SINAN agravo's name as its source writes it ("Dengue"), from its dataset's description; None when undescribed."""
    return _description(f"SINAN-{agravo}").get("official_name")


def _topic(doc: dict) -> str:
    """What a study is about, from its declaration's seeds read as names: a single SINAN agravo's name; a condition's
    name; up to three ICD-10 codes by their labels, more by the smallest ICD-10 group holding them all; SINAN agravos
    when no code names the topic; the label terms."""
    seeds = ((doc.get("topic") or {}).get("seeds") or {})
    parts = [str(r.get("name") or r.get("dataset")) for r in seeds.get("records") or []]
    codes = [str(c).replace(".", "") for c in seeds.get("icd10") or []]
    agravos = list(seeds.get("sinan") or [])
    if len(agravos) == 1 and not parts:
        # one notifiable disease names the topic as its readers do ("Dengue"); its ICD-10 codes are its definition
        name = _agravo_name(agravos[0])
        if name:
            return "; ".join([name, *(seeds.get("terms") or [])])
    if codes:
        tree = _icd10()
        if len(codes) <= 3:
            parts.append(", ".join(tree.get(c, (c, None))[0] for c in codes))
        else:
            def chain(c):
                out = []
                while c:
                    out.append(c)
                    c = tree.get(c, (None, None))[1]
                return out
            common = set(chain(codes[0]))
            for c in codes[1:]:
                common &= set(chain(c))
            shared = [c for c in chain(codes[0]) if c in common]
            parts.append(f"{tree[shared[0]][0]} ({shared[0]})" if shared else ", ".join(codes))
    if not codes:
        parts += [f"{a} (SINAN)" for a in seeds.get("sinan") or []]
    parts += list(seeds.get("terms") or [])
    return "; ".join(parts) or str(doc.get("study"))


def _region_name(r: dict) -> str:
    """A region's name: its own, a state's by its code, else its place without its code ("27001 AL 1ª Região de
    Saúde")."""
    import re

    place = str(r.get("place") or "")
    if r.get("place_name"):
        return str(r["place_name"])
    if r.get("geography") == "state" and place in _STATE_CODES:
        return STATES[_STATE_CODES[place]]
    return re.sub(r"^\d+\s+", "", place)


def _reading(field: str, roles: dict, label: str = "", place: str | None = None) -> str:
    """How a field counts its events, in words: the classifier column it reads (its role's name) or codes anywhere on
    the record; where it places them (the residence, or the place the source's stratum stands for, ``place``; else the
    support named in its id or, for a condition's field, its label's " — support:COLUMN")."""
    import re

    m = re.match(r"[^:]+:[^:]+:([A-Za-z_]+)\[(.*?)\]", field)
    how = "anywhere on the record" if field.split(":")[2].startswith("mentions") else \
        (roles.get(m.group(1)) or m.group(1)) if m else "the event's own classification"
    s = re.search(r"support=([A-Z_]+)", field) or re.search(r" — support:([A-Z_]+)", label)
    where = f"placed by {roles.get(s.group(1)) or s.group(1)}" if s else f"placed by {place or 'residence'}"
    return f"{how}; {where}"


_SUMMARIES: dict[str, tuple] = {}


def summary(name: str) -> dict:
    """`_summary_of` kept until the study's declaration, its folder, its last run or the code that summarises it (the
    engine's, pegasus_data's) changes: in memory, and on disk in ``PEGASUS_HOME/workspace/summaries``, so a window just
    opened draws its cards at once (21 studies took 6-10 s to summarise cold)."""
    path = find(name)
    prov = path.parent / _summary_name(path) / "provenance.json"
    stamp = [path.stat().st_mtime, prov.stat().st_mtime if prov.exists() else None,
             [[r["id"], r["state"]] for r in jobs.runs(limit=1, study=_summary_name(path))],
             config.code_version(), config.data_code_version()]
    kept = _SUMMARIES.get(name)
    if kept is not None and kept[0] == stamp:
        return kept[1]
    disk = config.home() / "workspace" / "summaries" / f"{name.replace('/', '__')}.json"
    try:
        held = json.loads(disk.read_text(encoding="utf-8"))
        if held.get("stamp") == stamp:
            _SUMMARIES[name] = (stamp, held["summary"])
            return held["summary"]
    except (OSError, ValueError):
        pass
    out = _summary_of(name)
    _SUMMARIES[name] = (stamp, out)
    disk.parent.mkdir(parents=True, exist_ok=True)
    jobs._write_json(disk, {"stamp": stamp, "summary": out})
    return out


def _summary_of(name: str) -> dict:
    """A study as the window shows it first: who and what it is about in words, its state, and for each field it read
    (the topic counted one way) the period's rate with its interval, the rates by year, the trend, the rates by sex,
    age band, race and region, and the case fatality; each number as the folder's estimates hold it."""

    import pegasus_data as pg
    import yaml

    from . import gateway

    path = find(name)
    s = _summary(path)
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        doc = {}
    out = {**s, "title": doc.get("title") or _topic(doc), "place": place_name(doc.get("where", "BR")),
           "fields": []}
    if not s["written"]:
        return out
    with _connect(name) as con:
        if "estimates" not in {t for (t,) in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}:
            # a folder written before its rates were kept in one `estimates` table (the smoke folders of 2026-10-13)
            return {**out, "note": "This folder was written by an earlier version of PegaSUS and holds no table of rates: "
                                   "run the study again to see them here."}

        def q(sql, params=()):
            cur = con.execute(sql, list(params))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]

        own = "geography IN ('area', 'national')"
        heads = q(f"""SELECT field, label, dataset, unit, denominator_kind, first, last, numerator AS events,
                             estimate, low, high
                      FROM estimates WHERE section = 'rates' AND {own} AND stratum IS NULL AND period_kind = 'period'
                        AND measure = 'crude_rate' AND label NOT LIKE '%— race:%'
                      ORDER BY strpos(field, 'support=') > 0, length(field)""")
        roles_of: dict[str, dict] = {}
        for h in heads:
            ds = h["dataset"]
            if ds not in roles_of:
                try:
                    roles_of[ds] = {r["column"]: r.get("name") for r in pg.roles(ds)}
                except Exception:  # noqa: BLE001 - a dataset without roles reads its columns as named
                    roles_of[ds] = {}
            f, label = h["field"], h["label"]

            def rate(measure, extra="", field=f, label=label):
                return q(f"""SELECT first, last, numerator AS events, estimate, low, high, stratum, geography,
                                    place, place_name, unit FROM estimates
                             WHERE section = 'rates' AND field = ? AND label = ? AND measure = ? {extra}""",
                         (field, label, measure))
            std = rate("standardised_rate", f"AND {own} AND stratum IS NULL AND period_kind = 'period'")
            series = {r["first"]: r for r in rate("crude_rate", f"AND {own} AND stratum IS NULL AND period_kind = 'year'")}
            std_series = {r["first"]: r for r in rate("standardised_rate",
                                                      f"AND {own} AND stratum IS NULL AND period_kind = 'year'")}
            trend = q(f"""SELECT variable, estimate, low, high, unit FROM estimates
                          WHERE section = 'trends' AND field = ? AND {own} AND stratum IS NULL AND measure = 'aapc'""",
                      (f,))
            strata = rate("crude_rate", f"AND {own} AND stratum IS NOT NULL AND period_kind = 'period'")
            races = q(f"""SELECT label, estimate, low, high, numerator AS events FROM estimates
                          WHERE section = 'rates' AND field = ? AND label LIKE ? AND {own} AND stratum IS NULL
                            AND period_kind = 'period' AND measure = 'crude_rate'""", (f, label + " — race:%"))
            regions = rate("crude_rate", "AND geography NOT IN ('area', 'national', 'reference', 'municipality') "
                                         "AND stratum IS NULL AND period_kind = 'period'")
            fatality = q("""SELECT period_kind, first, last, estimate, low, high, numerator, denominator, measure
                            FROM estimates WHERE section = 'case fatality' AND field = ? AND stratum IS NULL
                              AND measure IN ('case_fatality', 'case_fatality_adjusted', 'mortality_after')
                            ORDER BY measure, first""", (f,))

            def ci(r):
                return None if r is None else {"estimate": r["estimate"], "low": r["low"], "high": r["high"]}
            out["fields"].append({
                "field": f, "label": label.split(": ", 1)[-1].split(" — ")[0], "event": label.split(":")[0],
                "dataset": ds, "reading": _reading(f, roles_of[ds], label, gateway.place_label(ds)),
                "primary": "support=" not in f and " — support:" not in label,
                "unit": h["unit"], "per": h["denominator_kind"], "first": h["first"], "last": h["last"],
                "events": h["events"], "crude": ci(h), "standardised": ci(std[0] if std else None),
                "series": [{"year": y, "events": r["events"], **ci(r),
                            "standardised": ci(std_series.get(y))} for y, r in sorted(series.items())],
                "trend": [{"of": t["variable"], "estimate": t["estimate"], "low": t["low"], "high": t["high"],
                           "unit": t["unit"]} for t in trend],
                "sex": [{"group": r["stratum"].removeprefix("sex: "), **ci(r)} for r in strata
                        if r["stratum"].startswith("sex: ") and "age" not in r["stratum"]],
                "age": [{"group": r["stratum"].removeprefix("age "), **ci(r)} for r in strata
                        if r["stratum"].startswith("age ")],
                "race": [{"group": r["label"].rsplit("race: ", 1)[-1], "events": r["events"], **ci(r)} for r in races],
                # a region's name is its place without its code ("27001 AL 1ª Região de Saúde")
                "regions": [{"level": r["geography"], "place": _region_name(r), **ci(r)} for r in regions],
                "case_fatality": [{"measure": r["measure"], "period": r["period_kind"], "first": r["first"],
                                   "last": r["last"], "deaths": r["numerator"], "cases": r["denominator"], **ci(r)}
                                  for r in fatality],
            })
    return out


def cards() -> list[dict]:
    """Every study as a card: its title, place and period, its state, and its fields as the period's rate with its
    interval, the trend and the rates by year (each source's own reading of the topic, most events first: a card that
    showed one field had shown suicide in Rio Grande do Sul by its admissions, 0.15 per 100,000, not its deaths)."""
    out = []
    for path in declarations():
        name = _summary_name(path)
        try:
            s = summary(name)
        except Exception as exc:  # noqa: BLE001 - a study whose folder cannot be read is a card that says why
            s = {**_summary(path), "title": name, "place": None, "fields": [], "error": f"{type(exc).__name__}: {exc}"}
        heads = sorted((f for f in s["fields"] if f["primary"]), key=lambda f: -(f["events"] or 0))[:4]
        out.append({k: s.get(k) for k in ("name", "title", "place", "period", "depth", "group", "written", "body",
                                          "last_run", "error", "note")}
                   | {"fields": [{
                       "label": h["label"], "event": h["event"], "dataset": h["dataset"], "reading": h["reading"],
                       "unit": h["unit"], "events": h["events"], "crude": h["crude"],
                       "trend": next((t for t in h["trend"] if str(t["of"] or "").startswith("crude")), None),
                       "series": [{"year": p["year"], "estimate": p["estimate"]} for p in h["series"]]}
                       for h in heads]})
    return out
