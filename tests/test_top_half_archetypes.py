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

        status, archetype, gap = evaluate_top_half(values)

        self.assertEqual(status, "RECONCILES")
        self.assertEqual(archetype, "ARCH_1B_OPERATING_COSTS_SGA_DA")
        self.assertLessEqual(gap, 2_000_000)

    def test_operating_costs_are_not_full_costs(self):
        """The CCL subtotal alone must not be mistaken for all operating costs."""
        values = blank_values()
        values.update({
            "revenue": 26_622_000_000,
            "operating_costs_and_expenses": 15_947_000_000,
            "operating_income": 4_483_000_000,
        })

        status, archetype, _ = evaluate_top_half(values)

        self.assertNotEqual(archetype, "ARCH_1_TOTAL_COSTS")
        self.assertNotEqual(status, "RECONCILES")


if __name__ == "__main__":
    unittest.main()
