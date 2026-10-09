# SEC XBRL Income Statement Research Findings

Status: Research only. Not yet a production NorthStar source.

Last major sample: 100-company S&P-style ticker sample from `tickers_100_usable.txt`.

---

## Objective

Determine whether SEC XBRL can support NorthStar/Canneberge income-statement
needs as a reliable source for:

- revenue
- operating income / EBIT
- pretax income
- taxes
- net income including NCI
- NCI
- parent net income
- EPS / shares
- major bridge lines

The long-term goal is not to map every US-GAAP concept.

The goal is to determine whether SEC XBRL can reliably provide valuation-grade
financial statement metrics across realistic GPC peer sets.

---

## Current architectural conclusion

SEC XBRL has two materially different layers:

### 1. SEC CompanyFacts

Strengths:
- easy API
- standardized JSON
- good coverage of many core facts
- useful for revenue, taxes, net income, EPS, shares, many anchors

Weaknesses:
- excludes many company-extension concepts
- does not always expose annual face-of-statement facts
- can miss required line items even when they appear in the 10-K
- cannot reconstruct every statement subtotal

CompanyFacts alone is not enough to fully reconstruct the top half of the
income statement.

### 2. Raw filing XBRL / Inline XBRL

Strengths:
- includes company-extension concepts
- includes the actual statement presentation hierarchy
- includes calculation linkbases with filer-provided summation weights
- can reconstruct exact statement math

Weaknesses:
- more complex
- filing-format variations exist
- some filings lack standalone `_pre.xml`
- requires context / dimension filtering
- requires accession alignment between facts and presentation

Raw filing-level XBRL is the path toward a true SEC-native statement source.

---

## Key tools built

### CompanyFacts tools

- `Dev_tools/xbrl/harvest_tags.py`
- `Dev_tools/xbrl/build_xbrl_glossary.py`
- `Dev_tools/xbrl/scale_is_waterfall.py`
- `Dev_tools/xbrl/diagnose_scaled_is.py`
- `Dev_tools/xbrl/diagnose_top_half.py`
- `Dev_tools/xbrl/diagnose_top_half_formulas.py`
- `Dev_tools/xbrl/validate_top_half_archetypes.py`

### Filing-level tools

- `Dev_tools/xbrl/harvest_filing_facts.py`
- `Dev_tools/xbrl/harvest_presentations.py`
- `Dev_tools/xbrl/reconstruct_income_statement_from_filing.py`
- `Dev_tools/xbrl/batch_reconstruct_is.py`
- `Dev_tools/xbrl/diagnose_batch_exceptions.py`

### Mapping/test files

- `northstar/data/transforms/sec_xbrl_key.py`
- `northstar/data/transforms/sec_xbrl.py`
- `tests/test_sec_xbrl_key.py`
- `tests/test_sec_xbrl.py`
- `tests/test_parent_net_income.py`
- `tests/test_top_half_archetypes.py`
- `tests/test_batch_reconstruct_is.py`

---

## Current 100-company filing-level IS result

Latest filing-level reconstruction batch result:

```text
RECONCILES       68
PARTIAL          21
FAIL              6
NO_PRESENTATION   5
Interpretation:

RECONCILES
All detected statement totals reconcile using the filing's own calculation
linkbase for the selected annual period.

PARTIAL
No calculation failures, but one or more subtotal checks are skipped because
a component fact is missing or no usable calculation arc exists. These are
not necessarily unusable statements.

FAIL
At least one subtotal fails against the filing's own calculation linkbase.
These are the highest-priority investigation cases.

Current FAIL tickers:

AMZN
AEP
AON
BAC
COF
CVNA
NO_PRESENTATION
Filing facts exist, but no usable income-statement presentation tree was
available under the current harvester.

Known reasons:

some filings lack standalone _pre.xml
some package presentation information differently
some need ZIP/XSD presentation extraction
Current NO_PRESENTATION tickers:

AMP
BLK
BX
BRO
BLDR
Note: AMP was previously an accession-alignment problem. The current remaining
NO_PRESENTATION group should be rechecked after the next scaled run.

Important fixes already made
Revenue priority and industry overrides
Global ordering cannot blindly prefer industry-specific component tags.

Examples:

CPT: needs OperatingLeaseLeaseIncome for property revenue.
LNT: needs Revenues, not RegulatedAndUnregulatedOperatingRevenue.
NEE: needs RegulatedAndUnregulatedOperatingRevenue because current
Revenues is not available.
Current research solution:

default mapping prefers broad Revenues
REIT override includes lease-income tags
utility override prefers Revenues, then falls through to regulated revenue
Parent net income
ProfitLoss is not a valid direct fallback for parent net income because it
can include noncontrolling interest.

Fix:

net_income maps only to NetIncomeLoss
research resolver can derive parent net income as:
ProfitLoss - total NCI
derived values are explicitly labeled and not treated as independent proof
Bridge concepts
Evidence-backed bridge lines added:

equity-method earnings
discontinued operations
These explain several pretax-to-net-income residuals.

Filing-level extension facts
MO proved why filing-level extraction is required.

MO FY2025:

text

Revenue
- COGS
- Other Cost of Operating Revenue
= Gross Profit

Gross Profit
- Marketing / Administration / Research
- Asset Impairment and Business Exit Costs
- Goodwill Impairment
= Operating Income
The key line mo:MarketingAdministrationandResearchCosts is a company
extension and is unavailable from SEC CompanyFacts.
Role-scoped calculation linkbases
Early reconstruction double-counted components because calculation arcs from
all roles were flattened together.

Fix:

restrict calculation arcs to the statement role being rendered
this eliminated exact 2x subtotal failures
Policy decision so far
Do not build company-specific mappings into sec_xbrl_key.py.

Company extensions should be handled by the filing-level statement
reconstructor, not by hard-coded company mappings.

Reusable mappings belong in sec_xbrl_key.py only when there is evidence
across multiple companies / statement roles.

Current strategic view
SEC XBRL should remain research-stage until the income-statement pipeline is
tested at a larger scale.

The likely final platform model is:

text

StockAnalysis:
    practical normalized rolling statement source

SEC CompanyFacts:
    standardized fact source
    validation/fallback source
    fast source for many anchors

SEC filing-level XBRL:
    authoritative source for exact filing statements
    required for as-filed/as-of workflows
    required for company extensions and exact statement reconstruction
Do not wire SEC into Canneberge until IS, BS, and CFS behavior is well
understood and the source priority policy is explicit.

---

## 250-company filing-level IS reconstruction result

After adding filing-level fact harvest, accession-aligned presentation harvest,
and role-scoped calculation-linkbase reconstruction, the 250-company sample
produced:

```text
RECONCILES       169
PARTIAL           55
FAIL              11
NO_PRESENTATION   13
NO_TOTALS          1
NO_FACTS           1
Interpretation:

RECONCILES: all detected statement totals reconcile to the filer's own
calculation linkbase.
PARTIAL: no arithmetic failures, but at least one subtotal check was
skipped due to a missing component or missing calculation arc.
FAIL: at least one subtotal disagrees with the filing's calculation
linkbase and requires review.
NO_PRESENTATION: filing facts exist, but no standalone usable presentation
linkbase was harvested.
NO_FACTS: filing-fact harvest failed or no usable annual filing facts were
extracted.
NO_TOTALS: presentation/facts exist but no subtotal checks were identified.
Effective tested filing group:

text

250 - 13 NO_PRESENTATION - 1 NO_FACTS = 236
Within the tested group:

text

RECONCILES + PARTIAL = 224 / 236 = 94.9% with no arithmetic FAIL
FAIL = 11 / 236 = 4.7%
NO_TOTALS = 1 / 236 = 0.4%
This is strong evidence that raw filing-level XBRL can reconstruct income
statements across a broad public-company sample far better than CompanyFacts
alone.

Remaining research items before production use:

Investigate the 11 FAIL cases:

AMZN
AEP
AON
BAC
COF
CVNA
CSX
FANG
FDX
HAL
HST
Investigate 13 NO_PRESENTATION filings:

BLK
BX
BRO
BLDR
CHD
CPRT
DVN
D
DPZ
EXPD
GRMN
HCA
IBKR
Determine whether NO_PRESENTATION is caused by:

no standalone _pre.xml,
presentation data embedded in another package,
XBRL ZIP / XSD-only filing structure,
or harvester limitations.
Decide if PARTIAL rows are valuation-usable by checking whether skipped
subtotals are minor/ancillary or affect primary financial metrics.
