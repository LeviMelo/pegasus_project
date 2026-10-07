"""Phase 4: prospective surveillance (ADR-0004; the alarm baseline, ADR-0012; ARCHITECTURE §12, O10).

Early alarms on recent, incomplete data, for every place of a field. Three pieces, each an established method:

- **Weeks.** One rule for every system (`epi_week`): the epidemiological week of SINAN and of the US MMWR, Sunday to
  Saturday, week 1 being the week that holds 4 January. SIM and SIH publish no week, so theirs are derived by the
  same rule, and SINAN's published NU_SEMANA is the rule's test.
- **The nowcast** (`delays`, `nowcast`). An event of onset week w is known by week w + d with probability F(d),
  the reporting delay's distribution. F is estimated per place from a closed year (the delay is not stable across
  years, states or epidemic load: evaluation 2026-10-05, surveillance lags), each place's distribution shrunk toward
  the nation's by empirical Bayes (a Dirichlet–multinomial with its concentration by the method of moments).
  Given y events known for a week of age a, binomial thinning with a flat prior on the week's total gives the
  eventual count as y + NegBin(y + 1, F(a)) (the Poisson–gamma form of the nowcasts of Höhle & an der Heiden 2014 and
  McGough et al. 2020, without their smoothing over weeks).
- **The alarm** (`alarm`). The ADR's design is a false-alarm rate per place over time, a recurrence interval, not an
  FDR over one search. With the alarm baseline's predictive NB(μ, φ) (tier BPA, ADR-0012), a week's alarm threshold
  is its upper quantile at 1 − 1/R, R the declared recurrence in place-weeks (5 years: R = 260), so a place with no
  departure raises one false alarm per R weeks. A week alarms when the nowcast puts its eventual count at or above
  the threshold with probability at least ``confidence``.

What is not here yet: the revisions of preliminary files (records changed or discarded after they first appear,
ADR-0004 point 3), which need dated snapshots of pegasus_data's catalog; and the benchmark against InfoDengue's
alerts (point 5), which `harness` will hold beside the documented events.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


def epi_week(dates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(epidemiological year, week) of each date (datetime64[D]): weeks run Sunday to Saturday, and week 1 of year
    Y is the week holding 4 January of Y, so a week belongs to the year of its Wednesday."""
    d = np.asarray(dates, dtype="datetime64[D]")
    dow = (d.astype(np.int64) + 4) % 7                   # 1970-01-01 was a Thursday: 0 = Sunday
    start = d - dow.astype("timedelta64[D]")
    year = (start + np.timedelta64(3, "D")).astype("datetime64[Y]").astype(np.int64) + 1970
    jan4 = (np.array(year - 1970, dtype="datetime64[Y]").astype("datetime64[D]") + np.timedelta64(3, "D"))
    first = jan4 - ((jan4.astype(np.int64) + 4) % 7).astype("timedelta64[D]")
    week = ((start - first).astype(np.int64) // 7 + 1).astype(np.int64)
    return year.astype(np.int64), week


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

    def F(self, place: int, age: int) -> float:
        """P(known within ``age`` weeks of onset) at ``place`` (the national F for a place with no history)."""
        i = np.searchsorted(self.places, place)
        row = self.cdf[i] if i < len(self.places) and self.places[i] == place else np.cumsum(self.national)
        return float(row[min(max(age, 0), len(row) - 1)])


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


def nowcast(known: np.ndarray, F: np.ndarray, quantiles: tuple[float, ...] = (0.05, 0.5, 0.95)) -> dict:
    """The eventual counts of recent weeks: ``known`` [n] the events known so far, ``F`` [n] the probability an event
    of each week is known by now. Under binomial thinning with a flat prior on the week's total, the events still to
    come are NegBin(y + 1, F): mean (y + 1)(1 − F)/F. Returns the mean and the requested quantiles of the eventual
    count; F = 1 returns the known count."""
    y = np.asarray(known, dtype=float)
    f = np.clip(np.asarray(F, dtype=float), 1e-6, 1.0)
    mean = y + np.where(f < 1, (y + 1) * (1 - f) / f, 0.0)
    out = {"mean": mean}
    for qq in quantiles:
        out[qq] = y + np.where(f < 1, stats.nbinom.ppf(qq, y + 1, f), 0.0)
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
    ``phi`` the alarm baseline's predictive (tier BPA). P(eventual ≥ threshold) under the nowcast is
    P(NegBin(y + 1, F) ≥ k − y); a week alarms when it is at least ``confidence``. Returns the threshold, that
    probability, the nowcast's mean and the alarm flags."""
    y = np.asarray(known, dtype=float)
    f = np.clip(np.asarray(F, dtype=float), 1e-6, 1.0)
    k = threshold(mu, phi, recurrence)
    need = k - y
    p_exceed = np.where(need <= 0, 1.0, np.where(f < 1, stats.nbinom.sf(need - 1, y + 1, f), 0.0))
    return {"threshold": k, "p_exceed": p_exceed, "nowcast": nowcast(y, f, ())["mean"],
            "alarm": p_exceed >= confidence, "recurrence": recurrence}


def expected_false_alarms(places: int, weeks: int, recurrence: float) -> float:
    """The false alarms the design allows: places × weeks / R (the ADR's calibration target, checked on null worlds)."""
    return places * weeks / recurrence
