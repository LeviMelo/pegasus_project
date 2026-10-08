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
from . import replication


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
    where = ", ".join(_place(c, names) for c in pl[:4]) + (f" (+{len(pl) - 4})" if len(pl) > 4 else "")
    if ld.locus.get("institutions"):
        where = "institution " + ", ".join(ld.locus["institutions"][:3]) + (f"; {where}" if where else "")
    return (f"| {ld.fields[0].split(':')[-1]} | {yrs[0]}–{yrs[-1]} | {where} | {ld.effect:.2f} | {'+'.join(ld.provenance.get('methods', []))} "
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
        group = sorted(answers[fam], key=register_mod.reading_order)   # §9.1: evidence × effect × replication
        explained = sum(x.status == "explained" for x in group)
        out += [f"## {fam}: {len(group)} answers{f', {explained} explained by triage' if explained else ''}", "",
                "| field | years | places | effect | methods | shapes | triage | tier | q |",
                "|---|---|---|---|---|---|---|---|---|"]
        out += [_answer_row(x, names) for x in group[:limit]]
        out.append("")
    rel = sorted((x for x in leads if x.kind == "relation" and x.status != "retired"), key=register_mod.reading_order)
    if rel:
        out += [f"## Relations: {len(rel)}", "", "| band | field | leader | lag | ρ | direct | q |", "|---|---|---|---|---|---|---|"]
        out += [f"| {x.locus.get('band')} | {x.fields[0]} | {x.fields[1]} | {x.locus.get('lag')} | {x.effect:+.3f} | "
                f"{ {True: 'direct', False: 'shared driver'}.get(x.provenance.get('direct'), '') } | {x.q:.1e} |"
                for x in rel[:limit]]
        unanswered = sorted({u for x in rel for u in x.provenance.get("unanswered", [])})
        if unanswered:
            out += ["", "**Scales left unanswered:**", *[f"- {u}" for u in unanswered]]
        out.append("")
    # race disparities (§3.4, S3.2): a place's race-j ratio over the reference race's, against Brazil's
    disp = sorted((x for x in leads if x.estimand == "race_disparity" and x.status != "retired"), key=register_mod.reading_order)
    if disp:
        out += [f"## Race disparities: {len(disp)}", "",
                "| field | place | race / reference | years | disparity | Brazil's | events | q |",
                "|---|---|---|---|---|---|---|---|"]
        out += [f"| {x.fields[0]} | {_place(x.locus['places'][0], names)} | {x.locus.get('race')} / "
                f"{x.locus.get('reference')} | {x.locus['years'][0]}–{x.locus['years'][-1]} | {x.effect:.2f} | "
                f"{x.provenance.get('national_disparity', 0):.2f} | {x.provenance.get('events', 0):.0f} / "
                f"{x.provenance.get('events_reference', 0):.0f} | {x.q:.1e} |" for x in disp[:limit]]
        out.append("")
    # cohorts (§7.8, S2.1): an attribute's level against its reference, for an outcome after the event
    coh = sorted((x for x in leads if x.kind == "cohort" and x.status != "retired"), key=register_mod.reading_order)
    if coh:
        out += [f"## Cohorts: {len(coh)}", "", "| persons | outcome | attribute: level / reference | rate ratio | q |",
                "|---|---|---|---|---|"]
        out += [f"| {x.fields[0]} | {x.fields[1] if len(x.fields) > 1 else ''} | {x.locus.get('attribute')}: "
                f"{x.locus.get('level')} / {x.locus.get('reference')} | {x.effect:.2f} | {x.q:.1e} |"
                for x in coh[:limit]]
        out.append("")
    return "\n".join(out)


def write(path: str | Path, **kw) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(report(**kw), encoding="utf-8")
    return p


# ---------------------------------------------------------------------- the dossier (S5)

VERDICTS = ("confirmed", "artefact", "unknown")


def _session(lead: register_mod.Lead, cache: dict):
    """The session a lead's field was read in (None when the lead has no places or its field no session)."""
    from . import config, graphs, tools

    if "source" not in lead.provenance or not lead.locus.get("places") or lead.fields[0].count(":") < 3:
        return None
    ds, ev, *_ = lead.fields[0].split(":")
    pv = lead.provenance
    key = (ds, ev, tuple(pv.get("years") or config.FIT_YEARS), pv.get("graph") or graphs.DEFAULT,
           repr(sorted((pv.get("source") or {}).items())))
    if key not in cache:
        cache[key] = tools.Session(ds, ev, list(key[2]), key[3], source=pv.get("source") or {})
    return cache[key]


def _codes_table(lead: register_mod.Lead, sess) -> str:
    """The lead's places' block by code and year around its window, the codes that move most first, the lead's own in
    bold: what a recoding or an event looks like in the counts (every verdict of the first dossier was read from it)."""
    import html

    import numpy as np

    node = lead.fields[0].split(":")[-1]
    try:
        d = sess._data(sess.expectations.registry.chapter(node))
        mine = {d.leaves[j] for j in sess._leaves(node)[1]}
    except Exception:  # noqa: BLE001 - a dossier without its table says so
        return "<p><i>codes not available</i></p>"
    if d.n is not None:                      # a measure's cells hold means, not counts
        return ""
    sel = np.isin(np.asarray(d.places).astype(int)[d.u], [int(p) for p in lead.locus["places"]])
    yrs = np.asarray(d.periods())
    w = lead.locus.get("years") or [int(yrs[0]), int(yrs[-1])]
    show = np.flatnonzero((yrs >= w[0] - 2) & (yrs <= w[-1] + 2))
    counts = np.zeros((len(d.leaves), len(yrs)))
    np.add.at(counts, (d.e[sel], d.t[sel]), d.y[sel])
    sub = counts[:, show]
    order = [i for i in np.argsort(-(sub.max(1) - sub.min(1)))[:8] if sub[i].max() > 0]
    head = "".join(f"<th>{int(yrs[j])}</th>" for j in show)
    rows = "".join(f"<tr><td>{'<b>' + html.escape(d.leaves[i]) + '</b>' if d.leaves[i] in mine else html.escape(d.leaves[i])}"
                   f"</td>" + "".join(f"<td>{sub[i, k]:.0f}</td>" for k in range(len(show))) + "</tr>" for i in order)
    total = "".join(f"<td>{v:.0f}</td>" for v in sub.sum(0))
    return (f"<table><tr><th>{html.escape(d.block)}</th>{head}</tr>{rows}<tr><td><i>all codes</i></td>{total}</tr></table>")


def _series_svg(lead: register_mod.Lead, sess) -> str:
    """The lead's locus summed over its places: observed against expected by period, as inline SVG (its field's B1
    surprise; empty when the lead has no session)."""
    import io

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    if sess is None:
        return ""
    places = lead.locus["places"]
    try:
        s = sess.surprise(lead.fields[0].split(":")[-1], "B1")
    except Exception:  # noqa: BLE001 - a dossier without its figure says so
        return "<p><i>series not available</i></p>"
    sel = np.isin(np.asarray(s.places).astype(int), [int(p) for p in places])
    y, mu = s.y[sel].sum(0), s.mu[sel].sum(0)
    yrs = np.asarray(s.years)
    fig, ax = plt.subplots(figsize=(6, 2.4))
    ax.plot(yrs, mu, color="0.5", label="expected (B1)")
    ax.plot(yrs, y, "o-", color="#b5302a", label="observed")
    w = lead.locus.get("years") or []
    if w:
        ax.axvspan(w[0] - 0.4, w[-1] + 0.4, color="#f2d0cc", alpha=0.6, lw=0)
    ax.legend(frameon=False, fontsize=8)
    ax.tick_params(labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    buf = io.StringIO()
    fig.tight_layout()
    fig.savefig(buf, format="svg")
    plt.close(fig)
    return buf.getvalue()[buf.getvalue().index("<svg"):]


def _claim(ld: register_mod.Lead, names: dict) -> str:
    where = ", ".join(_place(c, names) for c in (ld.locus.get("places") or [])[:5])
    if ld.locus.get("institutions"):
        where = "institution " + ", ".join(ld.locus["institutions"][:3])
    yrs = ld.locus.get("years") or ["", ""]
    what = ld.fields[0].split(":")[-1] if ld.fields else ""
    return (f"{ld.fields[0].split(':')[0] if ld.fields else ''} {what}: {ld.estimand} at {where or 'its locus'}, "
            f"{yrs[0]}–{yrs[-1]}, effect {ld.effect:.2f} ({ld.scale}), q {ld.q:.1e}")


def dossier(path: str | Path, limit: int = 30, kinds: tuple[str, ...] = ("answer", "relation", "subset", "cohort",
                                                                        "residual")) -> Path:
    """One HTML page of dossiers, the leads in §9.1's rank: each lead's claim, its locus's series against its
    expectation, the methods and shapes, stage E's verdict (triage class, grade, reason; replication; corroboration),
    the method's measured record, and its human verdict if one was recorded (`record_verdict`)."""
    import html

    names = _names()
    sessions: dict = {}
    leads = [x for x in register_mod.Register().current() if x.kind in kinds and x.status != "retired"]
    leads = sorted(leads, key=register_mod.reading_order)[:limit]
    parts = ["<!doctype html><meta charset='utf-8'><title>PegaSUS dossiers</title>",
             "<style>body{font:14px/1.45 system-ui,sans-serif;max-width:860px;margin:2em auto;padding:0 16px;color:#222}"
             "section{border-top:1px solid #ddd;padding:1em 0}h2{font-size:16px;margin:.2em 0}"
             "table{border-collapse:collapse;font-size:13px}td{padding:2px 8px;vertical-align:top}"
             ".k{color:#666;white-space:nowrap}</style>",
             f"<h1>PegaSUS: the first {len(leads)} leads by rank</h1>",
             "<p>Statistical leads (stages C–D), with stage E's reading. A person's verdict is recorded with "
             "<code>pegasus-core verdict LEAD_ID confirmed|artefact|unknown --note …</code>.</p>"]
    for ld in leads:
        tri = ld.robustness.get("triage", {})
        corr = ld.replications.get("corroboration", {})
        verdict = ld.robustness.get("verdict")
        fac = tri.get("facility") or {}
        rows = [("lead", f"{ld.id} ({ld.kind}, rank {ld.rank:.1f})"),
                ("methods", ", ".join(ld.provenance.get("methods", [])) or "—"),
                ("triage", f"{tri.get('class', '—')} ({tri.get('grade') or 'ungraded'}): {tri.get('reason', '')}"),
                ("facilities", f"{', '.join(fac.get('top', []))} carry {fac.get('share', 0):.0%} of the change"
                               f"{'; the place’s sole provider' if fac.get('sole_provider') else ''}; the codes' share "
                               f"inside them {fac.get('mix_inside', ['', ''])[0]} → {fac.get('mix_inside', ['', ''])[-1]}"
                               if fac.get("top") else "—"),
                ("replication", ld.replication),
                *((f"independent: {k}", v) for k, v in replication.account(ld).items()),
                ("corroboration", f"{corr.get('label', '—')}: {'yes' if corr.get('ok') else 'no'}"
                                  f" (p {corr.get('p', float('nan')):.2g})" if corr else "—"),
                ("method record", "; ".join(f"{m}: {r.get('calibrated')}" for m, r in (ld.method or {}).items()
                                            if isinstance(r, dict)) or "—"),
                ("verdict", f"{verdict['verdict']} — {verdict.get('note', '')}" if verdict else "none recorded")]
        sess = _session(ld, sessions)
        parts.append("<section><h2>" + html.escape(_claim(ld, names)) + "</h2>" + _series_svg(ld, sess) +
                     (_codes_table(ld, sess) if sess is not None else "") + "<table>" +
                     "".join(f"<tr><td class=k>{k}</td><td>{html.escape(str(v))}</td></tr>" for k, v in rows) +
                     "</table></section>")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(parts), encoding="utf-8")
    return p


def record_verdict(lead_id: str, verdict: str, note: str = "", by: str = "person") -> register_mod.Lead:
    """A person's verdict on a lead, written back to the register (§9.1): confirmed (an event in the world, which
    becomes a documented event for the methods that did not find it, `harness.verdict_positives`), artefact, or
    unknown. A verdict annotates the lead and orders it (an artefact after the others, `leads.Register.current`); it
    never closes it: only a tested explanation does (P14)."""
    import dataclasses
    import time

    if verdict not in VERDICTS:
        raise ValueError(f"verdict {verdict!r} not in {VERDICTS}")
    reg = register_mod.Register()
    ld = reg.get(lead_id)
    stamp = {"verdict": verdict, "note": note, "by": by, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    new = dataclasses.replace(ld, robustness={**ld.robustness, "verdict": stamp})
    reg.add([new])
    return new
