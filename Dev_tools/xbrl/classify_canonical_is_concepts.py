import csv
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("Dev_tools/xbrl/runlogs")
INVENTORY = ROOT / "canonical_is_concept_inventory.csv"
ZONES = ROOT / "canonical_is_zone_summary.csv"
OUTPUT = ROOT / "canonical_is_concept_classification.csv"

ANCHORS = {
    "GrossProfit": ("gross_profit", "gross_profit"),
    "OperatingIncomeLoss": ("operating_income", "operating_income"),
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": ("pretax_income", "pretax"),
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments": ("pretax_income", "pretax"),
    "IncomeTaxExpenseBenefit": ("income_tax", "income_taxes"),
    "ProfitLoss": ("net_income_subtotal", "net_income"),
    "NetIncomeLoss": ("net_income", "net_income"),
}

SUBTOTALS = {
    "CostsAndExpenses",
    "OperatingExpenses",
    "OperatingCostsAndExpenses",
    "BenefitsLossesAndExpenses",
    "NonoperatingIncomeExpense",
    "NoninterestExpense",
    "TotalFeeRevenue",
    "TotalNonPropertyIncomeLoss",
}

def result(role, section, method, note):
    return role, section, method, note

def classify(concept, evidence):
    tag = concept.split(":", 1)[-1]
    low = tag.lower()

    if tag in ANCHORS:
        return result(*ANCHORS[tag], "explicit", "Recognized earnings anchor")

    if low.endswith("textblock"):
        return result("disclosure", "supplementary", "explicit", "Text-block disclosure, not an additive financial line")

    if "weightedaverage" in low and "share" in low:
        return result("share_count", "supplementary", "explicit", "Weighted-average shares")

    if "pershare" in low or "earningspershare" in low:
        return result("per_share", "supplementary", "explicit", "Per-share measure")

    if "othercomprehensiveincome" in low or low.startswith("oci"):
        return result("comprehensive_income", "comprehensive_income", "explicit", "OCI component")

    if "comprehensiveincome" in low:
        return result("comprehensive_income", "comprehensive_income", "explicit", "Comprehensive income measure")

    if "discontinuedoperation" in low:
        return result("discontinued_operations", "discontinued_operations", "explicit", "Discontinued operations")

    if any(x in low for x in (
        "noncontrollinginterest", "attributabletoparent",
        "availabletocommonstockholders", "preferredstockdividends",
        "convertiblepreferreddividends",
    )):
        return result("attribution", "net_income", "explicit", "Net income attribution or common earnings adjustment")

    if tag in SUBTOTALS:
        return result("subtotal", "contextual", "explicit", "Reported subtotal; components require separate treatment")

    if tag in {"Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
               "SalesRevenueNet", "RegulatedAndUnregulatedOperatingRevenue"}:
        return result("revenue", "revenue", "explicit", "Revenue measure")

    if "incometax" in low or "taxexpensebenefit" in low:
        return result("line_item", "income_taxes", "explicit", "Current, deferred or total income tax")

    # Revenue and income-generating activity.
    revenue_terms = (
        "revenue", "revenues", "premiumsearned", "brokeragecommissions",
        "investmentbankingrevenue", "foreignexchangerevenue",
        "capitalmarketsfees", "commercialbankingrevenue",
        "commercialpaymentsrevenue", "consumerbankingrevenue",
        "propertymanagementdevelopmentandotherfees",
        "securitiesservicingandtreasuryservicesfees",
        "servicechargesandfees", "wealthfees", "interchangefees",
        "intellectualpropertyandcustomdevelopmentincome",
    )
    if any(x in low for x in revenue_terms):
        return result("line_item", "revenue", "semantic", "Revenue-generating activity")

    # Cost of revenue and direct production/service costs.
    direct_cost_terms = (
        "costofrevenue", "costofgoods", "costofservices",
        "costofsales", "crudeoil", "productpurchases",
        "productionandmanufacturing", "directcostsof",
        "costofore", "costoffeeandassetmanagement",
    )
    if any(x in low for x in direct_cost_terms):
        return result("line_item", "cost_of_revenue", "semantic", "Direct cost of revenue or production")

    # Operating expense families, including industry-specific expenses.
    operating_terms = (
        "sellinggeneral", "generalandadministrative", "sellingandmarketing",
        "researchanddevelopment", "professionalfees",
        "communicationsandinformationtechnology", "deferredpolicyacquisition",
        "policyholderbenefits", "benefitslossesandexpenses",
        "insurancecommissions", "underwriting", "occupancynet",
        "cardandprocessingexpense", "distributionexpenses",
        "provisionforloanlosses", "creditlossexpense",
        "equipmentexpense", "corporateexpenses",
        "regulatoryfees", "bankassessmentcharges",
        "subcustodianandclearingexpense", "transactional",
        "acquisitionrelatedcosts", "integrationrelatedcosts",
        "businessseparationcosts", "restructuring",
        "impairment", "amortization", "depreciation",
        "compensation", "salaries", "laborandrelated",
        "royaltyexpense", "realestatetaxexpense",
        "federaldepositinsurance", "otherunderwritingexpense",
        "assetretirementobligationaccretion",
        "provisionfordoubtfulaccounts", "otherdeductionsnet",
    )
    if any(x in low for x in operating_terms):
        return result("line_item", "operating_expenses", "semantic", "Operating or industry-specific expense")

    if "interestexpenseoperating" in low:
        return result("line_item", "operating_expenses", "explicit", "Explicitly identified operating interest expense")

    if "interestexpensenonoperating" in low or "interestexpensedeposits" in low:
        return result("line_item", "nonoperating", "explicit", "Explicitly identified nonoperating interest expense")

    # Financial-services operating revenue.
    financial_revenue_terms = (
        "noninterestincome",
        "interestanddividendincomesecurities",
        "interestandfeeincomeloans",
        "otherinterestanddividendincome",
        "interestincomedepositswithfinancialinstitutions",
        "feesandcommissions",
        "mortgagebankingandservicing",
        "administrationandotherfiduciaryfees",
        "investmentmanagementandperformancefees",
        "foreignexchangeandtradefinancefees",
        "letterofcreditandloanfees",
        "cardmember",
        "interchangefees",
        "investmentandotherincome",
    )
    if any(x in low for x in financial_revenue_terms):
        return result("line_item", "revenue", "semantic", "Financial-services operating revenue")

    # Operating taxes and utility/production costs.
    operating_cost_terms = (
        "taxesexcludingincome",
        "taxesother",
        "propertytax",
        "premiumtax",
        "utilitiesoperatingexpense",
        "fuelcost",
        "fuelandpurchasedpower",
        "purchasedpower",
        "transmissioncost",
        "maintenanceoperations",
        "maintenanceandoperations",
        "explorationexpense",
        "costdirectmaterial",
        "costdirectlabor",
        "productiontax",
        "gatheringprocessing",
        "transportationcost",
        "drillholecost",
        "dryholecost",
        "liftingcost",
        "productioncost",
        "refineryexpense",
        "operatingleaseexpense",
        "aircraftmaintenance",
        "aircraftrental",
        "landingfees",
        "capacitypurchase",
        "patientcarecost",
        "fulfillmentexpense",
        "technologyandinfrastructureexpense",
    )
    if any(x in low for x in operating_cost_terms):
        return result("line_item", "operating_expenses", "semantic", "Operating, utility, production or service cost")

    if "operatingleaseleaseincome" in low or low in {"leaseincome", "operatingleaseincome"}:
        return result("line_item", "revenue", "semantic", "Operating lease income")

    if "realizedinvestmentgainslosses" in low or "tradinggainslosses" in low:
        return result("line_item", "nonoperating", "semantic", "Investment or trading gain/loss")

    if "interestincomeexpensenonoperatingnet" in low:
        return result("line_item", "nonoperating", "explicit", "Net nonoperating interest income/expense")

    if "interestexpensedebt" in low or "interestexpenselongtermdebt" in low or "interestexpenseshortterm" in low or "interestexpenseborrowings" in low:
        return result("line_item", "nonoperating", "semantic", "Debt financing interest expense")

    if "othernoninterestexpense" in low:
        return result("line_item", "operating_expenses", "semantic", "Other noninterest operating expense")

    if low in {"otherincome", "otherincomeexpense"}:
        return result("line_item", "context_dependent", "contextual", "Other income; classification depends on business and statement context")

    # Generic interest tags need the actual company's business context.
    if "interestexpense" in low or "interestincomeexpense" in low:
        return result("line_item", "context_dependent", "contextual", "Generic interest concept; operating/nonoperating treatment varies")

    if "interestincomeoperating" in low or "interestanddividendincomeoperating" in low:
        return result("line_item", "revenue", "explicit", "Operating interest income")

    # Other operating income and expense.
    if "otheroperatingincomeexpense" in low or "othercostandexpenseoperating" in low:
        return result("line_item", "operating_expenses", "semantic", "Other operating income or expense")

    # Nonoperating income, gains, losses and financing activity.
    nonoperating_terms = (
        "nonoperating", "investmentincome", "gainlossoninvestments",
        "gainlossonsaleofbusiness", "gainlossonsaleofproperty",
        "gainlossondisposition", "gainsonremeasurement",
        "gainlossonextinguishmentofdebt", "derivativegainloss",
        "foreigncurrencytransaction", "financingcosts",
        "incomeon equitymethod", "incomelossfromequitymethod",
        "incomeon deferredcompensation", "otherprincipaltransactions",
        "marketmakingnet", "transactionbased",
    )
    if any(x in low for x in nonoperating_terms):
        return result("line_item", "nonoperating", "semantic", "Nonoperating income, expense, gain or loss")

    if "incomelossfromcontinuingoperations" in low:
        return result("net_income_subtotal", "net_income", "semantic", "Continuing-operations income measure")

    if "otherexpenseincomenet" in low or "otherincome" == low:
        return result("line_item", "context_dependent", "contextual", "Other income/expense requires presentation context")

    # Additional industry-specific concepts identified in the unresolved review.
    insurance_expense_terms = (
        "accidentandhealthinsurancecontractbenefits",
        "interestsensitivecontractbenefits",
        "investmentcontractsinsurancelosses",
        "liabilityforfuturepolicybenefit",
        "provisionforcreditloss",
        "financingreceivableexcluding",
        "creditlossexpense",
        "productdeliveryandtransactionrelatedexpenses",
        "distributionandservicing",
        "unregulatedoperatingexpense",
        "acquirediprd",
        "businessdevelopment",
    )
    if any(x in low for x in insurance_expense_terms):
        return result("line_item", "operating_expenses", "semantic", "Industry-specific operating or insurance expense")

    acquisition_expense_terms = (
        "businesscombinationintegration",
        "businesscombinationacquisitionintegration",
        "debtrefinancing",
        "changeinestimatedacquisitionearnout",
    )
    if any(x in low for x in acquisition_expense_terms):
        section = "nonoperating" if "debtrefinancing" in low else "operating_expenses"
        return result("line_item", section, "semantic", "Acquisition, integration or financing-related cost")

    if any(x in low for x in (
        "netlossesgainsfinancialinstruments",
        "gainfromperiodicdistribution",
        "gainonremeasurementofcoinvestment",
        "incomelossonequitymethodinvestmentnotereceivable",
        "interestandotherfinancialcharges",
    )):
        return result("line_item", "nonoperating", "semantic", "Financial instrument, investment or financing result")

    if any(x in low for x in (
        "investmentmanagement",
        "financingrelatedfees",
        "servicechargesandothercustomerrelatedfees",
        "interestincomesecuritiesoperating",
    )):
        return result("line_item", "revenue", "semantic", "Financial-services operating revenue")

    if "costreimbursements" in low:
        return result("line_item", "revenue", "contextual", "Reimbursements; gross versus net presentation requires company context")

    if "collaborationprofitlosssharing" in low:
        return result("line_item", "context_dependent", "contextual", "Collaboration economics may be income or expense")

    if any(x in low for x in (
        "expenseandincomeother",
        "otherexpenseandincome",
        "interestandotherincomeexpense",
        "incomefromrelatedparties",
    )):
        return result("line_item", "context_dependent", "contextual", "Combined or generic income/expense concept")

    # Advertising and marketing expenses are operating expenses.
    advertising_marketing_expense_terms = {
        "us-gaap:advertisingexpense",
        "us-gaap:marketingandadvertisingexpense",
        "us-gaap:marketingexpense",
    }
    if concept.lower() in advertising_marketing_expense_terms:
        return result(
            "line_item",
            "operating_expenses",
            "semantic",
            "Advertising, marketing or selling expense",
        )

    # Use observed placement for concepts not resolved by semantic rules.
    usable = {
        zone: values for zone, values in evidence.items()
        if zone not in {"unplaced_or_anchor_missing", "anchor"}
    }
    if usable:
        best_zone, best = max(
            usable.items(),
            key=lambda item: (item[1]["companies"], item[1]["groups"])
        )
        sections = {
            "revenue_to_gross_profit": "cost_of_revenue",
            "gross_profit_to_operating_income": "operating_expenses",
            "revenue_to_operating_income_no_gross_profit": "context_dependent",
            "operating_income_to_pretax": "nonoperating",
            "pretax_to_tax": "income_taxes",
            "tax_to_net_income": "net_income",
            "pretax_to_net_income_no_tax": "net_income",
            "after_net_income": "supplementary",
            "before_revenue": "context_dependent",
        }
        section = sections.get(best_zone, "context_dependent")
        return result("line_item", section, "presentation_evidence", f"Strongest observed zone: {best_zone}")

    return result("unresolved", "unresolved", "unresolved", "Requires company-specific hierarchy review")


def main():
    evidence = defaultdict(dict)

    with ZONES.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            evidence[row["concept"]][row["zone"]] = {
                "companies": int(row["company_count"]),
                "groups": int(row["filing_role_count"]),
                "occurrences": int(row["presentation_count"]),
            }

    output_rows = []

    with INVENTORY.open(newline="", encoding="utf-8") as f:
        for source in csv.DictReader(f):
            concept = source["concept"]
            zones = evidence.get(concept, {})
            role, section, method, note = classify(concept, zones)

            strongest = max(
                (
                    (zone, values)
                    for zone, values in zones.items()
                    if zone not in {"unplaced_or_anchor_missing", "anchor"}
                ),
                key=lambda item: (item[1]["companies"], item[1]["groups"]),
                default=("", {"companies": 0, "groups": 0}),
            )

            output_rows.append({
                "concept": concept,
                "concept_role": role,
                "canonical_section": section,
                "placement_method": method,
                "strongest_evidence_zone": strongest[0],
                "evidence_company_count": strongest[1]["companies"],
                "evidence_group_count": strongest[1]["groups"],
                "presentation_company_count": source["company_count"],
                "presentation_group_count": source["filing_role_count"],
                "presentation_count": source["presentation_count"],
                "classification_notes": note,
            })

    fields = list(output_rows[0])
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(output_rows, key=lambda r: r["concept"]))

    print(f"Concepts classified: {len(output_rows)}")
    print(f"Output: {OUTPUT}")

    print("\nClassification methods:")
    for method, count in sorted(Counter(r["placement_method"] for r in output_rows).items()):
        print(f"  {method:<22} {count:>4}")

    print("\nRole / section totals:")
    totals = Counter((r["concept_role"], r["canonical_section"]) for r in output_rows)
    for (role, section), count in sorted(totals.items()):
        print(f"  {role:<25} {section:<25} {count:>4}")

    print("\nMost frequent unresolved concepts:")
    unresolved = sorted(
        (r for r in output_rows if r["placement_method"] == "unresolved"),
        key=lambda r: (-int(r["presentation_company_count"]), r["concept"])
    )
    for r in unresolved[:30]:
        print(f'  {r["presentation_company_count"]:>3} companies | {r["concept"]}')

if __name__ == "__main__":
    main()
