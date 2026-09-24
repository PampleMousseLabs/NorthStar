from northstar.data.transforms.sa_key import (
    SA_REVERSE,
    get_sa_label,
    get_sa_labels,
    get_sa_source,
    get_sign_flip,
)
from northstar.data.transforms.sa_utils import build_lookup, to_float


def test_sa_key():
    assert get_sa_label("revenue") == "revenue"
    assert get_sa_source("revenue") == "IS"
    assert get_sa_source("capex") == "CFS"
    assert get_sign_flip("capex") is True
    assert get_sa_labels("unknown_example") == ["unknown example"]
    assert SA_REVERSE["operating income"] == "ebit"


def test_sa_utils():
    rows = [
        {
            "Ticker": "AAPL",
            "Key": "revenue",
            "Line Item": "Revenue",
            "TTM": "100,000",
        },
        {
            "Ticker": "MSFT",
            "Key": "revenue",
            "Line Item": "Revenue",
            "TTM": "200,000",
        },
    ]

    lookup = build_lookup(rows, "aapl")

    assert lookup == {
        "revenue": {
            "TTM": "100,000",
        }
    }

    assert to_float("1,234.50") == 1234.5
    assert to_float(None) is None
    assert to_float("not a number") is None
    assert to_float(float("nan")) is None
    assert to_float(float("inf")) is None


if __name__ == "__main__":
    test_sa_key()
    test_sa_utils()
    print("NorthStar transformation-layer tests: PASS")