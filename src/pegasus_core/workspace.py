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
    study folder's own copy (``study.yml``, ``scope.yml``) is not a declaration."""
    grouped = [p for p in studies_dir().glob("*/*.yml") if not (p.parent / "study.yml").exists()]
    return sorted([*studies_dir().glob("*.yml"), *grouped],
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
    what is deferred or not read and why, what each choice costs; written to ``scope.yml`` in its folder."""
    import yaml

    from . import study

    decl = study.load(find(name))
    resolved = study.resolve(decl)
    out = resolved.to_dict()
    folder = study.folder_of(decl)
    folder.mkdir(parents=True, exist_ok=True)
    # written, not printed: the console wraps long lines and the printed YAML did not parse (2026-10-12)
    (folder / "scope.yml").write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {**out, "written": str(folder / "scope.yml"),
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
        sql_order = f" ORDER BY {', '.join(keys)}" if keys else ""
        keep = ", ".join(col(c) for c in columns) if columns else "*"
        total = con.execute(f'SELECT count(*) FROM "{table}"{sql_where}', params).fetchone()[0]
        cur = con.execute(f'SELECT {keep} FROM "{table}"{sql_where}{sql_order} LIMIT ? OFFSET ?',
                          [*params, int(limit), int(offset)])
        names = [d[0] for d in cur.description]
        data = [list(r) for r in cur.fetchall()]
    return {"table": table, "columns": names, "rows": data, "total": total, "limit": limit, "offset": offset}
