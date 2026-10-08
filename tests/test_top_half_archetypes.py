"""Behavioral tests for top-half income-statement archetypes."""

import unittest

from Dev_tools.xbrl.validate_top_half_archetypes import evaluate_top_half
from northstar.data.transforms.sec_xbrl_key import get_xbrl_concepts


def blank_values():
    return {
        "revenue": None,
        "cogs": None,
        "gross_profit": None,
        "sga": None,
        "ga_expense": None,
        "rd": None,
        "operating_expenses": None,
        "operating_costs_and_expenses": None,
        "costs_and_expenses": None,
        "depreciation_amortization": None,
        "goodwill_impairment": None,
        "restructuring_charges": None,
        "asset_impairment": None,
        "equity_method_earnings": None,
        "other_operating_income": None,
        "operating_income": None,
    }


class TopHalfArchetypeTests(unittest.TestCase):
    def test_operating_costs_mapping(self):
        self.assertEqual(
            get_xbrl_concepts("operating_costs_and_expenses"),
            [("us-gaap", "OperatingCostsAndExpenses")],
        )

    def test_ccl_operating_cost_stack(self):
        values = blank_values()
        values.update({
            "revenue": 26_622_000_000,
            "operating_costs_and_expenses": 15_947_000_000,
            "sga": 3_402_000_000,
            "depreciation_amortization": 2_790_000_000,
            "operating_income": 4_483_000_000,
        })

        status, formula, gap, adjustments = evaluate_top_half(values)

        self.assertEqual(status, "RECONCILES")
        self.assertEqual(formula, "revenue - operating_costs - sga - d&a")
        self.assertEqual(adjustments, "")
        self.assertLessEqual(gap, 2_000_000)

    def test_operating_costs_are_not_full_costs(self):
        """The CCL subtotal alone must not be mistaken for all operating costs."""
        values = blank_values()
        values.update({
            "revenue": 26_622_000_000,
            "operating_costs_and_expenses": 15_947_000_000,
            "operating_income": 4_483_000_000,
        })

        status, formula, gap, adjustments = evaluate_top_half(values)

        self.assertNotEqual(status, "RECONCILES")

    def test_adjustment_bridge_closes_exact_gap(self):
        """Tagged D&A + restructuring between gross-sga and operating income."""
        values = blank_values()
        values.update({
            "revenue": 10_000_000_000,
            "cogs": 4_000_000_000,
            "gross_profit": 6_000_000_000,
            "sga": 3_000_000_000,
            "depreciation_amortization": 1_500_000_000,
            "restructuring_charges": 500_000_000,
            "operating_income": 1_000_000_000,
        })

        status, formula, gap, adjustments = evaluate_top_half(values)

        self.assertEqual(status, "RECONCILES")
        self.assertIn("adj(", formula)
        self.assertEqual(adjustments, "d&a+restructuring")
        self.assertLessEqual(gap, 2_000_000)

    def test_untagged_adjustment_is_not_assumed(self):
        """Same gap, but the adjustments are not tagged: must not reconcile."""
        values = blank_values()
        values.update({
            "revenue": 10_000_000_000,
            "cogs": 4_000_000_000,
            "gross_profit": 6_000_000_000,
            "sga": 3_000_000_000,
            "operating_income": 1_000_000_000,
        })

        status, formula, gap, adjustments = evaluate_top_half(values)

        self.assertEqual(status, "MISMATCH")
        self.assertEqual(adjustments, "")
        self.assertAlmostEqual(gap, 2_000_000_000)

    def test_equity_earnings_adjustment_adds(self):
        """Equity-method earnings are income: they add to the base."""
        values = blank_values()
        values.update({
            "revenue": 10_000_000_000,
            "cogs": 4_000_000_000,
            "gross_profit": 6_000_000_000,
            "sga": 3_000_000_000,
            "equity_method_earnings": 500_000_000,
            "operating_income": 3_500_000_000,
        })

        status, formula, gap, adjustments = evaluate_top_half(values)

        self.assertEqual(status, "RECONCILES")
        self.assertEqual(adjustments, "equity_method_earnings")

    def test_no_operating_income(self):
        status, formula, gap, adjustments = evaluate_top_half(blank_values())
        self.assertEqual(status, "NO_OPERATING_INCOME")


if __name__ == "__main__":
    unittest.main()
