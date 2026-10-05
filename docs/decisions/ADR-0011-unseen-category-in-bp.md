# ADR-0011: A category the training fit never saw has no expectation in BP: it leaves the node, is counted, and alarms at five events a year

**Date.** 2026-10-05. **Status.** Active.

**Evidence.** `docs/evaluation/2026-10-05-bp-level.md` (section "Follow-up: the blocked origins, the outbreak lens, the unseen category"; `data/p5/unseen_category.py`, artefact `data/logs/unseen_category.json`). Origin is OQ 6 ("categories born after the fit").

## Decision

In `Expectations.prospective`, a leaf of the node with no event in the training fit is not given an expectation:

1. it is **out of the node**: neither its expectation nor its events enter BP's μ, y, PIT and calibration;
2. its events are **counted**: `extras["new_category"]` holds the leaf's national events per year, and the cells holding them carry the flag `NEW_CATEGORY` (16; the lenses ignore it);
3. it **alarms**: `extras["new_category_alarm"]` lists (leaf, year, events) for years with `NEW_CATEGORY_ALARM` = 5 events or more (the threshold of a documented place in the lens positives);
4. a node whose leaves are all unseen raises `LookupError`.

Rejected: the **parent's rate** (θ_cat = v_cat = 0, the group's per-leaf level) and the fit's **default** (the leaf's shrunk prior).

## Why

Chapter I, origin 2019, test 2020–23: 15 of its leaves have no event in 2010–19 and 4 have events later (A67, B35, B96: one death each; B04, mpox: 14 deaths, 11 of them in 2022).

- **The fit's default is already a near-zero expectation** (θ_cat −0.3 to −5.3: 0.2 to 0.7 expected events per leaf over four years), but unreported: mpox's 14 deaths against 0.29 expected raised no cell (p < 10⁻⁶ in none).
- **The parent's rate invents events:** 0.2 to 104 expected deaths per leaf (cholera A00: 104 against 0; 4 to 33 for most), and still no detection of mpox (0 cells). It moves the chapter's log score by 450 nats of 355 k: nothing.
- **Zero with a count and an alarm** costs nothing in the chapter (17 events of 958,617 leave it) and reports what the other two cannot: B04 2022 (11 deaths) alarms; the three single deaths do not.
- **COVID-19 is not an unseen category in this fit.** B34 had 802 training deaths (about 340 expected, 714,782 observed): its departure is the lens's positive and chapter I stays uncalibrated (KS .54) because of it, as it should. Treated as unseen *as a test of the options*, the departure is found by every option that keeps the leaf in a lens (99.1 % of the leaf's events in cells with p < 10⁻⁶ under the fit's default, 99.6 % under the parent's rate), by the alarm (97.9 % of events in place-years of five or more), and **not** by "zero with a flag" alone, which removes it from the lenses (and restores the rest of the chapter: KS .54 → .025, log score −355 k → −48 k). Hence the alarm is part of the decision, not an addition to it.

## Consequences

The threshold (5) was fixed before measurement (the lens positives' documented-place minimum) but is checked on four examples only. A new code that appears inside a known 3-character category (B34.2 within B34) is not unseen at this resolution and is the lens's to find. The chapter-level `Surprise.y` excludes the unseen leaves' events (17 of 958,617 in chapter I at 2019).
