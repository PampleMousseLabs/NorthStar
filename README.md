# NORTH_STAR.md

### Personal Financial Platform — Master Vision & Roadmap

**Owner:** [Your Name]
**Started:** August 2026
**Last revised:** September 2026
**Status:** Active — Canneberge foundation shipped; platform extraction beginning

---

# 1. Mission Statement

Build a self-hosted, local-first financial data and analytics platform that
collectively reproduces — and in targeted areas surpasses — the analytical
capabilities of institutional financial terminals such as Bloomberg Terminal,
without requiring a recurring terminal subscription.

The platform will aggregate financial and market data from multiple sources,
normalize that information into a common internal financial model, persist
useful historical data locally, and expose reusable data and analytical
services to a family of independent financial applications.

The goal is **not** to recreate Bloomberg's breadth.

The goal is to build a **private financial intelligence platform tailored to
the needs of a sophisticated valuation and capital-markets practitioner**.

The platform should make it progressively cheaper — in both development time
and data-acquisition effort — to build each subsequent financial application.

---

# 2. The Core Mental Model

The project is evolving from:

> **"I built a financial application."**

into:

> **"I am building a financial platform, and financial applications are
> products built on top of it."**

Canneberge is the first major application.

The long-term architecture is:

```text
                         FINANCIAL PLATFORM
                                │
              ┌─────────────────┴─────────────────┐
              │                                   │
         DATA PLATFORM                       ANALYTICS PLATFORM
              │                                   │
      ┌───────┼────────┐                  ┌───────┼────────┐
      │       │        │                  │       │        │
   Sources  Normalize  Store            Valuation  Macro  Derivatives
      │       │        │
      └───────┼────────┘
              │
       Canonical Data Model
              │
       Shared Data Services
              │
       ┌──────┼──────┬────────┐
       │      │      │        │
       ▼      ▼      ▼        ▼
   Canneberge App 2    App 3   App 4...
       │
   ┌───┴────┐
   │        │
 PyQt6    Dash
```

The platform owns the **reusable capabilities**.

Individual applications own their **specialized workflows, calculations,
and user experiences**.

---

# 3. Guiding Principles

### 1. Platform before duplication

If a capability will reasonably be used by multiple applications, extract it
into the shared platform rather than rebuilding it inside each application.

Do not prematurely generalize code simply because it *might* be reusable.

> **Promote functionality when reuse is real or highly probable.**

---

### 2. Data is a first-class asset

Source data should not be treated merely as an input to one application's
calculations.

The platform should progressively build a reusable financial data asset.

```text
External Sources
       ↓
Source Adapters
       ↓
Normalization / Transformation
       ↓
Canonical Financial Model
       ↓
Shared Data Store
       ↓
Multiple Applications
```

---

### 3. Own the data pipeline

Prefer free APIs, public sources, scraping, locally cached datasets, and
other legally/technically sustainable sources before considering paid data
feeds.

When multiple sources provide the same information, the platform should be
capable of selecting among them rather than becoming permanently dependent on
one provider.

---

### 4. Source-specific code stays at the edge

Applications should not need to know that a particular metric came from
StockAnalysis, MarketScreener, yfinance, FRED, SEC filings, or another
provider.

Source-specific logic belongs in the data platform.

Applications consume standardized data.

```text
Canneberge
      ↓
financial_data.get_income_statement(...)
      ↓
Data Platform
      ↓
StockAnalysis / SEC / future source
```

---

### 5. Establish a canonical internal data model

External providers use different:

* identifiers
* ticker conventions
* terminology
* period labels
* financial statement structures
* units
* metadata

The platform should establish its own internal vocabulary.

For example:

```text
revenue
ebit
ebitda
adjusted_ebitda
cash
total_debt
shares_outstanding
beta
price
risk_free_rate
```

Applications should operate primarily on this canonical representation rather
than provider-specific schemas.

---

### 6. Pure mathematics stays independent of UI

Calculation engines should never depend on PyQt, Dash, browser components,
or other presentation frameworks.

```text
                 Calculation Engine
                /                  \
             PyQt                  Dash
```

The same calculation should produce the same answer regardless of the
interface calling it.

This enables:

* multiple UIs
* CLI execution
* automated testing
* batch analysis
* future APIs
* future applications

---

### 7. Institutional rigor, practical implementation

Use rigorous methodologies where they materially improve the analysis.

Where a full institutional implementation is unnecessary, documented
shortcuts and proxies are acceptable.

Examples:

* Book Debt ≈ Fair Value Debt
* free-data proxies for unavailable market data
* simplified econometric specifications
* cached data rather than unnecessary real-time retrieval

Assumptions must be explicit.

---

### 8. Actionability over decorative complexity

Every major analytical module should ultimately produce information that can
inform:

* a valuation conclusion
* an investment decision
* a risk assessment
* a portfolio decision
* a trade structure
* a scenario analysis

Avoid building complexity merely because the capability is technically
interesting.

---

### 9. Local-first

The system is designed primarily for personal use.

Initial deployment should favor:

* local execution
* local storage
* local networking
* local caching
* self-hosted services

Internet connectivity may be required for data acquisition, but the
application ecosystem itself should not require SaaS infrastructure.

---

# 4. The Platform

The platform is the most important new phase of the project.

It should eventually contain the capabilities that multiple applications can
consume.

## 4.1 Data Platform

The initial shared platform should focus on financial data.

### Sources

Source adapters responsible only for communicating with external providers.

Initial candidates:

```text
platform/data/sources/

stockanalysis.py
marketscreener.py
yfinance.py
fred.py
```

Future candidates may include:

```text
SEC / EDGAR
Federal Reserve datasets
Treasury data
CBOE / options data
NASDAQ
company filings
other public sources
```

A source adapter answers:

> "How do I obtain data from this provider?"

It should not answer:

> "How does Canneberge calculate a DCF?"

---

## 4.2 Transforms

Transforms convert source-specific data into the platform's canonical
representation.

Examples:

```text
platform/data/transforms/

financial_statements.py
market_data.py
securities.py
identifiers.py
periods.py
```

Responsibilities include:

* cleaning
* type conversion
* period normalization
* unit normalization
* line-item mapping
* identifier mapping
* schema normalization
* source-specific quirks

---

# 5. Canonical Data Model

The canonical data model is one of the highest-priority architectural
objectives.

The platform should eventually define common representations for:

### Companies

```text
Company
├── internal_id
├── legal_name
├── common_name
├── country
├── industry
└── identifiers
```

### Securities

```text
Security
├── internal_id
├── company_id
├── ticker
├── exchange
├── currency
├── ISIN
└── provider-specific identifiers
```

### Financial Statements

```text
FinancialStatement
├── company/security
├── statement_type
├── line_item
├── period
├── fiscal_year
├── value
├── currency
├── source
└── retrieved_at
```

### Market Data

```text
MarketData
├── security
├── timestamp
├── price
├── volume
├── market_cap
├── beta
└── other observations
```

The exact schema should be designed after examining the real data already
produced by Canneberge rather than invented abstractly beforehand.

---

# 6. Data Storage Evolution

Do not build a giant data warehouse on Day 1.

Evolve the storage architecture as the requirements become clear.

### Stage 1 — Application/session caching

Existing Canneberge JSON/session mechanisms.

### Stage 2 — Shared local data store

Likely SQLite initially.

Purpose:

* shared financial data
* source results
* cached market data
* macroeconomic series
* company/security metadata
* retrieval timestamps
* source provenance

### Stage 3 — Persistent financial database

As data volume and query requirements grow, evaluate PostgreSQL or another
appropriate database.

### Stage 4 — Financial data warehouse

Only if the scale and analytical requirements justify it.

The objective is eventually:

```text
                    External Sources
                          ↓
                       Ingest
                          ↓
                     Normalize
                          ↓
                  Canonical Data
                          ↓
                   Persistent Store
                          ↓
                  Data Services API
                          ↓
        ┌─────────────────┼─────────────────┐
        ↓                 ↓                 ↓
   Canneberge          Macro App       Future Apps
```

---

# 7. Shared Data Services

Applications should consume the data platform through service-level
interfaces rather than importing source adapters directly.

Examples:

```text
financials_service.py
market_data_service.py
company_service.py
macro_service.py
security_service.py
```

Conceptually:

```python
financials.get_income_statement("AAPL")
market_data.get_price("AAPL")
company.get_company("LVMH")
macro.get_series("DGS10")
```

The underlying source should be an implementation detail.

This creates a stable contract between the platform and applications.

---

# 8. Shared Analytics Platform

Not all financial calculations belong to the shared platform.

The initial rule is:

> **Extract a calculation into the shared analytics layer when multiple
> applications genuinely need it.**

Potential future shared capabilities include:

```text
platform/analytics/

financial_math/
statistics/
valuation/
market/
risk/
```

Potential candidates:

* WACC
* beta calculations
* capital structure mathematics
* common financial ratios
* Black-Scholes
* bond mathematics
* statistical functions
* common valuation mathematics

Canneberge-specific methodologies should remain in Canneberge until another
application actually needs them.

---

# 9. Common Infrastructure

Potential shared infrastructure includes:

```text
platform/common/

config/
logging/
utils/
themes/
session/
validation/
```

Candidates for extraction from Canneberge:

* common configuration
* logging
* theme/font system
* reusable UI-independent utilities
* session infrastructure
* validation
* common error handling

Again, extraction should follow actual reuse rather than speculative
generalization.

---

# 10. Application Architecture

Each application should eventually follow the same high-level pattern:

```text
apps/
│
├── Canneberge/
│   ├── calculations/
│   ├── desktop/
│   ├── web/
│   └── app_state.py
│
├── Macro/
│   ├── calculations/
│   ├── desktop/
│   └── web/
│
├── Derivatives/
│   ├── calculations/
│   ├── desktop/
│   └── web/
│
└── ...
```

An application should own:

* application-specific calculations
* application-specific workflows
* application-specific state
* desktop UI
* web UI
* application-specific visualization

The platform should own:

* shared data
* shared services
* shared canonical models
* genuinely reusable analytics
* common infrastructure

---

# 11. Canneberge — Application 1

**Status:** Foundation shipped / final application cleanup underway

**Purpose:** Institutional-grade fundamental valuation platform with
peer-relative multiples and reverse-DCF market-implied growth analysis.

## Core Capabilities

* Full DCF engine
* FCFF / FCFE functionality
* WACC / Ke
* Beta relevering
* Capital structure controls
* FRED-linked risk-free rate and corporate spreads
* Debt Schedule
* NWC modeling
* Subject Financials
* Guideline Transactions
* Guideline Public Companies
* Reverse DCF
* Valuation Surface
* Session save/load
* Theme system
* Analytics / reconciliation diagnostics
* PyQt6 desktop interface
* Dash web interface

## Remaining Canneberge Work

* PVGO / Growth Decomposition Engine
* Session caching optimization
* DCF sensitivity pure-math refactor
* Expand GPC QA universe
* Basis of Value propagation
* Final architecture cleanup
* Extraction of reusable platform components

### Important

Canneberge is **not** to become the shared platform.

The objective is to finish the application while extracting the components
that genuinely belong to the platform.

---

# 12. Future Application Portfolio

The following applications represent the current strategic vision.

They are not all immediate commitments.

The platform must be developed first enough that future applications can
actually benefit from it.

---

## App 2 — Macro & Econometrics

**Purpose:** Macro environment analysis and transmission of macroeconomic
shocks into security-level valuation and risk.

Potential capabilities:

* Fed funds path
* Yield curve
* real rates
* breakevens
* credit spreads
* employment
* inflation
* macro release calendar
* econometric relationships
* scenario/shock engine
* WACC / Ke shock propagation
* security-level impact analysis

Integration:

```text
Macro Platform
      ↓
Macro Shock
      ↓
Canneberge
      ↓
DCF / WACC / Target Value
```

---

## App 3 — Derivatives & Trade Engineering

**Working name:** DerivaGem++

**Purpose:** Derivatives pricing, trade construction, hedging, and payoff
analysis.

Potential capabilities:

* options chain ingestion
* Black-Scholes
* binomial / trinomial models
* exotic options
* Greeks
* multi-leg strategies
* payoff diagrams
* scenario analysis
* volatility analysis

Potential integration:

```text
Canneberge Target Value
          +
Macro Scenarios
          ↓
Derivatives / Hedging Analysis
```

---

## App 4 — Home / News / Portfolio Command Center

**Purpose:** Daily personal financial command center.

Potential capabilities:

* RSS/news aggregation
* ticker filtering
* watchlists
* portfolio tracking
* P&L
* dividend calendar
* market monitoring
* macro calendar
* technical alerts
* application launch/integration

This becomes the eventual **"start here"** interface for the broader
platform.

---

## App 5 — Credit & Distressed Debt

**Purpose:** Credit analysis, debt valuation, and distressed securities.

Potential capabilities:

* credit scorecard
* financial ratio analysis
* yield-to-maturity
* yield-to-worst
* default probability
* Merton / structural models
* recovery analysis
* distressed debt valuation
* fair value of debt

Potential integration:

```text
Credit Platform
      ↓
Fair Value Debt
      ↓
Canneberge
      ↓
Enterprise / Equity Value
```

---

# 13. Cross-Application Architecture

The long-term architecture should resemble:

```text
                         ┌──────────────────────┐
                         │   EXTERNAL SOURCES   │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │    SOURCE ADAPTERS   │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │      TRANSFORMS      │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │  CANONICAL DATA MODEL│
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │     DATA STORAGE     │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │    DATA SERVICES     │
                         └──────────┬───────────┘
                                    ↓
                  ┌─────────────────┼─────────────────┐
                  ↓                 ↓                 ↓
             Canneberge         Macro App       Derivatives
                  ↓                 ↓                 ↓
              PyQt/Dash         PyQt/Dash         PyQt/Dash
```

Shared data and services flow downward/upward through defined interfaces.

Applications should not directly reach into another application's internals.

---

# 14. Repository Target Architecture

The target repository architecture is:

```text
4_application/
│
├── platform/
│   │
│   ├── data/
│   │   ├── sources/
│   │   ├── transforms/
│   │   ├── models/
│   │   ├── services/
│   │   └── storage/
│   │
│   ├── analytics/
│   │   ├── financial_math/
│   │   ├── statistics/
│   │   ├── valuation/
│   │   └── risk/
│   │
│   └── common/
│       ├── config/
│       ├── logging/
│       ├── themes/
│       └── utils/
│
├── apps/
│   │
│   ├── Canneberge/
│   │   ├── calculations/
│   │   ├── desktop/
│   │   ├── web/
│   │   └── app_state.py
│   │
│   ├── Macro/
│   │   ├── calculations/
│   │   ├── desktop/
│   │   └── web/
│   │
│   ├── Derivatives/
│   │   ├── calculations/
│   │   ├── desktop/
│   │   └── web/
│   │
│   └── ...
│
├── Dev_tools/
│
├── tests/
│
├── requirements.txt
└── NORTH_STAR.md
```

This is a **target architecture**, not a mandate to reorganize everything in
one pass.

---

# 15. Development Roadmap

## Phase 0 — Canneberge Completion

**Objective:** Finish Canneberge without introducing unnecessary new
architecture.

* [ ] Complete remaining Canneberge analytical features
* [ ] Complete final QA
* [ ] Confirm desktop/web calculation parity
* [ ] Finalize current source integrations
* [ ] Document current architecture
* [ ] Freeze Canneberge as a stable application baseline

**Exit condition:**

Canneberge can be treated as a finished application rather than an actively
changing architectural experiment.

---

# Phase 1 — Repository & Architecture Extraction

**Objective:** Separate platform capabilities from Canneberge-specific code.

### Inventory

* [ ] Inventory every Canneberge module
* [ ] Classify each module as:

  * Platform candidate
  * Canneberge-specific
  * UI-specific
  * Temporary/dev tooling
  * Unclear
* [ ] Identify dependencies between modules
* [ ] Identify source-specific assumptions
* [ ] Identify duplicated desktop/web logic

### Initial extraction candidates

* [ ] `Sources/`
* [ ] reusable `Transforms/`
* [ ] reusable `Services/`
* [ ] source-independent data models
* [ ] common configuration
* [ ] logging
* [ ] reusable utilities

### Do NOT extract yet

* [ ] Canneberge-specific DCF workflow
* [ ] Canneberge-specific GT/GPC workflow
* [ ] Canneberge-specific Value Bridge
* [ ] UI-specific code
* [ ] speculative "future reusable" calculations

**Exit condition:**

There is a clear architectural boundary between:

```text
Platform
```

and

```text
Canneberge
```

---

# Phase 2 — Build the Shared Data Platform

**Objective:** Make financial data a reusable platform capability.

* [ ] Create `platform/data/`
* [ ] Move/refactor source adapters
* [ ] Standardize source adapter interfaces
* [ ] Build canonical company model
* [ ] Build canonical security model
* [ ] Build canonical financial statement model
* [ ] Build canonical market-data model
* [ ] Build identifier mapping
* [ ] Normalize financial periods
* [ ] Normalize currencies/units where appropriate
* [ ] Add source provenance
* [ ] Add retrieval timestamps
* [ ] Add validation
* [ ] Add error handling
* [ ] Build initial data services

**Exit condition:**

A new application can request standardized financial/market data without
knowing which external source supplied it.

---

# Phase 3 — Shared Data Storage

**Objective:** Move from transient retrieval toward a persistent shared
financial data asset.

### Initial implementation

* [ ] Evaluate SQLite
* [ ] Design schema
* [ ] Store company/security metadata
* [ ] Store financial statement observations
* [ ] Store market observations
* [ ] Store macroeconomic series
* [ ] Store source/provenance metadata
* [ ] Add retrieval timestamps
* [ ] Add cache freshness rules

### Later

* [ ] Evaluate PostgreSQL
* [ ] Evaluate historical data retention
* [ ] Evaluate incremental refresh
* [ ] Evaluate background refresh jobs
* [ ] Evaluate data versioning

**Exit condition:**

Multiple applications can use the same persistent local financial dataset.

---

# Phase 4 — Reconnect Canneberge to the Platform

**Objective:** Prove the architecture using the application that created
the original data infrastructure.

* [ ] Replace direct source calls with platform services
* [ ] Remove unnecessary Canneberge source dependencies
* [ ] Confirm desktop functionality
* [ ] Confirm web functionality
* [ ] Confirm calculation parity
* [ ] Confirm session behavior
* [ ] Confirm performance
* [ ] Confirm source refresh behavior

**Critical test:**

Canneberge should behave essentially the same from the user's perspective
even though its data infrastructure now lives outside the application.

**Exit condition:**

Canneberge is a consumer of the platform rather than the owner of the
platform.

---

# Phase 5 — Shared Analytics Extraction

**Objective:** Extract genuinely reusable financial mathematics.

Potential candidates:

* [ ] WACC
* [ ] beta
* [ ] capital structure
* [ ] common financial ratios
* [ ] statistical functions
* [ ] common valuation functions
* [ ] derivatives mathematics
* [ ] fixed-income mathematics

For each candidate:

1. Identify actual reuse.
2. Remove UI dependencies.
3. Define inputs/outputs.
4. Add tests.
5. Move into shared analytics package.
6. Update applications to consume it.

**Exit condition:**

Shared financial mathematics can be consumed by multiple applications
without importing application-specific UI or state.

---

# Phase 6 — Build Application 2

**Objective:** Validate that the platform actually makes a second application
faster to build.

Candidate:

> Macro & Econometrics

The key metric is not simply whether App 2 works.

The key metric is:

> **How much infrastructure did App 2 NOT have to rebuild?**

Track reuse of:

* data ingestion
* company/security identification
* market data
* macro data
* storage
* configuration
* logging
* UI conventions
* shared analytics

**Exit condition:**

A second independent application successfully consumes the shared platform.

---

# Phase 7 — Application Ecosystem

Potential future applications:

* [ ] Macro & Econometrics
* [ ] Derivatives / Trade Engineering
* [ ] Home / News / Portfolio
* [ ] Credit & Distressed Debt
* [ ] Additional applications as justified

At this stage, the project should be treated as an **application ecosystem**
rather than a collection of unrelated projects.

---

# 16. Starter Shell — Later, Not Now

Once the platform and at least two applications are stable, create a reusable
application starter template.

The starter should provide:

```text
New Application
├── standard project structure
├── desktop shell
├── web shell
├── configuration
├── logging
├── testing
├── platform connection
└── standard development tooling
```

The starter shell should be created **from proven patterns**, not designed
speculatively in advance.

The objective is:

> **Build the second and third applications first. Then turn what actually
> worked into the starter shell.**

---

# 17. Long-Term Deployment Model

### Phase 1 — Local workstation

```text
Windows
├── PyQt6 desktop
├── Dash localhost
└── Local data store
```

### Phase 2 — Home server

```text
Home Server
├── Data Platform
├── Database
├── Financial Applications
└── Local network / Tailscale access
```

Applications become accessible from:

* desktop
* laptop
* tablet
* browser

without requiring a commercial SaaS platform.

### Phase 3 — Mature personal financial terminal

Potential architecture:

```text
                   HOME SERVER
                       │
        ┌──────────────┼──────────────┐
        │              │              │
     Database      Data Platform   Applications
        │              │              │
        └──────────────┼──────────────┘
                       │
                 API / Web Layer
                       │
              ┌────────┼────────┐
              ↓        ↓        ↓
            PC      Tablet    Laptop
```

---

# 18. What This Is NOT

* **Not a SaaS product.**
* **Not a Bloomberg clone in terms of breadth.**
* **Not an attempt to reproduce every Bloomberg terminal function.**
* **Not initially a commercial product.**
* **Not an order-execution platform.**
* **Not a research publication platform.**
* **Not a reason to pay for data unnecessarily.**
* **Not an excuse to build infrastructure for its own sake.**
* **Not open-source initially unless there is a specific reason.**

The objective is a private, highly capable financial intelligence and
analytics environment.

---

# 19. Success Criteria

The project is succeeding when each new application becomes materially
cheaper and faster to build because the platform already provides:

### Data

* Company identifiers
* Financial statements
* Market data
* Macro data
* Historical observations
* Source provenance

### Infrastructure

* Storage
* Caching
* Logging
* Configuration
* Validation
* Refresh mechanisms

### Analytics

* Reusable financial mathematics
* Statistical tools
* Valuation tools
* Risk tools

### Interfaces

* Proven PyQt patterns
* Proven Dash patterns
* Shared themes/components where appropriate

The ultimate test is:

> **Can a new financial application be built primarily by adding new
> analytical logic and UI rather than rebuilding data infrastructure?**

If yes, the platform is working.

---

# 20. Anti-Scope-Creep Rules

Every new idea gets evaluated against these questions:

### 1. Is this platform infrastructure or application functionality?

If platform infrastructure, determine whether multiple applications genuinely
need it.

If application-specific, keep it in the application.

### 2. Am I abstracting because there is real reuse?

Do not create generic frameworks merely because they sound architecturally
clean.

### 3. Does it improve the financial analysis?

If not, deprioritize it.

### 4. Does it require paid data?

Find a sustainable free/public alternative first.

### 5. Does it create unnecessary coupling?

Avoid:

```text
App A → App B
```

Prefer:

```text
App A → Platform
App B → Platform
```

### 6. Does this belong in the data platform?

If yes, keep source-specific logic out of applications.

### 7. Am I building infrastructure instead of the product?

Infrastructure is valuable only when it enables applications.

### 8. Is this being built because it is cool?

If yes, ask whether it also provides meaningful analytical or architectural
value.

---

# 21. Immediate Roadmap

## Now

**Finish Canneberge.**

Then:

**Freeze Canneberge.**

Then:

**Create the new repository for the Financial Platform.**

Then:

### Milestone 1

```text
Inventory Canneberge
        ↓
Identify platform candidates
        ↓
Design target repository
        ↓
Extract data infrastructure
```

### Milestone 2

```text
Sources
   ↓
Transforms
   ↓
Canonical Models
   ↓
Data Services
```

### Milestone 3

```text
Data Services
      ↓
Persistent Local Store
```

### Milestone 4

```text
Canneberge
      ↓
Shared Platform
```

### Milestone 5

```text
Shared Platform
      ↓
Application #2
```

### Milestone 6

```text
Platform + 2 Apps
      ↓
Proven Starter Shell
```

---

# 22. The Ultimate Vision

The end state is not five applications.

The end state is:

```text
                         PERSONAL FINANCIAL TERMINAL
                                      │
                 ┌────────────────────┴────────────────────┐
                 │                                         │
          FINANCIAL DATA PLATFORM                  ANALYTICAL PLATFORM
                 │                                         │
       ┌─────────┼──────────┐                 ┌────────────┼────────────┐
       │         │          │                 │            │            │
    Markets  Financials   Macro             Valuation    Risk       Derivatives
       │         │          │                 │            │            │
       └─────────┼──────────┘                 └────────────┼────────────┘
                 │                                         │
                 └──────────────────┬──────────────────────┘
                                    │
                             APPLICATION LAYER
                                    │
             ┌──────────────────────┼──────────────────────┐
             │                      │                      │
        Canneberge             Macro App            Derivatives App
             │                      │                      │
          PyQt/Dash              PyQt/Dash              PyQt/Dash
             │                      │                      │
             └──────────────────────┼──────────────────────┘
                                    │
                              USER / ANALYST
```

The applications are the **views and workflows**.

The platform is the **underlying financial intelligence system**.

That is the long-term architecture.

---

# 23. Revision Log

| Date       | Change                                                                                                                                                                                                                                     |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 2026-08-28 | Initial draft. Documented five-app vision and Canneberge roadmap.                                                                                                                                                                          |
| 2026-09-23 | Reframed project around a shared financial platform. Added canonical data model, source/data-service separation, persistent data-store evolution, platform extraction roadmap, application architecture, and eventual starter-shell phase. |

---

# 24. North Star

> **Build a private financial intelligence platform once, then build
> increasingly powerful financial applications on top of it.**

Or, more simply:

> **Build the Bloomberg underneath the apps.**
