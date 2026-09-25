from northstar.data.transforms.sec_xbrl import (
    select_annual_facts,
    to_financial_observations,
)


def _payload():
    return {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "label": "Revenue from Contract with Customer, Excluding Assessed Tax",
                    "units": {
                        "USD": [
                            # FY2025
                            {
                                "val": 416161000000,
                                "start": "2024-09-29",
                                "end": "2025-09-27",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-10-31",
                                "accn": "2025-filing",
                            },

                            # FY2024 as originally filed
                            {
                                "val": 391035000000,
                                "start": "2023-10-01",
                                "end": "2024-09-28",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-11-01",
                                "accn": "2024-filing",
                            },

                            # Same FY2024 comparative fact in next 10-K
                            {
                                "val": 391035000000,
                                "start": "2023-10-01",
                                "end": "2024-09-28",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-10-31",
                                "accn": "2025-filing",
                            },

                            # Quarterly-duration fact: must be rejected
                            {
                                "val": 100000000000,
                                "start": "2025-06-29",
                                "end": "2025-09-27",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-10-31",
                                "accn": "2025-filing",
                            },
                        ]
                    },
                }
            }
        }
    }


def test_select_annual_facts():
    facts = select_annual_facts(_payload(), "revenue")

    assert len(facts) == 2

    assert facts[0]["end"] == "2025-09-27"
    assert facts[0]["value"] == 416161000000

    assert facts[1]["end"] == "2024-09-28"
    assert facts[1]["value"] == 391035000000

    # Duplicate period should resolve to latest-filed representation.
    assert facts[1]["filed"] == "2025-10-31"


def test_to_financial_observations():
    observations = to_financial_observations(
        _payload(),
        ticker="AAPL",
        metric="revenue",
    )

    assert len(observations) == 2

    assert observations[0].ticker == "AAPL"
    assert observations[0].metric == "revenue"
    assert observations[0].period == "LFY"
    assert observations[0].value == 416161000000.0

    assert observations[1].period == "LFY-1"
    assert observations[1].value == 391035000000.0


if __name__ == "__main__":
    test_select_annual_facts()
    test_to_financial_observations()
    print("NorthStar SEC XBRL transform tests: PASS")