"""Behavioral tests for the research-only parent-income resolver."""

import unittest

from Dev_tools.xbrl.scale_is_waterfall import resolve_parent_net_income
from northstar.data.transforms.sec_xbrl_key import get_xbrl_concepts


def fact(tag, value, **changes):
    record = {
        "taxonomy": "us-gaap",
        "tag": tag,
        "value": value,
        "unit": "USD",
        "start": "2025-01-01",
        "end": "2025-12-31",
        "accn": "0001324404-26-000007",
    }
    record.update(changes)
    return record


class ParentIncomeTests(unittest.TestCase):
    def test_parent_mapping_excludes_total_income(self):
        self.assertEqual(
            get_xbrl_concepts("net_income"),
            [("us-gaap", "NetIncomeLoss")],
        )

    def test_cf_verified_filing_numbers(self):
        value, source, _ = resolve_parent_net_income(
            None,
            fact("ProfitLoss", 1_798_000_000),
            fact("NetIncomeLossAttributableToNoncontrollingInterest", 343_000_000),
            None,
        )
        self.assertEqual(value, 1_455_000_000)
        self.assertEqual(source, "derived_incl_nci_minus_nci")

    def test_negative_nci_is_subtracted_with_its_sign(self):
        value, source, _ = resolve_parent_net_income(
            None,
            fact("ProfitLoss", 8_882_000_000),
            fact("NetIncomeLossAttributableToNoncontrollingInterest", -2_000_000),
            None,
        )
        self.assertEqual(value, 8_884_000_000)
        self.assertEqual(source, "derived_incl_nci_minus_nci")

    def test_reported_parent_income_takes_priority(self):
        value, source, _ = resolve_parent_net_income(
            fact("NetIncomeLoss", 100),
            fact("ProfitLoss", 150),
            fact("NetIncomeLossAttributableToNoncontrollingInterest", 10),
            fact("NetIncomeLossAvailableToCommonStockholdersBasic", 90),
        )
        self.assertEqual(value, 100)
        self.assertEqual(source, "tagged")

    def test_nci_takes_priority_over_common_fallback(self):
        value, source, _ = resolve_parent_net_income(
            None,
            fact("ProfitLoss", 100),
            fact("NetIncomeLossAttributableToNoncontrollingInterest", 10),
            fact("NetIncomeLossAvailableToCommonStockholdersBasic", 99),
        )
        self.assertEqual(value, 90)
        self.assertEqual(source, "derived_incl_nci_minus_nci")

    def test_common_fallback_when_no_nci(self):
        value, source, _ = resolve_parent_net_income(
            None,
            fact("ProfitLoss", 181_862_000),
            None,
            fact("NetIncomeLossAvailableToCommonStockholdersBasic", 181_840_000),
        )
        self.assertEqual(value, 181_840_000)
        self.assertEqual(source, "fallback_common_stockholders_basic")

    def test_profitloss_fallback_when_no_nci_and_no_common(self):
        value, source, _ = resolve_parent_net_income(
            None,
            fact("ProfitLoss", 23_126_000_000),
            None,
            None,
        )
        self.assertEqual(value, 23_126_000_000)
        self.assertEqual(source, "fallback_profitloss_no_nci_tag")

    def test_partial_nci_is_not_used_as_total_nci(self):
        value, source, _ = resolve_parent_net_income(
            None,
            fact("ProfitLoss", 100),
            fact("NetIncomeLossAttributableToRedeemableNoncontrollingInterest", 10),
            None,
        )
        self.assertIsNone(value)
        self.assertEqual(source, "missing")

    def test_different_filing_is_not_combined(self):
        value, source, _ = resolve_parent_net_income(
            None,
            fact("ProfitLoss", 100),
            fact(
                "NetIncomeLossAttributableToNoncontrollingInterest",
                10,
                accn="different-filing",
            ),
            None,
        )
        self.assertIsNone(value)
        self.assertEqual(source, "missing")

    def test_different_period_is_not_combined(self):
        value, source, _ = resolve_parent_net_income(
            None,
            fact("ProfitLoss", 100),
            fact(
                "NetIncomeLossAttributableToNoncontrollingInterest",
                10,
                start="2025-10-01",
            ),
            None,
        )
        self.assertIsNone(value)
        self.assertEqual(source, "missing")

    def test_continuing_income_is_not_used_as_total_income(self):
        value, source, _ = resolve_parent_net_income(
            None,
            fact(
                "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
                100,
            ),
            fact("NetIncomeLossAttributableToNoncontrollingInterest", 10),
            None,
        )
        self.assertIsNone(value)
        self.assertEqual(source, "missing")


if __name__ == "__main__":
    unittest.main()
