# tests/test_financial_statements.py
import pandas as pd
from northstar.data.transforms.financial_statements import stockanalysis_to_observations


def test_stockanalysis_to_observations():
    df = pd.DataFrame([
        {"Line Item": "Revenue", "TTM": "391,035", "LFY": "383,285"},
        {"Line Item": "Cost of Revenue", "TTM": "210,352", "LFY": "214,137"},
        {"Line Item": "Some Unmapped Weird Row", "TTM": "999"},
    ])

    obs = stockanalysis_to_observations(df, ticker="AAPL", statement="IS")

    metrics = {(o.metric, o.period): o.value for o in obs}
    assert metrics[("revenue", "TTM")] == 391035.0
    assert metrics[("cogs", "LFY")] == 214137.0
    assert not any(o.raw_label == "Some Unmapped Weird Row" for o in obs)


if __name__ == "__main__":
    test_stockanalysis_to_observations()
    print("NorthStar financial statement transform test: PASS")