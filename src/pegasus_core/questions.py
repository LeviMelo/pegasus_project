"""Questions and the methods that answer them (docs/plans/2026-10-07-questions-and-methods.md).

A **question** is fixed: its estimand, stage, reference tier, locus type and effect scale. Its **methods** are
interchangeable answers, each with assumptions and a measured record (calibration on null worlds, recall on the
documented events of ARCHITECTURE §10.1, real negative controls). An investigation branches into many methods towards
one question without multiplying its claims:

- **Multiplicity is the question's.** Each of a question's k methods runs at q/k and the findings are their union,
  whose false-discovery rate is at most the sum, q (a union bound). Adding a method cannot buy findings. The Cauchy
  combination of per-locus p-values (Liu & Xie 2020) replaces this once every method reports a p-value at every
  locus, not only at its selected ones.
- **Agreement is reported.** Findings of different methods whose loci overlap (a shared place and overlapping
  periods) are one answer, which names every method that found it, with each method's effect, p-value and scale.
  A regional finding no cell method shows, or the reverse, is a statement about the departure's scale.
- **Roles come from records**, never from a constant tuned to make an event appear.
- **The course in time is attributed, not assumed.** A method's contrast can fire on a departure of another shape (a
  suffix sum on a one-year epidemic). Each finding carries its shape by Chen & Liu's intervention analysis
  (`departures.attribute`); an answer none of whose findings takes one of the question's ``shapes`` is not discarded
  but returned apart (``AnswerList.other_shape``): it answers a sibling question.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Method:
    id: str                     # the name `tools.Session.scan` runs
    assumptions: str
    regimes: str = "any"
    kinds: tuple[str, ...] = ("count",)     # the field kinds it reads (count; mark: a measurement's location)


@dataclass(frozen=True)
class Question:
    id: str
    stage: str
    estimand: str
    reference: str
    locus: str
    scale: str
    methods: tuple[Method, ...]
    shapes: tuple[str, ...] = ()                # the courses in time that answer it (`departures.attribute`); () any


QUESTIONS: dict[str, Question] = {q.id: q for q in (
    Question("excess", "C", "counts above the expectation in a place and period, at any spatial scale", "B1",
             "area × period", "rate ratio", (
                 Method("cell_excess", "two-group model on the PIT scores; supports from the IBGE ladder",
                        kinds=("count", "mark")),
                 Method("excess", "multiscale graph peaks of a gamma tail score (a location's standardised excess); "
                                  "places joined by N1's noise", kinds=("count", "mark")),
                 Method("outbreak", "each cell's NB tail, BH; the v0 lens"),
             ), ("spike", "transient")),
    Question("step", "C", "a lasting rise in level from some period to the series' end", "B1",
             "area × window", "rate ratio", (
                 Method("excess_step", "multiscale graph peaks of suffix sums; N1's correlation over periods",
                        kinds=("count", "mark")),
                 Method("step", "Bayesian single change point per place, tempered by N1's correlation"),
                 Method("change_point", "trailing-window NB tails against the place's past course; the v0 lens"),
             ), ("step",)),
    Question("trend", "C", "a course bending upward from some period", "B1", "area × window", "rate ratio", (
        Method("excess_trend", "multiscale graph peaks of hinge contrasts", kinds=("count", "mark")),
    ), ("trend",)),
    # the questions the declared positives also ask (harness.POSITIVES), answered for now by their v0 lenses alone:
    # a question is kept while its departure model (ARCHITECTURE §12, O6: BYM2 exceedance, the group interaction) is
    # built, never dropped with its lens (CLAUDE.md)
    Question("cluster", "C", "a connected set of places above the expectation over the whole period", "B0", "area",
             "rate ratio", (
                 Method("excess_level", "multiscale graph peaks of the whole period's excess against B0 (no place "
                                        "effects), STEM; a cluster at its own scale, no zoning", kinds=("count", "mark")),
                 Method("spatial_cluster", "expectation-based Poisson scan over graph-connected sets; the v0 lens"),
             )),
    Question("share", "C", "a field's share of all events departing from its expectation in a place and period: "
             "recording practice (the ill-defined share) or composition", "B1", "area × period", "share ratio", (
                 Method("share_excess", "beta-binomial on the observed total, the share expected from stage B, "
                                        "θ by central matching; two-sided"),
             )),
    Question("institution", "C", "one institution's events departing, over a window, from its catchment's expectation "
             "(a step specific to it, or the volume of all its chapters)", "B1", "institution × window", "rate ratio", (
                 Method("institution_step", "best window's likelihood ratio against the facility's constant ratio to "
                                            "its catchment; Bonferroni over the T(T+1)/2 windows; the v0 lattice's gates"),
             )),
    Question("group", "C", "a place whose excess differs across sex × age groups from the national pattern", "B0",
             "area × group", "rate ratio", (
                 Method("group_disparity", "likelihood-ratio heterogeneity of the groups' SIRs; the v0 lens"),
             )),
)}


@dataclass
class Answer:
    """One locus answering a question: the places and periods every agreeing method covered, and each method's
    finding there."""
    question: str
    places: set
    years: tuple
    findings: dict = field(default_factory=dict)        # method -> the finding

    @property
    def methods(self) -> list[str]:
        return sorted(self.findings)

    @property
    def p(self) -> float:
        return min(f.p for f in self.findings.values())

    @property
    def shapes(self) -> dict[str, str]:
        """Each method's attributed course in time; "unattributed" where the method reports none."""
        return {m: f.stats.get("shape", {}).get("shape", "unattributed") for m, f in self.findings.items()}


def _years(f) -> tuple[int, int]:
    y = f.locus.get("years") or [-10 ** 9, 10 ** 9]
    return int(y[0]), int(y[-1])


def _shape(session, node: str, f, tier: str) -> dict:
    """A finding's course in time when its method does not report one: `departures.attribute` on the field's series
    summed over the finding's places, its window the finding's years. Every method's answer then carries a shape."""
    from . import departures

    s = session.surprise(node, tier)
    w = np.isin(np.asarray(s.places).astype(int), [int(p) for p in f.locus.get("places", [])]).astype(float)
    if not w.any():
        return {"shape": "unattributed"}
    y0, y1 = _years(f)
    yrs = np.asarray(s.years)
    inside = np.flatnonzero((yrs >= y0) & (yrs <= y1))
    window = (int(inside[0]), int(inside[-1]) + 1) if inside.size else None
    return departures.attribute(*departures.series(s, w), window=window, years=s.years)


def ask(session, question: str, node: str, q: float = 0.05, **kw) -> list[Answer]:
    """Every method of ``question`` on the field ``node`` at q/k, the union merged into answers by overlapping loci,
    strongest first. A method that fails is reported in the answer list's ``failed`` attribute and the rest go on."""
    # one surprise per (node, tier) while the question is asked: every method and every finding's shape reads it
    # (recomputed per finding, a field's hundreds of cell findings each re-ran N1's estimation, 2026-10-07)
    owner = getattr(session._local, "memo", None) is None
    if owner:
        session._local.memo = {}
    try:
        return _ask(session, question, node, q, **kw)
    finally:
        if owner:
            session._local.memo = None


def _ask(session, question: str, node: str, q: float = 0.05, **kw) -> list[Answer]:
    qn = QUESTIONS[question]
    kind = session.surprise(node, kw.get("tier", "B1")).extras.get("kind", "count")
    methods = [m for m in qn.methods if kind in m.kinds]
    k = max(len(methods), 1)
    answers: list[Answer] = []
    failed = {} if methods else {"*": f"no method of {question!r} reads a {kind} field yet"}
    for m in methods:
        try:
            found = session.scan(node, m.id, q=q / k, **kw)
        except Exception as exc:  # noqa: BLE001 - one method's failure is reported, the question still answered
            failed[m.id] = f"{type(exc).__name__}: {exc}"
            continue
        for f in found:
            if "shape" not in f.stats:
                f.stats["shape"] = _shape(session, node, f, kw.get("tier", "B1"))
            pl, (y0, y1) = {int(p) for p in f.locus.get("places", [])}, _years(f)
            home = None
            for a in answers:
                if a.places & pl and a.years[0] <= y1 and y0 <= a.years[1]:
                    home = a
                    break
            if home is None:
                home = Answer(question, set(pl), (y0, y1))
                answers.append(home)
            else:
                home.places |= pl
                home.years = (min(home.years[0], y0), max(home.years[1], y1))
            if m.id not in home.findings or f.p < home.findings[m.id].p:
                home.findings[m.id] = f
    answers.sort(key=lambda a: a.p)
    fits = [not qn.shapes or any(v in qn.shapes or v == "unattributed" for v in a.shapes.values()) for a in answers]
    out = AnswerList([a for a, ok in zip(answers, fits, strict=True) if ok])
    out.other_shape = [a for a, ok in zip(answers, fits, strict=True) if not ok]
    out.failed = failed
    out.k = k                   # the methods that read this field's kind: the answer's Bonferroni factor
    return out


class AnswerList(list):
    failed: dict
    other_shape: list
    k: int


def agreement(answers: list[Answer]) -> dict[str, int]:
    """How many answers each combination of methods produced."""
    out: dict[str, int] = {}
    for a in answers:
        key = "+".join(a.methods)
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def summary(a: Answer) -> dict:
    states = np.unique(np.array(sorted(a.places)) // 10000).tolist() if a.places else []
    return {"question": a.question, "years": list(a.years), "places": len(a.places), "states": states,
            "methods": a.methods, "p": float(f"{a.p:.3g}"), "shapes": a.shapes,
            "effects": {m: round(float(f.effect), 2) for m, f in a.findings.items()}}
