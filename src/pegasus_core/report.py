"""Stage F (ARCHITECTURE §1.1, O10): the register read as a person would read it.

For each family of answers (a stage-C question in a block), the strongest answers: the field, the years, the
municipalities that carry them (named, from pegasus_data's geography), the effect, which methods agree and the
shape each attributes, the triage class (stage E) and the replication tier. Then the strongest relations (stage D),
with the scales left unanswered. A report states what the statistics say; whether a lead is an event in the world is
its triage's and the reader's (P16)."""

from __future__ import annotations

import collections
from pathlib import Path

from . import leads as register_mod


def _names() -> dict:
    from . import gateway

    try:
        return gateway.municipality_names()
    except Exception:  # noqa: BLE001 - names are a convenience: codes stand in without them
        return {}


def _place(code, names: dict) -> str:
    m = names.get(str(int(code))[:6])
    return f"{m['name']}/{m['uf_sigla']}" if m else str(code)


def _answer_row(ld: register_mod.Lead, names: dict) -> str:
    pl = ld.locus.get("places", [])
    by = ld.provenance.get("by_method", {})
    shapes = ", ".join(f"{m}:{v.get('stats', {}).get('shape', {}).get('shape')}" for m, v in by.items()
                       if v.get("stats", {}).get("shape"))
    tri = ld.robustness.get("triage", {})
    yrs = ld.locus.get("years") or ["", ""]
    return (f"| {ld.fields[0].split(':')[-1]} | {yrs[0]}–{yrs[-1]} | {', '.join(_place(c, names) for c in pl[:4])}"
            f"{f' (+{len(pl) - 4})' if len(pl) > 4 else ''} | {ld.effect:.2f} | {'+'.join(ld.provenance.get('methods', []))} "
            f"| {shapes} | {tri.get('class', '')} | {ld.replication} | {ld.q:.1e} |")


def report(leads: list[register_mod.Lead] | None = None, limit: int = 25, title: str = "PegaSUS leads") -> str:
    """The register (or ``leads``) as Markdown: answers per family, then relations, strongest first."""
    leads = register_mod.Register().current() if leads is None else leads
    names = _names()
    out = [f"# {title}", ""]
    answers = collections.defaultdict(list)
    for ld in leads:
        if ld.kind == "answer" and ld.status != "retired":
            answers[ld.family].append(ld)
    for fam in sorted(answers):
        group = sorted(answers[fam], key=lambda x: -x.rank)   # §9.1: evidence × effect × replication
        explained = sum(x.status == "explained" for x in group)
        out += [f"## {fam}: {len(group)} answers{f', {explained} explained by triage' if explained else ''}", "",
                "| field | years | places | effect | methods | shapes | triage | tier | q |",
                "|---|---|---|---|---|---|---|---|---|"]
        out += [_answer_row(x, names) for x in group[:limit]]
        out.append("")
    rel = sorted((x for x in leads if x.kind == "relation" and x.status != "retired"), key=lambda x: -x.rank)
    if rel:
        out += [f"## Relations: {len(rel)}", "", "| band | field | leader | lag | ρ | direct | q |", "|---|---|---|---|---|---|---|"]
        out += [f"| {x.locus.get('band')} | {x.fields[0]} | {x.fields[1]} | {x.locus.get('lag')} | {x.effect:+.3f} | "
                f"{ {True: 'direct', False: 'shared driver'}.get(x.provenance.get('direct'), '') } | {x.q:.1e} |"
                for x in rel[:limit]]
        unanswered = sorted({u for x in rel for u in x.provenance.get("unanswered", [])})
        if unanswered:
            out += ["", "**Scales left unanswered:**", *[f"- {u}" for u in unanswered]]
        out.append("")
    return "\n".join(out)


def write(path: str | Path, **kw) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(report(**kw), encoding="utf-8")
    return p
