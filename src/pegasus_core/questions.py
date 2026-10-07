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
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Method:
    id: str                     # the name `tools.Session.scan` runs
    assumptions: str
    regimes: str = "any"


@dataclass(frozen=True)
class Question:
    id: str
    stage: str
    estimand: str
    reference: str
    locus: str
    scale: str
    methods: tuple[Method, ...]


QUESTIONS: dict[str, Question] = {q.id: q for q in (
    Question("excess", "C", "counts above the expectation in a place and period, at any spatial scale", "B1",
             "area × period", "rate ratio", (
                 Method("cell_excess", "two-group model on the PIT scores; supports from the IBGE ladder"),
                 Method("excess", "multiscale graph peaks of a gamma tail score; places joined by N1's noise"),
                 Method("outbreak", "each cell's NB tail, BH; the v0 lens"),
             )),
    Question("step", "C", "a lasting rise in level from some period to the series' end", "B1",
             "area × window", "rate ratio", (
                 Method("excess_step", "multiscale graph peaks of suffix sums; N1's correlation over periods"),
                 Method("step", "Bayesian single change point per place, tempered by N1's correlation"),
                 Method("change_point", "trailing-window NB tails against the place's past course; the v0 lens"),
             )),
    Question("trend", "C", "a course bending upward from some period", "B1", "area × window", "rate ratio", (
        Method("excess_trend", "multiscale graph peaks of hinge contrasts"),
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


def _years(f) -> tuple[int, int]:
    y = f.locus.get("years") or [-10 ** 9, 10 ** 9]
    return int(y[0]), int(y[-1])


def ask(session, question: str, node: str, q: float = 0.05, **kw) -> list[Answer]:
    """Every method of ``question`` on the field ``node`` at q/k, the union merged into answers by overlapping loci,
    strongest first. A method that fails is reported in the answer list's ``failed`` attribute and the rest go on."""
    qn = QUESTIONS[question]
    k = len(qn.methods)
    answers: list[Answer] = []
    failed = {}
    for m in qn.methods:
        try:
            found = session.scan(node, m.id, q=q / k, **kw)
        except Exception as exc:  # noqa: BLE001 - one method's failure is reported, the question still answered
            failed[m.id] = f"{type(exc).__name__}: {exc}"
            continue
        for f in found:
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
    out = AnswerList(answers)
    out.failed = failed
    return out


class AnswerList(list):
    failed: dict


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
            "methods": a.methods, "p": float(f"{a.p:.3g}"),
            "effects": {m: round(float(f.effect), 2) for m, f in a.findings.items()}}
