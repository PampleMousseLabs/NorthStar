"""Tests for filing-level batch income-statement role selection."""

import unittest

from Dev_tools.xbrl.batch_reconstruct_is import select_role


def row(role: str, category: str) -> dict:
    return {
        "statement_role": role,
        "statement_category": category,
    }


class BatchRoleSelectionTests(unittest.TestCase):
    def test_prefers_income_statement_over_comprehensive_role(self):
        """Use the actual income statement when both statement types exist."""
        rows = [
            row("role/ConsolidatedStatementsOfOperations", "income_statement"),
            row(
                "role/ConsolidatedStatementsOfOperationsAndComprehensiveIncome",
                "comprehensive_income_statement",
            ),
            row(
                "role/ConsolidatedStatementsOfOperationsAndComprehensiveIncome",
                "comprehensive_income_statement",
            ),
        ]

        self.assertEqual(
            select_role(rows),
            "role/ConsolidatedStatementsOfOperations",
        )

    def test_falls_back_to_comprehensive_role_when_no_income_role(self):
        """
        Combined statements sometimes receive only a comprehensive-income
        classification, e.g. ALLE / ATO. They are still valid statement trees.
        """
        rows = [
            row(
                "role/ConsolidatedStatementsOfIncomeAndComprehensiveIncome",
                "comprehensive_income_statement",
            ),
            row(
                "role/ConsolidatedStatementsOfIncomeAndComprehensiveIncome",
                "comprehensive_income_statement",
            ),
            row(
                "role/ConsolidatedStatementsOfEquity",
                "equity_statement",
            ),
        ]

        self.assertEqual(
            select_role(rows),
            "role/ConsolidatedStatementsOfIncomeAndComprehensiveIncome",
        )


if __name__ == "__main__":
    unittest.main()
