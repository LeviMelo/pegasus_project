"""Step 7: the verdicts (fixed by reading steps 2-6) joined to the features; prints the markdown table and the summary figures."""
import os, sys, json
os.chdir("C:/Users/Galaxy/LEVI/projects/pegasus_project")
import numpy as np, pandas as pd, pyarrow as pa
import pegasus_data as pg
from pegasus_core import gateway

f = pd.read_pickle("data/replicated_claims/features.pkl").merge(pd.read_pickle("data/replicated_claims/family.pkl")[["id", "beta_block_incl", "beta_chapter_incl"]], on="id")
tree = gateway.code_structure("ICD10").to_pandas().set_index("code")
nodes = sorted(f.node.unique())
lab = {r["CAUSABAS"]: r["CAUSABAS_label"] for r in pg.translate(pa.table({"CAUSABAS": nodes}), system="SIM").to_pylist()}
for n in nodes:
    if not lab.get(n):
        lab[n] = tree.loc[n, "label"] if n in tree.index else ""

# class: S substantive, A artefact (tag), U unresolved. Tags: sib = sibling substitution; res = residual/unspecified code; R = ill-defined chapter usage;
# step = abrupt one-year administrative step; off = national-course misfit (claim halves or vanishes under year-specific national rates);
# ill = ill-defined <-> defined exchange; comp = within-family composition.
V = {
 ("I10", 32): ("A-sib", "I11-I13 +480 of I10 -160 deaths a year; I10-I15 flat (-0.01)"),
 ("I24", 42): ("U", "R falls .74 to .44 in SC, block falls too (no mirror); real IHD decline vs certification not separable"),
 ("I60", 23): ("U", "gradual from 2010, before CE's R fall (2017); block flat"),
 ("I63", 24): ("U", "all-cause SMR in RN .83 to .98; step 2017; block flat"),
 ("I63", 32): ("A-sib", "I64 932 (2010) to 84 (2023) as I63 40 to 885; step 2017; I60-I69 flat (-0.03)"),
 ("I63", 41): ("A-off", "att -0.36: no divergence under year-specific national rates"),
 ("I64", 32): ("A-sib", "the pair of I63 ES"),
 ("I64", 43): ("A-sib", "I63 RS 451 (2016) to 2,229 (2019), I64 2,846 to 1,644; att .24"),
 ("I67", 17): ("A-step", "step 2016 (O/E .6 to .2); sibling change .94 of the node's"),
 ("I67", 42): ("U", "gradual 1.2 to .55; R falls; sibling mirror .21"),
 ("I67", 43): ("A-step", "1,117 to 162 deaths in 2018; I63 RS x4 the same year"),
 ("I69", 21): ("U", "MA all-cause SMR +17% relative (2010-19), node x2.3; completeness product +5% only"),
 ("I69", 22): ("A-sib", "I69 up while the rest of I60-I69 falls (mirror .68); block flat"),
 ("I70", 31): ("U", "step 2016-17 (.84 to .42), no mirror in I70-I79; probable code practice"),
 ("I73", 23): ("U", "CE group: R falls 3,331 to 1,642 (2016-19)"),
 ("I73", 26): ("U", "gradual x2; PE R falls .82 to .61 in 2017-19"),
 ("J60-J70", 23): ("A-ill", "CE: J12-J18 +712 of R -1,689 (2016-19), step 2017; respiratory chapter +0.11"),
 ("J60-J70", 43): ("A-ill", "RS: R excluding the node .66 to .88 of expected while J60-J81 falls"),
 ("J69", 23): ("A-ill", "as J60-J70 CE (J69 is 76-93% of J60-J70 there)"),
 ("J81", 43): ("A-ill", "as J60-J70 RS; step 2015-17"),
 ("R00-R09", 52): ("A-R", "GO R95-R99 1,395 to 710 in 2012; a claim on certification"),
 ("R50-R69", 41): ("A-R", "PR R excl. falls .78 to .42 (certification)"),
 ("R54", 41): ("A-R", "inside R50-R69 PR"),
 ("R57", 33): ("A-R", "ill-defined chapter; att .45"),
 ("R68", 23): ("A-R", "ill-defined chapter; att .40"),
 ("R68", 52): ("A-R", "GO 2012 step"),
 ("R96", 21): ("A-R", "R98 583 to 298 while R96 35 to 495 and R99 261 to 685: usage shift inside R"),
 ("R98", 23): ("A-R", "att .11; R98 is being retired as a code"),
 ("R98", 29): ("A-R", "att .05; O/E 3.5 to 5.0 to .8 (humped)"),
 ("V09", 23): ("A-off", "att .33; residual transport code"),
 ("V22", 23): ("U", "specific code rising x2.7 in CE; family flat; not tested at sub-block level"),
 ("V29", 29): ("U", "residual motorcyclist code up in BA; family +0.05"),
 ("V29", 41): ("A-res", "residual code; V01-V99 of PR diverges -0.03 against -0.42"),
 ("V49", 21): ("A-res", "residual code falling while V01-V99 of MA rises (+0.07)"),
 ("V49", 41): ("A-res", "as V29 PR"),
 ("V87", 35): ("A-res", "V01-V99 of SP -0.05 against -0.62; V87 131 to 22"),
 ("V89", 41): ("A-res", "V89+V99 680 to 123 while V01-V99 -29%; family -0.03"),
 ("V89", 43): ("A-res", "V01-V99 of RS +0.03 against node -0.37"),
 ("V99", 31): ("A-res", "family -0.01 against node -0.21"),
 ("V99", 35): ("A-res", "family -0.05 against node -0.53"),
 ("W01", 27): ("U", "step 7 to 104 deaths 2016-19, no mirror in W00-W19; probable code practice"),
 ("W18", 24): ("A-off", "att .47"),
 ("W18", 26): ("A-off", "att -0.06; W19 to W18 swap in 2023 (W19 385 to 135, W18 172 to 554)"),
 ("W19", 26): ("U", "x3.3 by 2019 then swapped with W18 in 2023: code is labile"),
 ("W19", 43): ("U", "gradual x2.5; siblings of W00-W19 also double"),
 ("W78", 42): ("A-off", "att .48; step 2017"),
 ("X93", 50): ("A-sib", "X95 311 to 119 as X93 4 to 89 (2015-19); X85-Y34 of MS -0.09"),
 ("X95", 35): ("A-comp", "pooling Y10-Y34 cuts the family from -0.19 to -0.07: about 60% moved to undetermined intent"),
 ("Y00", 35): ("A-comp", "as X95 SP"),
 ("Y10-Y34", 43): ("A-comp", "RS X85-Y34 pooled +0.03; RS R rising"),
 ("Y21", 31): ("A-off", "att .38"),
 ("Y21", 35): ("A-off", "att .27"),
 ("Y21", 52): ("A-off", "att .45"),
 ("Y35", 52): ("S", "police registry: GO 265 killings 2017, 425 in 2018 (press quoting the Anuario FBSP), SIM Y35 45 and 76; size recording-confounded"),
 ("Y35-Y36", 52): ("S", "same deaths as Y35 GO"),
 ("Y40-Y84", 23): ("A-step", "O/E 3.3-4.0 in 2010-11 to 1.25 in 2012"),
 ("Y83", 23): ("A-step", "inside Y40-Y84 CE"),
}
f["cls"] = [V[(n, u)][0] for n, u in zip(f.node, f.uf)]
f["why"] = [V[(n, u)][1] for n, u in zip(f.node, f.uf)]
assert len(f) == 57 and f.cls.notna().all()
f["label"] = f.node.map(lambda n: lab[n][:34])
print("| field | UF | beta survey / direct (att) | x over 2010-19 | obs/exp 2020-23 | all-cause beta | block beta (incl.) | class | evidence |")
print("|---|---|---|---|---|---|---|---|---|")
for _, r in f.iterrows():
    print(f"| {r.node} {r.label} | {r.uf_name} | {r.claim_beta:+.2f} / {r.beta_pop:+.2f} ({r.att:.2f}) | {r.change9:.2f} | {r.obs_exp_2020_23:.2f} | {r.beta_all:+.2f} | {r.beta_block_incl:+.2f} | {r.cls} | {r.why} |")
print()
print(f.cls.str.split("-").str[0].value_counts().to_dict(), f.cls.value_counts().to_dict())
print("direct beta same sign & att>=.5:", int((f.att >= .5).sum()), "att<.5:", int((f.att < .5).sum()))
print("den (account-3 vs POPSVS slope change) max %.3f median %.3f; max |beta_acc-beta_pop| %.3f" % (f.den.max(), f.den.median(), (f.beta_acc - f.beta_pop).abs().max()))
print("pop_rel (account-3/POPSVS, unit vs nation) 2010 %.3f-%.3f, 2019 %.3f-%.3f" % (f.pop_rel_2010.min(), f.pop_rel_2010.max(), f.pop_rel_2019.min(), f.pop_rel_2019.max()))
print("comp_dlog_rel range %.3f..%.3f; basis 2019: %s" % (f.comp_dlog_rel.min(), f.comp_dlog_rel.max(), f.comp_basis_2019.value_counts().to_dict()))
print("beta_all range %.3f..%.3f ; max comp share %.2f ; share>=.2: %d" % (f.beta_all.min(), f.beta_all.max(), f.comp.max(), int((f.comp >= .2).sum())))
print("units:", f.uf_name.value_counts().to_dict())
print("distinct deaths sets:", 57 - 4)
print("persist 2020-23 own estimate agrees in direction:", int((np.sign(np.log(f.oe_2020_23_mine)) == np.sign(f.z)).sum()), "of 57")
print("delta state beta", np.log(1.2) / ((2019 - 2010) / np.std(np.arange(2010, 2020))))
f.to_pickle("data/replicated_claims/final.pkl")
