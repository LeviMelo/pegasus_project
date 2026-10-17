"""The ``pegasus`` command (ARCHITECTURE §10.6; ADR-0038): nouns and verbs over the engine, each the peer of an
action in the desktop window (pegasus_app), which calls the same functions (`workspace`, `jobs`). ``--json`` before
the noun makes a command print JSON instead of tables, for scripts and for an assistant the person consults."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="pegasus", help="PegaSUS: epidemiological studies of Brazil's health data, each from one "
                  "declaration. A study: `study search` -> `study new` -> `study scope` -> `study run` -> `study "
                  "audit`; `run` follows and stops runs; `data` shows what DATASUS holds; `explore` is the "
                  "hypothesis-generating machinery; `context` prints what an outside assistant needs.",
                  no_args_is_help=True, pretty_exceptions_enable=False)
study_app = typer.Typer(help="Studies: design, price, run, check and export them.", no_args_is_help=True)
run_app = typer.Typer(help="Runs: every heavy job, detached, admitted by memory; follow, list and stop them.",
                      no_args_is_help=True)
data_app = typer.Typer(help="The data: datasets, their columns and what reads them.", no_args_is_help=True)
plot_app = typer.Typer(help="Plots and maps of a study's tables: Vega-Lite files in its folder, rendered for a paper.",
                       no_args_is_help=True)
store_app = typer.Typer(help="The engine's store: plans, link runs, keys and caches.", no_args_is_help=True)
explore_app = typer.Typer(help="Exploration (hypothesis-generating): fits, scans, leads, stories, the ledger.",
                          no_args_is_help=True)
app.add_typer(study_app, name="study")
app.add_typer(run_app, name="run")
app.add_typer(plot_app, name="plot")
app.add_typer(data_app, name="data")
app.add_typer(store_app, name="store")
app.add_typer(explore_app, name="explore")
console = Console()
STATE = {"json": False}


@app.callback()
def _root(json_: bool = typer.Option(False, "--json", help="print JSON instead of tables")) -> None:
    STATE["json"] = json_


def _emit_json(obj) -> bool:
    """Print ``obj`` as JSON when ``--json`` was asked; whether it was."""
    if STATE["json"]:
        sys.stdout.write(json.dumps(obj, indent=1, default=str, ensure_ascii=False) + "\n")
    return STATE["json"]

Years = typer.Option("2010-2023", help="first-last year of the fitted monolith")


def _years(text: str) -> list[int]:
    a, b = text.split("-")
    return list(range(int(a), int(b) + 1))


def _session(dataset: str, event: str, years: str, graph: str, grain: str = "year"):
    from . import tools

    return tools.Session(dataset, event, _years(years), graph, source={"grain": grain} if grain != "year" else {})


@explore_app.command("fit")
def fit(dataset: str, event: str, blocks: list[str], years: str = Years, graph: str = "contiguity",
        device: str | None = None,
        source: str = typer.Option(None, help="a non-default reader as JSON, e.g. a declared field's "
                                               "(`fields.measure_source`); block * is the event type without its tree"),
        cold: bool = typer.Option(False, help="start from nothing, not from the best related stored fit")) -> None:
    """Fit monolith blocks (chapters) and store them with their robust refit, under the machine's job slot (`jobs`);
    one ``BLOCK <name> <summary>`` line each, and a failed block is reported and the next one fitted."""
    import time

    from . import jobs, monolith

    with jobs.slot(f"fit {dataset} {' '.join(blocks)}", gpu=device != "cpu"):
        jobs.threads()
        failed = 0
        for block in blocks:
            start = time.time()
            try:
                model = monolith.fit_block(dataset, event, block, _years(years), graph, device,
                                         source=json.loads(source) if source else None,
                                         warm=None if cold else "auto", log=console.print)
            except Exception as exc:  # noqa: BLE001 - one block's failure is reported, the next one is fitted
                console.print(f"BLOCK {block} FAILED {type(exc).__name__}: {exc}")
                failed += 1
                continue
            print(f"BLOCK {block} {json.dumps(model.summary(), default=float)} {time.time() - start:.0f}s", flush=True)
    raise typer.Exit(1 if failed else 0)


@data_app.command("coverage")
def coverage(dataset: str = typer.Argument(None, help="a dataset; none: every dataset, summarised"),
             event: str = typer.Argument(None, help="its event type (default: the first declared)"),
             gaps: bool = typer.Option(False, help="only the columns read by nothing")) -> None:
    """Every column pegasus_data declares for a dataset and what reads it, or why nothing does (`fields.coverage`);
    without a dataset, the same over every dataset with event types (`fields.coverage_summary`)."""
    from collections import Counter

    from . import fields as fields_mod
    from . import gateway

    if dataset is None:
        rows = fields_mod.coverage_summary()
        t = Table("dataset", "columns", "read", "not read, by reason")
        total: Counter = Counter()
        for r in rows:
            total.update(r["reasons"])
            t.add_row(r["dataset"], str(r["columns"]), str(r["read"]),
                      r.get("error") or "; ".join(f"{n} {k}" for k, n in list(r["reasons"].items())[:3]))
        console.print(t)
        ran = [r for r in rows if "error" not in r]
        console.print(f"{len(ran)} of {len(rows)} datasets: {sum(r['read'] for r in ran)} of "
                      f"{sum(r['columns'] for r in ran)} columns read")
        for k, n in total.most_common(8):
            console.print(f"  {n:5d}  {k}")
        return
    rows = fields_mod.coverage(dataset, event or gateway.event_types(dataset)[0]["name"])
    t = Table("column", "model", "kind", "read by", "reason")
    for r in rows:
        if gaps and r["read_by"]:
            continue
        t.add_row(r["column"], str(r["model"]), r["kind"], ", ".join(r["read_by"]), r["reason"])
    console.print(t)
    read = sum(bool(r["read_by"]) for r in rows)
    console.print(f"{len(rows)} columns: {read} read, {len(rows) - read} with a reason, "
                  f"{sum(not r['read_by'] and not r['reason'] for r in rows)} with neither")


@store_app.command("links")
def plan_links(plan: str = typer.Argument(..., help="a plan file (YAML)")) -> None:
    """Compute the stored link runs a plan reads for its years (`update`'s first step, alone), under the job slot."""
    from . import jobs, update

    with jobs.slot(f"links {plan}"):
        out: dict = {}
        update._ensure_links(update.Plan.load(plan), out, log=console.print)
    for k, v in out.items():
        console.print(f"{k}: {v}")


@store_app.command("update")
def update_state(plan: str = typer.Argument(..., help="a plan file (YAML): years, systems, relations, triage, report"),
                 force: bool = typer.Option(False, help="redo every reading, current or not")) -> None:
    """Bring the persistent state (fits, register, report) up to a plan, redoing only what changed (`update`), under
    the machine's job slot and the GPU slot (`jobs`)."""
    import time

    from . import jobs, update

    with jobs.slot(f"update {plan}", gpu=True):
        jobs.threads()
        # each line stamped with the clock: a plan's log is its throughput measurement (S0.8)
        out = update.run(update.Plan.load(plan), force=force,
                         log=lambda line: console.print(f"[{time.strftime('%H:%M:%S')}] {line}", markup=False))
    console.print_json(json.dumps(out, default=str))


@run_app.command("start", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(ctx: typer.Context, gpu: bool = typer.Option(False, help="also take the GPU slot"),
        wait: bool = typer.Option(False, help="follow the run here until it ends"),
        threads: int = typer.Option(0, help="threads for the commands (default: half the logical cores)"),
        log: list[str] = typer.Option(None, help="one log per command, in order (default: this output)")) -> None:
    """Run heavy commands as one run, one after another under the machine's job slot: `pegasus run start [--gpu] [--log
    a.log --log b.log] -- python scripts/x.py ARGS :: python scripts/y.py ARGS` ("python" is this interpreter). The run
    is detached; `--wait` follows it here."""
    from . import jobs

    args = [a for a in ctx.args if a != "--"]
    commands, cur = [], []
    for a in args:
        if a == "::":
            commands.append(cur)
            cur = []
        else:
            cur.append(a)
    commands += [cur] if cur else []
    if log and len(log) != len(commands):
        raise typer.BadParameter(f"{len(log)} logs for {len(commands)} commands")
    r = jobs.submit("commands", " ; ".join(" ".join(c) for c in commands)[:80], commands=commands,
                    options={"logs": log, "gpu": gpu, "threads": threads or None})
    _started(r, wait)


@explore_app.command("fields")
def fields(dataset: str, event: str, block: str, years: str = Years, graph: str = "contiguity") -> None:
    """The admissible fields of a fitted block."""
    s = _session(dataset, event, years, graph)
    t = Table("field", "level", "label")
    for f in s.fields(block):
        t.add_row(f.node, f.level, f.label[:70])
    console.print(t)


@explore_app.command("surprise")
def surprise(dataset: str, event: str, node: str, tier: str = "B1", years: str = Years,
             graph: str = "contiguity") -> None:
    """A field's calibration at a tier, and its most surprising cells."""
    import numpy as np

    s = _session(dataset, event, years, graph).surprise(node, tier)
    console.print_json(json.dumps(s.calibration, default=float))
    order = np.argsort(-np.abs(s.z), axis=None)[:15]
    t = Table("place", "year", "observed", "expected", "z")
    for i in order:
        u, k = np.unravel_index(i, s.z.shape)
        t.add_row(str(s.places[u]), str(s.years[k]), f"{s.y[u, k]:.0f}", f"{s.mu[u, k]:.1f}", f"{s.z[u, k]:+.2f}")
    console.print(t)


@explore_app.command("scan")
def scan(dataset: str, event: str, node: str, lens: str, years: str = Years, graph: str = "contiguity",
         tier: str = typer.Option(None, help="defaults to the lens's tier")) -> None:
    """One lens on one field (ledgered)."""
    hits = _session(dataset, event, years, graph).scan(node, lens, tier)
    t = Table("locus", "effect", "p")
    for h in sorted(hits, key=lambda h: h.p)[:30]:
        t.add_row(json.dumps(h.locus)[:80], f"{h.effect:.3g}", f"{h.p:.2g}")
    console.print(t)


@explore_app.command("survey")
def survey(dataset: str, event: str, years: str = Years, graph: str = "contiguity",
           blocks: list[str] = typer.Option(None, help="default: every fitted block"),
           levels: list[str] = typer.Option(None, help="tree levels to read (e.g. group); default: every level"),
           ) -> None:
    """The scheduled pass over every field with events: each stage-C question asked through all its methods
    (`questions`), error control per question and block, the answers to the register."""
    s = _session(dataset, event, years, graph)
    admitted = s.survey_questions(blocks or None, levels=tuple(levels) if levels else None, log=console.print)
    console.print(f"{len(admitted)} leads admitted")


@explore_app.command("ask")
def ask(dataset: str, event: str, question: str, node: str, years: str = Years, graph: str = "contiguity",
        q: float = 0.05, limit: int = 20, grain: str = "year") -> None:
    """One stage-C question (excess, step, trend; seasonality at ``--grain month``) of one field, through every method that answers it."""
    from . import questions

    s = _session(dataset, event, years, graph, grain)
    answers = s.ask(question, node, q=q)
    t = Table("years", "places", "states", "methods", "shapes", "effects", "p")
    for a in answers[:limit]:
        sm = questions.summary(a)
        t.add_row(f"{sm['years'][0]}–{sm['years'][1]}", str(sm["places"]), ",".join(map(str, sm["states"][:6])),
                  "+".join(sm["methods"]), ", ".join(f"{k}:{v}" for k, v in sm["shapes"].items()),
                  ", ".join(f"{k} {v}" for k, v in sm["effects"].items()), f"{sm['p']:.2g}")
    console.print(t)
    console.print(f"{len(answers)} answers; {len(getattr(answers, 'other_shape', []))} of another shape; "
                  f"agreement {questions.agreement(answers)}; failed {getattr(answers, 'failed', {})}")


@explore_app.command("relations")
def relations(plan: list[str] = typer.Argument(..., help="DATASET:EVENT:BLOCK[,BLOCK…], e.g. SIM.DO:death:I,IX"),
              years: str = Years, graph: str = "contiguity", min_events: int = 2000, q: float = 0.05) -> None:
    """Stage D across systems: which fields' departures move together, at which spatial scale and lag."""
    from . import tools

    parsed = [(p.split(":")[0], p.split(":")[1], p.split(":")[2].split(",")) for p in plan]
    admitted = tools.relation_survey(parsed, _years(years), graph, min_events=min_events, q=q, log=console.print)
    t = Table("band", "field", "leader", "lag", "rho", "q")
    for x in sorted(admitted, key=lambda x: x.q)[:40]:
        t.add_row(x.locus["band"], x.fields[0], x.fields[1], str(x.locus["lag"]), f"{x.effect:+.3f}", f"{x.q:.2g}")
    console.print(t)


@explore_app.command("triage")
def triage(dataset: str, event: str, years: str = Years, graph: str = "contiguity",
           replicate: bool = True, stale: bool = typer.Option(False, help="only the leads whose verdict other rules made")) -> None:
    """Classify the open leads (substitution, system, noise, signal) and replicate them (§7.7, §8.3)."""
    from . import leads as register

    s = _session(dataset, event, years, graph)
    done = s.triage(replicate=replicate, log=lambda m: None, stale=stale)
    counts = register.triage_counts(done)
    t = Table("class", "leads", "R1", "R2", "R3", "top chapters")
    for cls, row in sorted(counts.items(), key=lambda kv: -sum(v for k, v in kv[1].items() if not k.startswith("R"))):
        ch = sorted(((k, v) for k, v in row.items() if not (k.startswith("R") and len(k) == 2)), key=lambda kv: -kv[1])
        t.add_row(cls, str(sum(v for _, v in ch)), *(str(row.get(f"R{i}", 0)) for i in (1, 2, 3)),
                  ", ".join(f"{k} {v}" for k, v in ch[:5]))
    console.print(t)


@explore_app.command("grid")
def grid(dataset: str, event: str, node: str, years: str = Years, graph: str = "contiguity",
         kinds: str = "place,cluster,region,state,macro", shapes: str = "spike,step,trend,group", grain: str = "year",
         lenses: str = typer.Option(None, help="methods to read, comma-separated; default every method of the questions"),
         worlds: int = 4, null_worlds: int = 4, replicates: int = 100, out: str = typer.Option(None),
         minimum_effects: str = typer.Option(None, help='JSON of minimum effects (theta0) per lens, e.g. {"outbreak": [1.0, 1.2, 1.5]}'),
         tiers: str = typer.Option(None, help='JSON of expectation tiers per lens, e.g. {"change_point": ["B1", "B2"]}')
         ) -> None:
    """The designed grid of planted signals (§10.3) on one field: refitted worlds read by the production lenses, the
    false leads of null worlds, and each lens's power surface (minimum detectable rate ratio by expected events)."""
    from . import harness as h

    res = h.grid(_session(dataset, event, years, graph, grain), node, kinds=tuple(kinds.split(",")),
                 shapes=tuple(shapes.split(",")), lens_names=tuple(lenses.split(",")) if lenses else h.question_methods(), worlds=worlds,
                 null_worlds=null_worlds, replicates=replicates, log=console.print,
                 sink=str(Path(out).with_suffix(".jsonl")) if out else None,
                 minimum_effects={k: tuple(v) for k, v in json.loads(minimum_effects).items()} if minimum_effects else None,
                 tiers={k: tuple(v) for k, v in json.loads(tiers).items()} if tiers else None)
    res["surface"], res["absorbed"] = h.surface(res["rows"]), h.absorbed(res["rows"])
    if out:
        Path(out).write_text(json.dumps(res, default=float), encoding="utf-8")
    console.print_json(json.dumps(res["surface"], default=float))


@explore_app.command("relation")
def relation(dataset: str, event: str, node: str, exposure: list[str], years: str = Years, graph: str = "contiguity",
             grain: str = "month", max_lag: int = 12, scale: str = "ibge_immediate_region",
             within: str = typer.Option(None, help="macro-regions, e.g. 2 for the Northeast"),
             reverse: bool = typer.Option(False, help="the negative control: the outcome leading its exposure")) -> None:
    """The distributed-lag relation of an exposure (DATASET:EVENT sources, summed, per 1,000 residents) to a field's
    rate (§7.5): the lag curve, its cumulative effect and the lags its simultaneous band separates from zero."""
    s = _session(dataset, event, years, graph, grain)
    x = s.exposure([tuple(e.split(":", 1)) for e in exposure])
    c = s.relation(node, x, max_lag, scale=scale, within=[int(w) for w in within.split(",")] if within else None,
                   reverse=reverse)
    console.print_json(json.dumps(c.summary(), default=float))


@explore_app.command("leads")
def leads(limit: int = 30, offset: int = 0,
          cls: str = typer.Option(None, "--class", help="triage class: signal, noise, substitution, system"),
          tier: str = typer.Option(None), place: int = typer.Option(None, help="a municipality code"),
          code: str = typer.Option(None, help="an ICD-10 node: leads on it or under it"),
          estimand: str = typer.Option(None), min_replication: str = typer.Option(None, help="R0..R3"),
          status: str = typer.Option(None), direction: str = typer.Option(None), year: int = typer.Option(None),
          min_effect: float = typer.Option(None), max_q: float = typer.Option(None)) -> None:
    """The lead register, best rank first (evidence x effect x replication), filtered: hypothesis-generating."""
    from . import workspace

    out = workspace.leads({"cls": cls, "tier": tier, "place": place, "code": code, "estimand": estimand,
                           "min_replication": min_replication, "status": status, "direction": direction,
                           "year": year, "min_effect": min_effect, "max_q": max_q}, limit, offset)
    if _emit_json(out):
        return
    t = Table("rank", "id", "estimand", "tier", "field", "places", "years", "effect", "q", "R", "triage", "status")
    for r in out["rows"]:
        t.add_row(f"{r['rank']:.2f}", r["id"], r["estimand"], str(r["tier"]), r["node"],
                  ",".join(map(str, r["places"][:3])) + ("..." if r["n_places"] > 3 else ""), str(r["years"] or ""),
                  f"{r['effect']:.3g}" if r["effect"] is not None else "", f"{r['q']:.2g}" if r["q"] is not None
                  else "", r["replication"], str(r["triage"] or ""), str(r["status"] or ""))
    console.print(t)
    console.print(f"{out['matched']:,} of {out['register']:,} leads")


@explore_app.command("events")
def events(years: str = Years) -> None:
    """Every method of every built question against the documented positives (`harness.event_record`)."""
    from . import harness

    t = Table("positive", "question", "status / methods")
    for r in harness.event_record(years=_years(years), log=lambda m: None):
        cell = r.get("status") if r.get("status") != "scored" else ", ".join(
            f"{k} {'error' if 'error' in v else 'FOUND' if v['found'] else 'missed'}" for k, v in r["methods"].items())
        t.add_row(r["name"][:60], r["question"], cell)
    console.print(t)


@explore_app.command("alarms")
def alarms(dataset: str, event: str, node: str, as_of: str,
           report: str = typer.Option(None, help="the date an event becomes known (default: the declared entry date)"),
           years: str = Years, recurrence: float = 260.0, weeks: int = 8) -> None:
    """Phase 4: the place-weeks before AS_OF whose nowcast exceeds the alarm baseline at the declared recurrence."""
    s = _session(dataset, event, years, "contiguity")
    t = Table("place", "week", "known", "nowcast", "threshold", "P(exceed)")
    from . import gateway

    for r in s.alarms(node, as_of, report or gateway.entry_date(dataset), recurrence, weeks)[:40]:
        t.add_row(str(r["place"]), str(r["week"]), str(r["known"]), f"{r['nowcast']:.1f}", f"{r['threshold']:.0f}",
                  f"{r['p_exceed']:.2f}")
    console.print(t)


@explore_app.command("joint")
def joint(fields: list[str] = typer.Argument(..., help="DATASET:EVENT:NODE, e.g. SIM.DO:death:A90-A99"),
          years: str = Years, q: float = 0.05, limit: int = 30) -> None:
    """Places and periods where several fields depart together (the fast subset scan over fields, §7.3)."""
    from . import gateway, tools

    names = gateway.municipality_names()
    found = tools.joint([tuple(f.split(":", 2)) for f in fields], _years(years), q=q)
    t = Table("place", "year", "fields", "rate ratio", "p")
    for f in sorted(found, key=lambda x: x.p)[:limit]:
        m = names.get(str(f.locus["places"][0]))
        t.add_row(f"{m['name']}/{m['uf_sigla']}" if m else str(f.locus["places"][0]), str(f.locus["years"][0]),
                  ", ".join(x.split(":")[0] + ":" + x.split(":")[-1] for x in f.locus["fields"]), f"{f.effect:.2f}",
                  f"{f.p:.1e}")
    console.print(t)
    console.print(f"{len(found)} joint departures")


@store_app.command("keys")
def keys(action: str = typer.Argument(..., help="snapshot, migrate, window or gc"),
         path: str = typer.Argument(..., help="snapshot: the file to write; migrate: the snapshot taken before"),
         apply: bool = typer.Option(False, help="migrate: move the entries (default: count them only)")) -> None:
    """The code keys of every entry recorded under code_keys, and the store migrated between two snapshots: run
    ``snapshot`` on the code before a change that alters what keys cover but no result (keys narrowed, plumbing made
    keyless, code moved), then ``migrate`` with it on the code after: every stored artefact keyed by an old key is
    re-addressed to the new one instead of being computed again (`store.migrate`)."""
    from pathlib import Path

    from . import config, store

    def current() -> dict[str, str]:
        names: set[str] = set()
        for f in (config.home() / "code_keys").glob("*.json"):
            try:
                names |= set(json.loads(f.read_text(encoding="utf-8")))
            except ValueError:
                continue
        out = {}
        for name in sorted(names):
            try:
                out[name] = config._computed_key(tuple(name.split("|")))
            except LookupError:
                continue                    # an entry no longer defined: its artefacts are stale already
        return out

    if action == "gc":
        # the entries no code computes a key for: every code value outside the window `path` (keys window's file)
        window = frozenset(json.loads(Path(path).read_text(encoding="utf-8"))) | frozenset(current().values())
        store.unreachable(window, remove=apply)
        return
    if action == "window":
        # the code-key values of a change of keys alone, before and after: reads that miss adopt entries keyed by them
        # (``PEGASUS_ADOPT``, `store._entry`)
        values = sorted(set(json.loads(Path(path).read_text(encoding="utf-8")).values()) | set(current().values()))
        out = Path(path).with_name(Path(path).stem + "_window.json")
        out.write_text(json.dumps(values), encoding="utf-8")
        print(f"{len(values)} code-key values written to {out}: set PEGASUS_ADOPT to it while the studies run")
        return
    if action == "snapshot":
        keys_now = current()
        Path(path).write_text(json.dumps(keys_now, indent=1, sort_keys=True), encoding="utf-8")
        print(f"{len(keys_now)} entries' keys written to {path}")
        return
    if action != "migrate":
        raise typer.BadParameter("snapshot or migrate")
    before, after = json.loads(Path(path).read_text(encoding="utf-8")), current()
    mapping = {old: after[name] for name, old in before.items() if name in after and after[name] != old}
    print(f"{len(mapping)} of {len(before)} entries' keys changed")
    store.migrate(mapping, dry_run=not apply)


@explore_app.command("compare")
def compare(x: str = typer.Argument(..., help="DATASET:EVENT:NODE"), y: str = typer.Argument(..., help="DATASET:EVENT:NODE"),
            years: str = Years, q: float = 0.05, lags: int = 2, grain: str = typer.Option("year", help="year or month"),
            window: str = typer.Option(None, help="first,last period label, e.g. 201401,201712"),
            macro: str = typer.Option(None, help="macro-regions, e.g. 2 for the Northeast"),
            x_source: str = typer.Option(None, help="x's reader as JSON, e.g. '{\"source\": \"code_list\", \"column\": \"CODANOMAL\"}'"),
            y_source: str = typer.Option(None, help="y's reader as JSON")) -> None:
    """Do two fields move together, at which spatial support and lag? The relation estimator: every graph band and the
    regional and national courses, lags 0..LAGS periods, circular-shift nulls, one BH; the partial and direct read of
    the reported ones."""
    from . import tools

    sources = [json.loads(s) if s else None for s in (x_source, y_source)]
    rows = tools.relate([tuple(x.split(":", 2)), tuple(y.split(":", 2))], _years(years), lags=lags, q=q, grain=grain,
                        window=tuple(int(w) for w in window.split(",")) if window else None,
                        macro=[int(m) for m in macro.split(",")] if macro else None,
                        sources=sources if any(sources) else None)
    t = Table("support", "follower", "leader", "lag", "ρ", "z", "direct", "p", "reported")
    for r in sorted(rows, key=lambda r: r["p"])[:30]:
        t.add_row(r["support"], r["field"].split(":")[0] + ":" + r["field"].split(":")[-1],
                  r["leader"].split(":")[0] + ":" + r["leader"].split(":")[-1], str(r["lag"]), f"{r['rho']:+.3f}",
                  f"{r['z']:+.1f}", {True: "direct", False: "shared driver"}.get(r.get("direct"), ""), f"{r['p']:.1e}",
                  str(r["reported"]))
    console.print(t)


@explore_app.command("cohort")
def cohort(dataset: str, event: str, role: str, year: int,
           outcome: list[str] = typer.Option(..., help="an outcome kind, DATASET:ROLE (pegasus_data codes), repeatable"),
           draws: int = 10, q: float = 0.05) -> None:
    """The cohort scan on persons: every declared attribute against each outcome a person reaches (§7.8), e.g.
    `cohort SINASC-DN birth baby 2021 --outcome SIM-DO:deceased --outcome SIH-RD:patient`."""
    from . import tools

    found = tools.cohort(dataset, event, role, [tuple(o.split(":", 1)) for o in outcome], year, draws=draws, q=q,
                         log=console.print)
    t = Table("outcome", "attribute", "level", "reference", "RR", "95 %", "q")
    for x in sorted(found, key=lambda x: x.q)[:40]:
        t.add_row(x.fields[1].removeprefix("person:"), x.locus["attribute"], x.locus["level"], x.locus["reference"],
                  f"{x.effect:.2f}",
                  f"{x.interval[0]:.2f}–{x.interval[1]:.2f}", f"{x.q:.1e}")
    console.print(t)


@explore_app.command("disparity")
def disparity(dataset: str, event: str, node: str, years: str = Years, reference: str = "1", q: float = 0.05) -> None:
    """Race disparities of a field: places whose disparity departs from the national one (indirect standardisation)."""
    from . import gateway, tools

    names = gateway.municipality_names()
    found = tools.disparity(dataset, event, node, _years(years), reference=reference, q=q, log=console.print)
    t = Table("race", "place", "disparity", "national", "q")
    for x in sorted(found, key=lambda x: x.q)[:40]:
        m = names.get(str(x.locus["places"][0]))
        t.add_row(gateway.RACE.get(x.locus["race"], x.locus["race"]), f"{m['name']}/{m['uf_sigla']}" if m else
                  str(x.locus["places"][0]), f"{x.effect:.2f}", f"{x.provenance['national_disparity']:.2f}", f"{x.q:.1e}")
    console.print(t)


@explore_app.command("dossier")
def dossier(out: str = typer.Option("reports/dossier.html", help="the HTML page written"), limit: int = 30) -> None:
    """One page of dossiers, the leads in rank order: claim, series, methods, stage E's reading, verdict."""
    from . import report as report_mod

    console.print(f"written {report_mod.dossier(out, limit=limit)}")


@explore_app.command("verdict")
def verdict(lead_id: str, kind: str = typer.Argument(..., help="confirmed | artefact | unknown"),
            note: str = typer.Option("", help="what the verdict rests on")) -> None:
    """Record a person's verdict on a lead (written back to the register; confirmed leads become documented events)."""
    from . import report as report_mod

    x = report_mod.record_verdict(lead_id, kind, note)
    console.print(f"{x.id}: {kind} ({x.status})")


@explore_app.command("report")
def report(out: str = typer.Option("reports/leads.md", help="the Markdown file written"), limit: int = 25) -> None:
    """The register as a person reads it: answers per question and block with named places, then relations."""
    from . import report as report_mod

    path = report_mod.write(out, limit=limit)
    console.print(f"written {path}")


@explore_app.command("stories")
def stories(limit: int = 25, cls: str = typer.Option(None, "--class", help="keep leads of this triage class"),
            place: int = typer.Option(None, help="that place's story")) -> None:
    """Leads grouped into stories (by place or subset), best first."""
    from . import workspace

    out = workspace.stories(cls, place, limit)
    if _emit_json(out):
        return
    t = Table("rank", "story", "fields", "leads", "flags")
    for st in out["stories"]:
        t.add_row(f"{st['rank']:.1f}", st["key"], ", ".join(st["fields"])[:60], str(st["n_leads"]),
                  "; ".join(st["flags"])[:50])
    console.print(t)


@explore_app.command("ledger")
def ledger(family: str = typer.Option(None)) -> None:
    """Tests in the ledger, by family."""
    from collections import Counter

    from . import control

    if STATE["json"] and family is None:
        from . import workspace

        _emit_json(workspace.ledger())
        return
    rows = control.Ledger().table().to_pylist()
    counts = Counter(r["family"] for r in rows if r["kind"] == "pending" and (family is None or r["family"] == family))
    t = Table("family", "tests")
    for k, v in counts.most_common():
        t.add_row(k, str(v))
    console.print(t)


@explore_app.command("split-fit")
def split_fit(dataset: str, event: str, blocks: list[str], years: str = Years, graph: str = "contiguity",
              device: str | None = None) -> None:
    """Deal the events of blocks to the sides A, E and fit each block on side A alone (§8.3)."""
    from . import replication

    for block in blocks:
        model = replication.prepare(dataset, event, block, _years(years), graph, device,
                                    log=lambda line, b=block: console.print(f"{b} {line}"))
        console.print_json(json.dumps(model.summary(), default=float))


@explore_app.command("split-survey")
def split_survey(dataset: str, event: str, years: str = Years, graph: str = "contiguity",
                 blocks: list[str] = typer.Option(None, help="default: every fitted block")) -> None:
    """The survey on side A, then the size of each lead it selects read on side E (§8.3: a size, never a verdict)."""
    s = _session(dataset, event, years, graph)
    admitted = s.side("A").survey_questions(blocks or None, log=console.print)
    console.print(f"{len(admitted)} leads selected on side A")
    done = s.honest_sizes(log=console.print)
    console.print(f"{sum(1 for x in done if x.replications.get('honest', {}).get('sized'))} sized on side E")


@explore_app.command("temporal-survey")
def temporal_survey(dataset: str, event: str, last: int, years: str = Years, graph: str = "contiguity",
                    blocks: list[str] = typer.Option(None, help="default: every fitted block")) -> None:
    """Select on the years up to LAST (its own register leads_T<LAST>), then test what it selected on the later years of
    ``years`` against a fit that ends at LAST (§8.3, later years). Needs the blocks fitted on the years up to LAST."""
    s = _session(dataset, event, years, graph)
    admitted = s.train(last).survey_questions(blocks or None, log=console.print)
    console.print(f"{len(admitted)} leads selected on the years up to {last}")
    done = s.temporal_confirm(last, log=console.print)
    console.print(f"{sum(1 for x in done if x.replication != 'R0')} stand on the later years")



@study_app.command("search")
def search_command(query: str = typer.Argument(..., help="a term, or several separated by commas (infarto, "
                                                         "leptospir)")) -> None:
    """What a study of QUERY would seed on: ICD-10 codes by label, the SINAN agravos holding them, matching contexts."""
    from . import study

    found = study.search(query)
    if _emit_json(found):
        return
    t = Table("ICD-10", "level", "label")
    for r in found["icd10"]:
        t.add_row(r["code"], r["level"], r["label"])
    console.print(t)
    if found["sinan"]:
        t = Table("SINAN agravo (--sinan)", "dataset", "its ICD-10 codes")
        for r in found["sinan"]:
            t.add_row(r["sinan"], r["dataset"], ", ".join(r["codes"]))
        console.print(t)
    if found["contexts"]:
        t = Table("context (--contexts)", "label")
        for r in found["contexts"]:
            t.add_row(r["context"], str(r["label"])[:90])
        console.print(t)
    if found["roles"]:
        t = Table("dataset", "role (--records DATASET: role op value)", "kind", "label")
        for r in found["roles"]:
            t.add_row(r["dataset"], r["role"], r["kind"], str(r["name"])[:70])
        console.print(t)
    console.print("next: pegasus study new NAME --icd10 CODES [--sinan AGRAVOS] --where UF --period FIRST-LAST")


def _list(text: str | None) -> list[str] | None:
    return [x.strip() for x in text.split(",") if x.strip()] if text else None


@study_app.command("new")
def new_command(name: str = typer.Argument(..., help="the study's name (its file and folder)"),
                icd10: str = typer.Option(None, help="ICD-10 codes, comma-separated (I21,I22)"),
                sinan: str = typer.Option(None, help="SINAN agravos, comma-separated (LEPT)"),
                terms: str = typer.Option(None, help="label terms, comma-separated"),
                where: str = typer.Option("BR", help="BR, a state (AL) or states/municipalities comma-separated"),
                period: str = typer.Option("2014-2023", help="first-last year"),
                depth: str = typer.Option("standard", help="survey, standard, deep or exhaustive"),
                only: str = typer.Option(None, help="the sources read, comma-separated (SIM-DO,SIH-RD)"),
                contexts: str = typer.Option(None, help="context fields, comma-separated (default: auto)"),
                records: str = typer.Option(None, help="a record condition: 'SINASC-DN: birth.weight < 2500' "
                                                       "(clauses joined by ' and ')"),
                name_: str = typer.Option(None, "--name", help="the condition topic's name (low birth weight)"),
                per: str = typer.Option(None, help="the events a condition topic is rated per (SINASC-DN)"),
                folder: str = typer.Option("studies", help="where the declaration is written"),
                scratch: bool = typer.Option(False, help="a quick look, kept in studies/scratch/ until promoted")
                ) -> None:
    """Write a study declaration from its choices, validated and commented (the step after search)."""
    from . import study

    places = _list(where) or ["BR"]
    seeds = [study.parse_records(records, name_ or name, per)] if records else None
    if scratch:
        from . import workspace

        folder = str(workspace.scratch_dir())
    path = study.new(name, _list(icd10), _list(sinan), _list(terms), places[0] if len(places) == 1 else places,
                     period, depth, _list(only), _list(contexts), folder, seeds)
    console.print(f"written {path}\nnext: pegasus study scope {name}   (what it reads, and the minutes)\n"
                  f"      pegasus study run {name}     (the folder lands in {Path(folder) / name})")


@study_app.command("scope")
def scope_command(name: str = typer.Argument(..., help="the study's name or its declaration's path"),
                  last: bool = typer.Option(False, "--last", help="the last priced scope as written, not priced again")
                  ) -> None:
    """What a study declaration resolves to (ARCHITECTURE §3.2): the sources it reads and why, the years and their
    download cost, what is deferred past the declaration's choices, what a seed named and is not read. Writes the
    priced scope beside the declaration (``NAME.scope.yml``) and shows what each choice costs."""
    from . import gateway, workspace

    if last:
        kept = workspace.priced(name)
        if kept is None:
            raise LookupError(f"{name} has not been priced: `pegasus study scope {name}`")
        if not _emit_json(kept):
            console.print(f"{kept['source']} scope written {kept['written']} ({kept['path']})")
            console.print_json(json.dumps(kept["scope"].get("minutes_by_choice"), ensure_ascii=False))
        return
    scope = workspace.scope(name)
    if _emit_json(scope):
        return
    t = Table("read", "dataset", "event", "years", "minutes", "why")
    for i in scope["read"]:
        base, cond = gateway.split_event(i["event"])
        t.add_row("", i["dataset"], base + (f" ({cond['name']})" if cond else ""),
                  f"{i['years'][0]}-{i['years'][-1]}" if i["years"] else "", f"{(i['est_seconds'] or 0) / 60:.1f}",
                  i["reason"][:90])
    console.print(t)
    console.print_json(json.dumps(scope["minutes_by_choice"], ensure_ascii=False))
    console.print(f"{len(scope['read'])} read, {len(scope['deferred'])} deferred, {len(scope['not_read'])} not read; "
                  f"estimated {scope['estimated_minutes']} min; written to {scope['written']}")
    if scope["nothing_read"]:
        console.print(f"[bold red]{scope['nothing_read']}[/bold red]")


@study_app.command("run")
def study_command(name: str = typer.Argument(..., help="the study's name or its declaration's path"),
                  products_only: bool = typer.Option(False, help="the products alone, from the fits and answers the "
                                                                 "store holds (the lanes not run)"),
                  wait: bool = typer.Option(True, help="follow the run here until it ends (Ctrl+C leaves it running)")
                  ) -> None:
    """Run a study (ARCHITECTURE §3): a detached run, admitted by memory beside the others, which writes the folder
    beside the declaration. The window shows it as it runs."""
    from . import workspace

    _started(workspace.start_study(name, products_only), wait)


def _started(r: dict, wait: bool) -> None:
    from . import jobs

    if _emit_json(r) or not wait:
        if not STATE["json"]:
            console.print(f"run {r['id']} started (pid {r['pid']}); `pegasus run show {r['id']}`, "
                          f"`pegasus run stop {r['id']}`")
        return
    console.print(f"run {r['id']} started; following its log (Ctrl+C leaves it running)", highlight=False)
    try:
        meta = jobs.wait(r["id"], follow=lambda line: console.print(line, markup=False, highlight=False))
    except KeyboardInterrupt:
        console.print(f"\nleft running: `pegasus run show {r['id']}`, `pegasus run stop {r['id']}`")
        return
    console.print(f"run {meta['id']}: {meta['state']}" + (f" ({meta['error']})" if meta.get("error") else ""))
    raise typer.Exit(0 if meta["state"] == "done" else 1)


@study_app.command("audit")
def audit_command(folder: str) -> None:
    """A study folder's analytic body (each part a paper needs: met or missing, with evidence), then the win
    condition's acceptance items 1-10."""
    from . import study

    if _emit_json({"body": study.body(folder), "audit": study.audit(folder)}):
        return
    t = Table("part", "status", "evidence")
    for r in study.body(folder):
        t.add_row(r["part"], r["status"], r["evidence"])
    console.print(t)
    t = Table("item", "what", "status", "evidence", "missing")
    for r in study.audit(folder):
        t.add_row(str(r["item"]), r["what"], r["status"], r["evidence"], r["missing"])
    console.print(t)


@study_app.command("export")
def export_command(folder: str, to: str = typer.Option(..., help="the directory to write"),
                   tables: str = typer.Option(None, help="comma-separated views of study.duckdb; default all"),
                   fmt: str = typer.Option("parquet", "--format", help="parquet or csv")) -> None:
    """Materialise a study folder, by default whole (ARCHITECTURE §3.6): the only operation that copies data."""
    from . import study

    console.print(f"exported to {study.export(folder, to, tables.split(',') if tables else None, fmt)}")


@store_app.command("gc")
def gc_command(budget_gb: float = typer.Option(4.0, help="what the caches (gateway, blockdata) may hold"),
               keep_hours: float = typer.Option(24.0, help="entries read or written this recently are kept"),
               dry_run: bool = typer.Option(False, help="count what would go, delete nothing")) -> None:
    """Evict the least recently read cache entries to a budget; fits and results are never evicted."""
    from . import store

    print(store.gc(budget_gb, keep_hours, dry_run))


@explore_app.command("map")
def dependency_map(years: str = typer.Option("2015-2019", help="first-last year of the health fields"),
                   negatives: int = typer.Option(0, help="worlds of Moran-randomised surrogates for the false-edge rate"),
                   health_only: bool = typer.Option(False, help="negatives keep the real context fields"),
                   plan: str = typer.Option("plans/default.yml", help="the plan whose systems and contexts are mapped"),
                   top: int = 20) -> None:
    """Dependency map (§7.6): the plan's systems' fields and its context fields, every testable pair in two layers
    (marginal E_b, conditional on the contexts), controlled over the whole map (`dependency`)."""
    import numpy as np

    from . import dependency, harness, update

    loaded = update.Plan.load(plan)
    r = dependency.dependency_map([(x.dataset, x.event, x.blocks) for x in loaded.systems],
                                  loaded.extra.get("contexts") or [], _years(years))
    if negatives:
        r["summary"]["negatives"] = harness.dependency_negatives(r, negatives, health_only)
    console.print_json(json.dumps(r["summary"], default=float))
    e = r["edges"].to_pylist()
    e = [x for x in e if x["admitted"] or x.get("admitted_c")]
    e.sort(key=lambda x: -abs(x["rho"]) if np.isfinite(x["rho"]) else 0)
    t = Table("x", "y", "rho", "n_eff", "rho|Z", "status")
    for x in e[:top]:
        t.add_row(x["x"], x["y"], f"{x['rho']:+.3f}", f"{x['n_eff']:.0f}", f"{x['rho_c']:+.3f}", x["status"] or "-")
    console.print(t)


# ------------------------------------------------------------------------------------------------- studies and runs


@study_app.command("list")
def study_list() -> None:
    """Every study in the workspace: where, when, its depth, its analytic body and its last run."""
    from . import workspace

    rows = workspace.studies()
    if _emit_json(rows):
        return
    t = Table("study", "where", "period", "depth", "body", "last run", "written")
    for r in rows:
        last = r["last_run"]
        t.add_row(r["name"] if not r["group"] else f"{r['group']}/{r['name']}", str(r["where"]), str(r["period"]),
                  str(r["depth"]), f"{r['body']['met']}/{r['body']['total']}" if r["body"] else "-",
                  f"{last['state']} {last['id']}" if last else "-", str(r["written"] or "-"))
    console.print(t)


@study_app.command("show")
def study_show(name: str = typer.Argument(..., help="the study's name or its declaration's path")) -> None:
    """One study: its declaration, what it reads, its analytic body part by part, its folder's files, its runs."""
    from . import workspace

    d = workspace.study_detail(name)
    if _emit_json(d):
        return
    console.print(f"[bold]{d['name']}[/bold]  {d['declaration']}\nfolder {d['folder']}  written {d['written'] or '-'}")
    if d["parts"]:
        t = Table("part", "status", "evidence")
        for r in d["parts"]:
            t.add_row(r["part"], r["status"], r["evidence"])
        console.print(t)
    t = Table("run", "state", "created", "ended", "peak GB")
    for r in d["runs"][:10]:
        t.add_row(r["id"], r["state"], r["created"], str(r["ended"] or "-"), str(r["peak_gb"] or "-"))
    console.print(t)


@study_app.command("check")
def study_check(name: str = typer.Argument(..., help="the study's name or a declaration file")) -> None:
    """A declaration's problems (none: it can run) and the value each choice takes after its depth."""
    from . import workspace

    path = Path(name) if Path(name).suffix in (".yml", ".yaml") else workspace.find(name)
    out = workspace.check(path.read_text(encoding="utf-8"))
    if _emit_json(out):
        return
    for problem in out["problems"]:
        console.print(f"[red]problem[/red] {problem}", highlight=False)
    if out["effective"]:
        for k, v in out["effective"].items():
            console.print(f"{k}: {json.dumps(v)}", highlight=False)
    raise typer.Exit(1 if out["problems"] else 0)


@study_app.command("set")
def study_set(name: str = typer.Argument(..., help="the study's name"),
              key: str = typer.Argument(..., help="a declaration key: depth, related, topic.seeds.icd10, ..."),
              value: str = typer.Argument(None, help="its value as YAML ([I21, I22], 3, true); none removes the key")
              ) -> None:
    """Set one key of a study's declaration, its comments and order kept, and write it once it has no problem: what
    the window's form does."""
    import yaml

    from . import workspace

    path = workspace.find(name)
    text = workspace.set_key(path.read_text(encoding="utf-8"), key, None if value is None else yaml.safe_load(value))
    d = workspace.save_declaration(name, text)
    if not _emit_json(d):
        console.print(f"{key} set; {d['path']} written")


@study_app.command("promote")
def study_promote(name: str = typer.Argument(..., help="a scratch study's name")) -> None:
    """Make a scratch study one of the workspace's: its declaration and folder moved from studies/scratch/."""
    from . import workspace

    d = workspace.promote(name)
    if not _emit_json(d):
        console.print(f"{d['name']} promoted: {d['declaration']}")


@study_app.command("compare")
def study_compare(names: list[str] = typer.Argument(..., help="two studies or more"),
                  table: str = typer.Option(..., help="a table every study holds (rates, municipalities, ...)"),
                  where: list[str] = typer.Option(None, help="a filter 'column op value'; repeat for more"),
                  order: str = typer.Option(None), columns: str = typer.Option(None),
                  limit: int = typer.Option(200), offset: int = typer.Option(0),
                  csv: str = typer.Option(None, help="write the rows to this CSV file")) -> None:
    """One table's query over several studies, side by side, each row led by its study."""
    from . import workspace

    out = workspace.compare(names, table, where=[_filter(w) for w in where or []], columns=_list(columns),
                            order=_list(order), limit=limit, offset=offset)
    if csv:
        import csv as csv_mod

        with open(csv, "w", newline="", encoding="utf-8") as fh:
            wr = csv_mod.writer(fh)
            wr.writerow(out["columns"])
            wr.writerows(out["rows"])
        console.print(f"{len(out['rows'])} rows written to {csv}")
        return
    if _emit_json(out):
        return
    t = Table(*out["columns"])
    for r in out["rows"]:
        t.add_row(*["" if v is None else str(v) for v in r])
    console.print(t)
    console.print(", ".join(f"{k}: {v:,} rows" for k, v in out["totals"].items()))


@study_app.command("tables")
def study_tables(name: str = typer.Argument(..., help="the study's name or its declaration's path")) -> None:
    """A study's tables (the views of its study.duckdb): rows and columns."""
    from . import workspace

    rows = workspace.tables(name)
    if _emit_json(rows):
        return
    t = Table("table", "rows", "columns")
    for r in rows:
        t.add_row(r["table"], f"{r['rows']:,}", ", ".join(c["name"] for c in r["columns"]))
    console.print(t)


def _filter(text: str) -> dict:
    """``"col op value"``: op one of `workspace.FILTER_OPS`; the value read as JSON when it parses (numbers, lists)."""
    import re

    m = re.match(r"^\s*(\w+)\s*(is not null|is null|!=|<=|>=|=|<|>|\bin\b|\blike\b)\s*(.*)$", text, re.IGNORECASE)
    if not m:
        raise typer.BadParameter(f"{text!r}: write 'column op value', e.g. 'first >= 2019'")
    column, op, raw = m.group(1), m.group(2).lower(), m.group(3).strip()
    try:
        value = json.loads(raw) if raw else None
    except ValueError:
        value = raw
    return {"column": column, "op": op, "value": value}


@study_app.command("table")
def study_table(name: str = typer.Argument(..., help="the study's name or its declaration's path"),
                table: str = typer.Argument(..., help="a table of `study tables`"),
                where: list[str] = typer.Option(None, help="a filter 'column op value' (=, !=, <, <=, >, >=, in, "
                                                           "like, is null); repeat for more"),
                order: str = typer.Option(None, help="columns to order by, comma-separated; -col descends"),
                columns: str = typer.Option(None, help="the columns kept, comma-separated"),
                limit: int = typer.Option(50, help="rows shown"), offset: int = typer.Option(0),
                csv: str = typer.Option(None, help="write the matching rows (up to --limit) to this CSV file"),
                methods: bool = typer.Option(False, help="how the table's numbers were made, not its rows")) -> None:
    """Rows of one of a study's tables, filtered and ordered: what the window's table browser shows."""
    from . import workspace

    if methods:
        m = workspace.methods_of(name, table)
        if not _emit_json(m):
            for x in m["measures"]:
                console.print(f"[bold]{x['measure']}[/bold] ({', '.join(x['columns']) or 'measure'}): {x['method']}",
                              highlight=False)
            console.print(f"provenance: {m['provenance']}", highlight=False)
        return

    out = workspace.rows(name, table, [_filter(w) for w in where or []], _list(order), _list(columns), limit, offset)
    if csv:
        import csv as csv_mod

        with open(csv, "w", newline="", encoding="utf-8") as fh:
            w = csv_mod.writer(fh)
            w.writerow(out["columns"])
            w.writerows(out["rows"])
        console.print(f"{len(out['rows'])} of {out['total']} rows written to {csv}")
        return
    if _emit_json(out):
        return
    t = Table(*out["columns"])
    for r in out["rows"]:
        t.add_row(*["" if v is None else str(v) for v in r])
    console.print(t)
    console.print(f"rows {offset + 1}-{offset + len(out['rows'])} of {out['total']:,}")


@data_app.command("datasets")
def data_datasets(system: str = typer.Option(None, help="one system (SIM, SIH, SINAN, ...)"),
                  readable: bool = typer.Option(False, help="only datasets with event types a study reads"),
                  refresh: bool = typer.Option(False, help="list the catalog again, not from its kept listing")) -> None:
    """What DATASUS publishes, by system: files, gigabytes, years, states, and the event types a study reads."""
    from . import workspace

    d = workspace.datasets(refresh)
    rows = [r for r in d["datasets"] if (not system or r["system"].upper() == system.upper())
            and (not readable or r["event_types"])]
    if _emit_json({**d, "datasets": rows}):
        return
    t = Table("system", "dataset", "name", "years", "files", "GB", "event types")
    for r in rows:
        t.add_row(r["system"], r["code"], str(r["name"] or ""), str(r["years"] or ""), f"{r['files'] or 0:,}",
                  f"{r['gigabytes'] or 0:,.1f}", ", ".join(r["event_types"]))
    console.print(t)
    console.print(f"{len(rows)} datasets (catalog crawled {d['as_of']})")


@data_app.command("show")
def data_show(dataset: str = typer.Argument(..., help="a dataset: SIM-DO, SIH-RD, SINAN-DENG, ...")) -> None:
    """One dataset: its years in the catalog and the lake, the reserve, its event types, its columns' roles (meaning,
    kind, codelists, valid years, not-recorded codes) and its links."""
    from . import workspace

    d = workspace.dataset(dataset)
    if _emit_json(d):
        return
    console.print(f"[bold]{d['code']}[/bold] {d['name']} ({d['system']}): {d['years']}, {d['files']:,} files, "
                  f"{d['gigabytes']:,.1f} GB")
    console.print(f"lake, whole years: {', '.join(map(str, d['whole_years'])) or 'none'}; "
                  f"reserved: {', '.join(map(str, d['reserved_years'])) or 'none'}")
    for e in d["event_types"]:
        console.print(f"event type {e['name']} ({e['kind']}): {e['grain']}")
    t = Table("column", "role", "kind", "model", "name", "years", "not recorded")
    for r in d["roles"]:
        t.add_row(r["column"], str(r["role"]), str(r["kind"]), str(r["model"]), str(r["name"] or ""),
                  f"{r['first_year'] or ''}-{r['last_year'] or ''}", ", ".join(r["missing"] or []))
    console.print(t)
    for link in d["links"]:
        console.print(f"link {link['link']}: {link['left']} -> {link['right']}")


@data_app.command("records")
def data_records(dataset: str = typer.Argument(...), year: int = typer.Argument(...),
                 partition: str = typer.Option(None, help="BR or a state the lake holds for the year"),
                 rows: list[str] = typer.Option(None, help="COLUMN=PREFIX[,PREFIX]: records whose column starts with "
                                                           "a prefix (CODMUNRES=27); repeat for more"),
                 where: list[str] = typer.Option(None, help="a condition on a role 'role op value' (birth.weight < "
                                                            "2500); repeat for more"),
                 limit: int = typer.Option(20), offset: int = typer.Option(0),
                 reveal: bool = typer.Option(False, help="show the identifier columns, hidden by default"),
                 csv: str = typer.Option(None, help="write the page to this CSV file")) -> None:
    """Records as filed, each value with its label, from the lake only (nothing is downloaded); identifier columns are
    hidden unless --reveal; the confirmation reserve's years are refused."""
    from . import workspace

    filters = {}
    for r in rows or []:
        col, _, prefixes = r.partition("=")
        filters[col.strip()] = [x.strip() for x in prefixes.split(",") if x.strip()]
    condition = [{"role": f["column"], "op": f["op"], "value": f["value"]} for f in map(_role_filter, where or [])]
    out = workspace.records(dataset, year, partition, filters or None, condition or None, limit, offset, reveal)
    if csv:
        import csv as csv_mod

        with open(csv, "w", newline="", encoding="utf-8") as fh:
            w = csv_mod.writer(fh)
            w.writerow(out["columns"])
            w.writerows(out["rows"])
        console.print(f"{len(out['rows'])} of {out['total']:,} records written to {csv}")
        return
    if _emit_json(out):
        return
    for i, r in enumerate(out["rows"]):
        console.rule(f"record {offset + i + 1} of {out['total']:,}")
        for c, v in zip(out["columns"], r, strict=True):
            if v is not None:
                console.print(f"{c}: {v}", highlight=False, markup=False)
    if out["hidden"]:
        console.print(f"hidden (identifiers; --reveal shows them): {', '.join(out['hidden'])}")


def _role_filter(text: str) -> dict:
    """``"role op value"`` for a condition on roles: the role may hold dots (birth.weight)."""
    import re

    m = re.match(r"^\s*([\w.]+)\s*(!=|<=|>=|==|=|<|>|\bnot in\b|\bin\b)\s*(.*)$", text, re.IGNORECASE)
    if not m:
        raise typer.BadParameter(f"{text!r}: write 'role op value', e.g. 'birth.weight < 2500'")
    raw = m.group(3).strip()
    try:
        value = json.loads(raw)
    except ValueError:
        value = raw
    op = {"=": "==", "in": "in", "not in": "not in"}.get(m.group(2).lower(), m.group(2))
    return {"column": m.group(1), "op": op, "value": value}


@data_app.command("codes")
def data_codes(dataset: str = typer.Argument(...), column: str = typer.Argument(..., help="a column (RACACOR)"),
               year: int = typer.Argument(...),
               partition: str = typer.Option(None, help="BR or a state the lake holds for the year")) -> None:
    """A column's values in one year as the lake holds them: each code with the label its codelist gives it that year,
    the records holding it, and the records with none (the column's completeness)."""
    from . import workspace

    out = workspace.codes(dataset, column, year, partition)
    if _emit_json(out):
        return
    console.print(f"{out['dataset']} {out['column']} ({out['name']}) {out['year']} {out['partition']}: "
                  f"{out['records']:,} records, {out['empty']:,} empty ({(out['filled_share'] or 0):.1%} filled)")
    t = Table("code", "label", "records", "share")
    for r in out["values"]:
        t.add_row(r["code"], str(r["label"] or "(undecoded)"), f"{r['records']:,}",
                  f"{r['records'] / out['records']:.1%}" if out["records"] else "")
    console.print(t)


@data_app.command("contexts")
def data_contexts(filter_: str = typer.Option(None, "--filter", help="a word in the name or what it measures")) -> None:
    """The municipal contexts a study relates its rates to: what each measures, its unit, years, denominator, source."""
    from . import workspace

    rows = [r for r in workspace.contexts() if not filter_ or filter_.lower() in
            f"{r['context']} {r['what'] or ''}".lower()]
    if _emit_json(rows):
        return
    t = Table("context", "what", "unit", "years", "over", "source")
    for r in rows:
        t.add_row(r["context"], str(r["what"] or "")[:70], str(r["unit"] or "")[:30], str(r["years"] or ""),
                  str(r["over"] or ""), str(r["source"] or ""))
    console.print(t)


@plot_app.command("list")
def plot_list(name: str = typer.Argument(..., help="the study's name")) -> None:
    """A study's plots."""
    from . import plots

    rows = plots.plots(name)
    if _emit_json(rows):
        return
    t = Table("plot", "title", "table", "mark", "map", "modified")
    for r in rows:
        t.add_row(r["id"], str(r.get("title") or r.get("error") or ""), str(r.get("table", "")),
                  str(r.get("mark", "")), "yes" if r.get("map") else "", str(r.get("modified", "")))
    console.print(t)


@plot_app.command("new")
def plot_new(name: str = typer.Argument(..., help="the study's name"),
             plot_id: str = typer.Argument(..., help="the plot's id (its file name)"),
             table: str = typer.Option(..., help="a table of `study tables`"),
             mark: str = typer.Option("line", help="point, line, bar, area, rect, tick, boxplot (a map: --map)"),
             x: str = typer.Option(None, help="field:type (q, n, o, t), agg(field):type, or count()"),
             y: str = typer.Option(None), color: str = typer.Option(None), size: str = typer.Option(None),
             shape: str = typer.Option(None), column: str = typer.Option(None), row: str = typer.Option(None),
             tooltip: str = typer.Option(None, help="encodings, comma-separated"),
             where: list[str] = typer.Option(None, help="a filter 'column op value'; repeat for more"),
             title: str = typer.Option(None),
             map_: bool = typer.Option(False, "--map", help="a map: the folder's municipal boundaries, coloured by "
                                                           "--color"),
             geometry: str = typer.Option("municipalities.geojson", help="the boundaries file of the folder (--map)"),
             key: str = typer.Option("u", help="the column joining rows to the boundaries (--map)")) -> None:
    """Write a plot from a table, a mark and its encodings, checked against the study; the window's editor opens it."""
    from . import plots

    spec = plots.build(table, mark, {"x": x, "y": y, "color": color, "size": size, "shape": shape, "column": column,
                                     "row": row, "tooltip": tooltip}, [_filter(w) for w in where or []], title,
                       geometry if map_ else None, key)
    row_ = plots.save(name, plot_id, spec)
    if not _emit_json(row_):
        console.print(f"written {plot_id}: `pegasus plot render {name} {plot_id} --out {plot_id}.png`")


@plot_app.command("save")
def plot_save(name: str = typer.Argument(..., help="the study's name"), plot_id: str = typer.Argument(...),
              spec: str = typer.Option(..., help="a Vega-Lite file whose usermeta.pegasus names its table")) -> None:
    """Write a plot from a Vega-Lite file edited by hand, checked against the study."""
    from . import plots

    row_ = plots.save(name, plot_id, json.loads(Path(spec).read_text(encoding="utf-8")))
    if not _emit_json(row_):
        console.print(f"written {plot_id}")


@plot_app.command("show")
def plot_show(name: str = typer.Argument(...), plot_id: str = typer.Argument(...)) -> None:
    """A plot's Vega-Lite specification, as stored."""
    from . import plots

    sys.stdout.write(json.dumps(plots.get(name, plot_id), indent=1, ensure_ascii=False) + "\n")


@plot_app.command("render")
def plot_render(name: str = typer.Argument(...), plot_id: str = typer.Argument(...),
                out: str = typer.Option(..., help="the file written; its format from --format"),
                fmt: str = typer.Option("png", "--format", help="png, svg or pdf"),
                scale: float = typer.Option(2.0, help="pixels per unit for png")) -> None:
    """Draw a plot headless (vl-convert) to PNG, SVG or PDF."""
    from . import plots

    data = plots.render(name, plots.get(name, plot_id), fmt, scale)
    Path(out).write_bytes(data)
    if not _emit_json({"out": out, "bytes": len(data)}):
        console.print(f"written {out} ({len(data):,} bytes)")


@plot_app.command("data")
def plot_data(name: str = typer.Argument(...), plot_id: str = typer.Argument(...),
              out: str = typer.Option(..., help="the CSV file written")) -> None:
    """The rows a plot draws, as CSV: what a paper's figure is made of."""
    import csv as csv_mod

    from . import plots

    d = plots.data(name, plots.get(name, plot_id))
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv_mod.writer(fh)
        w.writerow(d["columns"])
        w.writerows(d["rows"])
    if not _emit_json({"out": out, "rows": len(d["rows"])}):
        console.print(f"{len(d['rows']):,} rows written to {out}")


@plot_app.command("delete")
def plot_delete(name: str = typer.Argument(...), plot_id: str = typer.Argument(...)) -> None:
    """Delete a plot's file."""
    from . import plots

    plots.delete(name, plot_id)
    if not _emit_json({"deleted": plot_id}):
        console.print(f"deleted {plot_id}")


@run_app.command("list")
def run_list(limit: int = typer.Option(30, help="the newest runs shown"),
             study: str = typer.Option(None, help="one study's runs")) -> None:
    """The runs, newest first: state, when, memory."""
    from . import jobs

    rows = jobs.runs(limit, study)
    if _emit_json(rows):
        return
    t = Table("run", "state", "label", "created", "ended", "need GB", "peak GB")
    for r in rows:
        t.add_row(r["id"], r["state"], r["label"], r["created"], str(r["ended"] or "-"), str(r["need_gb"] or "-"),
                  str(r["peak_gb"] or "-"))
    console.print(t)


@run_app.command("show")
def run_show(run_id: str) -> None:
    """One run's record and what it has done: its phases, lanes, items and products, from its events."""
    from . import jobs

    meta, events = jobs.get(run_id), jobs.events(run_id)
    if _emit_json({**meta, "events": events}):
        return
    console.print_json(json.dumps({k: v for k, v in meta.items() if k not in ("commands",)}, default=str))
    t = Table("time", "kind", "what", "status", "seconds", "detail")
    for e in events:
        if e["kind"] == "resources":
            continue
        what = e.get("phase") or e.get("item") or e.get("lane") or e.get("product") or e.get("target") or ""
        detail = e.get("error") or e.get("state") or ""
        t.add_row(time.strftime("%H:%M:%S", time.localtime(e["t"])), e["kind"],
                  str(what)[:70], str(e.get("status", "")), str(e.get("seconds", "")), str(detail)[:80])
    console.print(t)


@run_app.command("log")
def run_log(run_id: str, lines: int = typer.Option(60, help="the last lines shown"),
            follow: bool = typer.Option(False, "--follow", "-f", help="follow it until the run ends")) -> None:
    """A run's output."""
    from . import jobs

    if follow:
        jobs.wait(run_id, follow=lambda line: console.print(line, markup=False, highlight=False))
        return
    text = jobs.log_tail(run_id, lines)
    if not _emit_json({"id": run_id, "text": text}):
        console.print(text, markup=False, highlight=False)


@run_app.command("events")
def run_events(run_id: str, since: float = typer.Option(0.0, help="only the events after this unix time")) -> None:
    """A run's typed events, as JSON lines: what each of its processes did."""
    from . import jobs

    for e in jobs.events(run_id, since):
        sys.stdout.write(json.dumps(e, default=str, ensure_ascii=False) + "\n")


@run_app.command("stop")
def run_stop(run_id: str) -> None:
    """End a run and every process it started."""
    from . import jobs

    meta = jobs.stop(run_id)
    if not _emit_json(meta):
        console.print(f"run {run_id}: {meta['state']}")


@run_app.command("wait")
def run_wait(run_id: str) -> None:
    """Follow a run's log until it ends; the exit code says whether it was done."""
    from . import jobs

    meta = jobs.wait(run_id, follow=None if STATE["json"] else
                     (lambda line: console.print(line, markup=False, highlight=False)))
    _emit_json(meta)
    raise typer.Exit(0 if meta["state"] == "done" else 1)


@app.command("machine")
def machine_command() -> None:
    """The machine as runs see it: memory, CPU, disks, the heavy slots and who holds them."""
    from . import jobs

    m = jobs.machine()
    if _emit_json(m):
        return
    console.print(f"memory {m['ram_available_gb']} of {m['ram_total_gb']} GB available, CPU {m['cpu_percent']} %, "
                  f"{m['slots']} heavy slots")
    for d in m["disks"]:
        console.print(f"disk {d['path']} {d['free_gb']} of {d['total_gb']} GB free")
    for h in m["holders"]:
        console.print(f"holder {h['pid']} {h['label']}: needs {h['need_gb']}, expects {h['expect_gb']}, "
                      f"holds {h['rss_gb']} GB" + (f" (run {h['run']})" if h.get("run") else ""))


def _command_list() -> list[dict]:
    """Every command of this program with its arguments and first help line: what `context` lists."""
    root = typer.main.get_command(app)
    out = []

    def walk(cmd, path):
        if hasattr(cmd, "commands"):                     # a group (typer vendors its own click)
            for name, sub in sorted(cmd.commands.items()):
                walk(sub, [*path, name])
            return
        params = " ".join(p.name.upper() if p.required else f"[{p.name.upper()}]"
                          for p in cmd.params if getattr(p, "param_type_name", "") == "argument")
        out.append({"path": " ".join(path) + (f" {params}" if params else ""),
                    "help": " ".join((cmd.help or "").split("\n\n")[0].split())})
    walk(root, [])
    return out


@app.command("context")
def context_command(study: str = typer.Argument(None, help="a study whose declaration, scope, body and tables are "
                                                           "included"),
                    out: str = typer.Option(None, help="write it to this file instead of printing it")) -> None:
    """What an assistant outside PegaSUS (a chatbot you consult) needs to read this workspace and propose commands:
    PegaSUS's rules, its commands, the declaration, the studies, and a study in detail. Paste it, or attach the file."""
    from . import workspace

    text = workspace.context(study, _command_list())
    if out:
        Path(out).write_text(text, encoding="utf-8")
        console.print(f"written {out} ({len(text):,} characters)")
    elif not _emit_json({"markdown": text}):
        sys.stdout.write(text)


@app.command("ui")
def ui_command(serve: bool = typer.Option(False, help="serve the interface to a browser tab instead of a window")
               ) -> None:
    """Open the desktop window (pegasus_app) on this workspace."""
    try:
        from pegasus_app import __main__ as desktop
    except ImportError as exc:
        raise typer.BadParameter("pegasus_app is not installed in this environment (pip install -e "
                                 "../pegasus_app)") from exc
    desktop.main(["--serve"] if serve else [])


# ------------------------------------------------------------------------- exploration: what the MCP tools served


@explore_app.command("blocks")
def explore_blocks(dataset: str = typer.Argument(None), event: str = typer.Argument(None)) -> None:
    """The fitted blocks in the store, by dataset, event, graph and years: a block is fitted before its fields are
    read."""
    from . import tools

    rows = tools.fitted(dataset, event)
    if _emit_json(rows):
        return
    t = Table("dataset", "event", "graph", "years", "block")
    for r in rows:
        y = r["years"]
        t.add_row(r["dataset"], r["event"], r["graph"], f"{y[0]}-{y[-1]}" if y else "", r["block"])
    console.print(t)


@explore_app.command("lead")
def explore_lead(lead_id: str) -> None:
    """One lead in full: its lens's statistics and null, its triage with evidence, each replication, its siblings and
    its story."""
    from . import workspace

    console.print_json(json.dumps(workspace.lead(lead_id), default=str))


@explore_app.command("methods")
def explore_methods() -> None:
    """Every method's measured record (ARCHITECTURE §10.5): the documented events it found, its findings in null
    worlds."""
    from . import workspace

    console.print_json(json.dumps(workspace.methods(), default=str))


@explore_app.command("confirm")
def explore_confirm(node: str = typer.Argument(..., help="the field: an ICD-10 node"),
                    lens: str = typer.Argument(..., help="outbreak | change_point | space_time | spatial_cluster"),
                    places: str = typer.Option(..., help="municipality codes, comma-separated"),
                    years: str = typer.Option(..., help="first-last: the window the lead was selected on"),
                    direction: str = typer.Option(..., help="up | down"),
                    caller: str = typer.Option(..., help="who asks: recorded with the claim"),
                    spend: bool = typer.Option(False, help="spend the reserve; without it, a dry run"),
                    dataset: str = "SIM.DO", event: str = "death", span: str = "2010-2023",
                    graph: str = "contiguity") -> None:
    """SPENDS error budget. Test one claim, fixed before looking, once on the confirmation reserve (the reserved period
    no scan, fit or exploration reads) under online FDR (LOND). Without --spend, the level it would be tested at; a
    claim already spent returns its earlier verdict."""
    from . import control, replication

    if lens not in replication.THETA:
        raise typer.BadParameter(f"lens {lens!r} cannot be confirmed; one of {sorted(replication.THETA)}")
    if direction not in ("up", "down"):
        raise typer.BadParameter("direction is up or down")
    span_years = _years(years) if "-" in years else [int(years)]
    locus = {"places": sorted(int(x) for x in places.split(",")), "years": [span_years[0], span_years[-1]],
             "direction": direction}
    s = _session(dataset, event, span, graph)
    s.expectations.field(node)
    spec = {"field": node, "lens": lens, "locus": locus}
    reserve = control.Reserve(s.ledger)
    prev = reserve.previous(spec)
    if prev:
        console.print_json(json.dumps({"status": "already_spent", "claim": spec, "earlier": prev}, default=str))
        return
    if not spend:
        console.print_json(json.dumps({"status": "dry_run", "claim": spec, "reserve": reserve.status()}, default=str))
        return
    result = s.confirm(node, lens, locus, actor="person", caller=caller.strip())
    console.print_json(json.dumps({"status": "spent", "claim": spec, "result": result,
                                   "reserve": control.Reserve(s.ledger).status()}, default=str))


def main() -> None:
    """The console entry point. Click expands wildcards in arguments on Windows, which turned the root field ``*``
    into the folder's file names; the arguments are passed as typed. A refusal the engine states (a bad name, filter
    or query; a study already running) is printed as its sentence, not a traceback."""
    try:
        app(windows_expand_args=False, standalone_mode=True)
    except (ValueError, LookupError, FileNotFoundError, PermissionError, RuntimeError) as exc:
        if STATE["json"]:
            sys.stdout.write(json.dumps({"error": type(exc).__name__, "detail": str(exc)}, ensure_ascii=False) + "\n")
        else:
            console.print(f"[bold red]{type(exc).__name__}:[/bold red] {exc}", highlight=False)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
