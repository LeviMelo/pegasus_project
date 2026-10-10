"""Phase 4: prospective surveillance (ADR-0004; the alarm baseline, ADR-0012; ARCHITECTURE §12, O10).

Early alarms on recent, incomplete data, for every place of a field. Three pieces, each an established method:

- **Weeks.** One rule for every system (`epi_week`): the epidemiological week of SINAN and of the US MMWR, Sunday to
  Saturday, week 1 being the week that holds 4 January. SIM and SIH publish no week, so theirs are derived by the
  same rule, and SINAN's published NU_SEMANA is the rule's test.
- **The nowcast** (`delays`, `nowcast`). An event of onset week w is known by week w + d with probability F(d),
  the reporting delay's distribution. F is estimated per place from a closed year (the delay is not stable across
  years, states or epidemic load: evaluation 2026-10-05, surveillance lags), each place's distribution shrunk toward
  the nation's by empirical Bayes (a Dirichlet–multinomial with its concentration by the method of moments).
  Given y events known for a week of age a, binomial thinning gives the eventual count as y plus the events still
  to come, and the prior on the week's total is the alarm baseline's own NB(μ, φ) (the null being tested, as in the
  Bayesian nowcasts of Höhle & an der Heiden 2014 and McGough et al. 2020): with the Poisson–gamma form of that
  prior the events to come are NegBin(φ + y, (φ/μ + F) / (φ/μ + 1)). A flat prior on the total would read 1 death
  known at F = 0.26 as a week of 7 and alarm everywhere (2026-10-10).
- **The alarm** (`alarm`). The ADR's design is a false-alarm rate per place over time, a recurrence interval, not an
  FDR over one search. With the alarm baseline's predictive NB(μ, φ) (tier BPA, ADR-0012), a week's alarm threshold
  is its upper quantile at 1 − 1/R, R the declared recurrence in place-weeks (5 years: R = 260). A week alarms when the nowcast puts its eventual count at
  or above the threshold with probability at least ``confidence`` c. Under the baseline as the truth the posterior
  probability averages to the prior's 1/R, so by Markov's inequality a place with no departure raises at most one
  false alarm per c·R place-weeks (2 per R at c = 0.5), whatever its delay.
- **Weeks** (`window`). The last weeks that have ended by the as-of date, counted by position, so a window crosses
  an epidemiological year (and the calendar year of the files holding its events) without bookkeeping of its own.

What is not here yet: the revisions of preliminary files (records changed or discarded after they first appear,
ADR-0004 point 3), which need dated snapshots of pegasus_data's catalog; and the benchmark against InfoDengue's
alerts (point 5), which `harness` will hold beside the documented events.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from .gateway import epi_week  # noqa: F401 - the week rule is the data's (gateway); re-exported for readers


@dataclass
class Delays:
    """Each place's reporting-delay distribution: ``places`` [U], ``pmf`` [U, D + 1] (the last cell the delays of
    ``max_delay`` weeks and more), ``cdf`` F(d) [U, D + 1], the national pmf, and the Dirichlet concentration of the
    places around it."""
    places: np.ndarray
    pmf: np.ndarray
    cdf: np.ndarray
    national: np.ndarray
    concentration: float

    def F(self, place, age):
        """P(known within ``age`` weeks of onset) at ``place`` (the national F for a place with no history); arrays
        of places and ages give an array."""
        place, age = np.broadcast_arrays(np.asarray(place), np.asarray(age))
        i = np.minimum(np.searchsorted(self.places, place), len(self.places) - 1)
        known = self.places[i] == place
        rows = np.where(known[..., None], self.cdf[i], np.cumsum(self.national))
        a = np.clip(age, 0, rows.shape[-1] - 1)
        out = np.take_along_axis(rows, a[..., None], axis=-1)[..., 0]
        return out if place.ndim else float(out)


def delays(table, max_delay: int = 26) -> Delays:
    """`Delays` from a closed year's delay counts (`gateway.delay_counts`: u, delay, n): each place's pmf is its
    counts plus the national pmf times a concentration α, normalised (the posterior mean under a Dirichlet prior
    centred on the nation). α by the method of moments: the places' between-place variance of the delay shares
    against the multinomial variance their counts would give (Mosimann 1962)."""
    u = np.asarray(table.column("u").to_numpy(zero_copy_only=False)).astype(np.int64)
    d = np.minimum(np.asarray(table.column("delay").to_numpy(zero_copy_only=False)).astype(np.int64), max_delay)
    n = np.asarray(table.column("n").to_numpy(zero_copy_only=False)).astype(float)
    places, inv = np.unique(u, return_inverse=True)
    C = np.zeros((len(places), max_delay + 1))
    np.add.at(C, (inv, d), n)
    nat = C.sum(0) / max(C.sum(), 1.0)
    tot = C.sum(1)
    big = tot >= 20
    alpha = 50.0
    if big.sum() >= 10:
        share = C[big] / tot[big, None]
        between = float(np.average(((share - nat) ** 2).sum(1), weights=tot[big]))
        multinomial = float(np.average((nat * (1 - nat)).sum() / tot[big], weights=tot[big]))
        # Var(share) = (1 − nat)nat · (1/N + (1 − 1/N)/(α + 1)) under the Dirichlet–multinomial: solve for α
        excess = between - multinomial
        alpha = float(np.clip((nat * (1 - nat)).sum() / max(excess, 1e-9) - 1.0, 1.0, 1e5)) if excess > 0 else 1e5
    pmf = (C + alpha * nat) / (tot + alpha)[:, None]
    return Delays(places, pmf, np.cumsum(pmf, 1), nat, alpha)


def _pending(known, F, mu, phi) -> tuple:
    """The events still to come for a week, with its baseline NB(μ, φ) as the prior on its total (a gamma frailty
    λ ~ Gamma(φ, φ/μ) times a Poisson). The known y ~ Poisson(λF) and the pending ~ Poisson(λ(1 − F)) are independent
    given λ, so λ | y ~ Gamma(φ + y, φ/μ + F) and the pending are NegBin(φ + y, p) with p = rate / (rate + 1 − F),
    rate = φ/μ + F; Poisson(μ(1 − F)) where φ is infinite. Returns y, F, the NegBin's size and p, the Poisson's mean
    and the mask of the finite φ, all of one shape."""
    y, f, m = np.broadcast_arrays(np.asarray(known, dtype=float), np.clip(np.asarray(F, dtype=float), 1e-6, 1.0),
                                  np.maximum(np.asarray(mu, dtype=float), 1e-12))
    ph = np.broadcast_to(np.asarray(phi, dtype=float), y.shape)
    fin = np.isfinite(ph)
    shape = np.where(fin, ph, 1.0)
    rate = shape / m + f
    return y, f, shape + y, rate / (rate + 1 - f), m * (1 - f), fin


def nowcast(known: np.ndarray, F: np.ndarray, mu: np.ndarray, phi: np.ndarray | float,
            quantiles: tuple[float, ...] = (0.05, 0.5, 0.95)) -> dict:
    """The eventual counts of recent weeks: ``known`` [n] the events known so far, ``F`` [n] the probability an event
    of each week is known by now, ``mu`` and ``phi`` the week's baseline NB, the prior on its total (`_pending`).
    Returns the posterior mean and the requested quantiles of the eventual count. F = 1 gives the known count; a
    week whose F is near 0 gives its baseline."""
    y, f, n, p, lam, fin = _pending(known, F, mu, phi)
    out = {"mean": y + np.where(fin, n * (1 - p) / p, lam)}
    for qq in quantiles:
        out[qq] = y + np.where(fin, stats.nbinom.ppf(qq, n, p), stats.poisson.ppf(qq, lam))
    return out


def threshold(mu: np.ndarray, phi: np.ndarray | float, recurrence: float) -> np.ndarray:
    """The alarm threshold: the smallest count k with P(Y ≥ k) ≤ 1/R under the baseline's NB(μ, φ) (Poisson where φ
    is infinite), R the recurrence interval in place-weeks."""
    mu = np.asarray(mu, dtype=float)
    ph = np.broadcast_to(np.asarray(phi, dtype=float), mu.shape)
    p = 1.0 / recurrence
    fin = np.isfinite(ph)
    n = np.where(fin, ph, 1.0)
    k = np.where(fin, stats.nbinom.isf(p, n, n / (n + np.maximum(mu, 1e-12))),
                 stats.poisson.isf(p, np.maximum(mu, 1e-12)))
    return k + 1.0


def alarm(known: np.ndarray, F: np.ndarray, mu: np.ndarray, phi: np.ndarray | float, recurrence: float = 260.0,
          confidence: float = 0.5) -> dict:
    """Alarms for recent place-weeks: ``known`` events so far, ``F`` the share known by now (`Delays.F`), ``mu`` and
    ``phi`` the alarm baseline's predictive (tier BPA). P(eventual ≥ threshold) is P(pending ≥ k − y) under
    `_pending`; a week alarms when it is at least ``confidence``. Returns the threshold, that probability, the
    nowcast's mean and the alarm flags."""
    y, f, n, p, lam, fin = _pending(known, F, mu, phi)
    k = threshold(mu, phi, recurrence)
    need = k - y
    p_exceed = np.where(need <= 0, 1.0, np.where(fin, stats.nbinom.sf(need - 1, n, p), stats.poisson.sf(need - 1, lam)))
    return {"threshold": k, "p_exceed": p_exceed, "nowcast": nowcast(y, f, mu, phi, ())["mean"],
            "alarm": p_exceed >= confidence, "recurrence": recurrence}


def window(day, weeks: int) -> dict:
    """The last ``weeks`` epidemiological weeks that have ended by ``day`` (a week ends on its Saturday, so ``day`` itself
    closes a week only when it is one), by ``age`` (0 the newest): ``start`` (its Sunday), ``year`` and ``week``
    (`epi_week`) and ``anchor`` (its Wednesday, whose calendar year and month a baseline period is read at). A week
    still running is not a week of events: its total is not yet there to be nowcast, and a first week of the year
    holding one day of it read as a whole week was the boundary's false alarms (evaluation 2026-10-10). Delays are
    whole weeks, so a week's age is the weeks since it ended."""
    d = np.datetime64(day, "D")
    end = d - ((d.astype(np.int64) + 4 + 1) % 7).astype("timedelta64[D]")           # the last Saturday on or before d
    age = np.arange(weeks)
    start = end - np.timedelta64(6, "D") - (7 * age).astype("timedelta64[D]")
    ey, ew = epi_week(start)
    return {"age": age, "start": start, "year": ey, "week": ew, "anchor": start + np.timedelta64(3, "D")}


def expected_false_alarms(places: int, weeks: int, recurrence: float) -> float:
    """The false alarms the design allows: places × weeks / R (the ADR's calibration target, checked on null worlds)."""
    return places * weeks / recurrence
