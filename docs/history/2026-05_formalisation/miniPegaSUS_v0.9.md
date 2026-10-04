# miniPegaSUS (v1.0 Production Contract): Core Architecture, Formal Operational Specifications, and Mathematical Verification Engine

This document serves as the absolute production specification and immutable systems contract for the **miniPegaSUS** project. It details the operational, mathematical, and algorithmic requirements for compiling public health event streams and socioeconomic indicators into a provenance-aware, statistically adjusted, causal-hypothesis-generating epidemiological space. Every module, registry, and operator defined herein represents an explicit, binding software contract to govern implementation.

---

## 1. Global Pipeline Architecture & Relational Topology

The miniPegaSUS architecture decomposes the processing pipeline into three coupled, dependent mathematical layers. It operates as an automated compilation chain where the output of each phase parameterizes and restricts the state space of the subsequent block:

$$\mathcal{D} \xrightarrow{\text{Problem 3}} \mathcal{B} \xrightarrow{\text{Problem 1}} \mathcal{G}_{\text{DAG}} \xrightarrow{\text{Problem 2}} \mathcal{M}_{\text{stat}} \times \text{HSIC}_{\text{residual}} \to \mathcal{O}_{\text{run}}$$

```
+---------------------------------------------------------------------------------------+
|                                DATA SUBSTRATE LAYER (D)                               |
|   E_SIM (Deaths) | E_SIH (Hospital) | E_SINASC (Births) | R_CNES (Stocks) | C_SIDRA     |
+-------------------------------------------+-------------------------------------------+
                                            |
                                            v [M_geo Geospatial Harmonization Selection]
+---------------------------------------------------------------------------------------+
|                         PROBLEM 3: SUBSTRATE COMPILATION (B)                          |
|  - Joint Spatiotemporal Population Path Optimizer: P_hat, eta_hat over full time T    |
|  - Multi-Link Spatiotemporal Dynamic Factor Model (ST-DFM) for Sparse Context Cubes   |
|  - Invariant Type-Guarded Disaggregation (P-Splines) & Real Currency Deflation        |
+-------------------------------------------+-------------------------------------------+
                                            |
                                            v [Seeded Matrix Optimization: V_core U V_0]
+---------------------------------------------------------------------------------------+
|                        PROBLEM 1: MEASURE FIELDS DAG (G_DAG)                          |
|  - Automated Ingestion Alignment (Align) & 7-Part Legality Predicate Verification     |
|  - Branch-and-Bound ICD-10/Phenotype Tree Exploration & Volatility Quarantine        |
|  - Non-Destructive Equivalence Compression & Marked Functional (Psi) Derivation       |
+-------------------------------------------+-------------------------------------------+
                                            |
                                            v [Hierarchical Likelihood Selection]
+---------------------------------------------------------------------------------------+
|                    PROBLEM 2: INFERENCE, ADJUSTMENT & EXPLORATION                    |
|  - regularized Spatiotemporal Panel GLM/GAM Contextual Neighborhood Estimation (M_stat)|
|  - Orthogonalized Residual Transformation Matrix & Quenched Gravity Smoothing         |
|  - Approximate Scalable HSIC Copula Scanner (Nyström / Random Fourier Features)       |
+-------------------------------------------+-------------------------------------------+
                                            |
                                            v [Cryptographic Manifest Logging]
+---------------------------------------------------------------------------------------+
|                         PRODUCTION RUN OUTPUT BUNDLE (O_run)                         |
+---------------------------------------------------------------------------------------+

```

### 1.1 The User Intent Boundary Specification

The system completely rejects user-authored mathematical formulas or statistical recipes. The user interacts with the system exclusively by defining the high-level **User Intent Tuple ($\mathcal{I}$)**, which parameterizes the autonomous traversal mechanics of the compilation engines:

$$\mathcal{I} = \left( G, T, \mathcal{H}_0, \mathcal{V}_0, \mathbf{w}_{\text{systems}}, \mathcal{C}_{\text{policy}}, B, \mathcal{M}_{geo}, \mathcal{R}_{\text{force}}, \mathcal{D}_{\text{exclude}} \right)$$

where:

* $G \subset S_t$ is the target geographic bounding polygon or spatial selector.
* $T = [t_{\text{start}}, t_{\text{end}}] \subset \mathbb{Y}$ is the temporal window boundary range.
* $\mathcal{H}_0 \subset \mathfrak{I}_{\text{ICD}}$ is the set of initial seeds in the health-event ontology (Chapters, Blocks, or Curated Phenotypes) from which the DAG descends.
* $\mathcal{V}_0$ is the set of mandatory anchor variables or field families forced into the root execution layer.
* $\mathbf{w}_{\text{systems}} \in [0, 1]^5$ is the priority weight allocation vector mapped to individual source databases: $\mathbf{w}_{\text{systems}} = [w_{\text{SIM}}, w_{\text{SIH}}, w_{\text{SINASC}}, w_{\text{CNES}}, w_{\text{SIDRA}}]^T$.
* $\mathcal{C}_{\text{policy}}$ selects the allowed context field families: $\mathcal{C}_{\text{policy}} \subseteq \{\text{socioeconomic}, \text{sanitation}, \text{demographics}, \text{capacity}, \text{observer}\}$.
* $B \in \{\text{fast}, \text{standard}, \text{deep}\}$ is the computational budget token that strictly maps to processing capacity thresholds.
* $\mathcal{M}_{geo}$ determines the explicit geospatial structural alignment mode.
* $\mathcal{R}_{\text{force}} \subseteq \mathcal{V}_{\text{core}} \cup \mathfrak{I}_{\text{ICD}} \cup (\mathcal{A} \times \mathcal{S} \times \mathcal{R})$ is the explicit target slice selector set forcing the preservation and reporting of highly unstable or sparse demographic/clinical strata.
* $\mathcal{D}_{\text{exclude}} \subset \{SIM, SIH, SINASC, CNES, SIDRA\}$ enforces hard software blocks on specific input pipelines.

### 1.2 Geometrically Bounded Spatial Support Modes ($S^*(\mathcal{M}_{geo})$)

Let $S_t$ be the dynamic geospatial lattice of Brazilian municipalities at year $t$. The engine resolves spatial support deformations by mapping the spatial support function $S^*(\mathcal{M}_{geo})$ to one of four execution modes:

$$S^*(\mathcal{M}_{geo}) = \begin{cases} 
S_t & \text{if } \mathcal{M}_{geo} = \text{native} \\
\bar{S} & \text{if } \mathcal{M}_{geo} = \text{AMC} \\
S_{t_{\text{current}}} & \text{if } \mathcal{M}_{geo} = \text{geneallocated} \\
\left(\bar{S}, S_{t_{\text{current}}}\right) & \text{if } \mathcal{M}_{geo} = \text{hybrid}
\end{cases}$$

1. **Native Municipality-Year Mode ($\text{native}$):** Retains the raw support $S_t$ for each independent cross-section. It explicitly prohibits the execution of any cross-temporal lag operations $\tau$ across years that intersect structural border splits or merges.
2. **AMC Contraction Mode ($\text{AMC}$):** Maps the dynamic lattice to an invariant space of Minimum Comparable Areas $\bar{S}$ via the spatial contraction matrix $\mathbf{W}_{t} \in \{0, 1\}^{|\bar{S}| \times |S_t|}$, where element $w_{i,j} = 1$ if municipality $j \in S_t$ historically belongs to AMC envelope $i \in \bar{S}$:

$$\nu_{\bar{s}, t} = (\pi_* \nu_t)(\bar{s}) = \mathbf{W}_t \boldsymbol{\nu}_t = \sum_{j \in \mathbf{W}_t^{-1}(\bar{s})} \nu_t(j) \quad \forall \nu \in \mathcal{M}_{base}$$


3. **Genealolocated Allocation Mode ($\text{geneallocated}$):** Preserves contemporary municipality boundaries $S_{t_{\text{current}}}$ across the entire historical sequence. For a historical AMC envelope $\bar{s}$ containing an emancipation split, the allocation kernel $\mathbf{A}_t: \bar{S} \times S_t \to [0, 1]$ distributes historical volumes backward in time using a demographic proxy weight $\xi$:

$$(\mathcal{A}_{t*} \nu_{\bar{s}})(s) = \nu_{\bar{s}, t} \times \frac{\xi_t(s)}{\sum_{j \in \mathbf{W}_t^{-1}(\bar{s})} \xi_t(j)} \quad \forall s \in \mathbf{W}_t^{-1}(\bar{s})$$


4. **Composed Hybrid Mode ($\text{hybrid}$):** Executes a two-stage spatial compilation layout. It enforces AMC contraction $\bar{S}$ throughout the multivariate modeling and non-linear scanning layers to maximize statistical reliability, then projects the resulting fields back onto the contemporary municipality support lattice $S_{t_{\text{current}}}$ via the allocation kernel $\mathbf{A}_t$ exclusively for final presentation and report generation.

---

## 2. Joint Spatiotemporal Population Path Optimizer (Problem 3 Core)

The canonical population denominator tensor is estimated as an invariant path-space trajectory across the full multi-year temporal support range $T$. The target optimization objects are the global multi-year population tensor $\mathbf{P} = \{P_{s,t,a,x,r} : t \in T\}$ and the joint net migration field $\boldsymbol{\eta} = \{\eta_{s,t,a,x,r} : t \in T\}$, operating over the mode-dependent lattice $\Omega_{epi}(\mathcal{M}_{geo}) = S^*(\mathcal{M}_{geo}) \times T \times \mathcal{A} \times \mathcal{S} \times \mathcal{R}$.

The system computes the demographic solution by minimizing the regularized path-space loss objective function:

$$\widehat{\mathbf{P}}, \widehat{\boldsymbol{\eta}} = \arg\min_{\mathbf{P}, \boldsymbol{\eta}} \mathcal{L}(\mathbf{P}, \boldsymbol{\eta})$$

### 2.1 The Global Loss Formulations

$$\mathcal{L}(\mathbf{P}, \boldsymbol{\eta}) = \sum_{t \in T} \left[ \lambda_A \mathcal{L}_{aging}(t) + \lambda_B \mathcal{L}_{birth}(t) + \lambda_D \mathcal{L}_{death}(t) + \lambda_M \mathcal{L}_{migration}(t) + \lambda_R \mathcal{L}_{race}(t) + \lambda_S \mathcal{L}_{smooth}(t) \right]$$

The constituent loss metrics are explicitly formalized as:


$$\mathcal{L}_{aging}(t) = \sum_{s, a, x, r} \left( P_{s, t, a+1, x, r} - \left[ P_{s, t-1, a, x, r} (1 - \delta_{s, t-1, a, x, r}) + \eta_{s, t-1, a, x, r} \right] \right)^2$$

$$\mathcal{L}_{birth}(t) = \sum_{s, x, r} \left( P_{s, t, 0, x, r} - \left[ B^{\text{newborn}}_{s, t-1, x, r} + \eta_{s, t-1, 0, x, r} \right] \right)^2$$

$$\mathcal{L}_{death}(t) = \sum_{s, a, x, r} \left( \delta_{s, t, a, x, r} P_{s, t, a, x, r} - D_{s, t, a, x, r}^{SIM} \right)^2$$

$$\mathcal{L}_{migration}(t) = \sum_{s, a, x, r} \left( \eta_{s, t, a, x, r} - 2\eta_{s, t-1, a, x, r} + \eta_{s, t-2, a, x, r} \right)^2$$

$$\mathcal{L}_{race}(t) = \sum_{s, a, x} \|\text{ilr}(\mathbf{p}_{s, t, a, x, \cdot}) - \mathbf{z}_{s, t, a, x}^{\text{bridge}}\|^2_2$$

$$\mathcal{L}_{smooth}(t) = \sum_{s, a, x, r} \left( P_{s, t, a, x, r} - 2P_{s, t, a-1, s, r} + P_{s, t, a-2, s, r} \right)^2$$

### 2.2 Invariant Boundary & Closure Constraints

The optimization path is strictly bounded by hard algebraic closure constraints across every point in the manifold:


$$\sum_{a \in \mathcal{A}} \sum_{x \in \mathcal{S}} \sum_{r \in \mathcal{R}} P_{s, t, a, x, r} = E_{s, t} \quad \forall s \in S^*(\mathcal{M}_{geo}), \forall t \in T \quad \text{[Absolute Annual Closure]}$$

$$P_{s, t_c, a, x, r} = C_{s, t_c, a, x, r} \quad \forall t_c \in \{2000, 2010, 2022\} \quad \text{[Rigid Census Cross-Section Anchors]}$$

### 2.3 Regularization Tuning Contract ($\mathbf{\Lambda}_{\text{pop}}$)

The penalty weighting vectors are selected dynamically by evaluating reconstruction errors over a 10% spatial municipality holdout grid $S_{\text{val}} \subset S^*(\mathcal{M}_{geo})$ evaluated during census cross-sections:


$$\mathbf{\Lambda}_{\text{pop}} = (\lambda_A, \lambda_B, \lambda_D, \lambda_M, \lambda_R, \lambda_S)^T = \operatorname{Tune}_{\text{pop}}\left( \mathbf{C}_{t_c}, S_{\text{val}}, \mathcal{L}_{\text{smoothness}} \right)$$

| Parameter Weight | Mapping Domain | Target Target Optimization Value | Selection Rule Criteria |
| --- | --- | --- | --- |
| $\lambda_A$ | Cohort Transit | $1.0$ | Fixed benchmark scale constraint |
| $\lambda_B$ | Birth Injection | $0.8$ | Regulated by the SINASC municipal reporting coverage score |
| $\lambda_D$ | Mortality Prior | $0.9$ | Controlled by the localized SIM sub-registration index |
| $\lambda_M$ | Migration Smooth | $\alpha_{\text{tune}}$ | Minimized over out-of-sample intercensal error variance |
| $\lambda_R$ | Race Simplex | $\beta_{\text{tune}}$ | Calibrated against the self-identification reclassification drift |
| $\lambda_S$ | Age Smoothing | $\gamma_{\text{tune}}$ | Tied directly to the target P-Spline smoothness index |

### 2.4 Decoupled Mortality Prior & Local Frailty Modifiers ($\psi_{s, a}$)

The cell-specific mortality risk prior $\delta_{s, t, a, x, r}$ is race-neutral by design and decoupled from contemporary municipal death counts to prevent numerical leakage into Problem 2. It uses state-level life table models modified by a localized spatial age-frailty vector $\boldsymbol{\psi}_{s}$:

$$\delta_{s, t, a, x, r} = \left[ \frac{\sum_{k=1}^{3} \omega_k \cdot \text{LifeTable}_{\text{UF}(s), t-k, a, x}}{\sum_{k=1}^{3} \omega_k} \right] \times \left(1 + \psi_{s, a}\right)$$

The municipal frailty modifier $\psi_{s, a}$ is estimated as a static parameter solved exclusively during the decadal census cross-sections $t_c$:


$$\widehat{\psi}_{s, a} = \arg\min_{\psi_{s, a}} \sum_{t_c \in \{2000, 2010, 2022\}} \sum_{x \in \mathcal{S}} \sum_{r \in \mathcal{R}} \left( \delta_{s, t_c, a, x, r}(\psi_{s, a}) P_{s, t_c, a, x, r} - D_{s, t_c, a, x, r}^{SIM} \right)^2$$

### 2.5 National Migration Enclosure Regimes ($\mathcal{M}_{\text{migration}}$)

The boundaries governing the net migration field $\boldsymbol{\eta}$ are explicitly parameterized via the selected execution regime:


$$\mathcal{M}_{\text{migration}} \in \{ \text{closed national}, \text{open national residual}, \text{external migration prior} \}$$

$$\sum_{s \in S^*(\mathcal{M}_{geo})} \eta_{s, t, a, x, r} = M^{\text{national}}_{t, a, x, r}$$

1. **Closed National Mode:** Forces the migration field to sum to zero across the entire boundary space: $M^{\text{national}}_{t, a, x, r} = 0$.
2. **Open National Residual Mode:** Sets the national boundary equal to the net international migration adjustment calculated from official demographic residual accounts: $M^{\text{national}}_{t, a, x, r} = \Delta^{\text{residual}}_{t, a, x, r}$.
3. **External Migration Prior Mode:** Restricts the optimization using a fixed, regularized matrix drawn from national migration surveys: $M^{\text{national}}_{t, a, x, r} = \boldsymbol{\Psi}^{\text{prior}}_{t, a, x, r}$.

### 2.6 Dual-Axis Birth Input Separators

To maintain demographic coherence, birth inputs are split across independent tracking dimensions:

* **Maternal Fertility Vector ($B^{\text{maternal}}_{s, t, a_m, r_m}$):** Extracted from $\mathcal{E}_{SINASC}$ to compile age-specific fertility rates inside $V_{core}$.
* **Newborn Entry Vector ($B^{\text{newborn}}_{s, t, x_n, r_n}$):** Maps directly to the $a=0$ tensor cell. If the newborn's race $r_n$ is omitted in the record stream, it is imputed using a multi-tiered conditional probability network hierarchy that flows automatically down to national baselines if local data is sparse:

$$P(r_n \mid r_m, s) \xrightarrow{\text{fallback if } n < 30} P(r_n \mid r_m, \text{UF}(s)) \xrightarrow{\text{fallback}} P(r_n \mid r_m, \text{Region}(s)) \xrightarrow{\text{fallback}} P(r_n \mid r_m, \text{Brazil})$$



---

## 3. Continuous Sociological Latent Inference Space (ST-DFM Specification)

For temporally sparse SIDRA tables where the context classifier outputs $R(q) = \text{bounded\_interpolate}$, the unobserved values are reconstructed using a Spatiotemporal Dynamic Factor Model ($\text{ST-DFM}$).

### 3.1 Non-Linear Measurement Link Transformations ($g_q$)

Let $Y_{s, t, q}$ be the raw observed variable $q$ with missingness mask $M_{s, t, q}$. To enforce structural boundaries (such as bounding percentages between $0$ and $1$), the data generation layer passes through an explicit non-linear link function $g_q(\cdot)$ before mapping to the continuous latent factor matrix $\mathbf{F}_{s, t} \in \mathbb{R}^K$:

$$g_q(Y_{s, t, q}) = \boldsymbol{\lambda}_q^T \mathbf{F}_{s, t} + \epsilon_{s, t, q} \quad \forall (s, t, q) \text{ where } M_{s, t, q} = 1$$

$$\mathbf{F}_{s, t} = \mathbf{A} \mathbf{F}_{s, t-1} + \mathbf{B} \mathbf{Z}_{s, t} + \boldsymbol{\eta}_{s, t}$$

The link function selection is governed deterministically by variable properties:


$$g_q(Y) = \begin{cases} 
\log(Y + \epsilon) & \text{if } \text{Type}(q) = m \lor \text{Type}(q) = c \quad \text{[Positive Monetary / Count Contexts]} \\
\text{logit}(Y) = \log\left(\frac{Y}{1-Y}\right) & \text{if } \text{Type}(q) = p \quad \text{[Bounded Proportions / Percentages]} \\
\text{clr}(\mathbf{Y}) & \text{if } \text{Type}(q) = \text{simplex} \quad \text{[Compositional Shares]} \\
\text{identity} & \text{if } \text{Type}(q) = o \quad \text{[Continuous Gaussian Measurements]} \\
\text{forbidden} & \text{if } \text{Type}(q) \in \{\text{median}, \text{quantile}\} \quad \text{[Halts Execution Steps]}
\end{cases}$$

### 3.2 Matrix Identifiability Constraints

To resolve the rotation, sign, and scale indeterminacy inherent to latent factor configurations, the loading matrix $\mathbf{\Lambda} = [\boldsymbol{\lambda}_1, \dots, \boldsymbol{\lambda}_Q]^T$ is restricted to a lower-triangular form with strictly positive diagonal elements:


$$\lambda_{q,k} = 0 \quad \forall k > q, \quad \lambda_{q,q} > 0 \quad \forall q \le K$$


The latent factors are forced to maintain an orthogonal variance profile over space-time: $\mathbb{E}[\mathbf{F}_{s,t} \mathbf{F}_{s,t}^T] = \mathbf{I}_K$.

### 3.3 Multi-Stage Cross-Validation & Latent Field Certification

Rather than relying on a single error term, the generated latent field $\widetilde{X}_{s, t, q} = g_q^{-1}(\widehat{\boldsymbol{\lambda}}_q^T \widehat{\mathbf{F}}_{s, t})$ must pass a multi-stage spatial and temporal out-of-sample holdout test.

```
+------------------------------------------------------------+
|             LATENT FIELD CANDIDATE GEN (X_tilde)           |
+------------------------------+-----------------------------+
                               |
                               v
+------------------------------------------------------------+
|             STAGE 1: INTERCENSAL TEMPORAL HOLDOUT         |
|         Drop 2010 Anchor; Fit Model; Check Absolute Error  |
+------------------------------+-----------------------------+
                               | Pass
                               v
+------------------------------------------------------------+
|             STAGE 2: SPATIAL MACROREGION HOLDOUT           |
|        Drop 10% Municipalities; Evaluate Kriging Fit       |
+------------------------------+-----------------------------+
                               | Pass
                               v
+------------------------------------------------------------+
|             CERTIFICATION TERMINAL COMPLETE                |
|      Set Prov = latent; DashboardSafe = 0; Commit Field    |
+------------------------------------------------------------+

```

1. **Stage 1: Intercensal Temporal Holdout:** The system drops the entire 2010 census anchor matrix for variable $q$, fits the model over the remaining anchors (2000, 2022), and calculates the Mean Absolute Percentage Error ($\text{MAPE}$) over the omitted 2010 data:

$$\text{MAPE}_{2010} = \frac{1}{|S^*|} \sum_{s \in S^*} \left| \frac{Y_{s, 2010, q} - \widetilde{X}_{s, 2010, q}}{Y_{s, 2010, q}} \right|$$


2. **Stage 2: Spatial Macroregion Holdout:** The system drops a contiguous 10% spatial cluster of municipalities, re-estimates the factors, and computes the spatial interpolation error.

$$\text{Certification Contract}: \text{State}(\widetilde{X}_q) = \begin{cases} 
\text{valid} & \text{if } \text{MAPE}_{2010} \le 0.15 \land \sigma_q^2/\text{Var}(Y_q) \le 0.25 \\
\text{fragile} & \text{if } 0.15 < \text{MAPE}_{2010} \le 0.35 \land \sigma_q^2/\text{Var}(Y_q) \le 0.40 \\
\text{illegal} & \text{otherwise [Field is destroyed; processing halts]}
\end{cases}$$

Continuous field metrics that pass certification are assigned a locked metadata token: $\text{Prov}(\widetilde{X}_q) = \text{latent}$. Their uncertainty distribution is propagated directly into the diagnostic tensor $Q(v)$ by adding the estimation variance matrix $\text{Var}(\widehat{\mathbf{F}}_{s,t})$ to the global noise field.

---

## 4. The Multi-Dimensional Measure DAG Space & Operator Grammar (Problem 1)

### 4.1 The Complete Node Schema Contract ($\Gamma(v)$)

Every node instantiated inside $\mathcal{G}_{\text{DAG}}$ is defined by a rigorous 14-parameter structural metadata schema:

$$\Gamma(v) = \left( \text{id}, \text{name}, \text{kind}, \text{carrier}, \text{unit}, L_v, \text{axes}, \text{aggregation}, \text{role}, \text{source}, \text{operator}, \text{provenance}, \text{state}, \text{warnings} \right)$$

where:

* `id` is a unique SHA-256 cryptographic hash derived from the node's expression lineage.
* `kind` distinguishes the measure type: $\text{kind} \in \{\text{extensive\_measure}, \text{intensive\_density}, \text{marked\_functional}, \text{context\_gradient}, \text{bridge\_divergence}\}$.
* `carrier` identifies the underlying event system or data carrier: $\text{carrier} \in \{\text{Deaths}, \text{Hospitalizations}, \text{LiveBirths}, \text{Facilities}, \text{Domiciles}, \text{SocioeconomicRealms}\}$.
* `unit` maps the physical measurement metric: $\text{unit} \in \{\text{counts}, \text{person-years}, \text{currency\_real}, \text{ratios}, \text{days}, \text{grams}, \text{proportions}\}$.
* `L_v` defines the explicit high-dimensional spatiotemporal view domain lattice constraint.
* `axes` is an ordered list mapping active dimensions of stratification: $\text{axes} \subseteq \{\mathcal{A}, \mathcal{S}, \mathcal{R}, \mathcal{H}, \mathcal{F}, \mathcal{C}\}$.
* `aggregation` defines the valid marginalization law: $\text{aggregation} \in \{\text{additive}, \text{weighted\_mean}, \text{non\_aggregable}\}$.
* `role` maps the functional destination inside Phase 2 regressions: $\text{role} \in \{\text{outcome}, \text{exposure\_offset}, \text{covariate}, \text{observer\_proxy}, \text{exploratory\_field}\}$.
* `source` logs the contributing databases: $\text{source} \subseteq \{SIM, SIH, SINASC, CNES, SIDRA\}$.
* `operator` identifies the executing transformation morphism from the grammar $\mathcal{O}$.
* `provenance` tracks the variable's generation history: $\text{provenance} \in \{\text{official}, \text{harmonized}, \text{deflated}, \text{latent}, \text{forced\_fragile}\}$.
* `state` sets the active quarantine status validation tag.
* `warnings` is an append-only character array carrying structural error messages inherited from upstream nodes.

### 4.2 The Core Ingestion Alignment Contract ($\text{Align}(\nu, \mu)$)

Before evaluating any graph operations or checking the legality predicate, the DAG passes incoming field pairs through a deterministic support-balancing loop. The alignment engine resolves dimensional mismatches by applying pushforward operators ($\pi_*$) or blocking illegal pullbacks according to structural rules:

```
                            +-----------------------------------+
                            |        Align(Numerator, Denom)     |
                            +-----------------+-----------------+
                                              |
                                              v
                                     /-----------------\
                                    /   Is Numerator    \
                                    \   Finer than Denom? /
                                     \--------+--------/
                                              |
                                     +--------+--------+
                                     | Yes             | No
                                     v                 v
                        [Pushforward Numerator]    /-----------------\
                        [   Axes to Match     ]   /   Is Denom Finer  \
                                                  \   than Numerator? /
                                                   \------+--------/
                                                          |
                                                 +--------+--------+
                                                 | Yes             | No
                                                 v                 v
                                      [Pushforward Denominator] [Check Context]
                                      [     Axes to Match     ]      |
                                                                     v
                                                          /---------------------\
                                                         /  Is Denom an External \
                                                         \  Measure Context?     /
                                                          \----------+----------/
                                                                     |
                                                            +--------+--------+
                                                            | Yes             | No
                                                            v                 v
                                                    [Contextual Pullback] [REJECT]
                                                    [  Covariate Only   ] [Delta = 0]

```

```python
def Align(numerator, denominator):
    axes_num = set(numerator.axes)
    axes_den = set(denominator.axes)
    
    if axes_num == axes_den:
        return numerator, denominator, "aligned_identity"
        
    # Case 1: Numerator has surplus dimensions (Finer stratification than Denominator)
    if axes_num > axes_den:
        surplus_axes = axes_num - axes_den
        aligned_num = numerator
        for axis in surplus_axes:
            aligned_num = pushforward_marginalize(aligned_num, axis)
        return aligned_num, denominator, "aligned_numerator_pushforward"
        
    # Case 2: Denominator has surplus dimensions (Finer stratification than Numerator)
    if axes_den > axes_num:
        if denominator.role == "context" and denominator.unit in ["ratios", "proportions", "monetary_pc"]:
            # Contextual pullback allowed only as a covariate, never as a rate exposure base
            return numerator, denominator, "aligned_contextual_pullback"
        else:
            # Enforce Pullback Trap Protection: collapse denominator resolution upward to match numerator
            surplus_axes = axes_den - axes_num
            aligned_den = denominator
            for axis in surplus_axes:
                aligned_den = pushforward_marginalize(aligned_den, axis)
            return numerator, aligned_den, "aligned_denominator_pushforward"
            
    # Case 3: Mismatched, non-nested dimensional topologies
    return None, None, "rejected_incompatible_structures"

```

---

## 5. Formal Production Registries & Verification Specs

### 5.1 The Production Carrier Compatibility Registry ($\mathcal{K}_{\text{carrier}}$)

The structural link connecting numerators, denominators, and regression targets is governed by the complete initial carrier compatibility registry lookup table. Any modification step that attempts to generate a Radon-Nikodym rate from unlisted carrier pairs is rejected ($\Delta_{\text{carrier}} = 0$):

| Numerator Carrier String | Denominator Carrier String | Allowed Operator Type | Inferred Variable Target Role | Mathematical Definition Contract |
| --- | --- | --- | --- | --- |
| `Deaths` | `Population` | `RN` | `outcome` | Crude/Cause-Specific Mortality Field over $\Omega_{epi}$ |
| `HospitalDeaths` | `HospitalAdmissions` | `RN` | `exploratory\_field` | Inpatient Case Fatality Divergence Field |
| `LowBirthWeightBirths` | `LiveBirths` | `RN` | `outcome` | Low Birth Weight Proportion Vector Space |
| `PretermBirths` | `LiveBirths` | `RN` | `outcome` | Prematurity Proportion Field Layer |
| `CesareanBirths` | `LiveBirths` | `RN` | `outcome` | Delivery Mode Distribution Simplex Matrix |
| `PrenatalAdequacyCount` | `LiveBirths` | `RN` | `covariate` | Kotelchuck Prenatal Care Adequacy Distribution |
| `CongenitalAnomalies` | `LiveBirths` | `RN` | `outcome` | Congenital Anomaly Prevalence Field |
| `HospitalAdmissions` | `Population` | `RN` | `outcome` | General/Diagnosis-Specific Inpatient Admission Rate |
| `ICUAdmissions` | `HospitalAdmissions` | `RN` | `covariate` | ICU Access Intensity Proportion Field |
| `HospitalCosts` | `HospitalAdmissions` | `RN` | `covariate` | Mean Deflated Financial Cost per Admission |
| `HospitalDays` | `HospitalAdmissions` | `RN` | `covariate` | Mean Length of Stay Marked Metric |
| `Physicians` | `Population` | `RN` | `covariate` | Clinical Workforce Resource Stock Density |
| `Facilities` | `Population` | `RN` | `covariate` | Infrastructure Access Facility Density Field |
| `DomicilesWithSanitation` | `Domiciles` | `RN` | `covariate` | Structural Sanitation Coverage Percentage |

### 5.2 The Intent-Conditioned Field Utility Score ($U_{\mathcal{I}}(v)$)

The DAG ranks and prunes candidate nodes during automated chart traversal by calculating the explicit algebraic utility score function:

$$U_{\mathcal{I}}(v) = \alpha_1 \cdot \text{Core}(v) + \alpha_2 \cdot \text{Rel}_{\mathcal{I}}(v) + \alpha_3 \cdot \text{SourceWeight}(v) + \alpha_4 \cdot \text{Bridge}(v) + \alpha_5 \cdot \text{Quality}(v) - \alpha_6 \cdot \text{Complexity}(v) - \alpha_7 \cdot \text{Cost}(v)$$

where:

* $\text{Core}(v) = \mathbb{I}(v \in V_{\text{core}})$.
* $\text{Rel}_{\mathcal{I}}(v) = \max_{H \in \mathcal{H}_0} [ 1 - \text{TreeDistance}(v_{\mathcal{H}}, H) ]$.
* $\text{SourceWeight}(v) = \sum_{s \in \text{source}(v)} \mathbf{w}_{\text{systems}}[s]$.
* $\text{Bridge}(v) = \mathbb{I}(|\sigma(v)|_0 \ge 2) \cdot \text{BridgePriorityWeight}$.
* $\text{Quality}(v) = 1 - \text{Frag}(v) - \mathbb{E}_\Omega[CV(v)]$.
* $\text{Complexity}(v) = \text{GraphDepth}(v)$.
* $\text{Cost}(v) = \text{ExecutionTimeMs}(v) / 1000$.

The fixed hyperparameter weight profile is mapped down to system hardware constants: $\boldsymbol{\alpha} = (10.0, 5.0, 3.0, 4.0, 2.0, 1.5, 0.5)^T$. Nodes that evaluate to $U_{\mathcal{I}}(v) < \theta_{\text{compile}}$ are frozen from memory allocations.

### 5.3 Complete Parameterized State Tensor Formulas ($Q(v)$)

The state tensor $Q(v)$ extracts structural diagnostics across the entire spatiotemporal matrix support. Each sub-parameter is calculated using explicit mathematical operations:

#### 5.3.1 Effective Sample Size ($n_{\text{eff}}$)

Adjusts absolute case counts for spatial inflation using the contiguity weight matrix $\mathbf{W}$:


$$n_{\text{eff}}(v) = \frac{\left( \sum_{s \in S^*} \sum_{t \in T} v(s, t) \right)^2}{\sum_{s \in S^*} \sum_{t \in T} v(s, t)^2 \cdot \left( 1 + \max(0, \mathcal{I}_{\text{Moran}}(v)) \right)}$$


where the spatial autocorrelation index $\mathcal{I}_{\text{Moran}}$ is evaluated over the continuous field:


$$\mathcal{I}_{\text{Moran}}(v) = \frac{|S^*|}{\sum_{i,j} W_{ij}} \cdot \frac{\sum_{i,j} W_{ij} (v_i - \bar{v})(v_j - \bar{v})}{\sum_i (v_i - \bar{v})^2}$$

#### 5.3.2 Zero-Inflation Index ($\zeta$)

$$\zeta(v) = \frac{1}{|S^*|\cdot|T|} \sum_{s \in S^*} \sum_{t \in T} \mathbb{I}(v(s, t) == 0)$$

#### 5.3.3 Denominator Fragility Score ($\text{Frag}(v)$)

Tracks rate volatility across thin local cells:


$$\text{Frag}(v) = \frac{1}{|S^*|\cdot|T|} \sum_{s \in S^*} \sum_{t \in T} \mathbb{I}\left(\mu_{\text{denom}}(s,t) < 50 \right)$$

#### 5.3.4 Temporal Roughness Index ($\mathcal{R}_T$)

Measures structural volatility trends over time:


$$\mathcal{R}_T(v) = \frac{1}{|S^*|\cdot(|T|-2)} \sum_{s \in S^*} \sum_{t=3}^{|T|} \left( v(s, t) - 2v(s, t-1) + v(s, t-2) \right)^2$$

### 5.4 The Strict Quarantine Permissions Matrix

Every field node is routed into one of five validation classes:


$$\text{Class}(v) \in \{ \text{verified}, \text{fragile}, \text{forced}, \text{quarantined}, \text{illegal\_excluded} \}$$


The allowed algorithmic actions for each class are determined by a strict permissions matrix:

$$\text{Perm}(\text{Class}(v), \text{operator}) \to \{0, 1\}$$

$$\begin{array}{lccccc}
\hline
\textbf{Variable Classification State} & \text{Modelable As Outcome} & \text{Modelable As Covariate} & \text{Can Generate RN Rate} & \text{Can Deepen ICD Traversal} & \text{Dashboard Safe} \\ \hline
\text{verified} & 1 & 1 & 1 & 1 & 1 \\
\text{fragile} & 1 & 1 & 0 & 1 & 1 \\
\text{quarantined\_descriptive} & 0 & 1 & 0 & 0 & 0 \\
\text{forced\_fragile} & 1 & 1 & 0 & 0 & 0 \\
\text{illegal\_excluded} & 0 & 0 & 0 & 0 & 0 \\ \hline
\end{array}$$

### 5.5 Multi-Axis Equivalence Compression Matrix ($\mathbb{C}$)

To insulate downstream regressions from multicollinearity failures, the DAG passes field pairs through an explicit correlation sieve before model building:


$$\mathbb{C}(X_i, X_j) = \max \left( |\text{Pearson}(X_i, X_j)|, |\text{Spearman}(X_i, X_j)| \right)$$

$$\text{If } \mathbb{C}(X_i, X_j) \ge 0.98 \quad \text{OR} \quad \text{Lineage}(X_i) \equiv \text{Lineage}(X_j) \implies X_i \equiv X_j$$


The node with the lower $U_{\mathcal{I}}$ score is compressed into the equivalence class of the dominant field, removing it from the statistical predictor stack while preserving its tracking properties.

---

## 6. Hierarchical Model Selection & Precedence Engine (Problem 2)

Problem 2 isolates adjusted associations by fitting regularized parametric models before executing non-linear copula scans.

```
                           +------------------------------------+
                           |    Ingest Outcome Variable (Y)     |
                           +-----------------+------------------+
                                             |
                                             v
                                    /-----------------\
                                   |  Is Y an Event    |
                                   |  Count Measure?   |
                                    \--------+--------/
                                             |
                                    +--------+--------+
                                    | Yes             | No -> [Check Proportions]
                                    v                 v
                           /-----------------\   /-----------------\
                          /  Does ZeroRatio   \ /   Is Y a Bounded  \
                          \  Exceed 0.25?     / \   Percentage?     /
                           \--------+--------/   \--------+--------/
                                    |                     |
                           +--------+--------+            +--------+--------+
                           | Yes             | No                  | Yes     | No -> [Gamma GLM]
                           v                 v                     v         v
                  [Hurdle NegBinomial] [Negative Binomial]  [Beta-Binomial] [Gaussian Mark]

```

### 6.1 Hierarchical Precedence Selector Matrix ($\mathcal{M}_{\text{stat}}$)

The model configuration path follows a strict hierarchical evaluation tree to resolve overlapping likelihood conditions:

```python
def SelectModelRegime(Y, budget):
    if Y.kind == "intensive_density" and Y.carrier == "Deaths":
        # Force Count Model mapping via underlying extensive numerator
        Y_event = GetNumeratorCount(Y)
        offset_field = GetDenominatorExposure(Y)
    else:
        Y_event = Y
        offset_field = None

    if Y_event.unit == "counts":
        if zero_inflation_ratio(Y_event) > 0.25:
            return "Hurdle_Negative_Binomial"
        if budget == "deep":
            return "Generalized_Additive_Smooth_NB"
        if budget == "fast":
            return "Quasi_Poisson_Linear"
        return "Standard_Negative_Binomial"
        
    elif Y_event.unit == "proportions" or Y_event.unit == "ratios":
        if overdispersion_test(Y_event) == True:
            return "Beta_Binomial_Panel"
        return "Standard_Binomial_Panel"
        
    elif Y_event.unit == "currency_real" or Y_event.unit == "days":
        return "Log_Link_Gamma_GLM"
        
    elif Y_event.unit == "simplex":
        return "Dirichlet_Compositional"
        
    return "Gaussian_Spatial_Panel"

```

### 6.2 Structural Likelihood Equations with Dynamic Offsets ($E_i$)

The model equations replace uniform population offsets with flexible exposure baselines $E_i$ dynamically generated by the carrier compatibility registry $\mathcal{K}_{\text{carrier}}$:

#### 6.2.1 Standard Negative Binomial Panel Model

$$\log \lambda_{s, t, a, x, r} = \log E_{s, t, a, x, r} + \alpha + \alpha_{s} + \gamma_t + \eta_a + \delta_x + \kappa_r + \sum_{j=1}^{p} \beta_j X_{j, s, t} + u_{s} + v_t$$

#### 6.2.2 Generalized Additive Smooth Version ($\text{GAM/NB}$)

Used under deep budgets to capture non-linear contextual gradients directly within the regression layer:


$$\log \lambda_{s, t, a, x, r} = \log E_{s, t, a, x, r} + \alpha + \alpha_{s} + \gamma_t + \eta_a + \delta_x + \kappa_r + \sum_{j=1}^{m} f_j(X_{j, s, t}) + u_{s} + v_t$$


where $f_j(\cdot)$ is an unconstrained penalized thin-plate regression spline.

### 6.3 Definitive Residual Registry Contract

The non-linear scanner consumes residuals transformed specifically according to the converged likelihood family:


$$\mathbf{ModelFamily} \longrightarrow \mathbf{ResidualTransformationType}$$

$$\begin{array}{lcl}
\hline
\textbf{ Likelihood Model Family Status} & \text{Residual Type} & \text{Exact Mathematical Transformation Equation} \\ \hline
\text{Standard Negative Binomial} & \text{Deviance} & e_{i} = \text{sign}(y_i - \hat{\mu}_i) \sqrt{ 2 \left[ y_i \log\left(\frac{y_i}{\hat{\mu}_i}\right) - (y_i + \theta) \log\left(\frac{y_i + \theta}{\hat{\mu}_i + \theta}\right) \right] } \\
\text{Quasi-Poisson Linear} & \text{Pearson} & e_{i} = \frac{y_i - \hat{\mu}_i}{\sqrt{\phi \cdot \hat{\mu}_i}} \\
\text{Hurdle / Zero-Inflated NB} & \text{Quantile} & e_{i} = \Phi^{-1} \left( \text{Dunn-Smyth}(Y_i \mid \hat{\pi}_i, \hat{\mu}_i, \hat{\theta}) \right) \\
\text{Beta-Binomial Panel} & \text{Quantile} & e_{i} = \Phi^{-1} \left( \text{Uniform}\left( F_{\text{BetaBin}}(y_i - 1), F_{\text{BetaBin}}(y_i) \right) \right) \\
\text{Log-Link Gamma GLM} & \text{Deviance} & e_{i} = \text{sign}(y_i - \hat{\mu}_i) \sqrt{ 2 \nu \left[ \frac{y_i - \hat{\mu}_i}{\hat{\mu}_i} - \log\left(\frac{y_i}{\hat{\mu}_i}\right) \right] } \\
\text{Gaussian Spatial Panel} & \text{Normalized} & e_{i} = \frac{y_i - \hat{\mu}_i}{\sigma_\epsilon} \\ \hline
\end{array}$$

### 6.4 Non-Linear Scan & Block Permutation Registry

The structural null model permutations and stability cross-validation splits are indexed via a rigid lookup matrix:

$$\mathbf{M}_{\text{scan\_regime}} \to \left( \text{NullModel}, \text{Permutations}, \text{StabilityPartitions}, \text{FDRControl} \right)$$

$$\begin{array}{lcccc}
\hline
\textbf{Data Support Topology} & \text{Null Model Permutation Law} & \text{Permutation Count} & \text{Stability Selection Splits} & \text{FDR Family Control} \\ \hline
\text{Annual Municipal Panel} & \text{Spatial Block + Cyclic Time Shift} & 1000 & \text{5-Fold Spatial Macroregion} & \text{Benjamini-Yekutieli} \\
\text{Monthly Seasonal Panel} & \text{Within-Season Temporal Rotation} & 2000 & \text{Stratified Temporal Blocks} & \text{Benjamini-Yekutieli} \\
\text{Cross-Sectional Census} & \text{Contiguity Geo-Adjacency Shuffling} & 1000 & \text{Leave-Group-Out by State (UF)} & \text{Benjamini-Hochberg} \\
\text{Facility Capacity Stock} & \text{Restricted Intra-UF Spatial Swap} & 5000 & \text{Randomized Facility Holdouts} & \text{Storey's } q\text{-value} \\ \hline
\end{array}$$

---

## 7. Production Output & System Verification Bundle Contract ($\mathcal{O}_{run}$)

Every compilation run logs an immutable, auditable directory structured as a single 15-key JSON schema storage contract. The bundle includes dedicated, first-class storage vectors for tracking validation failures and data overrides:

```json
{
  "$schema": "https://pegasus.famed.ufal.br/schemas/run_contract_v1.json",
  "OutputBundle": {
    "V_fields": "String encoded path to Arrow RecordBatch tensor database storing verified field matrices",
    "E_DAG": "Adjacency matrix map logging full variable lineage histories and parent-child operator nodes",
    "Q_tensor": "Multi-dimensional diagnostic state history logging calculated Q(v) parameter vectors per cell",
    "P_vector": "Provenance vector tracking data modification and generation history tags across the universe",
    "ModelDiagnostics": "Converged maximum likelihood parameters, standard errors, fixed effects, and log-likelihood iterations",
    "Residuals": "Vector array storing calculated deviance and randomized quantile residuals generated in Phase 2",
    "Hypotheses": [
      {
        "Outcome_Field_ID": "SHA-256 hash of the target dependent variable field",
        "Covariate_Field_ID": "SHA-256 hash of the tested independent explorer variable",
        "NonLinear_HSIC_Score": 0.34215,
        "Empirical_P_Value": 0.002,
        "Adjusted_BY_Q_Value": 0.014,
        "Active_Null_Regime": "Spatial Block + Cyclic Time Shift",
        "Evaluation_Support_Size": 72410,
        "Residual_Likelihood_Type": "Deviance_Negative_Binomial"
      }
    ],
    "Tables": "Parquet binary collection storing aggregated demographic metrics, trends, and rankings",
    "Maps": "GeoParquet topological layer mapping spatial outcome distributions over the M_geo support lattice",
    "VariableDictionary": "Schema dictionary documenting generated variable definitions, labels, and base metrics",
    "FailedBranches": [
      {
        "Expression_Lineage": "RN(sigma_ICD=A30(nu_SIM), mu_POP)",
        "Failure_Reason": "Sparsity bound breach: Spatial Entropy H evaluate below theta_sparse limit",
        "Terminal_Step_Rank": 3
      }
    ],
    "QuarantinedFields": [
      {
        "Field_ID": "SHA-256 hash of the quarantined node",
        "Diagnostic_Trigger": "Expected global noise coefficient E_Omega[CV] exceeded eta_noise parameter limit",
        "Permission_State": "quarantined_descriptive"
      }
    ],
    "ForcedFields": [
      {
        "Field_ID": "SHA-256 hash of the user-forced field",
        "Override_Selector": "indigenous_specific_strata",
        "Inherited_Warning_Token": "forced_fragile_unstable_denominator_variance_warning"
      }
    ],
    "RunConfig": "System compilation configuration metadata recording execution budget mappings and M_geo geospatial modes",
    "ReproducibilityManifest": "Cryptographic SHA-256 hashes recording immutable database input states and execution random seeds"
  }
}

```

---

## 8. End-to-End Operational Compilation Algorithm

```
Input: Bounded User Intent Object I = (G, T, H_0, V_0, w_systems, C_policy, B, M_geo, R_force, D_exclude)

Phase A: Problem 3 Substrate Preparation Lifecycle
    1. Parse M_geo: Instanciate geospatial support function S*(M_geo).
    2. Ingest R_CNES: Process establishment panel records using structural omega_f capacity weights.
    3. Invoke regularizer tuning contract: Lambda_pop = Tune_pop(C_tc, S_val, Smoothness).
    4. Solve path-space demographic tensor optimizer to compile P_hat and eta_hat across time window T.
    5. Evaluate AgeHarmonize type-guard: drop medians/quantiles from single-year disaggregation; enforce terminal failure if unmatched.
    6. Ingest currency fields and execute Monetary Deflation Operator using the real consumer price index IPCA.
    7. Export normalized gap-free substrate cubes B = { B_GEO, B_POP, B_DATASUS, B_CNES, B_SIDRA }.

Phase B: Problem 1 Automated Variable DAG Exploration Space
    1. Seed graph root space: V_seed = V_core U V_0 U H_0.
    2. For each proposed operator step o(v_i, v_j):
        a. Execute Align(v_i, v_j) to resolve high-dimensional view support transformations.
        b. Evaluate seven-part legality predicate matrix Delta. If Delta == 0, sever branch and log to FailedBranches.
        c. Evaluate ICD tree via Branch-and-Bound: if H(G) < theta_sparse and G not in R_force, halt downward crawl.
        d. Ingest garbage codes inside G_quality: force DiseaseOutcome = 0 and route directly to observer_process fields.
        e. Calculate multi-axis State Tensor parameters: n_eff, zero-inflation, denominator fragility, and expected global noise E_Omega[CV].
        f. Check Quarantine Permissions: if E[CV] > eta_noise, verify R_force selector:
           - If unmapped: set Class = quarantined_descriptive; freeze node from child generation operations.
           - If mapped: set Class = forced_fragile; log node to ForcedFields and propagate structural warnings.
        g. Evaluate collinearity matrix C(X_i, X_j): compress near-identical fields into Equivalence Classes.
        h. Instantiate primitive Cross-System Bridge Grammars (D^MM_G, Bridge_MC, Bridge_HO, Bridge_DQ).
    3. Generate P1 analytical baseline profiles (Burden maps, Inequality gradients, Decomposition tables).

Phase C: Problem 2 Multivariate Statistical Explanation Layer
    1. Calculate Intent-Conditioned Field Utility Score U_I(v) for all non-quarantined variables.
    2. Filter predictor space to extract Top-K covariates X_model bounded by budget parameter mapping matrix.
    3. Query likelihood regime selector tree M_stat(Y) to determine optimal regression configuration.
    4. Fit regularized panel regression model; constrain random effects to orthogonal complement u^T X = 0.
    5. Extract likelihood-matched parametric deviance or randomized quantile residuals vector (e_Y).

Phase D: Non-Linear Residual Scan Lifecycle
    1. Map approximate HSIC execution mode (exact, Nystrom, RFF) based on active budget boundaries.
    2. Restrict residual scanning space strictly to mutually observed support intersections.
    3. Project kernels orthogonally to spatiotemporal drift using Quenched Gravity residualizers R_Z.
    4. Calculate copula trace metrics and control false discovery inflation via Benjamini-Yekutieli q-scores.

Phase E: Serialization & Output Validation
    1. Compile Arrow tensors, lineages, model errors, diagnostics, and validation manifests.
    2. Verify bundle structure against the 15-key JSON schema.
    3. Execute SHA-256 cryptographic signing over the data parameters.
    4. Export definitive bundle O_run to storage layout.

```

---

## 9. Implementation Phasing Strategy

To ensure systematic development of the engine, implementation is decoupled into four decoupled, dependent software engineering phases:

### Phase 1: Structural Scaffolding & System Contracts

Implement immediately to lock down memory footprints and input interfaces:

* The complete JSON configuration parsing schema for the User Intent Object $\mathcal{I}$.
* The high-dimensional node storage structure for the field schema $\Gamma(v)$ and view domains $L_v$.
* The immutable 15-key output bundle structural directory layout $\mathcal{O}_{\text{run}}$.

### Phase 2: Deterministic Preprocessing & Spatial Lattices

Implement over verified input data blocks:

* The spatial contraction matrix transformations ($\mathbf{W}_t$) for AMC and genealogical allocation operators.
* The CNES facility aggregation law configurations across additive and weighted asset views.
* The continuous monetary real-price index deflation algorithm using consumer price datasets.
* The age-harmonization interval type-guard fence.

### Phase 3: Demographic & Contextual Reconstruction Optimizers

Prototype as isolated mathematical engines, testing convergence against known census anchors:

* The multi-term path-space population optimizer solving $\mathcal{L}(\mathbf{P}, \boldsymbol{\eta})$ via gradient descent.
* The multi-link, regularized state-space factor model ($\text{ST-DFM}$) incorporating out-of-sample holdout checks.
* The automated alignment loop $\text{Align}(\nu, \mu)$ and the multi-axis set legality predicate $\Delta$.

### Phase 4: Statistical Modeling & Residual Scanning Space

Implement once the underlying variable field generation layer stabilizes:

* The hierarchical likelihood selector matrix $\mathcal{M}_{\text{stat}}$ routing count, percentage, and continuous fields.
* The regularized panel GLM regression engine outputting standardized deviance and quantile residuals.
* The approximate residual HSIC copula scanner running subsampled Fourier kernel mappings.