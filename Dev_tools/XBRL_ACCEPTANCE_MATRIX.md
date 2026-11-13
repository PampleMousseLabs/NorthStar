# NorthStar — SEC XBRL Acceptance Matrix

**Document type:** Research acceptance criteria and source-selection framework  
**Project:** NorthStar / PampleMousseLabs  
**Assessment date:** November 13, 2026  
**Status:** Proposed acceptance framework — thresholds require approval  
**Scope:** Filing-level SEC XBRL reconstruction, normalized financial mapping, and source suitability  
**Current recommendation:** Continue XBRL research; do not yet approve XBRL as the exclusive production source.

---

## 1. Executive summary

### Objective

Determine whether SEC filing-level XBRL can reliably supply NorthStar's normalized financial statement data, either as:

1. The primary and exclusive financial data source;
2. The primary source with an alternative-source fallback; or
3. A supplemental source, with another provider supplying the primary data.

The acceptance decision must evaluate two distinct capabilities:

- **Filing reconstruction:** Can the system accurately recover what the issuer reported in its filing?
- **Canonical mapping:** Can the system consistently translate the reported concepts into NorthStar's standardized financial model without changing their accounting meaning?

Passing one does not establish the other.

### Current evidence

The latest documented income-statement benchmark covers 250 companies:

| Classification | Companies | Share of total |
|---|---:|---:|
| RECONCILES | 169 | 67.6% |
| PARTIAL | 55 | 22.0% |
| FAIL | 11 | 4.4% |
| NO_PRESENTATION | 13 | 5.2% |
| NO_FACTS | 1 | 0.4% |
| NO_TOTALS | 1 | 0.4% |
| **Total** | **250** | **100.0%** |

Of the 250 companies, 236 had facts and presentation inputs sufficiently available for subtotal evaluation.

- 169 / 236 = **71.6%** fully reconciled under the benchmark's detected checks.
- 55 / 236 = **23.3%** partial.
- 11 / 236 = **4.7%** failed.
- 1 / 236 = **0.4%** had no identified subtotal checks.
- 224 / 236 = **94.9%** did not receive a FAIL classification.

The 94.9% figure is a no-FAIL rate. It is **not** a full-reconciliation rate, a mapping-accuracy rate, or a valuation-readiness rate.

The diagnostic review identified 15 failed subtotal checks across 11 companies. Some discrepancies remain unexplained; not every failure has an established root cause.

### November 12 calculation-role correction

Both `reconstruct_income_statement_from_filing.py` and `batch_reconstruct_is.py` were corrected so that an unmatched calculation role produces an empty calculation map rather than merging unrelated calculation networks.

The HST regression demonstrated why this matters: the selected presentation role had no matching calculation role, while a different calculation network existed. The previous behavior could merge unrelated arcs and double-count components, producing a $1,636 million pretax result against the $818 million reported figure.

The correction was tested with focused regression checks in both runners. HST's unmatched calculation role now means calculation-linkbase checks are unavailable. It does **not** establish that the subtotal reconciles.

**The 250-company benchmark has not been rerun after this correction.** Its results remain historical baseline evidence, not post-fix performance.

### Overall assessment

| Acceptance area | Current status |
|---|---|
| Income-statement reconstruction feasibility | Demonstrated |
| Income-statement mapping accuracy | Not yet established |
| Balance-sheet reconstruction and mapping | Not yet established |
| Cash-flow reconstruction and mapping | Not yet established |
| Cross-statement consistency | Not yet established |
| Production operational suitability | Not yet established |
| Exclusive XBRL source approval | Premature |

---

## 2. Acceptance principles

These principles apply to every gate.

### 2.1 Keep the quality dimensions separate

| Dimension | Question | Appropriate evidence |
|---|---|---|
| Harvest coverage | Did we obtain usable filing data? | Filing/facts/presentation availability |
| Reconstruction accuracy | Did we recover the issuer's reported lines and relationships? | Filing-to-reconstruction comparison |
| Mapping accuracy | Did we assign the correct NorthStar financial meaning? | Concept-level accounting review |
| Arithmetic validation | Do detected relationships and totals add up? | Calculation-linkbase and independent arithmetic checks |
| Accounting correctness | Are scope, classification, sign, period, and economic meaning correct? | Filing review and accounting analysis |
| Operational reliability | Can we repeat the process consistently? | Reproducibility, monitoring, failure handling |

A high score in one dimension must not compensate for a failure in another.

### 2.2 Use explicit result classifications

Every evaluated issuer-statement-period should receive one of the following statuses:

- **PASS:** Required data and checks are available, and the relevant acceptance criteria are satisfied.
- **PARTIAL:** Some required information or validation is unavailable, but no identified material error is present.
- **FAIL:** An identified material reconstruction, mapping, or accounting error exists.
- **UNAVAILABLE:** The required filing data, presentation, facts, or validation relationships cannot be obtained.
- **NOT TESTED:** The test has not yet been performed.

Do not treat PARTIAL, UNAVAILABLE, or NOT TESTED as PASS.

In particular:
- No calculation role match is not a successful reconciliation.
- Missing component facts are not successful subtotal checks.
- Missing presentation data is not evidence that the filing contains no relevant line items.
- A mathematically correct total is not proof that the components have the correct accounting meaning.

### 2.3 Preserve provenance

Every normalized financial value should be traceable to:

- Issuer and CIK;
- Filing form and accession number;
- Filing date and fiscal period;
- Original XBRL concept QName;
- Original label and statement role;
- Context, dimensions, unit, and period type;
- Raw reported value;
- Normalized value and unit;
- Transformation or mapping rule;
- Whether the value is directly reported, derived, or sourced elsewhere;
- Source file and relevant calculation/presentation evidence.

A reviewer should be able to move from a NorthStar financial-model cell back to the exact filing fact and transformation that produced it.

---

## 3. Proposed acceptance scorecard

The following thresholds are proposed starting points for review. They are not existing NorthStar policy.

| Gate | Proposed PASS | Proposed CONDITIONAL PASS | FAIL |
|---|---|---|---|
| 1. Income statements | At least 95% of evaluable cases pass reconstruction and mapping; material mapping errors below 1% | 90–95% pass, with bounded and documented exceptions | Below 90%, or systemic material mapping errors |
| 2. Balance sheets | At least 98% of evaluable cases pass core balance and mapping tests | 95–98%, with understood exceptions | Below 95%, or material balance/classification errors |
| 3. Cash flows | At least 95% pass cash reconciliation and mapping tests | 90–95%, with understood exceptions | Below 90%, or material cash-flow classification errors |
| 4. Cross-statement consistency | At least 98% pass applicable cross-statement checks | 95–98%, with explained exceptions | Below 95%, or systemic inconsistency |
| 5. Operational/source suitability | At least 99% repeatable successful processing of eligible filings; complete provenance and controlled failures | 97–99%, with operational fallback | Below 97%, irreproducible values, or uncontrolled data corruption |

**Important interpretation:** These percentages must be measured against clearly defined eligible/evaluable populations. Coverage and availability must be reported separately. The thresholds do not authorize excluding difficult issuers to improve the score.

A separate hard-stop rule applies to all gates: an unresolved systematic material error affecting a major financial concept prevents an overall PASS even if aggregate percentages meet the target.

---

## 4. Gate 1 — Income-statement reconstruction and canonical mapping

**Objective:** Demonstrate that the system can reconstruct reported income statements and normalize their material line items consistently across issuers and industries.

### Test design

Use the existing 250-company sample as the starting population, not as proof of final acceptance.

1. Preserve the original benchmark and its run artifacts.
2. Rerun the same sample after the calculation-role correction using a versioned run.
3. Compare pre-fix and post-fix classifications and affected calculations.
4. Investigate all 11 historical FAIL issuers and all 55 PARTIAL issuers.
5. Test at least two annual periods for a representative subset, including a restated or amended filing where available.
6. Independently review the normalized mappings for a stratified sample of at least 100 issuer-periods.

The sample should cover, at minimum:

- Technology and communications;
- Consumer discretionary and staples;
- Industrials and transportation;
- Energy;
- Utilities;
- Banks and diversified financials;
- Insurance;
- REITs and real estate;
- Healthcare and pharmaceuticals;
- Other service and asset-heavy industries.

Include issuers with significant company extensions, dimensional statements, unusual line-item structures, and nonstandard labels.

### Required test cases

| Test | Required behavior |
|---|---|
| Revenue | Select the economically appropriate revenue concept; do not rely on label similarity alone |
| Operating expenses | Correctly aggregate reported expense components without duplication |
| EBIT / operating income | Preserve the issuer's distinction between operating and nonoperating items |
| Pretax income | Reconstruct the appropriate pretax subtotal and bridges |
| Income tax | Preserve tax expense/benefit sign and scope |
| Net income | Distinguish consolidated profit from parent-attributable profit |
| NCI | Do not silently treat consolidated profit as parent net income |
| EPS and shares | Match period, unit, share basis, and basic/diluted distinctions |
| Extensions | Preserve issuer-specific concepts and map only when economically justified |
| Calculation roles | Restrict arcs to the selected statement role |
| Presentation fallback | Use presentation labels/relationships only under documented fallback rules |
| Missing facts | Mark unavailable checks explicitly; never treat missing components as reconciled |
| Period/context | Prevent mixing annual, quarterly, YTD, and comparative contexts |

### Proposed metrics and thresholds

| Metric | PASS | CONDITIONAL | FAIL |
|---|---:|---:|---:|
| Evaluable filing reconstruction pass rate | ≥95% | 90–95% | <90% |
| Material canonical mapping accuracy in reviewed lines | ≥99% | 97–99% | <97% |
| Unexplained material subtotal failures | 0 systemic causes; isolated cases documented | Limited unresolved cases with fallback | Systemic or recurring unexplained errors |
| Correct parent/consolidated/NCI treatment | ≥99% of reviewed cases | 97–99% | <97% or any systemic error |
| Provenance completeness | 100% for accepted values | Minor nonmaterial omissions | Missing traceability for material values |

Mapping accuracy should be assessed at the line-item level, not inferred from the statement's total reconciliation rate.

### Evidence to retain

- Versioned benchmark outputs and run configuration;
- Filing accession and period manifest;
- Original and reconstructed statements;
- Concept/label/role mapping review sheets;
- Calculation and presentation relationship extracts;
- All PASS, PARTIAL, FAIL, and UNAVAILABLE classifications;
- Before/after comparison for the November 12 fix;
- Root-cause register for the historical 15 failed checks;
- Independent reviewer sign-off for material mappings.

### Known limitations and dependencies

The existing benchmark tests detected subtotal relationships, not every reported line item. A statement may reconcile while still containing a misclassified or omitted line item. The benchmark also includes partial cases and does not establish full mapping accuracy.

Dependencies include stable filing accession selection, context filtering, dimensional handling, presentation extraction, calculation-role selection, and a reviewed canonical mapping policy.

**Current gate status: PARTIAL — feasibility demonstrated; mapping acceptance not yet established.**

---

## 5. Gate 2 — Balance-sheet reconstruction and mapping

**Objective:** Demonstrate complete and economically correct reconstruction of assets, liabilities, and equity, with reliable balance checks and classification.

### Test design

Start with a stratified pilot of at least 100 issuers, then expand to at least 250 issuers before a broad source decision.

For the pilot:
- Use the latest annual filing and at least one prior comparative period.
- Include amended/restated filings and issuers with complex balance-sheet structures.
- Cover the same major industries listed in Gate 1.
- Include banks, insurers, utilities, REITs, industrials, and technology companies.

### Required test cases

| Area | Test |
|---|---|
| Assets | Current/noncurrent classification and total assets |
| Liabilities | Current/noncurrent classification and total liabilities |
| Equity | Parent equity, NCI, and total equity distinctions |
| Balance equation | Assets = liabilities + equity, using consistent scope |
| Cash | Match cash and restricted-cash treatment to the reported balance sheet |
| Debt | Preserve short-term, long-term, lease, and other financing distinctions |
| Working capital | Correct current assets and current liabilities |
| Dimensions | Avoid mixing consolidated and segment or other dimensional facts |
| Comparative periods | Preserve the correct date and comparative context |
| Restatements | Identify revised values and retain filing provenance |

### Proposed metrics and thresholds

| Metric | PASS | CONDITIONAL | FAIL |
|---|---:|---:|---:|
| Evaluable balance-sheet reconstruction pass rate | ≥98% | 95–98% | <95% |
| Material mapping accuracy in reviewed lines | ≥99% | 97–99% | <97% |
| Balance equation checks | ≥99% pass where applicable | 97–99% | <97% |
| Parent/NCI and classification accuracy | ≥99% | 97–99% | <97% |
| Provenance completeness | 100% for accepted values | Minor nonmaterial omissions | Material traceability gaps |

Balance equation results must be measured only where the required facts and compatible contexts are available. Report the unavailable share separately.

### Evidence to retain

- Reconstructed balance sheets by issuer and period;
- Balance equation check outputs;
- Concept mapping and classification decisions;
- Context/dimension/unit validation logs;
- Restatement comparisons;
- Exception register and source citations.

### Known limitations and dependencies

A balance equation can pass while current/noncurrent classification, debt treatment, or equity attribution is wrong. The balance check is necessary but not sufficient.

Dependencies include reliable instant-period selection, dimension filtering, units, NCI handling, and the canonical balance-sheet model.

**Current gate status: NOT TESTED to the acceptance standard.**

---

## 6. Gate 3 — Cash-flow reconstruction and mapping

**Objective:** Demonstrate that operating, investing, and financing cash flows can be reconstructed and normalized without sign, classification, or cash-definition errors.

### Test design

Use a stratified pilot of at least 100 issuers, followed by at least 250 issuers before broad approval.

Include:
- Capital-intensive and asset-light businesses;
- Banks and insurers;
- Utilities and energy;
- REITs;
- Companies with acquisitions, divestitures, and substantial stock-based compensation;
- Companies with significant foreign-currency or discontinued-operation effects.

Test annual cash flows and comparative periods. Where possible, include issuers with amended statements or material restatements.

### Required test cases

| Area | Test |
|---|---|
| Operating cash flow | Reconstruct net cash from operating activities |
| Investing cash flow | Preserve capex, acquisitions, disposals, and investment activity |
| Financing cash flow | Preserve debt issuance/repayment, equity issuance, dividends, and buybacks |
| Net change in cash | Reconcile operating, investing, financing, and applicable FX effects |
| Depreciation and amortization | Avoid confusing noncash add-backs with cash expenditures |
| Working capital | Preserve correct direction and sign |
| Acquisitions | Separate acquisition consideration from ordinary capital expenditure |
| Restricted cash | Match the issuer's reported cash and restricted-cash definition |
| Financial institutions | Validate industry-specific cash-flow presentation rather than imposing industrial-company assumptions |
| Periods | Avoid mixing annual, quarterly, and YTD cash-flow facts |

### Proposed metrics and thresholds

| Metric | PASS | CONDITIONAL | FAIL |
|---|---:|---:|---:|
| Evaluable cash-flow reconstruction pass rate | ≥95% | 90–95% | <90% |
| Material mapping accuracy | ≥99% | 97–99% | <97% |
| Cash reconciliation checks | ≥99% pass where applicable | 97–99% | <97% |
| Material sign/classification accuracy | ≥99% | 97–99% | <97% |
| Provenance completeness | 100% for accepted values | Minor nonmaterial omissions | Material traceability gaps |

### Evidence to retain

- Reconstructed cash-flow statements;
- Cash reconciliation outputs;
- Component-level sign and classification reviews;
- Cash/restricted-cash policy;
- Acquisition and capex mapping examples;
- Industry-specific exception register.

### Known limitations and dependencies

Cash-flow statement relationships are not uniformly represented by calculation linkbases. A missing calculation relationship does not mean the cash-flow statement is wrong. Independent arithmetic and filing comparison will be necessary.

**Current gate status: NOT TESTED to the acceptance standard.**

---

## 7. Gate 4 — Cross-statement consistency

**Objective:** Demonstrate that accepted income-statement, balance-sheet, and cash-flow values agree with one another in scope, period, and accounting meaning.

### Test design

Use at least 100 issuers for the initial integrated pilot. Use the same accession and fiscal-period controls across all three statements. Expand to at least 250 issuers after the pilot.

### Required checks

| Relationship | Required validation |
|---|---|
| Net income | Income statement to cash-flow starting point, with documented adjustments |
| Cash | Cash-flow ending balance to balance-sheet cash definition |
| Debt | Balance-sheet debt movements compared with financing cash flows |
| PP&E | Capital expenditures and depreciation compared with PP&E movements, allowing for acquisitions/disposals and other changes |
| Equity | Net income, dividends, buybacks, issuance, and other equity movements |
| Working capital | Balance-sheet changes compared with operating cash-flow adjustments |
| NCI | Consistent treatment of consolidated and parent-attributable amounts |
| Period alignment | Matching fiscal periods and annual/YTD definitions |

These are accounting consistency checks, not necessarily direct arithmetic equalities. Every expected bridge must identify legitimate reconciling items.

### Proposed metrics and thresholds

| Metric | PASS | CONDITIONAL | FAIL |
|---|---:|---:|---:|
| Applicable cross-statement checks passing | ≥98% | 95–98% | <95% |
| Unexplained material differences | 0 systemic issues | Limited documented exceptions | Systemic or recurring issues |
| Period/scope alignment | 100% for accepted comparisons | No material issue | Any systematic misalignment |
| Provenance | 100% of accepted links traceable | Minor nonmaterial omissions | Material untraceable relationships |

### Evidence to retain

- Integrated issuer-period financial statements;
- Cross-statement bridge calculations;
- Reconciliation exception register;
- Scope and period alignment logs;
- Explanation of acquisitions, disposals, FX, NCI, and restatement effects.

### Known limitations and dependencies

Cross-statement movements often contain legitimate noncash, acquisition, foreign-exchange, and reclassification effects. Do not label a difference as a mapping failure until those effects have been considered.

This gate depends on passing the three individual statement gates.

**Current gate status: NOT TESTED.**

---

## 8. Gate 5 — Operational and source suitability

**Objective:** Establish that XBRL can be operated as a dependable NorthStar data source, with repeatable processing, traceability, controlled exceptions, and acceptable maintenance burden.

### Test design

Run repeatability and operational tests over the approved sample, including:
- New annual filings;
- Amended filings;
- Missing or changed filing-package components;
- Issuer extensions and taxonomy changes;
- Presentation extraction failures;
- Calculation-role mismatches;
- Missing facts and contexts;
- Network failures, rate limits, and retry behavior.

A successful financial result must be reproducible from the same filing accession and code/configuration version.

### Proposed metrics and thresholds

| Metric | PASS | CONDITIONAL | FAIL |
|---|---:|---:|---:|
| Successful processing of eligible filings | ≥99% | 97–99% | <97% |
| Repeatability of accepted outputs | 100% | Minor documented nonmaterial differences | Unexplained material differences |
| Accepted-value provenance | 100% | No material omissions | Material traceability gaps |
| Controlled error classification | 100% of known failure classes | Minor unresolved cases | Silent failures or false PASS results |
| Versioned reproducibility | 100% of production candidates | Limited documented gaps | Cannot reproduce accepted values |

Processing success is not financial accuracy. Report operational coverage separately from reconstruction and mapping quality.

### Operational requirements

- Preserve accession and filing-period identity through the pipeline.
- Version source code, mapping rules, taxonomy assumptions, and configuration.
- Retain raw source artifacts or stable retrieval references.
- Record every derived value and transformation.
- Make retries safe and avoid duplicate or mixed-period data.
- Distinguish a failed download from a failed reconstruction.
- Provide explicit exception statuses.
- Monitor SEC access policies and source availability.
- Document maintenance ownership and recovery procedures.
- Evaluate whether an alternative source can fill exceptions without silently overriding filing data.

### Evidence to retain

- Run manifests and logs;
- Source and code version identifiers;
- Filing retrieval and retry logs;
- Error classification statistics;
- Reproducibility checks;
- Provenance samples;
- Operational maintenance estimates.

### Known limitations and dependencies

SEC filing availability and filing structure can change. The system must be resilient to taxonomy changes, extensions, amendments, and package variations.

**Current gate status: NOT ESTABLISHED.**

---

## 9. Mandatory controls across all gates

These controls are not optional acceptance metrics; they are correctness requirements.

| Control | Required behavior |
|---|---|
| Accession | Facts and presentation must belong to the same filing accession |
| Fiscal period | Do not mix annual, quarterly, YTD, or comparative periods |
| Context | Validate instant vs duration context |
| Dimensions | Preserve or deliberately filter dimensions; never accidentally combine segments or consolidated facts |
| Units | Validate USD, shares, per-share amounts, percentages, and scaling |
| Signs | Preserve reported sign and document transformations |
| Parent vs consolidated | Distinguish parent-attributable income from consolidated profit |
| NCI | Preserve noncontrolling-interest treatment |
| Extensions | Retain original extension concepts and labels |
| Calculation roles | Use only the selected statement's calculation network |
| Presentation fallback | Document when presentation relationships substitute for calculation relationships |
| Missing facts | Mark checks unavailable; do not treat missing data as a pass |
| Restatements | Preserve original filing values and amended/restated values with provenance |
| Derived values | Label derivations and preserve the calculation method |
| Source priority | Never silently overwrite a filing-reported value with an alternative-source value |

---

## 10. Decision framework: which source architecture should NorthStar choose?

### Option A — XBRL-only

Choose this only if:

- All five acceptance gates pass;
- Material mapping errors are below the approved threshold;
- Coverage is sufficient across NorthStar's target universe;
- Extensions and industry-specific concepts are handled consistently;
- Restatements and accession alignment are reliable;
- Exceptions are rare, controlled, and explainable;
- Operational maintenance is acceptable.

**Advantages:** Filing-level provenance, issuer-specific concepts, control over reconstruction and normalization, and independence from a single commercial provider.

**Risks:** Harvesting complexity, taxonomy and extension maintenance, incomplete presentation/calculation relationships, and ongoing mapping governance.

**Current decision:** Not approved.

### Option B — Hybrid XBRL plus alternative source

Choose this if:

- XBRL performs well for a substantial share of issuers and financial concepts;
- Its exceptions are identifiable and bounded;
- An alternative provider can reliably fill selected gaps;
- Conflicts between sources can be detected and resolved explicitly;
- Every value retains source and provenance information.

The hybrid design should define source priority by field and situation, not simply take whichever value is available.

Example policy:

1. Use XBRL when the filing fact and mapping pass validation.
2. Use the alternative source for explicitly unavailable or unaccepted XBRL values.
3. Flag conflicts between XBRL and the alternative source.
4. Preserve both original values and the resolution decision.
5. Do not use a fallback to conceal a material XBRL mapping error.

**Advantages:** Better coverage and potentially lower maintenance burden while preserving XBRL's filing-level strengths.

**Risks:** Provider inconsistencies, licensing or recurring costs, differing definitions, and source reconciliation complexity.

**Current decision:** The most defensible architecture to evaluate first.

### Option C — Non-XBRL primary source

Choose this if:

- XBRL fails key reconstruction or mapping gates;
- Material errors are recurring or difficult to detect;
- Coverage is insufficient for NorthStar's intended universe;
- Operational maintenance exceeds the value of source independence;
- A non-XBRL provider meets accuracy, coverage, provenance, historical-depth, and cost requirements more reliably.

**Advantages:** Potentially simpler implementation and less internal taxonomy maintenance.

**Risks:** Vendor dependence, less control over definitions, limited visibility into issuer-specific reporting, recurring cost, and potential delays or opaque restatement handling.

**Current decision:** Retain as a benchmark alternative; do not select without a direct comparison.

---

## 11. Prioritized execution sequence

| Priority | Workstream | Deliverable | Completion condition |
|---:|---|---|---|
| 1 | Re-run income-statement benchmark | Post-fix 250-company results | Comparable run manifest and before/after analysis |
| 2 | Resolve historical failures and partials | Root-cause register | Every historical failure classified or explicitly unresolved |
| 3 | Validate canonical IS mapping | Reviewed mapping accuracy sample | Independent concept-level review meets proposed threshold |
| 4 | Build balance-sheet pilot | 100-company benchmark | Reconstruction and mapping metrics available |
| 5 | Build cash-flow pilot | 100-company benchmark | Reconstruction and mapping metrics available |
| 6 | Expand BS and CFS samples | 250-company benchmarks | Industry coverage and exceptions documented |
| 7 | Perform integrated checks | Cross-statement benchmark | Material differences explained or classified |
| 8 | Evaluate operations and alternative source | Source comparison | Accuracy, coverage, maintenance, cost, and provenance compared |
| 9 | Approve source architecture | Signed decision record | All hard stops resolved and exceptions accepted |

### Immediate next actions

1. Preserve the November 12 code correction and historical benchmark as the baseline.
2. Re-run the same 250-company IS sample with the corrected code, without changing other methodology unless separately versioned.
3. Quantify the impact of the correction, especially HST and any other unmatched calculation roles.
4. Work through the 11 historical failures and 55 partial cases.
5. Begin canonical mapping review using a stratified set of actual filing line items.
6. Do not begin broad BS/CFS expansion until the IS benchmark's post-fix methodology is stable enough to reuse.

---

## 12. Go / no-go recommendation

### Decision rules

**GO — XBRL-only**

All five gates pass, no systemic material mapping issue remains, and operational controls are proven.

**CONDITIONAL GO — Hybrid**

XBRL passes the core reconstruction and mapping tests for an identifiable portion of the target universe, while remaining gaps can be covered by a validated alternative source and explicit exception policy.

**NO-GO — XBRL as primary source**

One or more critical gates fail, material errors remain systemic or undetectable, or the system cannot reliably reproduce and explain accepted values.

### Current recommendation: Continue; do not yet commit exclusively

The evidence supports continued investment in filing-level XBRL. The income-statement work has demonstrated meaningful reconstruction feasibility, and the November 12 calculation-role correction addressed a real cross-network calculation defect.

However, the current evidence does not establish canonical mapping accuracy, balance-sheet or cash-flow readiness, cross-statement consistency, or production operational suitability.

The next decisive milestone is a **post-fix, comparable 250-company income-statement benchmark combined with independent canonical mapping review**. That will tell us whether the income-statement foundation is robust enough to expand confidently into the other statements.

Until then, the preferred architecture to investigate is **hybrid XBRL plus an alternative source**, while keeping XBRL-only as a possible future outcome.

---

## 13. Approval and decision record

The following items should be approved before treating this matrix as binding project policy:

- [ ] Approve or revise the proposed numeric thresholds.
- [ ] Confirm the target issuer universe and industry weighting.
- [ ] Approve the definition of material mapping error.
- [ ] Approve the required independent-review sample size.
- [ ] Define the alternative-source comparator.
- [ ] Approve source-priority and conflict-resolution rules.
- [ ] Approve hard-stop conditions for production use.

**Decision owner:** NorthStar project owner  
**Decision status:** Pending evidence and threshold approval  
**Next review point:** After the post-fix income-statement benchmark and mapping review.



