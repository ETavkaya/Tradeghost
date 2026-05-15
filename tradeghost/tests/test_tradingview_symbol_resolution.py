from tradeghost.services.scanner.engine import ScannerEngine


def test_tradingview_symbol_resolution_examples() -> None:
    assert ScannerEngine._resolve_tradingview_symbol("us", "KO") == "NYSE:KO"
    assert ScannerEngine._resolve_tradingview_symbol("us", "GS") == "NYSE:GS"
    assert ScannerEngine._resolve_tradingview_symbol("us", "AAPL") == "NASDAQ:AAPL"
    assert ScannerEngine._resolve_tradingview_symbol("us", "NVDA") == "NASDAQ:NVDA"
    assert ScannerEngine._resolve_tradingview_symbol("bist", "THYAO") == "BIST:THYAO"
