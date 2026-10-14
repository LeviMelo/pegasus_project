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

from . import config, control, gateway


def associated(dataset: str, event: str, years: list[int], columns: list[str], seeds: list[str], q: float = 0.05,
               min_both: int = 3) -> list[dict]:
    """The conditions the topic's records name beside it (multiple-cause analysis): for every ICD-10 category on the
    records carrying a seed (a certificate's lines, an admission's diagnoses) in the study's area and ``years``, the
    records carrying both (``with_code``), their share of the topic's records with its exact (Clopper–Pearson)
    interval, the records expected to carry both at the same sex and ten-year age band, the lift O/E with its exact
    interval, the one-sided p of O and its Benjamini–Hochberg q over every category with an expectation (the family is
    fixed before the data are looked at), and ``related``: q at most ``q`` and at least ``min_both`` records. Most
    frequent first: a profile of mortality reports the associated causes by how often they are named (hypertension,
    diabetes), where the lift ranks the codes most specific to the topic. One computation for the scope's related codes
    and the folder's associated.parquet, which had been two passes over the same tables, the second without p or q
    (the review of the study, 2026-10-14)."""
    import pyarrow as pa
    from scipy.stats import beta, chi2, poisson

    parts = []
    for y in years:
        try:
            t_ = gateway.cooccurrence(dataset, event, int(y), columns, seeds,
                                      area=(tuple(sorted(config.study_area())) if config.study_area() else None))
        except gateway.nothing_published():
            continue
        parts.append(t_.append_column("year", pa.array([int(y)] * t_.num_rows, pa.int32())))
    if not parts:
        return []
    t = pa.concat_tables(parts).to_pandas()
    for k in ("n_code", "n_both", "n", "n_seed"):
        t[k] = t[k].astype(float)
    t["e"] = t["n_code"] * t["n_seed"] / t["n"].clip(lower=1)
    # the topic's records (naming a seed on any of the columns): each (year, stratum) once, whatever its categories
    topic = float(t.drop_duplicates(["year", "sex", "band"])["n_seed"].sum())
    g = t.groupby("code").agg(o=("n_both", "sum"), e=("e", "sum"), n_code=("n_code", "sum")).reset_index()
    g = g[g["e"] > 0]
    if g.empty or topic <= 0:
        return []
    p = poisson.sf(g["o"].to_numpy() - 1, g["e"].to_numpy())
    qv = control.adjusted(p)
    shown = (g["o"] > 0).to_numpy()
    g, p, qv = g[shown], p[shown], qv[shown]
    labels = {r["code"]: r["label"] for r in gateway.code_tree("ICD10").to_pylist()}
    out = []
    for (_, r), pi, qi in zip(g.iterrows(), p, qv, strict=True):
        o, e = float(r["o"]), float(r["e"])
        out.append({"code": r["code"], "label": labels.get(r["code"]), "with_code": o, "topic_records": topic,
                    "share": o / topic,
                    "share_low": float(beta.ppf(0.025, o, topic - o + 1)),
                    "share_high": float(beta.ppf(0.975, o + 1, topic - o)) if o < topic else 1.0,
                    "expected": e, "lift": o / e,
                    "lift_low": chi2.ppf(0.025, 2 * o) / 2 / e, "lift_high": chi2.ppf(0.975, 2 * o + 2) / 2 / e,
                    "records_with_code": int(r["n_code"]), "p": float(pi), "q": float(qi),
                    "related": bool(qi <= q and o >= min_both)})
    return sorted(out, key=lambda r: -r["share"])
