"""On demand: explaining away and decomposition (ARCHITECTURE §7.7).

Explaining away: refit the lead's field over the lead's cells and their
surroundings with a candidate driver x added to log μ; report the coefficient
with its interval and the share of the lead's deviance the driver absorbs,

    A = 1 − D'_S / D_S,    D_S = 2 Σ_{c∈S} [ y log(y/μ) − (y − μ) ].

Decomposition: the change in expected events between two periods split into
population size, age–sex composition, place mix and risk, each by substitution
of one component at a time, averaged over all 24 orders (exact Shapley values
for four components).

Triage (§7.7, §9.1): which leads are artefacts of how events are recorded or
counted, from the data's own evidence about the lead's cells. `triage` reads
the arrays of one lead (`Evidence`) and returns one class; `split_effect` and
`tail_p` run the splits of §8.3 on the same arrays. No code's meaning is
guessed: the only code facts used are the tree (parent, chapter) and the
label's own words.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy import special, stats


def deviance(y: np.ndarray, mu: np.ndarray) -> float:
    mu = np.maximum(mu, 1e-300)
    with np.errstate(divide="ignore", invalid="ignore"):
        return float(2 * np.sum(np.where(y > 0, y * np.log(y / mu), 0.0) - (y - mu)))


@dataclass
class Explanation:
    coefficient: float
    sd: float
    interval: tuple[float, float]
    absorbed: float          # A over the lead's cells
    deviance_before: float
    deviance_after: float
    cells: int


def explain_away(y: np.ndarray, mu: np.ndarray, phi: np.ndarray, x: np.ndarray, lead: np.ndarray,
                 region: np.ndarray | None = None, iterations: int = 50) -> Explanation:
    """Arrays over cells (any shape, flattened together). ``lead`` marks the lead's cells,
    ``region`` the cells the coefficient is estimated on (default: everything given)."""
    shape = np.shape(mu)
    y, mu, x = (np.asarray(a, dtype=float).ravel() for a in (y, mu, x))
    phi = np.broadcast_to(np.asarray(phi, dtype=float), shape).ravel()
    S = np.asarray(lead, dtype=bool).ravel()
    fit = np.ones_like(S) if region is None else np.asarray(region, dtype=bool).ravel()
    fit &= np.isfinite(x) & (mu > 0)
    xs = (x - x[fit].mean()) / max(x[fit].std(), 1e-12)
    a, g = 0.0, 0.0                       # a free level over the region keeps g from absorbing the level
    pois = ~np.isfinite(phi)
    for _ in range(iterations):
        m = mu * np.exp(a + g * xs)
        w = np.where(pois, m, m / (1 + m / np.where(pois, 1, phi)))
        r = np.where(pois, y - m, (y - m) / (1 + m / np.where(pois, 1, phi)))
        X = np.column_stack([np.ones(fit.sum()), xs[fit]])
        H = (X * w[fit, None]).T @ X
        step = np.linalg.solve(H, X.T @ r[fit])
        a, g = a + step[0], g + step[1]
        if np.abs(step).max() < 1e-8:
            break
    cov = np.linalg.inv(H)
    sd_unit = float(np.sqrt(cov[1, 1]))
    scale = max(x[fit].std(), 1e-12)
    coef, sd = g / scale, sd_unit / scale
    z = special.ndtri(0.975)
    mu_new = mu * np.exp(a + g * xs)
    before = deviance(y[S], mu[S])
    after = deviance(y[S], mu_new[S])
    return Explanation(float(coef), float(sd), (float(coef - z * sd), float(coef + z * sd)),
                       float(1 - after / before) if before > 0 else float("nan"), before, after, int(S.sum()))


def decompose(N0: np.ndarray, r0: np.ndarray, N1: np.ndarray, r1: np.ndarray) -> dict[str, float | np.ndarray]:
    """Expected events E = Σ_{u,g} N·r between two periods, with N [U, G] person-years and r [U, G]
    rates. N = total × place share × composition within place. Returns the Shapley share of each
    of size, composition, place mix and risk (summing to E1 − E0), and risk's split by place
    and by group."""
    def parts(N: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
        total = N.sum()
        place = N.sum(1) / total
        comp = np.divide(N, N.sum(1, keepdims=True), out=np.zeros_like(N), where=N.sum(1, keepdims=True) > 0)
        return total, place, comp

    t0, p0, c0 = parts(N0)
    t1, p1, c1 = parts(N1)
    names = ("size", "composition", "place", "risk")
    start = {"size": t0, "composition": c0, "place": p0, "risk": r0}
    end = {"size": t1, "composition": c1, "place": p1, "risk": r1}

    def E(v: dict) -> np.ndarray:
        return v["size"] * v["place"][:, None] * v["composition"] * v["risk"]

    shap = dict.fromkeys(names, 0.0)
    risk_cells = np.zeros_like(N0, dtype=float)
    orders = list(itertools.permutations(names))
    for order in orders:
        cur = dict(start)
        for n in order:
            before = E(cur)
            cur[n] = end[n]
            delta = E(cur) - before
            shap[n] += delta.sum() / len(orders)
            if n == "risk":
                risk_cells += delta / len(orders)
    return {**shap, "total": float(E(end).sum() - E(start).sum()),
            "risk_by_place": risk_cells.sum(1), "risk_by_group": risk_cells.sum(0)}


# ---------------------------------------------------------------------- triage

SUBSTITUTION, SYSTEM, NOISE, SIGNAL, FACILITY = "substitution", "system", "noise", "signal", "facility"
THETA = 1.2               # the lenses' minimum rate ratio (§8.4)
DRIFT = 3.0               # a code whose national level moves by more than this over the period is being introduced or retired
SURGE = 5.0               # a place's peak year against its median: the expectation may have learned a surge
POP_BREAK = 1.25          # a place's person-years moving by more than this, beyond the nation's, in a year
EMPTY_YEAR_POP = 5000.0   # person-years above which a year without any death is not chance (about 30 expected)
RATE_BREAK = 1.6          # year-to-year ratio of the all-cause death rate, beyond the nation's, that breaks a series
RATE_BREAK_POP = 20000.0  # ... in places large enough for the rate to be stable (about 130 deaths a year)
ABSORB = 0.75            # the share of the lead's change a sibling (or the ill-defined chapter) must undo
SIGNIFICANT = 3.0         # z of a sibling's (or the ill-defined chapter's) opposite move, Poisson
MIN_EXCESS = 10.0         # events above (or below) the expectation under which a lead is noise
MIN_SPREAD = 0.3          # group disparity: sd of the groups' log SIR under which the lead sits near the minimum effect (0.2)
FAC_K = 3                 # a lead is one institution's when at most this many facilities carry its change ...
FAC_SHARE = 0.7           # ... this share of it
FAC_SOLE = 0.85           # the facilities hold this share of the place's block events in the base years: they are the place
FAC_P = 1e-3              # one-sided binomial p of that share against the facilities' own share of the place's events
FAC_VOLUME = 1.6          # the facilities' volume (without the lead's events) moving by more than this: opened, closed, entered or left the data
FAC_CATCH = 30            # events of the lead's codes among the facilities' other residents, under which they say nothing
FAC_STEP = 3.0            # z of the lead-code share's step among those other residents
RESIDUAL_WORDS = ("não especificad", "sem outra especifica", "inespecífic", "mal definid", "outras ", "outros ")


@dataclass
class FacilityTally:
    """One lead's events by recording institution, on the evidence grid's years. Rows are the facilities that
    recorded any event of the block for residents of the lead's places (name '' = the record names none)."""

    names: np.ndarray        # [F] facility codes
    lead: np.ndarray         # [F, T] events of the lead's field, residents of the lead's places
    block: np.ndarray        # [F, T] events of the lead's block (chapter), the same residents
    total: np.ndarray        # [F, T] events of any cause, the same residents
    outside: Callable[[np.ndarray], tuple[np.ndarray, np.ndarray]]   # rows -> ([k, T] lead, [k, T] block) of the
    #                                                                  same facilities' residents of every other place


@dataclass
class Evidence:
    """The arrays one lead is judged on; places on rows, years on columns, all over the same grid."""

    years: np.ndarray
    y: np.ndarray                   # the lead's field
    siblings: np.ndarray | None     # the other children of the field's parent (None: the parent is the root)
    ill_defined: np.ndarray | None  # chapter XVIII (None: the event has no such chapter)
    total: np.ndarray | None        # every cause
    pop: np.ndarray                 # person-years
    chapter: str = ""
    residual: bool = False          # the field's label is a residual category ("outros", "não especificad")
    group_spread: tuple[float, str] | None = None   # sd of the groups' log SIR and the groups furthest from the mean
    facility: FacilityTally | None = None           # the lead's events by the institution that recorded them
    per_year: int = 1               # periods in a year on the grid: 1 (annual), 12 (``years`` are YYYYMM)


@dataclass
class Triage:
    cls: str
    reason: str
    evidence: dict


def _contrast(a: np.ndarray, rows: np.ndarray, win: np.ndarray, base: np.ndarray) -> tuple[float, float]:
    """Mean yearly count over the rows in the window, and its median over the base years (a surge elsewhere in
    the period does not move the base)."""
    v = a[rows].sum(0)
    return float(v[win].mean()) if win.any() else 0.0, float(np.median(v[base])) if base.any() else 0.0


def _annual(a: np.ndarray, per_year: int) -> np.ndarray:
    """Sum the last axis from periods to calendar years (the identity at the annual grain)."""
    return a if per_year == 1 else a.reshape(*a.shape[:-1], -1, per_year).sum(-1)


def _thirds(years: np.ndarray, per_year: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """The last and the first third of the period, in whole years at the monthly grain (a third that starts
    mid-year would compare winter with summer)."""
    k = max(len(years) // 3 // per_year, 1) * per_year
    last, first = np.zeros(len(years), bool), np.zeros(len(years), bool)
    last[-k:], first[:k] = True, True
    return last, first


def _window(years: np.ndarray, span: list[int] | None, estimand: str, per_year: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """The lead's periods and the periods it is compared with: the rest of the period for a window, the last
    against the first third for a trend or a pattern. At the monthly grain the base is the window's own calendar
    months in the other years (an outbreak in the dengue season against the other seasons, not against the winter)."""
    if span and estimand != "trend_divergence":
        win = (years >= span[0]) & (years <= span[-1])
        if not win.all():
            if per_year == 1:
                return win, ~win
            month = years % 100
            seasonal = ~win & np.isin(month, month[win])
            return win, seasonal if seasonal.any() else ~win
    return _thirds(years, per_year)


def _moves(a: np.ndarray, rows: np.ndarray, win: np.ndarray, base: np.ndarray) -> tuple[float, float]:
    """The change between the base years and the window, and its z against the series' own year-to-year noise
    (the robust sd of its first differences, floored at Poisson): a heat-wave year in a sibling code is not a move."""
    v = a[rows].sum(0).astype(float)
    w, b = _contrast(a, rows, win, base)
    d = np.diff(v)
    noise = max((1.4826 * np.median(np.abs(d - np.median(d)))) ** 2 / 2, float(v.mean()), 1e-9)
    se = np.sqrt(noise * (1 / max(win.sum(), 1) + 1 / max(base.sum(), 1)))
    return w - b, (w - b) / se


def triage(estimand: str, rows: np.ndarray, span: list[int] | None, direction: int, ev: Evidence,
           observed: float | None = None, expected: float | None = None) -> Triage:
    """Classify one lead. ``rows`` index its places in the evidence arrays, ``span`` its years (first, last),
    ``direction`` is +1 for an excess or a rise, -1 for a deficit or a fall (0: a pattern). Order of reading:
    denominator, substitution, certification, recording, residual coding, noise, one institution; what is left is a
    signal. The facility read is filled for every lead that has a tally, whatever its class (``info["facility"]``)."""
    ppy = ev.per_year
    win, base = _window(ev.years, span, estimand, ppy)
    windowed = bool(span) and estimand != "trend_divergence"
    n_w, n_b = _contrast(ev.y, rows, win, base)
    d_node, _ = _moves(ev.y, rows, win, base)
    info: dict = {"node_window": round(n_w, 2), "node_base": round(n_b, 2)}
    nat = ev.y.sum(0)

    fac = None
    if ev.facility is not None and direction != 0 and estimand != "group_disparity":
        fac = facility_read(ev.facility, win, base, direction)
        info["facility"] = {**fac["evidence"], "one_institution": fac["facility"]}

    # 1. denominator: person-years missing, a year without a single death where the person-years would give dozens
    #    (a municipality not yet created or not reporting), or the crude death rate breaking beyond the nation's
    # (read in calendar years at the monthly grain: person-months are a twelfth of a year's, and a month without an
    # event is the season, not a place missing from the data)
    yrs = ev.years if ppy == 1 else ev.years[::ppy] // 100
    span_y = span if ppy == 1 or not span else [span[0] // 100, span[-1] // 100]
    pop = _annual(ev.pop[rows].sum(0), ppy)
    y_rows = _annual(ev.y[rows].sum(0), ppy)
    if (pop <= 0).any() and y_rows[pop <= 0].sum() > 0:
        return Triage(SYSTEM, "denominator: events in years without person-years (municipality created)", info)
    near = (yrs[1:] >= span_y[0] - 1) & (yrs[:-1] <= span_y[-1] + 1) if windowed else np.ones(len(yrs) - 1, bool)
    if ev.total is not None:
        deaths = _annual(ev.total[rows].sum(0), ppy)
        if np.any((deaths == 0) & (pop >= EMPTY_YEAR_POP)):
            info["empty_years"] = [int(t) for t in yrs[(deaths == 0) & (pop >= EMPTY_YEAR_POP)]]
            return Triage(SYSTEM, "denominator: a year with no deaths of any cause in a place with person-years", info)
        with np.errstate(divide="ignore", invalid="ignore"):
            rate = np.log((deaths - y_rows + 0.5) / np.maximum(pop, 1.0))     # without the lead's own events
            nat_rate = np.log(_annual(ev.total.sum(0), ppy) / _annual(ev.pop.sum(0), ppy))
            brk = np.abs(np.diff(rate) - np.diff(nat_rate))
        big = (pop[1:] >= RATE_BREAK_POP) & (pop[:-1] >= RATE_BREAK_POP)
        if np.any(brk[near & big] > np.log(RATE_BREAK)):
            info["death_rate_break"] = round(float(np.exp(brk[near & big].max())), 2)
            return Triage(SYSTEM, "denominator: the place's all-cause death rate breaks (boundary change or registration)", info)
    with np.errstate(divide="ignore", invalid="ignore"):
        jump = np.abs(np.diff(np.log(pop))) - np.abs(np.diff(np.log(_annual(ev.pop.sum(0), ppy))))
    if np.any(jump[near] > np.log(POP_BREAK)):
        info["population_jump"] = round(float(np.exp(np.nanmax(jump[near]))), 2)
        return Triage(SYSTEM, "denominator: the place's person-years break (boundary change or re-estimate)", info)

    # 2. coding substitution: the siblings under the same parent move the other way and absorb the change
    if ev.siblings is not None and direction != 0:
        s_w, s_b = _contrast(ev.siblings, rows, win, base)
        d_sib, z_sib = _moves(ev.siblings, rows, win, base)
        info.update(sibling_window=round(s_w, 2), sibling_base=round(s_b, 2))
        if d_node * d_sib < 0 and abs(d_sib) >= ABSORB * abs(d_node) and abs(z_sib) >= SIGNIFICANT:
            return Triage(SUBSTITUTION, "siblings move opposite and absorb most of the change", info)

    # 3. certification: the ill-defined chapter
    if ev.chapter == "XVIII":
        return Triage(SYSTEM, "certification: the lead is an ill-defined cause", info)
    if ev.ill_defined is not None and ev.total is not None and direction != 0:
        i_w, i_b = _contrast(ev.ill_defined, rows, win, base)
        t_w, t_b = _contrast(ev.total, rows, win, base)
        info.update(ill_share_window=round(i_w / max(t_w, 1.0), 3), ill_share_base=round(i_b / max(t_b, 1.0), 3))
        d_ill, z_ill = _moves(ev.ill_defined, rows, win, base)
        if d_node * d_ill < 0 and abs(d_ill) >= ABSORB * abs(d_node) and abs(z_ill) >= SIGNIFICANT:
            return Triage(SYSTEM, "certification: the change goes to the ill-defined chapter", info)

    # 4. recording: the code is being introduced or retired nationally, or the expectation learned a surge
    #    (the national course and a surge elsewhere are read in calendar years: a window touches every year it has a month in)
    nat_a = _annual(nat, ppy)
    win_a = win if ppy == 1 else _annual(win.astype(int), ppy) > 0
    spike = windowed and win_a.sum() <= 2 and (~win_a).sum() >= 6        # a short window is the event itself, not the code's drift
    keep = ~win_a if spike else np.ones(len(yrs), bool)
    k = max(min(3, int(keep.sum()) // 2), 1)
    first, last = np.median(nat_a[keep][:k]), np.median(nat_a[keep][-k:])
    info["national_first"], info["national_last"] = round(float(first), 1), round(float(last), 1)
    ratio = (last + 0.5) / (first + 0.5)
    national_peak = spike and direction > 0 and nat[win].max() >= 2 * max(np.median(nat[base]), 1.0)   # the nation peaks there too: an event
    if not national_peak and max(first, last) >= 20 and (ratio >= DRIFT or ratio <= 1 / DRIFT):
        return Triage(SYSTEM, f"recording: the code's national level moves x{ratio:.2g} over the period", info)
    if direction < 0 and windowed:
        rest = y_rows[~win_a]
        if rest.size >= 4 and rest.max() >= SURGE * max(np.median(rest), 1.0) and rest.max() - np.median(rest) >= 20:
            info["surge"] = [int(yrs[~win_a][rest.argmax()]), float(rest.max())]
            return Triage(SYSTEM, "model: a deficit against an expectation that learned a surge elsewhere in the period", info)

    # 5. residual categories ("other", "unspecified") that trend or differ by age and sex are coding practice;
    #    a small group spread is the minimum effect
    if ev.residual and estimand in ("trend_divergence", "change_point"):
        return Triage(SYSTEM, "coding practice: a residual category trending away from its neighbours", info)
    if estimand == "group_disparity":
        if ev.group_spread is not None:
            info["group_spread"], info["groups"] = round(ev.group_spread[0], 3), ev.group_spread[1]
        if ev.residual:
            return Triage(SYSTEM, "coding practice: a residual category whose age-sex pattern differs", info)
        if ev.group_spread is not None and ev.group_spread[0] < MIN_SPREAD:
            return Triage(NOISE, "the groups' log SIR spreads little more than the minimum effect", info)
        return Triage(SIGNAL, "age-sex pattern differs from the nation's in a specific category", info)

    # 6. noise: few events above or below the expectation, or an effect near the minimum with few events
    if observed is not None and expected is not None:
        info["observed"], info["expected"] = round(observed, 1), round(expected, 1)
        rr = observed / max(expected, 1e-9)
        if abs(observed - expected) < MIN_EXCESS or (observed < 30 and 1 / (THETA * 1.25) < rr < THETA * 1.25):
            return Triage(NOISE, f"small count: {abs(observed - expected):.0f} events from the expectation", info)
    elif estimand == "trend_divergence" and ev.y[rows].sum() < 100:
        return Triage(NOISE, f"small count: {ev.y[rows].sum():.0f} events in the place over the period", info)
    # 7. one institution: the change is carried by one (or a few) recording facilities whose own behaviour steps
    if fac is not None and fac["facility"]:
        return Triage(FACILITY, fac["reason"], info)
    return Triage(SIGNAL, "no recording or denominator explanation found in the data", info)


def facility_read(t: FacilityTally, win: np.ndarray, base: np.ndarray, direction: int) -> dict:
    """Is the lead's change one institution's? (ARCHITECTURE §7.7.) The change in the lead's events, facility by
    facility (window against base years, in the lead's direction); the smallest set of at most ``FAC_K`` facilities
    carrying ``FAC_SHARE`` of it, against those facilities' share of the block's events in the base years (a
    binomial tail, unless they are the whole place); then the mechanism, from the facilities' own behaviour:

      catchment  the same facilities' residents of *other* places show the same step in the lead-code share of
                 the block (a hospital codes alike for everyone it serves; a real change among these residents
                 does not reach the others), or
      volume     the facilities' volume without the lead's events stepped (opened, closed, entered or left the data).

    ``facility`` is true when the change is concentrated and a mechanism is found; ``evidence`` is always filled."""
    real = t.names != ""
    mean = lambda a, m: a[:, m].mean(1) if m.any() else np.zeros(a.shape[0])           # noqa: E731
    d = direction * (mean(t.lead, win) - mean(t.lead, base))
    gain = float(np.maximum(d, 0.0).sum())                  # per year, over every row including "names none"
    pos = np.where(real, np.maximum(d, 0.0), 0.0)
    excess = gain * int(win.sum())
    ev: dict = {"facilities": int(real.sum()), "excess": round(excess, 1)}
    out = {"facility": False, "reason": "", "evidence": ev}
    if excess < MIN_EXCESS or not real.any():
        return out
    order = np.argsort(-pos)
    block_b = mean(t.block, base)
    ref_all = float(block_b.sum())

    def ref(top: np.ndarray) -> float:
        return float(block_b[top].sum() / ref_all) if ref_all > 0 else 0.0

    ev["named_share"] = round(float(pos.sum() / gain), 3)
    k = next((k for k in range(1, FAC_K + 1) if pos[order[:k]].sum() / gain >= FAC_SHARE), None)
    top = order[:k or 1]
    ev.update(top=[str(t.names[i]) for i in top], k=len(top), share=round(float(pos[top].sum() / gain), 3),
              ref_share=round(ref(top), 3))
    if k is None:
        return out                                          # spread over more than FAC_K institutions
    n = int(round(excess))
    ev["sole_provider"] = ev["ref_share"] >= FAC_SOLE
    if not ev["sole_provider"]:
        ev["p_concentration"] = float(stats.binom.sf(int(round(ev["share"] * n)) - 1, n, min(max(ev["ref_share"], 1e-9), 1 - 1e-9)))
        if ev["p_concentration"] >= FAC_P:
            return out                                      # as much as the facilities' size would carry anyway
    # the facilities' own behaviour: volume without the lead's events, and the lead-code share of the block
    rest = (t.total - t.lead)[top]
    vol_w, vol_b = rest[:, win].sum(0).mean(), rest[:, base].sum(0).mean()
    ev["volume"] = [round(float(vol_b), 1), round(float(vol_w), 1)]
    ratio = (vol_w + 1) / (vol_b + 1)
    stepped = ratio >= FAC_VOLUME or ratio <= 1 / FAC_VOLUME
    a_w, b_w, a_b, b_b = (x[top][:, m].sum() for x, m in ((t.lead, win), (t.block, win), (t.lead, base), (t.block, base)))
    log_in = float(np.log((a_w + 0.5) / (b_w + 1) * (b_b + 1) / (a_b + 0.5)))
    ev["mix_inside"] = [round(float(a_b / max(b_b, 1)), 4), round(float(a_w / max(b_w, 1)), 4)]
    ev["inside_log_ratio"] = round(log_in, 2)
    out_lead, out_block = t.outside(top)
    o_w, ob_w, o_b, ob_b = (x[:, m].sum() for x, m in ((out_lead, win), (out_block, win), (out_lead, base), (out_block, base)))
    ev["outside_events"] = [int(o_b), int(o_w)]
    catch = None
    if o_w + o_b >= FAC_CATCH and ob_w > 0 and ob_b > 0:
        log_out = float(np.log((o_w + 0.5) / (ob_w + 1) * (ob_b + 1) / (o_b + 0.5)))
        z = log_out / float(np.sqrt(1 / (o_w + 0.5) + 1 / (o_b + 0.5)))
        ev["mix_outside"] = [round(float(o_b / max(ob_b, 1)), 4), round(float(o_w / max(ob_w, 1)), 4)]
        ev["outside_log_ratio"], ev["outside_z"] = round(log_out, 2), round(z, 1)
        catch = bool(direction * z >= FAC_STEP and direction * log_out >= 0.5 * direction * log_in)
    if catch:
        out.update(facility=True, reason="one institution: the same facilities show the same step among residents of other places")
    elif stepped:
        out.update(facility=True, reason="one institution: its volume stepped (opened, closed, or entered or left the data)")
    elif catch is False:
        ev["place_specific"] = True                         # the others it serves do not move: the change belongs to the residents
    return out


def residual_label(label: str) -> bool:
    """A residual category by the label's own words (Portuguese ICD-10): other, unspecified."""
    t = (label or "").lower()
    return any(w in t for w in RESIDUAL_WORDS)


def group_spread(y: np.ndarray, n: np.ndarray, rows: np.ndarray) -> tuple[float, str]:
    """Indirect standardisation of a place on the nation's age-sex rates, year by year: the expected-weighted sd
    of the groups' log SIR (groups with at least 5 expected events) and the two groups furthest from the mean.
    ``y`` and ``n`` are [U, T, G]."""
    tot = n.sum(0)
    rate = np.divide(y.sum(0), tot, out=np.zeros(tot.shape), where=tot > 0)                    # [T, G]
    E = (n[rows].sum(0) * rate).sum(0)                                                          # [G]
    obs = y[rows].sum((0, 1))
    ok = E >= 5
    if ok.sum() < 3:
        return 0.0, ""
    ls = np.log((obs[ok] + 0.5) / (E[ok] + 0.5))
    w = E[ok] / E[ok].sum()
    mean = float((w * ls).sum())
    sd = float(np.sqrt((w * (ls - mean) ** 2).sum()))
    far = np.argsort(-np.abs(ls - mean) * np.sqrt(E[ok]))[:2]
    return sd, ",".join(str(int(g)) for g in np.nonzero(ok)[0][far])


# ---------------------------------------------------------------------- replication


def tail_p(observed: float, mu: np.ndarray, phi: np.ndarray, up: bool = True) -> float:
    """One-sided p of a sum of negative-binomial cells, moment-matched: Var = M + M²/n (Poisson when φ is infinite).
    ``up``: P(Y ≥ observed); otherwise P(Y ≤ observed)."""
    M = float(np.sum(mu))
    finite = np.isfinite(phi)
    extra = float(np.sum(np.where(finite, mu ** 2 / np.where(finite, phi, 1.0), 0.0)))
    if M <= 0:
        return 1.0 if up else 0.0
    if extra <= 0:
        return float(stats.poisson.sf(observed - 1, M) if up else stats.poisson.cdf(observed, M))
    n = M ** 2 / extra
    return float(stats.nbinom.sf(observed - 1, n, n / (n + M)) if up else stats.nbinom.cdf(observed, n, n / (n + M)))


def split_effect(y: np.ndarray, mu: np.ndarray, phi: np.ndarray, rows: np.ndarray, cols: np.ndarray, sign: int
                 ) -> tuple[float, float]:
    """(log rate ratio, one-sided p in the lead's direction) over the cells ``rows`` × ``cols``."""
    if rows.size == 0 or not np.any(cols):
        return float("nan"), 1.0
    sub = np.ix_(rows, np.nonzero(cols)[0])
    Y, M = float(y[sub].sum()), float(mu[sub].sum())
    if M <= 0:
        return float("nan"), 1.0
    return float(np.log((Y + 0.5) / (M + 0.5))), tail_p(Y, mu[sub], phi[sub], up=sign > 0)
