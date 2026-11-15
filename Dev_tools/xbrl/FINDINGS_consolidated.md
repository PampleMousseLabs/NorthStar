# SEC XBRL Research Findings

> **Document type:** Living research log and interim findings record
> **Project:** NorthStar — SEC XBRL research
> **Status:** Research only; not approved as a production NorthStar data source
> **Latest recorded milestone:** Structural presentation-role classification and 250-company income-statement reconstruction rerun
> **Last updated:** 2026-11-14
> **Scope currently tested:** Income statements (IS) only

This document records what has been tested, what the evidence supports, what remains uncertain, and how the research direction has changed. Add dated entries as new experiments finish. Preserve older results as history rather than overwriting them when a new sample or method supersedes them.

---

## 1. Executive status

### Current conclusion

**Filing-level SEC XBRL is a promising candidate for reconstructing as-filed income statements, but it is not yet production-ready.**

The original 2026-10-08 benchmark and its 2026-11-12 diagnostic review remain the historical baseline. On 2026-11-14, the 250-company income-statement reconstruction was rerun after the structural presentation-role classifier was committed. The rerun produced 169 `RECONCILES`, 54 `PARTIAL`, 9 `FAIL`, 13 `NO_PRESENTATION`, 1 `NO_FACTS`, and 4 `NO_TOTALS`.

Among the 236 filings with facts and presentation inputs available for subtotal evaluation, 223 were classified as `RECONCILES` or `PARTIAL` (`169 RECONCILES + 54 PARTIAL`), or **94.5%**. The remaining 13 cases (9 `FAIL` and 4 `NO_TOTALS`) are excluded from that numerator. `PARTIAL` does not mean fully reconciled or valuation-ready.

Compared with the November 13 post-fix baseline, 249 companies were unchanged. EVRG moved from `NO_TOTALS` to `PARTIAL`: 12 totals were checked, 11 passed, and 1 was skipped. The remaining skip was associated with an extension concept absent from the filing instance. The `RECONCILES` count remained 169, and no other company-level status changed.

The November 14 run reused existing local presentation and filing-fact datasets and the mounted TV-box cache. It was a reconstruction rerun, not a fresh 250-company SEC data harvest. See the 2026-11-14 research-log entry for the method and limitations.

### Latest batch at a glance

| Result classification | Filings | Meaning |
|---|---:|---|
| `RECONCILES` | 169 | All detected subtotal checks reconciled to the filing's calculation linkbase |
| `PARTIAL` | 54 | No detected arithmetic failures, but one or more checks were skipped because a component fact or usable calculation arc was missing |
| `FAIL` | 9 | At least one identified subtotal disagreed with the filing's calculation linkbase |
| `NO_PRESENTATION` | 13 | Facts were available, but the current process did not harvest a usable income-statement presentation |
| `NO_FACTS` | 1 | Filing-fact harvesting failed or did not yield usable annual filing facts |
| `NO_TOTALS` | 4 | Facts and presentation were present, but no subtotal checks were identified |
| **Total sample** | **250** | All sample members accounted for |

**Calculation notes**

- Group with facts/presentation available for subtotal evaluation: `250 - 13 NO_PRESENTATION - 1 NO_FACTS = 236`.
- `RECONCILES` or `PARTIAL`: `169 + 54 = 223`, or `223 / 236 = 94.5%`.
- `FAIL` rate within that group: `9 / 236 = 3.8%`.
- `NO_TOTALS`: `4 / 236 = 1.7%`.
- These classifications measure pipeline/reconciliation outcomes, not full accounting correctness, completeness of every line item, or suitability for valuation.
- The November 13 baseline was 169 `RECONCILES`, 53 `PARTIAL`, 9 `FAIL`, 13 `NO_PRESENTATION`, 1 `NO_FACTS`, and 5 `NO_TOTALS`.

---

## 2. Research objective and acceptance criteria

Determine whether SEC XBRL can support NorthStar/Canneberge with reliable, reusable, valuation-grade financial statement data across realistic public-company peer sets.

The current income-statement scope includes:

- Revenue
- Operating income / EBIT and relevant operating subtotals
- Pretax income
- Income tax
- Net income, including noncontrolling-interest (NCI) distinctions
- Net income attributable to the parent
- EPS and share counts
- Material bridge lines needed to explain differences between statement subtotals

The goal is **not** to map every US-GAAP concept. It is to establish whether the filing can be reconstructed and normalized reliably enough for financial analysis, with explicit provenance and transparent handling of missing or derived values.

Before production consideration, research should establish at least:

1. Repeatable coverage on a documented sample.
2. Clear distinctions between fully reconciled, partial, failed, and unavailable results.
3. Accession-aligned filing facts and presentation data.
4. Reusable treatment of company extensions without proliferating company-specific hard-coded mappings.
5. A reviewed policy for missing, derived, conflicting, and restated values.
6. Separate evidence for income statements, balance sheets, and cash flow statements.
7. A documented source-priority policy and regression tests.

---

## 3. Current architecture assessment

SEC data is available through two materially different approaches.

### 3.1 SEC CompanyFacts

**Useful for:** standardized facts and many common anchors, including revenue, taxes, net income, EPS, and shares.

**Limitations observed:**

- Many company-extension concepts are not included.
- Annual face-of-statement line items may be missing.
- Available facts do not always contain enough information to reconstruct every subtotal.
- Standard concepts may not reproduce a company's presented statement by themselves.

**Current conclusion:** CompanyFacts alone is insufficient for dependable reconstruction of the full top half of the income statement. It remains useful as a standardized fact source, validation/fallback source, and efficient source for many common anchors.

### 3.2 Raw filing XBRL / Inline XBRL

**Advantages:**

- Can expose company-extension concepts.
- Provides the filing's presentation hierarchy.
- Provides calculation linkbases with filer-provided summation relationships and weights.
- Supports reconstruction and checks against the structure used in the actual filing.

**Challenges observed:**

- Filing-package structures vary.
- Some filings do not expose a standalone `_pre.xml` in the expected location.
- Presentation information may require extraction from other package files.
- Context, dimensions, periods, units, and accession alignment require careful filtering.
- Calculation arcs must be scoped to the statement role being reconstructed; flattening arcs from unrelated roles can double-count components.

**Current conclusion:** Filing-level XBRL is the strongest path investigated so far for as-filed statement reconstruction, but harvest coverage and exception handling remain material work items.

---

## 4. Key findings and decisions

### 4.1 Accession alignment matters

Facts and presentation data must refer to the same filing accession. Otherwise, an amended filing or a different filing's presentation may be combined with the selected facts. The harvesting pipeline has been developed to align presentation data with the accession associated with the harvested filing facts.

**Ongoing check:** Keep accession IDs visible in diagnostic outputs and verify alignment when investigating exceptions.

### 4.2 Calculation arcs must be role-scoped

An early reconstruction approach flattened calculation arcs across roles. This could count components from unrelated statement presentations and create artificial subtotal mismatches, including exact 2x failures.

**Decision:** Restrict calculation arcs to the statement role being rendered and checked.

### 4.3 Company extensions are a key reason to inspect the filing

MO FY2025 demonstrated that an important operating-expense concept, `mo:MarketingAdministrationandResearchCosts`, was a company extension unavailable from SEC CompanyFacts. Filing-level facts and presentation structure are therefore necessary to reconstruct some reported statements faithfully.

### 4.4 Reusable mapping policy

**Decision so far:** Do not add company-specific mappings to `northstar/data/transforms/sec_xbrl_key.py` merely to make an individual issuer pass.

- Keep reusable, cross-company mappings in the canonical key only when supported by evidence across companies and/or statement roles.
- Handle issuer-specific extension concepts through the filing-level statement reconstruction process.
- Preserve the original concept, label, role, accession, and calculation evidence so that normalization does not erase provenance.

### 4.5 Parent net income and NCI

`ProfitLoss` is not a safe direct fallback for parent-attributable net income because it may include NCI.

**Decision:** The direct `net_income` mapping uses `NetIncomeLoss`. Parent net income may be derived in research as `ProfitLoss - total NCI`, but derived values must be explicitly labeled and must not be treated as independent proof of a reported parent-net-income fact.

### 4.6 Industry-sensitive revenue concepts

A single global preference order can select a technically available but economically inappropriate revenue concept.

Examples observed:

- CPT: `OperatingLeaseLeaseIncome` is needed for property revenue.
- LNT: `Revenues` is preferred over `RegulatedAndUnregulatedOperatingRevenue`.
- NEE: `RegulatedAndUnregulatedOperatingRevenue` is needed when the current `Revenues` fact is unavailable.

**Current approach:** Prefer broad `Revenues` by default, with evidence-backed REIT and utility handling. Continue testing overrides against multiple issuers before treating them as canonical rules.

### 4.7 Bridge concepts can explain apparent residuals

Research has added evidence-backed bridge concepts, including equity-method earnings and discontinued operations, to explain some pretax-to-net-income residuals. Continue distinguishing a genuine accounting bridge from a coincidental arithmetic match.

---

## 5. Sample history

Keep prior runs here for comparison. Do not delete older outcomes when a larger or improved run becomes the current headline.

### 5.1 Earlier 100-company sample

An earlier filing-level run reported:

| Classification | Filings |
|---|---:|
| `RECONCILES` | 68 |
| `PARTIAL` | 21 |
| `FAIL` | 6 |
| `NO_PRESENTATION` | 5 |
| **Total** | **100** |

At that stage, the six reported failures were AMZN, AEP, AON, BAC, COF, and CVNA. The no-presentation list at that stage was AMP, BLK, BX, BRO, and BLDR. These are historical results, not the current exception list: accession alignment and harvesting logic subsequently changed, and the sample was expanded.

A separate 100-company reconstruction milestone recorded 58 reconciled, 18 partial, 6 failed, and 18 without presentation. Treat these figures as a distinct run/method milestone; do not merge the two 100-company result tables unless their run artifacts establish that they are directly comparable.

### 5.2 Historical 250-company sample — 2026-10-08

The current headline is the six-category result table in Section 1. The sample's documented exception lists are:

**Eleven `FAIL` tickers**

`AMZN, AEP, AON, BAC, COF, CVNA, CSX, FANG, FDX, HAL, HST`

**Thirteen `NO_PRESENTATION` tickers**

`BLK, BX, BRO, BLDR, CHD, CPRT, DVN, D, DPZ, EXPD, GRMN, HCA, IBKR`

The next investigation should establish whether each missing presentation reflects:

- No standalone `_pre.xml`
- Presentation data embedded in another filing-package artifact
- ZIP/XSD or other filing-package extraction requirements
- A harvester limitation or an incorrect file-selection assumption

The ticker lists and summary counts should be reconciled to the exact run log before any future result is marked final.

---

## 6. Tooling and artifacts

The research has included the following tools and test assets. This list is a working inventory, not a guarantee that every file is current or production-ready.

### CompanyFacts and analysis tools

- `Dev_tools/xbrl/harvest_tags.py`
- `Dev_tools/xbrl/build_xbrl_glossary.py`
- `Dev_tools/xbrl/scale_is_waterfall.py`
- `Dev_tools/xbrl/diagnose_scaled_is.py`
- `Dev_tools/xbrl/diagnose_top_half.py`
- `Dev_tools/xbrl/diagnose_top_half_formulas.py`
- `Dev_tools/xbrl/validate_top_half_archetypes.py`

### Filing-level reconstruction tools

- `Dev_tools/xbrl/harvest_filing_facts.py`
- `Dev_tools/xbrl/harvest_presentations.py`
- `Dev_tools/xbrl/reconstruct_income_statement_from_filing.py`
- `Dev_tools/xbrl/batch_reconstruct_is.py`
- `Dev_tools/xbrl/diagnose_batch_exceptions.py`
- `Dev_tools/xbrl/classify_is_coverage.py`
- `Dev_tools/xbrl/validate_mo_extension_math.py`
- `Dev_tools/xbrl/diagnose_top_half_residuals.py`

### Mapping and tests

- `northstar/data/transforms/sec_xbrl_key.py`
- `northstar/data/transforms/sec_xbrl.py`
- `tests/test_sec_xbrl_key.py`
- `tests/test_sec_xbrl.py`
- `tests/test_parent_net_income.py`
- `tests/test_top_half_archetypes.py`
- `tests/test_batch_reconstruct_is.py`

Other supporting files include ticker samples, runbooks, glossary outputs, diagnostic exports, and run logs. Record the exact command, commit, sample, and output path for each important new run.

---

## 7. Open issues and prioritized next steps

### Priority 1 — Explain the 11 `FAIL` cases

**Status as of 2026-11-12: Initial diagnostic review completed.** All 15 failed subtotal checks across the 11 tickers have been examined. The review identifies observed discrepancies and likely patterns; it does not claim that every underlying cause has been proven.

| Ticker | Failed checks | Observed calculated-minus-reported differences |
|---|---:|---|
| AMZN | 1 | -$13M |
| AEP | 1 | +$3,580M |
| AON | 2 | -$50M; +$50M |
| BAC | 1 | -$25M |
| COF | 1 | +$16M |
| CVNA | 1 | +$15M |
| CSX | 3 | +$8M; -$31M; +$31M |
| FANG | 1 | +$48M |
| FDX | 1 | +$31M |
| HAL | 2 | -$29M; +$29M |
| HST | 1 | +$818M |
| **Total** | **15** | **11 affected filings** |

Differences are in USD millions. They are the observed deltas from the available detailed outputs; they are not all established root causes.

**Diagnostic observations**

- **HST — calculation-network selection defect identified.** The presentation role had no matching calculation role. The diagnostic therefore merged calculation relationships across roles. The resulting pretax calculation added domestic and foreign pretax components to the consolidated pretax amount, producing an $818M overstatement. This demonstrates that merging unrelated calculation networks is unsafe. A general fix should reject or explicitly handle an unmatched role rather than silently combine networks.
- **CSX and HAL — linked pretax/net-income discrepancies.** CSX has opposite-signed $31M pretax and net-income differences; HAL has opposite-signed $29M differences. These patterns suggest that a pretax discrepancy carries through to net income, but the precise causes remain unresolved.
- **AON — linked $50M discrepancies.** The two failed checks have equal and opposite differences around profit and parent net income. The relationship to NCI warrants care; the exact root cause has not been established.
- **FANG, FDX, and COF — expense subtotal differences.** The observed differences are $48M, $31M, and $16M, respectively. Do not classify these as rounding without checking the underlying facts, precision, and calculation relationships.
- **AMZN, BAC, and CVNA — smaller observed differences.** The differences are $13M, $25M, and $15M, respectively. Their small relative size does not establish that they are harmless rounding differences.
- **AEP — individual-runner anomaly.** The detailed runner calculated twice the reported basic income available to common stockholders. The filing facts show ProfitLoss of $3,696M less NCI of $116M, equaling the reported $3,580M. The detailed runner's $7,160M result is therefore not a valid reconciliation. The precise implementation cause remains unresolved.

**Skipped checks are not failed checks.** The five-company diagnostic also found missing component facts for FANG revenue, HAL cost of goods and services sold, and HST cost of goods and services sold. These checks could not be evaluated. The original batch summary recorded eight skipped checks among the 11 `FAIL` filings and 82 skipped checks among `PARTIAL` filings.

**Methodology qualifications**

- The batch reconstruction uses a $2M absolute tolerance.
- The five-company diagnostic reproduced the batch reconstruction logic using local cached artifacts and no network access.
- The six earlier detailed reconstructions used a separate individual runner. Their outputs are useful diagnostic evidence but should not be treated as proof that both runners implement identical selection and calculation logic.
- No issuer-specific mapping exceptions have been approved from this review.
- The HST result identifies a general calculation-role fallback defect worth addressing before a future benchmark rerun.

**Disposition:** The initial failure-review objective is complete. Do not expand the exception investigation or rerun the 250-company sample merely to pursue the remaining small differences. Preserve the observed discrepancies and unresolved questions for a later, targeted methodology pass.

### Priority 2 — Improve presentation-harvest coverage


Investigate the 13 `NO_PRESENTATION` cases and classify the cause for each. Distinguish true filing-package limitations from gaps in the current harvesting implementation. Re-run the batch after a general fix and compare the before/after counts.

### Priority 3 — Determine whether `PARTIAL` statements are usable

For the 54 partial cases in the November 14 result, identify which checks were skipped and why. Prioritize whether the missing check affects major valuation metrics (revenue, operating income, pretax income, tax, net income) or only ancillary detail. Report completeness separately from arithmetic reconciliation.

### Priority 4 — Re-run and freeze a reproducible IS benchmark

**Status as of 2026-11-14: Reconstruction rerun completed after structural presentation-role classification.** The 250-company result is now recorded in Section 1 and the research log. This run reused existing local presentation and filing-fact datasets and the mounted TV-box cache; it was not a fresh SEC data harvest.

For the next benchmark intended to measure broader harvest or pipeline coverage:

- Use a documented, versioned ticker sample.
- Record the commit hash and run command.
- Preserve raw run logs and per-company outcomes.
- Compare category counts and root causes with the November 13 and November 14 results.
- Keep a clear denominator for every reported success rate.
- Distinguish reconstruction-only reruns from fresh filing/presentation/fact harvesting.

### Priority 5 — Expand statement coverage only after IS findings are stable

Balance sheet and cash flow statement reconstruction remain unproven by the income statement results in this document. Once the IS pipeline has a reproducible benchmark and understood exceptions, design separate BS and CFS tests rather than assuming the same logic generalizes unchanged.

### Priority 6 — Define the future source policy

Before production integration, specify the responsibilities of each source and the precedence rules for conflicts, periods, restatements, derived values, and missing concepts.

A plausible architecture to continue evaluating is:

- **StockAnalysis:** practical normalized rolling statements
- **SEC CompanyFacts:** standardized facts, validation/fallback, and common anchors
- **SEC filing-level XBRL:** as-filed statement reconstruction, company extensions, and filing-specific provenance

This remains a research hypothesis, not a final production decision.

---

## 8. Current decision log

| Date | Decision / conclusion | Status |
|---|---|---|
| 2026-10-08 | Keep SEC XBRL in research; do not integrate into Canneberge/NorthStar production yet | Active |
| 2026-10-08 | Scope calculation arcs to the statement role being reconstructed | Implemented; retain regression coverage |
| 2026-10-08 | Avoid issuer-specific hard-coded mappings in the canonical key without cross-company evidence | Active |
| 2026-10-08 | Label derived parent net income explicitly; do not treat it as a directly reported fact | Active |
| 2026-10-08 | Investigate failure causes and presentation-harvest gaps before expanding to BS/CFS | Next |
| 2026-11-12 | If no calculation network matches the selected presentation role, use an empty calculation map; never merge unrelated networks | Implemented in both runners |
| 2026-11-14 | Use structural presentation evidence to classify income-statement roles before relying on role-name heuristics | Implemented; benchmark rerun completed |

Update this table only when a decision changes or a new durable decision is made.

---

## 9. Research log — append one entry per meaningful milestone

Use the following template for future updates. Keep entries concise and link to detailed run logs or diagnostics where possible.

### 2026-11-12 — Diagnostic review of the 250-company IS failures

**Question:** What explains the 15 failed subtotal checks across the 11 `FAIL` filings in the 2026-10-08 benchmark?

**Method:** Reviewed existing individual reconstruction outputs for AMZN, AEP, AON, BAC, COF, and CVNA. For CSX, FANG, FDX, HAL, and HST, used a standard-library-only, read-only diagnostic reproducing the relevant batch reconstruction logic against the existing filing-fact CSVs, presentation rows, and cached calculation linkbases. No network access, package installation, or source-code changes were required.

**Result:** Examined all 15 failed checks. The five-company diagnostic reproduced the batch summary counts: CSX 3 failures, FANG 1, FDX 1, HAL 2, and HST 1. It also identified skipped checks caused by missing component facts in FANG, HAL, and HST. HST had no matching calculation role and was evaluated using relationships merged across roles, producing an $818M pretax overstatement. CSX and HAL showed equal-and-opposite pretax and net-income differences. Other observed differences ranged from $8M to $50M, except for the AEP individual-runner anomaly of $3,580M.

**Interpretation:** The review establishes the observed exception patterns, not the root cause of every discrepancy. The HST result demonstrates that an unmatched calculation role must not silently trigger cross-network merging. The AEP detailed-runner result is inconsistent with the filing facts: $3,696M ProfitLoss less $116M NCI equals $3,580M basic common income. Small differences should not automatically be attributed to rounding. The six individual-runner outputs and five batch-logic diagnostics are not assumed to be methodologically identical.

**Decision:** Mark the initial 11-filing diagnostic review complete. Retain all 15 exceptions in the research record. Do not introduce issuer-specific mappings or rerun the 250-company benchmark until a general methodology change is justified.

**Next action at the time:** Address calculation-role mismatch handling as a general methodology issue, then design a targeted regression test for HST. This work is documented in the subsequent November 12 entry. Keep the remaining discrepancies classified as unresolved until supported by filing-level evidence.


### 2026-11-12 — Calculation-role mismatch correction and HST regression

**Question:** Does an unmatched presentation/calculation role cause calculation arcs from unrelated networks to be merged, and can this be prevented consistently in both reconstruction runners?

**Method:** Updated `build_calc_map()` in `reconstruct_income_statement_from_filing.py` and `batch_reconstruct_is.py` to return an empty map when no calculation role matches, and to include only arcs belonging to the selected role. Updated both call sites to handle an unmatched role explicitly. Tested the extracted role-selection and map-building functions with exact-match, unmatched-role, and `None`-role cases. Inspected HST filing `000107075026000054`, its presentation rows, and cached calculation linkbase.

**Result:** Both implementations passed the focused regression checks. HST's batch-selected presentation role was `CONSOLIDATEDSTATEMENTSOFOPERATIONSHostHotelsResortsLPandSubsidiaries` (34 presentation rows), while the calculation linkbase had no exact matching role. The linkbase contained a different `CONSOLIDATEDSTATEMENTSOFOPERATIONS` network. The selected HST income-statement presentation rows had no `totalLabel` fallback groups. Both source files passed Python AST syntax checks, and `git diff --check` was clean.

**Interpretation:** The prior HST calculation could merge unrelated networks when role selection returned `None`, producing the observed $1,636M pretax calculation against the reported $818M. The correction prevents that cross-network merge. It does not establish that the underlying subtotal reconciles: when no matching calculation network or presentation fallback exists, the calculation check is unavailable. This is not a `RECONCILES` result. No 250-company benchmark rerun was performed.

**Decision:** Treat calculation-role scoping as implemented in both runners. An unmatched role must result in no calculation-linkbase checks, not an all-network merge. Preserve the original benchmark and diagnostic results as historical evidence until a justified, reproducible benchmark rerun is undertaken.

**Next action:** Continue investigating the remaining filing-level discrepancies and presentation coverage. Do not interpret unavailable calculation checks as successful reconciliations.

### 2026-11-14 — Structural presentation-role classifier and 250-company rerun

**Question:** Did the structural presentation-role classifier improve income-statement role selection across the existing 250-company sample without introducing company-level regressions?

**Method:** After commit `d4c4864` (`Add structural XBRL statement classification`), reran `Dev_tools/xbrl/batch_reconstruct_is.py` against `Dev_tools/xbrl/tickers_250_usable.txt` with `--limit 250`. The run used the existing local presentation and filing-fact datasets and the mounted TV-box cache. It was a reconstruction rerun, not a fresh SEC filing or data harvest. The November 13 post-fix company-level summary was used as the comparison baseline.

**Result:** The November 14 sample contained 169 `RECONCILES`, 54 `PARTIAL`, 9 `FAIL`, 13 `NO_PRESENTATION`, 1 `NO_FACTS`, and 4 `NO_TOTALS` (250 total). Relative to the November 13 baseline (169, 53, 9, 13, 1, and 5, respectively), 249 companies were unchanged. EVRG changed from `NO_TOTALS` to `PARTIAL`: 12 totals checked, 11 `OK`, and 1 `SKIP`. The remaining skip was associated with an extension concept absent from the filing instance. The fully reconciling count remained 169.

**Interpretation:** The classifier changed statement-role selection sufficiently to enable additional EVRG checks. The comparison found no status changes among the other 249 companies. The result does not establish broader fresh-harvest coverage, a higher `RECONCILES` count, or valuation readiness. Among the 236 companies with facts and presentations available for subtotal evaluation, 223 were classified `RECONCILES` or `PARTIAL` (94.5%); the remaining 13 cases (9 `FAIL` and 4 `NO_TOTALS`) are excluded from that numerator.

**Decision:** Record the November 14 reconstruction result as the current 250-company status while preserving the October 8 benchmark and November 12 diagnostic results as historical evidence. Do not describe this run as a fresh SEC data harvest.

**Next action:** Investigate the remaining `NO_PRESENTATION`, `PARTIAL`, and `FAIL` cases with targeted tests. Keep reconstruction-only reruns distinct from fresh-harvest benchmarks.

### YYYY-MM-DD — Short experiment / milestone title

**Question:** What uncertainty was this experiment intended to resolve?

**Method:** Sample, script/version, filing selection, and relevant configuration.

**Result:** Counts, denominator, key observations, and links/paths to artifacts.

**Interpretation:** What the evidence supports—and what it does not establish.

**Decision:** What changes in the research plan, if anything?

**Next action:** The next test or unresolved question.

---

## 10. Change history

- **2026-10-08:** Consolidated duplicate 250-company result sections; established a single current-status summary; retained prior 100-company results as historical context; clarified the 94.9% denominator and distinction between `RECONCILES`, `PARTIAL`, and valuation readiness; organized open issues, decisions, and a repeatable research-log template.
- **2026-11-12:** Recorded the diagnostic review of all 15 failed subtotal checks across 11 filings; documented the HST calculation-role fallback defect, linked discrepancy patterns, missing-component skips, and remaining uncertainties. Preserved the original 2026-10-08 benchmark results.
- **2026-11-12:** Corrected calculation-role mismatch handling in both income-statement reconstruction runners; added focused role-scope regression checks and documented the HST evidence. No benchmark rerun was performed.
- **2026-11-14:** Recorded the structural presentation-role classifier and the 250-company reconstruction rerun. Updated current benchmark counts and denominator while retaining the October 8 results as historical evidence. The rerun reused existing datasets and cache; it was not a fresh SEC data harvest.
