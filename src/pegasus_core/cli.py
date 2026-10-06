"""The ``pegasus-core`` command (ARCHITECTURE §9.3): a thin layer over `tools`."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="PegaSUS: one model of Brazil's health events, read for leads.", no_args_is_help=True)
console = Console()

Years = typer.Option("2010-2023", help="first-last year of the fitted monolith")


def _years(text: str) -> list[int]:
    a, b = text.split("-")
    return list(range(int(a), int(b) + 1))


def _session(dataset: str, event: str, years: str, graph: str):
    from . import tools

    return tools.Session(dataset, event, _years(years), graph)


@app.command()
def fit(dataset: str, event: str, blocks: list[str], years: str = Years, graph: str = "contiguity",
        device: str = "cpu") -> None:
    """Fit monolith blocks (chapters) and store them."""
    from . import graphs, monolith

    for block in blocks:
        data = monolith.assemble(dataset, event, block, _years(years))
        model = monolith.Monolith(data, graphs.graph(data.places, graph), graph, device=device)
        model.fit(log=lambda line, b=block: console.print(f"{b} {line}"))
        model.save()
        console.print_json(json.dumps(model.summary(), default=float))


@app.command()
def fields(dataset: str, event: str, block: str, years: str = Years, graph: str = "contiguity") -> None:
    """The admissible fields of a fitted block."""
    s = _session(dataset, event, years, graph)
    t = Table("field", "level", "label")
    for f in s.fields(block):
        t.add_row(f.node, f.level, f.label[:70])
    console.print(t)


@app.command()
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


@app.command()
def scan(dataset: str, event: str, node: str, lens: str, years: str = Years, graph: str = "contiguity",
         tier: str = typer.Option(None, help="defaults to the lens's tier")) -> None:
    """One lens on one field (ledgered)."""
    hits = _session(dataset, event, years, graph).scan(node, lens, tier)
    t = Table("locus", "effect", "p")
    for h in sorted(hits, key=lambda h: h.p)[:30]:
        t.add_row(json.dumps(h.locus)[:80], f"{h.effect:.3g}", f"{h.p:.2g}")
    console.print(t)


@app.command()
def survey(dataset: str, event: str, years: str = Years, graph: str = "contiguity",
           blocks: list[str] = typer.Option(None, help="default: every fitted block"),
           replicates: int = 100
           ) -> None:
    """The scheduled pass: every field with events, every lens combination, error control, leads with their method record."""
    s = _session(dataset, event, years, graph)
    admitted = s.survey(blocks or None, replicates=replicates, log=console.print)
    console.print(f"{len(admitted)} leads admitted")


@app.command()
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


@app.command()
def grid(dataset: str, event: str, node: str, years: str = Years, graph: str = "contiguity",
         kinds: str = "place,cluster,region,state,macro", shapes: str = "spike,step,trend,group",
         lenses: str = ",".join(("outbreak", "change_point", "space_time", "spatial_cluster", "trend_divergence",
                                "group_disparity")),
         worlds: int = 4, null_worlds: int = 4, replicates: int = 100, out: str = typer.Option(None),
         minimum_effects: str = typer.Option(None, help='JSON of minimum effects (theta0) per lens, e.g. {"outbreak": [1.0, 1.2, 1.5]}'),
         tiers: str = typer.Option(None, help='JSON of expectation tiers per lens, e.g. {"change_point": ["B1", "B2"]}')
         ) -> None:
    """The designed grid of planted signals (§10.3) on one field: refitted worlds read by the production lenses, the
    false leads of null worlds, and each lens's power surface (minimum detectable rate ratio by expected events)."""
    from . import harness as h

    res = h.grid(_session(dataset, event, years, graph), node, kinds=tuple(kinds.split(",")),
                 shapes=tuple(shapes.split(",")), lens_names=tuple(lenses.split(",")), worlds=worlds,
                 null_worlds=null_worlds, replicates=replicates, log=console.print,
                 sink=str(Path(out).with_suffix(".jsonl")) if out else None,
                 minimum_effects={k: tuple(v) for k, v in json.loads(minimum_effects).items()} if minimum_effects else None,
                 tiers={k: tuple(v) for k, v in json.loads(tiers).items()} if tiers else None)
    res["surface"], res["absorbed"] = h.surface(res["rows"]), h.absorbed(res["rows"])
    if out:
        Path(out).write_text(json.dumps(res, default=float), encoding="utf-8")
    console.print_json(json.dumps(res["surface"], default=float))


@app.command()
def leads(limit: int = 30, kind: str = typer.Option(None)) -> None:
    """The lead register, best rank first."""
    from . import leads as register

    t = Table("rank", "id", "kind", "estimand", "calibrated", "field", "locus", "effect", "q", "R")
    for x in [x for x in register.Register().current() if kind is None or x.kind == kind][:limit]:
        t.add_row(f"{x.rank:.2f}", x.id, x.kind, x.estimand, str(x.method.get("calibrated", "")), x.fields[0].split(":")[-1],
                  json.dumps(x.locus)[:50], f"{x.effect:.3g}", f"{x.q:.2g}", x.replication)
    console.print(t)


@app.command()
def stories(limit: int = 25) -> None:
    """Leads grouped into stories (by place or subset), best first."""
    from . import leads as register

    t = Table("rank", "story", "fields", "leads", "flags")
    for st in register.stories(register.Register().current())[:limit]:
        t.add_row(f"{st.rank:.1f}", st.key, ", ".join(st.fields)[:60], str(len(st.leads)), "; ".join(st.flags)[:50])
    console.print(t)


@app.command()
def ledger(family: str = typer.Option(None)) -> None:
    """Tests in the ledger, by family."""
    from collections import Counter

    from . import control

    rows = control.Ledger().table().to_pylist()
    counts = Counter(r["family"] for r in rows if r["kind"] == "pending" and (family is None or r["family"] == family))
    t = Table("family", "tests")
    for k, v in counts.most_common():
        t.add_row(k, str(v))
    console.print(t)


@app.command("split-fit")
def split_fit(dataset: str, event: str, blocks: list[str], years: str = Years, graph: str = "contiguity",
              device: str = "cpu") -> None:
    """Deal the events of blocks to the sides A, E and fit each block on side A alone (§8.3)."""
    from . import replication

    for block in blocks:
        model = replication.prepare(dataset, event, block, _years(years), graph, device,
                                    log=lambda line, b=block: console.print(f"{b} {line}"))
        console.print_json(json.dumps(model.summary(), default=float))


@app.command("split-survey")
def split_survey(dataset: str, event: str, years: str = Years, graph: str = "contiguity",
                 blocks: list[str] = typer.Option(None, help="default: every fitted block"),
                 replicates: int = 100) -> None:
    """The survey on side A, then the size of each lead it selects read on side E (§8.3: a size, never a verdict)."""
    s = _session(dataset, event, years, graph)
    admitted = s.side("A").survey(blocks or None, replicates=replicates, log=console.print)
    console.print(f"{len(admitted)} leads selected on side A")
    done = s.honest_sizes(log=console.print)
    console.print(f"{sum(1 for x in done if x.replications.get('honest', {}).get('sized'))} sized on side E")


@app.command("temporal-survey")
def temporal_survey(dataset: str, event: str, last: int, years: str = Years, graph: str = "contiguity",
                    blocks: list[str] = typer.Option(None, help="default: every fitted block"), replicates: int = 100) -> None:
    """Select on the years up to LAST (its own register leads_T<LAST>), then test what it selected on the later years of
    ``years`` against a fit that ends at LAST (§8.3, later years). Needs the blocks fitted on the years up to LAST."""
    s = _session(dataset, event, years, graph)
    admitted = s.train(last).survey(blocks or None, replicates=replicates, log=console.print)
    console.print(f"{len(admitted)} leads selected on the years up to {last}")
    done = s.temporal_confirm(last, log=console.print)
    console.print(f"{sum(1 for x in done if x.replication != 'R0')} stand on the later years")


@app.command("mcp")
def mcp_command(allow_confirm: bool = typer.Option(False, help="let confirm_claim spend the confirmation reserve"),
                ledger: str = typer.Option(None, help="a ledger directory other than PEGASUS_HOME/ledger")) -> None:
    """Serve the tools over MCP on stdio (needs the `mcp` extra); read-only unless --allow-confirm."""
    from . import mcp_server

    mcp_server.main((["--allow-confirm"] if allow_confirm else []) + (["--ledger", ledger] if ledger else []))



@app.command("map")
def dependency_map(years: str = typer.Option("2015-2019", help="first-last year of the health fields"),
                   negatives: int = typer.Option(0, help="worlds of Moran-randomised surrogates for the false-edge rate"),
                   health_only: bool = typer.Option(False, help="negatives keep the real context fields"),
                   top: int = 20) -> None:
    """Dependency map (§7.6): SIM and SIH chapters, SINASC indicators and context fields, every testable pair in
    two layers (marginal E_b, conditional on the contexts), controlled over the whole map."""
    import numpy as np

    from . import tools

    r = tools.dependency_map(_years(years), negatives, health_only)
    console.print_json(json.dumps(r["summary"], default=float))
    e = r["edges"].to_pylist()
    e = [x for x in e if x["admitted"] or x.get("admitted_c")]
    e.sort(key=lambda x: -abs(x["rho"]) if np.isfinite(x["rho"]) else 0)
    t = Table("x", "y", "rho", "n_eff", "rho|Z", "status")
    for x in e[:top]:
        t.add_row(x["x"], x["y"], f"{x['rho']:+.3f}", f"{x['n_eff']:.0f}", f"{x['rho_c']:+.3f}", x["status"] or "-")
    console.print(t)


if __name__ == "__main__":
    app()
