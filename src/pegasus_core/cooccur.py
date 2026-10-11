"""Related codes from records (ARCHITECTURE §4.2, BACKLOG 4.2): the codes that appear on the same record as the topic's
more often than their frequency predicts, observed against expected with an exact interval and FDR control.

A record (a death certificate's lines, an admission's diagnoses, a birth's anomaly list) carries several codes. For a
category c and the seeds S, within each stratum s (sex × ten-year age band) the expected records carrying both are
E_s = n_c,s · n_S,s / n_s (independence given the stratum), so two causes common at the same ages are not read as
related; the observed O = Σ_s n_both,s against E = Σ_s E_s is a stratified (Mantel–Haenszel-type) comparison. O is
read as Poisson(λE): the exact one-sided p of O ≥ observed, Benjamini–Hochberg over the categories at ``q``, and the
lift O/E with its exact 95 % interval. A related code is a lead for the scope (a field to read), never a cause: a
certificate co-mention is a recording fact (HIV and toxoplasmosis are certified together because one causes the other's
death), and its strength is the lift.
"""

from __future__ import annotations

from . import control, gateway


def related_codes(dataset: str, event: str, years: list[int], columns: list[str], seeds: list[str],
                  q: float = 0.05, min_both: int = 3) -> list[dict]:
    """The categories related to ``seeds`` on ``dataset``'s records over ``years`` (their ``columns`` read together),
    strongest first: code, label, observed and expected records with both, lift, its interval, p and BH q. Categories
    with fewer than ``min_both`` records carrying both are not tested (they cannot reach significance and add to the
    family)."""
    import pyarrow as pa
    from scipy.stats import chi2, poisson

    parts = []
    for y in years:
        try:
            parts.append(gateway.cooccurrence(dataset, event, int(y), columns, seeds))
        except gateway.nothing_published():
            continue
    if not parts:
        return []
    t = pa.concat_tables(parts).to_pandas()
    for c in ("n_code", "n_both", "n", "n_seed"):
        t[c] = t[c].astype(float)
    t["e"] = t["n_code"] * t["n_seed"] / t["n"].clip(lower=1)
    g = t.groupby("code").agg(o=("n_both", "sum"), e=("e", "sum"), n_code=("n_code", "sum")).reset_index()
    g = g[(g["o"] >= min_both) & (g["e"] > 0)]
    if g.empty:
        return []
    p = poisson.sf(g["o"].to_numpy() - 1, g["e"].to_numpy())
    qv = control.adjusted(p)
    labels = {r["code"]: r["label"] for r in gateway.code_tree("ICD10").to_pylist()}
    out = []
    for (_, r), pi, qi in zip(g.iterrows(), p, qv, strict=True):
        o, e = float(r["o"]), float(r["e"])
        out.append({"code": r["code"], "label": labels.get(r["code"]), "observed": o, "expected": e, "lift": o / e,
                    "low": chi2.ppf(0.025, 2 * o) / 2 / e, "high": chi2.ppf(0.975, 2 * o + 2) / 2 / e,
                    "records_with_code": int(r["n_code"]), "p": float(pi), "q": float(qi), "related": bool(qi <= q)})
    return sorted(out, key=lambda r: (not r["related"], -r["lift"]))
