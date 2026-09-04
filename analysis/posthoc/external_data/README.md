# External data — a boundary result, not validation

**Post-hoc. Not pre-registered.** See `../README.md`.

Full audit: `hillstrom-feasibility.md`.

## Why it was investigated

MarginPilot's finding is about **net contribution under promotion cost**, measured in a simulator. The obvious question a reviewer asks is whether a real randomized promotion experiment shows the same thing. The Hillstrom / MineThatData E-Mail Analytics And Data Mining Challenge dataset is the standard public candidate, so it was audited **before** any modelling, to establish whether it could answer the question at all.

## Provenance

Downloaded 1 September 2026 from the source the project owner authorized:

```
http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv
HTTP 200, no redirect · 3,964,977 bytes · 64,001 lines
sha256  0e5893329d8b93cefecc571777672028290ab69865718020c78c7284f291aece
md5     0af45f3c7ee495ed5654b398b1aab809
```

**The CSV is not committed.** This repository tracks only its own generated evidence, by explicit named exception (`tests/test_repo_hygiene.py`); there is no policy admitting third-party raw data, and none is invented here. The file lives outside the repository; its provenance and checksums above are sufficient for anyone to obtain the identical artifact.

## What inspection established

- **64,000 × 12**, zero nulls. Three arms via `segment`: Womens E-Mail 21,387 / Mens E-Mail 21,307 / No E-Mail 21,306.
- **Clean randomization** — largest standardized mean difference across all 18 covariate columns is **0.0169**.
- **Treatment is an email send.** A scan for any column matching `cost|price|margin|discount|coupon|offer|fee` returns **NONE**.
- **Spend is extremely sparse** — `spend == 0` for **99.0969%** of rows; **578 spenders** in the whole file, split 122 / 267 / 189 across arms. `conversion` is exactly the indicator `1{spend > 0}` on all 64,000 rows.
- Outcomes are positive on all three endpoints for both email arms.

## What it could test, and what it cannot

**Could test:** whether observable pre-campaign features locate a high-uplift cohort — a real external check on that narrower question. `visit` (2,262–3,894 events per arm) is the only endpoint with the power to support subgroup work; conversion resolves only coarsely (35.8% relative MDE at full arm, 101% at ⅛ of an arm); spend at 578 non-zero rows does not support individual-level heterogeneous effects.

**Cannot test:** the net-contribution-under-cost mechanism, which is what MarginPilot's finding is about. That mechanism depends on the **always-buyer penalty** — a customer who would have purchased anyway contributes `τ = 0` but still costs the merchant the incentive. With a near-zero-cost treatment, `net = τ`, there is no always-buyer penalty, and **any positive uplift is profitable by construction**. The incrementality-leakage tension does not exist in this dataset.

## What was deliberately not done

- **No model was fitted.** The audit is descriptive; no uplift model, no predictor, no policy.
- **No campaign cost, margin, or treatment effect was invented.** Attaching an assumed discount cost would manufacture the tension the dataset lacks and convert a measurement into an assumption. It was not done.
- **No held-out outcome was inspected to inform a modelling decision.**

## The claim that must not be made

> **This is not external validation of MarginPilot's economic finding, and must not be cited as evidence that the simulator result generalizes.**

It is a feasibility and boundary result: it establishes what a real, cleanly randomized promotion experiment of this kind *can* and *cannot* adjudicate. A further caveat is in the audit: MarginPilot's simulator generates three of its six customer fields independently of every latent, while Hillstrom's RFM fields carry whatever real coupling they have. A positive Hillstrom result would say something about real RFM data, not about the simulator's fields. The two are different questions.
