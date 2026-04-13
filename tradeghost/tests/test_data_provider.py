from __future__ import annotations

import pandas as pd

from tradeghost.services.data.providers import YFinanceMarketDataProvider


def test_normalize_download_columns_handles_multiindex() -> None:
    index = pd.date_range("2024-01-01", periods=2, freq="D")
    cols = pd.MultiIndex.from_product([["Open", "High", "Low", "Close", "Volume"], ["TSLA"]])
    df = pd.DataFrame(
        [
            [100.0, 101.0, 99.0, 100.5, 1_000_000],
            [101.0, 102.0, 100.0, 101.5, 1_100_000],
        ],
        columns=cols,
        index=index,
    )

    normalized = YFinanceMarketDataProvider._normalize_download_columns(df, "TSLA")
    assert list(normalized.columns) == ["Open", "High", "Low", "Close", "Volume"]

