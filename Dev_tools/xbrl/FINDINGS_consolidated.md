# SEC XBRL Research Findings

> **Document type:** Living research log and interim findings record
> **Project:** NorthStar — SEC XBRL research
> **Status:** Research only; not approved as a production NorthStar data source
> **Latest recorded milestone:** Five-company income-statement production-output validation
> **Last updated:** 2026-11-15
> **Scope currently tested:** Income statements (IS) only

This document records what has been tested, what the evidence supports, what remains uncertain, and how the research direction has changed. Add dated entries as new experiments finish. Preserve older results as history rather than overwriting them when a new sample or method supersedes it.

---

## 1. Executive status

### Current conclusion

**Filing-level SEC XBRL is a promising candidate for reconstructing as-filed income statements, but it is not yet production-ready.**

On 2026-11-15, the presentation harvester recovered 12 previously unavailable income-statement presentation networks from embedded filing XSDs. Calculation arcs were extracted from those same XSDs and integrated into batch reconstruction. A subsequent role-selection improvement prioritized presentation roles with matching calculation networks and ranked matching candidates by calculation-arc count, then presentation-arc count. The latest 250-company reconstruction produced 179 `RECONCILES`, 60 `PARTIAL`, 9 `FAIL`, 0 `NO_TOTALS`, 1 `NO_PRESENTATION`, and 1 `NO_FACTS`.

A subsequent five-company production-output test generated complete income-statement hierarchies with reported values for MMM, AAPL, AMD, KO, and AIG. All five outputs had no missing current-period values, and all 32 detected subtotal checks passed (32 OK, 0 FAIL, 0 SKIP, 0 NO_CALC). This establishes that the detailed runner can generate substantive statement output across several different statement structures. It is an initial five-company sample, not evidence that all 179 `RECONCILES` companies will produce equally complete or comparable statements. Manual line-by-line comparison against the filed 10-K statements remains outstanding.

Among the 248 filings with facts and presentation inputs available for subtotal evaluation, 239 were classified as `RECONCILES` or `PARTIAL` (179 + 60), or **96.4%**. The remaining 9 cases are `FAIL`. `PARTIAL` does not mean fully reconciled or valuation-ready.

The comparison against the immediately preceding November 15 reconstruction baseline found exactly five status changes: AEP, CEG, ESS, EVRG, and HST moved from `NO_TOTALS` to `PARTIAL`, `RECONCILES`, `RECONCILES`, `PARTIAL`, and `PARTIAL`, respectively. The other 245 companies were unchanged. Filing accessions and period ends were unchanged, and all nine existing `FAIL` cases remained unchanged.

The November 15 reconstruction reused the existing 250-company presentation rows and filing-fact data, plus the previously harvested embedded-XSD calculation rows. The other companies continued through the standalone `_cal.xml` calculation-linkbase path. The reconstruction also avoids an SEC filing-index lookup when the expected calculation file is already present in the local cache. This was a reconstruction-only regression, not a fresh 250-company filing-fact or presentation harvest.

### Latest batch at a glance

| Result classification | Filings | Meaning |
|---|---:|---|
| `RECONCILES` | 179 | All detected subtotal checks reconciled to the filing's calculation linkbase |
| `PARTIAL` | 60 | No detected arithmetic failures, but one or more checks were skipped because a component fact or usable calculation arc was missing |
| `FAIL` | 9 | At least one identified subtotal disagreed with the filing's calculation linkbase |
| `NO_TOTALS` | 0 | Facts and presentation were present, but no subtotal checks were identified |
| `NO_PRESENTATION` | 1 | Facts were available, but the current process did not harvest a usable income-statement presentation |
| `NO_FACTS` | 1 | Filing-fact harvesting failed or did not yield usable annual filing facts |
| **Total sample** | **250** | All sample members accounted for |

**Calculation notes**

- Group with facts/presentation available for subtotal evaluation: `250 - 1 NO_PRESENTATION - 1 NO_FACTS = 248`.
- `RECONCILES` or `PARTIAL`: `179 + 60 = 239`, or `239 / 248 = 96.4%`.
- `FAIL` rate within that group: `9 / 248 = 3.6%`.
- `NO_TOTALS`: `0 / 248 = 0.0%`.
- The immediately preceding November 15, pre-role-selection-improvement baseline was 177 `RECONCILES`, 57 `PARTIAL`, 9 `FAIL`, 5 `NO_TOTALS`, 1 `NO_PRESENTATION`, and 1 `NO_FACTS`.
- The earlier November 15, pre-calculation-integration baseline was 169 `RECONCILES`, 53 `PARTIAL`, 9 `FAIL`, 17 `NO_TOTALS`, 1 `NO_PRESENTATION`, and 1 `NO_FACTS`.
- These classifications measure pipeline/reconciliation outcomes, not full accounting correctness, completeness of every line item, or suitability for valuation.

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

**Status as of 2026-11-15:** The embedded-XSD presentation recovery work resolved 12 of the 13 previously identified `NO_PRESENTATION` cases. HONA remains the sole `NO_PRESENTATION` case; its harvest status was `NO_10K`, rather than an embedded-XSD parsing error.

**Next action:** Determine whether HONA should remain in the usable sample or be excluded under a documented filing-selection rule. Do not treat it as an unresolved embedded-XSD extraction defect.

### Priority 3 — Determine whether `PARTIAL` statements are usable

**Status as of 2026-11-14: Initial classification of the then-current 54 `PARTIAL` cases completed.** The diagnostic reproduced the skipped-check classification from the local filing facts, presentation data, and calculation linkbases. All 54 cases had the required local inputs; this was an offline diagnostic, not a new SEC harvest. The current November 15 benchmark contains 60 `PARTIAL` cases; the six additional cases have not yet been covered by that earlier 54-case diagnostic.

Across the 54 filings, the diagnostic identified 80 skipped subtotal checks:

| Skip classification | Checks | Interpretation |
|---|---:|---|
| Missing component; remaining components reconcile | 21 | Candidate redundant, inapplicable, or differently tagged component; not automatically safe to ignore |
| Missing component; remaining components do not reconcile | 55 | Unresolved difference; may be material and requires concept-level investigation |
| Reported subtotal fact missing | 4 | Subtotal itself unavailable for evaluation |
| **Total** | **80** | |

The most frequent missing components were `CostOfGoodsAndServicesSold` (23 checks) and `RevenueFromContractWithCustomerExcludingAssessedTax` (10 checks). Other examined clusters included `OtherCostAndExpenseOperating` (4) and `InterestExpenseNonoperating` (3).

Key observations:

- Missing COGS and customer-contract revenue tags are often issuer- or industry-specific presentation and tagging issues. The examined revenue cases included insurance, financial services, and energy issuers with materially different revenue structures. CVS, for example, reported the combined concept `PremiumsEarnedNetAndRevenueFromContractWithCustomerExcludingAssessedTax` rather than the exact expected customer-contract revenue concept.
- No universal replacement concept was established for either COGS or customer-contract revenue. Concepts such as `CostOfRevenue` and `NonInvestmentRevenue` may be relevant in individual filings, but their presence alone does not establish equivalence to a missing calculation component.
- Some skipped checks reconcile without the missing component, as in AFL's `OperatingExpenses` check. This is evidence for possible redundant or inapplicable components, not proof that the component can be globally excluded.
- Other cases leave large residuals, including APO, EXC, and F for operating expenses. These cannot be treated as harmless skips.
- Negative or otherwise implausible residuals in some interest-expense checks demonstrate that residual arithmetic alone cannot establish a substitute concept or validate a calculation relationship.

**Interpretation:** `PARTIAL` is heterogeneous. It includes potentially benign missing components, unresolved material differences, and unavailable subtotal facts. The 21 checks that reconcile without the missing component are not equivalent to 21 proven harmless omissions. Likewise, the 55 unreconciled checks do not prove economic incompleteness: alternate concepts and issuer-specific tagging may explain some cases.

The diagnostic does not yet establish whether every `PARTIAL` statement contains complete and reliable revenue, operating income, pretax income, tax, and net income data. Therefore, `PARTIAL` must remain distinct from `RECONCILES` and must not be described as valuation-ready.

**Decision:** Treat the initial classification objective as complete. Do not apply blanket aliases or globally suppress missing-component checks. Any future mapping should be supported by filing-specific presentation, calculation, and fact evidence, with material valuation metrics evaluated separately.

**Next action:** Resume investigation using the current 60-company `PARTIAL` population. First generate and inspect detailed statement outputs for a representative subset, distinguishing complete-looking statements with skipped arithmetic checks from genuinely incomplete or ambiguous statements. Trace missing concepts through issuer labels, presentation hierarchy, calculation relationships, and reported facts. Add glossary aliases or canonical-key mappings only when filing evidence supports equivalence; retain unresolved cases and avoid blanket substitutions. Expand the diagnostic to all 60 after the initial output review establishes useful categories.

### Priority 4 — Re-run and freeze a reproducible IS benchmark

**Status as of 2026-11-15: Embedded-XSD recovery and calculation-aware role selection validated across the 250-company sample.** The current result is recorded in Section 1 and the research log. The latest run reused existing presentation, filing-fact, and embedded calculation data, with the standalone `_cal.xml` fallback for other filings. It was a reconstruction-only regression, not a fresh 250-company filing-fact or presentation harvest.

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
| 2026-11-15 | Extract presentation and calculation relationships from embedded filing XSDs when standalone linkbase files are absent | Implemented; 12-company recovery and 250-company regression validated |
| 2026-11-15 | Prefer presentation roles with matching calculation networks; rank candidates by calculation-arc count, then presentation-arc count | Implemented; five-company targeted test and 250-company regression validated |
| 2026-11-15 | Treat successful detailed statement generation as a separate validation layer from batch subtotal status; evaluate `PARTIAL` outputs before rejecting them | Five-company output test passed; broader population review pending |

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

### 2026-11-14 — Classification of the 54 PARTIAL income-statement cases

**Question:** Are the skipped checks in the 54 `PARTIAL` cases likely to represent harmless omissions, issuer-specific tagging differences, or unresolved subtotal differences?

**Method:** Used the November 14 batch summary and existing local filing-fact, presentation, and calculation-linkbase datasets. Reproduced the relevant calculation checks and classified 80 skipped subtotal checks across all 54 `PARTIAL` filings. Follow-up diagnostics examined the most frequent missing components and selected issuer cases. No fresh SEC harvest or benchmark rerun was performed.

**Result:** Of the 80 skipped checks, 21 had remaining components that reconciled to the reported subtotal, 55 had remaining components that did not reconcile, and 4 lacked the reported subtotal fact. The most frequent missing components were `CostOfGoodsAndServicesSold` (23 checks) and `RevenueFromContractWithCustomerExcludingAssessedTax` (10). Additional targeted review examined `OtherCostAndExpenseOperating` (4) and `InterestExpenseNonoperating` (3).

The COGS review found no universal alternate concept across the examined cases. The revenue review found industry-specific reporting patterns, including insurance and premium concepts, interest-income concepts, and energy-related sales concepts. CVS reported a combined premium/customer-contract revenue concept. Operating-expense examples ranged from an exact reconciliation without the missing component (AFL) to material residuals (APO, EXC, and F).

**Interpretation:** `PARTIAL` is not a homogeneous quality category. A missing component can be redundant or inapplicable in one filing and material in another. A nonzero or negative residual does not by itself establish the correct replacement concept. The diagnostic classifies skipped checks; it does not prove metric-level completeness or valuation readiness.

**Decision:** Close the initial classification objective without applying blanket aliases or changing reconstruction logic. Preserve `PARTIAL` as a distinct status. Require filing-specific evidence before accepting alternate concepts or suppressing checks.

**Next action:** Defer exhaustive issuer-by-issuer review. Revisit individual cases when testing a specific mapping or validating metric-level completeness.

### 2026-11-15 — Embedded-XSD calculation recovery and 250-company regression

**Question:** Can calculation networks embedded in filing XSDs be harvested and used to reconstruct income statements for companies whose filings do not expose a standalone `_cal.xml`, without changing results for the rest of the sample?

**Method:** Extended `harvest_presentations.py` to extract calculation arcs from embedded XSDs and write a separate `calculation_rows.csv`, leaving the existing presentation-row schema unchanged. Extended `batch_reconstruct_is.py` to load accession-aligned embedded calculation rows and use the existing standalone `_cal.xml` retrieval path when embedded rows are unavailable. Harvested the 12 recovered companies (BLK, BX, BRO, BLDR, CHD, CPRT, D, DPZ, GRMN, HCA, IBKR, EXPD), then reran the 250-company reconstruction using the existing 250-company presentation rows and the new 12-company calculation rows.

**Result:** The 12-company embedded-XSD test harvested 16,014 presentation rows and 2,465 calculation arcs. All 12 companies selected calculation networks from their embedded XSDs. Across 71 subtotal checks, 66 reconciled, 5 were skipped because required facts were unavailable, and none failed; 8 companies fully reconciled and 4 were partial.

The full 250-company run produced 177 `RECONCILES`, 57 `PARTIAL`, 9 `FAIL`, 5 `NO_TOTALS`, 1 `NO_PRESENTATION`, and 1 `NO_FACTS`. Against the immediately preceding November 15 baseline (169, 53, 9, 17, 1, and 1, respectively), exactly 12 companies changed: BLDR, BRO, CPRT, DPZ, EXPD, GRMN, HCA, and IBKR moved from `NO_TOTALS` to `RECONCILES`; BLK, BX, CHD, and D moved from `NO_TOTALS` to `PARTIAL`. The other 238 companies were unchanged, including all nine existing `FAIL` cases. No new or missing companies, accession changes, or period-end changes were found. The five remaining `NO_TOTALS` cases are AEP, CEG, ESS, EVRG, and HST.

**Interpretation:** Embedded XSDs can supply both presentation and calculation relationships when standalone linkbase files are absent. The 250-company comparison demonstrates that the new calculation path improved the 12 recovered cases without collateral changes to the other 238 companies. The five remaining `NO_TOTALS` cases and nine existing failures remain unresolved. The result is a reconstruction regression using existing presentation and filing-fact data plus targeted embedded-XSD calculation harvesting, not a fresh full-sample SEC harvest. `PARTIAL` remains distinct from `RECONCILES` and is not evidence of valuation readiness.

**Decision:** Retain embedded-XSD extraction as a supported general harvesting path. Preserve the separate calculation CSV and existing presentation CSV schema. Keep the standalone `_cal.xml` path as fallback. Record the 250-company result as the current IS reconstruction benchmark while preserving prior runs as historical evidence.

**Next action:** The five remaining `NO_TOTALS` cases were addressed in the subsequent November 15 calculation-aware role-selection experiment recorded below. The nine existing `FAIL` cases remain unchanged; revisit them only through targeted, evidence-based methodology tests. Do not introduce issuer-specific mappings or treat skipped checks as successful reconciliations.

### 2026-11-15 — Calculation-aware presentation-role selection and 250-company regression

**Question:** Can matching calculation-network evidence improve presentation-role selection for the five remaining `NO_TOTALS` companies without changing results for the rest of the 250-company sample?

**Method:** Updated `batch_reconstruct_is.py` to load calculation arcs before selecting the presentation role. Selection remains income-statement-first, then considers comprehensive-income roles when no income-statement candidate has a matching calculation network. Among matching candidates, the selector ranks by calculation-arc count first and presentation-arc count second. If no candidate matches a calculation network, the original income-first fallback remains. Also added a cache-first check that avoids requesting the SEC filing index when the expected standalone `_cal.xml` file is already cached. Tested the five remaining cases individually, then reran the 250-company reconstruction against the existing presentation, filing-fact, and calculation datasets.

**Result:** The five-company test eliminated all five `NO_TOTALS` outcomes: AEP, EVRG, and HST became `PARTIAL`; CEG and ESS became `RECONCILES`. The full 250-company result changed from 177 `RECONCILES`, 57 `PARTIAL`, 9 `FAIL`, 5 `NO_TOTALS`, 1 `NO_PRESENTATION`, and 1 `NO_FACTS` to 179, 60, 9, 0, 1, and 1, respectively. Exactly those five companies changed status; the other 245 were unchanged. All nine `FAIL` cases remained unchanged. No accession or period-end changes were found.

**Interpretation:** Calculation-network availability and size provide useful evidence for distinguishing competing presentation roles, including subsidiary and parent-level alternatives. Ranking by calculation-arc count resolved the CEG parent-role selection that remained after the initial matching-network preference. The result supports a general role-selection improvement across this sample, not issuer-specific mapping. Among the 248 companies with facts and presentation data, 239 were `RECONCILES` or `PARTIAL` (96.4%). `PARTIAL` remains distinct from `RECONCILES` and does not establish valuation readiness. This was a reconstruction-only regression, not a fresh full-sample SEC harvest.

**Decision:** Retain calculation-aware presentation-role selection, with calculation-arc count as the primary ranking criterion and presentation-arc count as the tie-breaker. Preserve the original fallback when no matching calculation role exists. Retain the cache-first expected `_cal.xml` lookup.

**Next action:** Treat the 250-company IS reconstruction benchmark as the current result for this methodology version. Move to targeted metric-completeness work for `PARTIAL` cases or the design of separate BS/CFS tests; do not rerun the full sample without a substantive methodology or harvest change.

### 2026-11-15 — Five-company income-statement production-output validation

**Question:** Does the detailed filing-level runner produce complete, readable income-statement hierarchies with actual reported values across different company statement structures, rather than merely returning batch reconciliation statuses?

**Method:** Ran `reconstruct_income_statement_from_filing.py` for MMM, AAPL, AMD, KO, and AIG using their latest annual filing selections already represented in the 250-company benchmark. The runner used the existing local filing data and caches and generated a separate detailed CSV for each company. Reviewed the terminal-rendered hierarchies and subtotal-check summaries. No fresh 10-K harvest or line-by-line manual comparison against the filed statements was performed.

**Result:** All five detailed outputs were generated:

| Ticker | Filing accession | Period end | Subtotal checks | Result |
|---|---|---|---:|---|
| MMM | `0000066740-26-000014` | 2025-12-31 | 7/7 | All OK |
| AAPL | `0000320193-25-000079` | 2025-09-27 | 5/5 | All OK |
| AMD | `0000002488-26-000018` | 2025-12-27 | 7/7 | All OK |
| KO | `0001628280-26-010047` | 2025-12-31 | 5/5 | All OK |
| AIG | `0000005272-26-000023` | 2025-12-31 | 8/8 | All OK |

Across the five statements, 32 subtotal checks passed; there were no `FAIL`, `SKIP`, or `NO_CALC` outcomes and no missing current-period values. The outputs preserved statement hierarchy and displayed reported line items and values. The examples included materially different structures: manufacturing, technology, semiconductor costs and acquired-intangible amortization, consumer products with investment income, and insurance premiums and claims.

Detailed output files:

- `runlogs/reconstructed_IS_MMM_000006674026000014.csv`
- `runlogs/reconstructed_IS_AAPL_000032019325000079.csv`
- `runlogs/reconstructed_IS_AMD_000000248826000018.csv`
- `runlogs/reconstructed_IS_KO_000162828026010047.csv`
- `runlogs/reconstructed_IS_AIG_000000527226000023.csv`

**Interpretation:** This is positive evidence that the detailed runner can produce coherent, numerically checked income-statement output for a varied five-company sample. It supports proceeding to broader output-quality sampling. It does not establish that all 179 `RECONCILES` companies have equivalent statement completeness, that all line items have been manually matched to the 10-K face statements, or that the output is valuation-ready. A successful subtotal check validates the tested calculation relationship, not every classification or mapping decision.

**Decision:** Treat detailed statement generation as a separate validation layer from batch reconciliation status. Do not infer that `PARTIAL` outputs are unusable solely from their status. Investigate their actual hierarchies and reported facts; consider glossary aliases or canonical-key additions only when supported by filing-specific evidence and reusable cross-company patterns.

**Next action:** Begin a focused review of the current 60 `PARTIAL` cases. Generate detailed outputs for a representative subset, classify the reasons for partial status, and test whether missing concepts are recoverable through existing aliases, glossary coverage, or calculation/presentation interpretation. Preserve unresolved cases rather than forcing a mapping.

### 2026-11-16 — Advertising and marketing expense classification

**Date:** 2026-11-16

#### Classification decision

The following US-GAAP concepts are classified as operating expenses:

- `us-gaap:AdvertisingExpense`
- `us-gaap:MarketingAndAdvertisingExpense`
- `us-gaap:MarketingExpense`

The classification is based on their economic meaning, not whether a company separately presents the expense on the face of its income statement. These concepts retain separate provisional canonical identities. They are not aliases and their values must not be combined automatically.

All three use:
- `canonical_section = operating_expenses`
- `concept_role = line_item`
- `mapping_status = provisional`
- `placement_method = semantic`

#### Standardized export validation

The post-classification export covered 249 companies, 747 annual company-periods, and 710 canonical concepts, producing 530,370 rows.

Each of the three concepts has 747 company-period rows. Results:

| Concept | Reported observations | Presented on face | Not on face | No presentation evidence |
|---|---:|---:|---:|---:|
| Advertising Expense | 213 | 6 | 678 | 63 |
| Marketing and Advertising Expense | 63 | 15 | 669 | 63 |
| Marketing Expense | 33 | 21 | 663 | 63 |

These results demonstrate that presentation status and economic classification are independent. A concept can be classified as an operating expense while its reported fact is not separately presented on the income statement.

The export's overall value-status counts remained unchanged after this classification refinement:
- Reported: 31,612
- Derived: 130
- Not reported: 498,603
- Dimensional only: 25

The 130 derived observations remain gross profit calculations from reported revenue less reported cost of revenue. This classification change did not alter fact selection, reported values, or derivation logic.

### YYYY-MM-DD — Short experiment / milestone title

**Question:** What uncertainty was this experiment intended to resolve?

**Method:** Sample, script/version, filing selection, and relevant configuration.

**Result:** Counts, denominator, key observations, and links/paths to artifacts.

**Interpretation:** What the evidence supports—and what it does not establish.

**Decision:** What changes in the research plan, if anything?

**Next action:** The next test or unresolved question.

---

## 10. Change history
- **2026-11-16:** Documented semantic operating-expense classification for advertising and marketing concepts, preserving separate provisional identities; recorded 249-company standardized export validation.

- **2026-10-08:** Consolidated duplicate 250-company result sections; established a single current-status summary; retained prior 100-company results as historical context; clarified the 94.9% denominator and distinction between `RECONCILES`, `PARTIAL`, and valuation readiness; organized open issues, decisions, and a repeatable research-log template.
- **2026-11-12:** Recorded the diagnostic review of all 15 failed subtotal checks across 11 filings; documented the HST calculation-role fallback defect, linked discrepancy patterns, missing-component skips, and remaining uncertainties. Preserved the original 2026-10-08 benchmark results.
- **2026-11-12:** Corrected calculation-role mismatch handling in both income-statement reconstruction runners; added focused role-scope regression checks and documented the HST evidence. No benchmark rerun was performed.
- **2026-11-14:** Recorded the structural presentation-role classifier and the 250-company reconstruction rerun. Updated current benchmark counts and denominator while retaining the October 8 results as historical evidence. The rerun reused existing datasets and cache; it was not a fresh SEC data harvest.
- **2026-11-14:** Classified 80 skipped subtotal checks across all 54 `PARTIAL` income-statement cases. Documented missing-component patterns, issuer-specific tagging differences, and the distinction between potentially benign omissions and unresolved residuals. Closed the initial classification objective without introducing blanket concept aliases or treating `PARTIAL` as valuation-ready.
- **2026-11-15:** Recorded embedded-XSD presentation and calculation recovery, the 12-company calculation validation, and the initial 250-company regression. Preserved the 177 `RECONCILES`, 57 `PARTIAL`, 9 `FAIL`, 5 `NO_TOTALS`, 1 `NO_PRESENTATION`, and 1 `NO_FACTS` result as the intermediate benchmark.
- **2026-11-15:** Recorded calculation-aware presentation-role selection and its five-company targeted test and 250-company regression. Updated the current benchmark to 179 `RECONCILES`, 60 `PARTIAL`, 9 `FAIL`, 0 `NO_TOTALS`, 1 `NO_PRESENTATION`, and 1 `NO_FACTS`; documented that exactly five companies changed and the other 245 were unchanged.
- **2026-11-15:** Recorded detailed income-statement output validation for MMM, AAPL, AMD, KO, and AIG. All five statement files were generated, with 32/32 subtotal checks passing and no missing current-period values. Distinguished this initial output-quality test from both the 250-company status benchmark and pending manual 10-K comparison; prioritized investigation of the current 60 `PARTIAL` cases.
