# Hillstrom / MineThatData — feasibility audit

**Date:** 1 September 2026 · **Scope:** descriptive audit only. No model fitted, no LLM run, no MarginPilot file touched, no cost or margin invented. Nothing written into the repo.

## 0. Artifact

| | |
|---|---|
| **path** | `/private/tmp/claude-501/-Volumes-thanu-s-T7-margin-pilot/4f08ccbf-d390-4ead-87d8-d994463b68ae/scratchpad/hillstrom.csv` |
| **source** | `http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv` — HTTP 200, no redirect |
| **size** | 3,964,977 bytes (3.8 MB), 64,001 lines (header + 64,000 rows) |
| **sha256** | `0e5893329d8b93cefecc571777672028290ab69865718020c78c7284f291aece` |
| **md5** | `0af45f3c7ee495ed5654b398b1aab809` |

Downloaded to the scratchpad only. Not placed in the MarginPilot repo.

---

## 1. Dimensions and columns

**64,000 rows × 12 columns.** Zero nulls in every column.

| column | dtype | nunique | role |
|---|---|---|---|
| `recency` | int64 | 12 | pre-treatment feature |
| `history_segment` | object | 7 | pre-treatment feature |
| `history` | float64 | 34,833 | pre-treatment feature |
| `mens` | int64 | 2 | pre-treatment feature |
| `womens` | int64 | 2 | pre-treatment feature |
| `zip_code` | object | 3 | pre-treatment feature |
| `newbie` | int64 | 2 | pre-treatment feature |
| `channel` | object | 3 | pre-treatment feature |
| `segment` | object | 3 | **treatment assignment** |
| `visit` | int64 | 2 | **post-treatment outcome** |
| `conversion` | int64 | 2 | **post-treatment outcome** |
| `spend` | float64 | 429 | **post-treatment outcome** |

There is **no customer identifier** and **no date column**.

## 2. Treatment arms

`segment` — three arms, near-exact thirds:

| arm | n | share |
|---|---|---|
| Womens E-Mail | 21,387 | 33.417% |
| Mens E-Mail | 21,307 | 33.292% |
| No E-Mail | 21,306 | 33.291% |

`No E-Mail` is the control. **This is a three-arm design, not two.** Pooling the two email arms would estimate the effect of a *mixture* of two different creatives and is a different estimand; each email arm should be contrasted against control separately.

## 3. Pre-treatment observable features (8)

`recency`, `history_segment`, `history`, `mens`, `womens`, `zip_code`, `newbie`, `channel`.

Levels: `history_segment` ∈ {1) $0-$100 … 7) $1,000+}; `zip_code` ∈ {Rural, Surburban, Urban}; `channel` ∈ {Multichannel, Phone, Web}; `mens`/`womens`/`newbie` binary. `recency` ∈ 1–12 (months). `history` ∈ [29.99, 3,345.93], mean 242.09.

## 4. Post-treatment columns — prohibited as model inputs

`visit`, `conversion`, `spend`. All three are measured in the two-week window **after** the send and must never enter a feature set. `segment` is the assignment itself and is likewise not a feature (it is the intervention).

## 5. Outcome definitions and distributions

| outcome | definition | overall |
|---|---|---|
| `visit` | visited the site in the following two weeks | 14.678% |
| `conversion` | purchased in the following two weeks | 0.9031% |
| `spend` | dollars spent in the following two weeks | mean $1.0509, range $0–$499 |

**Structural nesting, verified:**

- `conversion == 1 & visit == 0` → **0 rows**. Conversion implies visit.
- `spend > 0 & conversion == 0` → **0 rows**; `spend == 0 & conversion == 1` → **0 rows**.
- Therefore **`conversion` is exactly the indicator `spend > 0`** (verified true on all 64,000 rows). It is a deterministic function of `spend` and carries no independent information.

**Per arm:**

| arm | n | visit | conversion | mean spend | spenders | total spend |
|---|---|---|---|---|---|---|
| No E-Mail | 21,306 | 0.10617 | 0.005726 | $0.6528 | 122 | $13,908.33 |
| Mens E-Mail | 21,307 | 0.18276 | 0.012531 | $1.4226 | 267 | $30,311.69 |
| Womens E-Mail | 21,387 | 0.15140 | 0.008837 | $1.0772 | 189 | $23,038.11 |

**Contrasts vs control** (descriptive, two-sample SE):

| arm | outcome | diff | SE | t |
|---|---|---|---|---|
| Mens | visit | +0.07659 | 0.00339 | +22.62 |
| Mens | conversion | +0.00681 | 0.00092 | +7.39 |
| Mens | spend | +$0.7698 | 0.14525 | +5.30 |
| Womens | visit | +0.04523 | 0.00323 | +13.98 |
| Womens | conversion | +0.00311 | 0.00082 | +3.78 |
| Womens | spend | +$0.4244 | 0.13033 | +3.26 |

Average treatment effects are unambiguously positive on all three outcomes for both arms.

## 6. Is `spend` sufficient for an economic objective?

**Partially, and only as revenue.** `spend` is gross revenue in the window. It is not contribution: there is no margin, no COGS, no unit cost anywhere in the file. So `spend` supports **incremental revenue per targeted customer** and nothing beyond it.

## 7. Is campaign / promotion cost available?

**No.** The twelve columns are listed in §1; a scan for any column matching `cost|price|margin|discount|coupon|offer|fee` returns **NONE**. There is no cost side of any kind.

## 8. What can be measured without inventing assumptions

Measurable, defensibly, from this file alone:

1. Incremental **visit** rate, per arm, overall and by pre-treatment subgroup.
2. Incremental **conversion** rate (≡ incremental P(spend > 0)).
3. Incremental **revenue** per targeted customer (`spend`), and its total over any targeted subset.
4. The **heterogeneity** of 1–3 across pre-treatment features.

**Not measurable:** contribution, net contribution, ROMI, break-even, or any quantity requiring a margin or a cost. A contribution figure could only be *parameterized* by an assumed margin and reported as a sensitivity curve — that is a family of hypotheses, not a measurement, and it must not be presented as one.

## 9. Randomization / balance

**Clean.** Across all 18 covariate columns (after one-hot expansion), the **largest standardized mean difference between any two arms is 0.0169**. Largest offenders: `channel_Phone` (0.0169), `history_segment_2` (0.0164), `channel_Web` (0.0162). `history` differs by $1.95 on a $256 SD; `recency` by 0.024 months. Arm sizes differ by ≤81 rows.

This is consistent with correct randomization and imposes no need for covariate adjustment (though adjustment remains available for variance reduction).

## 10. Missing values, duplicates, leakage

**Missing:** zero nulls in all 12 columns.

**Duplicates:** there is no customer ID, so duplicate *customers* cannot be identified — only duplicate *rows*.

- exact duplicate rows (all 12 columns): **6,562**; rows belonging to any exact-duplicate group: 7,634
- duplicate on the 8 features only: 7,791

**Resolution: these are almost certainly feature collisions, not repeated customers.** 99.2% of rows in a duplicate group have `history == 29.99` — a single common price point shared by 7,947 rows — and 7,012 of them carry all-zero outcomes. With eight coarse features (three binaries, three small categoricals, 12-level recency) and a spiky `history` distribution, collisions at this rate are expected. **Non-independence cannot be ruled out from the artifact**, only rendered unlikely; the file contains nothing that would let anyone do better.

**Leakage:** none found.

- `history_segment` is a **lossless binning of `history`** — 0 rows fall outside their stated bin. Redundant, not leaking.
- No post-treatment quantity is encoded in any feature.
- `conversion` is a deterministic function of `spend` (§5) — a redundancy *within* the outcome block, and a reason not to treat them as two independent endpoints.

## 11. Heterogeneous treatment effects — is there enough information?

**Yes for `visit`. Marginal for `conversion`. Thin for `spend`.**

Event counts per arm:

| arm | n | visits | conversions (= spenders) |
|---|---|---|---|
| No E-Mail | 21,306 | 2,262 | 122 |
| Mens E-Mail | 21,307 | 3,894 | 267 |
| Womens E-Mail | 21,387 | 3,238 | 189 |

Power sanity (α = 0.05, 80%, no model fitted):

| contrast | MDE | relative to control rate |
|---|---|---|
| conversion, full arm | 0.00205 | **35.8%** |
| conversion, ½ of an arm | 0.00290 | 50.6% |
| conversion, ¼ of an arm | 0.00410 | 71.5% |
| conversion, ⅛ of an arm | 0.00579 | **101.2%** |
| conversion, 1/16 of an arm | 0.00819 | 143.1% |
| spend, full arm | $0.408 | observed Mens diff = $0.770 |

**Reading.** `visit` has 2,262–3,894 events per arm and supports subgroup-level uplift comfortably. `conversion` has 122–267 events per arm; below roughly a quarter of an arm, the detectable effect exceeds 70% of the base rate, so fine-grained conversion HTE is not resolvable. `spend` has 578 non-zero observations in the entire 64,000-row file.

## 12. Recommended train/validation/test protocol

1. **Estimand first.** Analyze **each email arm separately against `No E-Mail`**. Do not pool the two email arms. Nominate one arm as primary in advance — `Mens E-Mail` carries the larger signal on every outcome.
2. **Split.** Stratify **on `segment` only** — never on an outcome. 50/25/25 train/validation/test, drawn with a recorded seed, the seed and the row indices written down before anything is fitted.
3. **Seal the test set.** One evaluation, pre-registered: the targeting rule, the treated fraction, and the primary metric all fixed before the seal is broken.
4. **Primary metric.** For a rule `π(X)` learned on train, estimate the incremental outcome on test as the difference of means between arms **within `{π(X) = 1}`**. This is unbiased because assignment is independent of `X` and `π` uses only pre-treatment features. Qini / uplift curves are legitimate as descriptive companions, not as the pre-registered primary.
5. **Primary outcome: `visit`.** It is the only endpoint with the event count to support subgroup inference. Report `conversion` and `spend` as secondary, each with its interval, and state the power limits from §11 rather than reading a null as a finding.
6. **Model selection on validation only.** Cross-fit within train if a nuisance model is needed.
7. **Multiplicity.** Two arms × three outcomes = six contrasts. State the correction in advance.
8. **Disclosure that belongs in the pre-registration:** this audit computed pooled and per-arm marginal outcome rates on the full file (§5). Those marginals are reported above, so the eventual test split is not virgin with respect to them. They inform no modeling decision, but the pre-registration should say so rather than imply an untouched dataset.

---

# 13. COST MECHANISM — the decisive item

**There is no cost column, and the treatment is an email send.** §7 is conclusive: nothing in the twelve columns encodes a discount, coupon, incentive, unit cost, or margin.

**Consequence, stated plainly.**

MarginPilot's finding is about `net = τ − cost · 1{converted}` (`src/eval/harness.py:279-293`). Its whole mechanism is the **always-buyer penalty**: a customer who would have purchased anyway contributes `τ = 0` but still costs the merchant the incentive, so a campaign with genuine positive uplift can still lose money. That tension exists only because treatment is *expensive per treated order*.

An email send has **near-zero marginal cost**, and this file records none. So in Hillstrom:

- `net = τ`. There is no always-buyer penalty — people who would have visited or bought anyway cost nothing.
- **Any positive uplift is profitable by construction.** The observed ATEs (§5) are positive and significant on all three outcomes for both arms.
- There is **no incrementality-leakage tension** to reproduce.

**Therefore:**

> Hillstrom **CAN** test: *do observable pre-campaign features locate a high-uplift cohort?* — a genuine external check on the Level-A / Level-B question about whether merchant-observable behavioural fields carry individual treatment-effect signal.
>
> Hillstrom **CANNOT** test the net-contribution-under-cost mechanism, which is the actual MarginPilot claim.

I am not attaching a discount cost to manufacture the tension. Doing so would convert a measurement into an assumption and would be the same error the audit sequence has been tracking.

**One structural caveat on even the weaker test.** MarginPilot's fields are `tenure_days`, `orders_last_90d`, `days_since_last_order`, `historical_aov_inr`, `segment_id` — and in the simulator the first three are independent draws by construction. Hillstrom's `recency`, `history`, `history_segment`, `mens`, `womens`, `channel`, `newbie` are real RFM-style attributes with whatever real coupling they carry. So a positive Hillstrom result would demonstrate that *real* RFM data carries uplift signal; it would **not** show that the simulator's fields do, nor the reverse. The two are different questions about different data, and the mapping between them is not established by anything here.

# 14. SPEND ZERO-INFLATION

| | |
|---|---|
| `spend == 0` | **99.0969%** — 63,422 of 64,000 rows |
| `spend > 0` | **0.9031%** — **578 rows** |

Distribution among the 578 spenders:

| stat | value |
|---|---|
| mean | $116.36 |
| std | $107.87 |
| min | $29.99 |
| p10 | $29.99 |
| p25 | $32.27 |
| **median** | **$80.80** |
| p75 | $153.35 |
| p90 | $256.49 |
| p95 | $362.20 |
| p99 / max | $499.00 |
| total | $67,258.13 |

Spend is heavily right-skewed but not dominated by a handful of whales — the top 1% of spenders hold 3.71% of total spend. The binding problem is **sparsity, not skew**: 578 non-zero observations spread across three arms (122 / 267 / 189).

**Verdict.** Spend is **not sufficient for individual-level heterogeneous treatment effects.** Any subgroup fine enough to be interesting contains a handful of spenders, and the full-arm spend MDE ($0.408) is already more than half the observed Mens effect ($0.770). Conversion-based uplift is estimable at coarse granularity only (§11), and `visit` is the sole endpoint with comfortable power.

**Consequence for the economic target.** The economic quantity you would want — incremental revenue per targeted customer — is the one with the least statistical support. Treating `visit` as the workhorse and revenue as a secondary, interval-reported endpoint is the honest configuration.

# 15. FEATURE / OUTCOME SPLIT — confirmation

**Confirmed:** the eight features `recency`, `history_segment`, `history`, `mens`, `womens`, `zip_code`, `newbie`, `channel` are pre-treatment, and `visit`, `conversion`, `spend` are the only post-treatment outcomes. No fourth outcome column exists.

**Timing flags — stated rather than glossed.**

1. **The file contains no dates.** Every timing claim rests on the challenge's published documentation (all eight features describe the **prior twelve months**; outcomes describe the **two weeks after** the send), not on anything verifiable inside the artifact. Classification: *documented pre-treatment, not file-verifiable.*
2. **The balance evidence supports it.** If any feature were contaminated by post-treatment behaviour it would differ across arms; the largest standardized difference across all 18 covariate columns is 0.0169 (§9). That is strong circumstantial confirmation, and it is not proof.
3. **`history` / `history_segment` are mutually redundant**, not ambiguous — the binning is exact (0 violations).
4. **`newbie`** ("new customer in the past twelve months") is the one field whose window could in principle overlap the campaign. Documentation places it in the prior year; the file cannot adjudicate. Flagged as the single feature whose timing is least self-evident, though its balance across arms (0.5020 / 0.5015 / 0.5032, SMD 0.0034) shows no contamination signature.
5. **`conversion` is not an independent endpoint** — it is exactly `1{spend > 0}` (§5). Using both as separate outcomes double-counts one signal.

---

## Bottom line

The dataset is clean, well randomized, has no missing values, no leakage, and no post-treatment contamination of its features. It is a sound instrument — for a narrower question than the one under audit.

**It has no cost side.** It can therefore test whether observable pre-campaign features locate a high-uplift cohort, and it cannot test the net-contribution-under-cost mechanism that MarginPilot's finding is about. Within the weaker question, `visit` is the only endpoint with the power to support subgroup work; `spend` at 0.90% non-zero is too sparse.

**This does not validate the simulator finding, and nothing above should be read as if it did.** No model was fitted, no cost or margin was invented, and no held-out outcome was inspected to make a modelling decision.

*Stopped here.*
